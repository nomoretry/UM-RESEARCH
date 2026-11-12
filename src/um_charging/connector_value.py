"""Price the second port connector on frozen, identical truck duties."""
import argparse
import csv
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import sys

import scipy

from .__main__ import checked_output, write_json
from .connector_cost import break_even
from .day_ahead import ROOT, read_json
from .fleet_design import failure_reasons
from .fleet_market import WEEK, common_trucks, paired_bill, prices_for_day, summarize_run
from .fleet_service import audit, build_case, dispatch, immediate, max_service, subset_case

FLEET = ROOT / "studies/fleet-service"
MARKET = ROOT / "studies/day-ahead"
NATIVE = MARKET / "native_2021_prices.csv"
RELEASE = 45
TOL = 1e-6


def csv_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def hourly_curve(records, day):
    """For modeled 24h days, match actual local offsets and consecutive UTC deliveries."""
    start = datetime.fromisoformat(day["start"])
    end = datetime.fromisoformat(day["end"])
    points = [(datetime.fromisoformat(row["start_berlin"]), float(row["eur_per_mwh"]))
              for row in records if row["start_berlin"][:10] == day["date"]]
    utc = [t.astimezone(timezone.utc).timestamp() for t, _ in points]
    if (end.timestamp() - start.timestamp() != 86400 or len(points) != 24
            or utc != [start.timestamp() + h * 3600 for h in range(24)]
            or [t.hour for t, _ in points] != list(range(24))
            or any(t.utcoffset() != start.utcoffset() or not math.isfinite(p) for t, p in points)):
        raise ValueError(f"Expected a complete native hourly curve for the modeled day {day['date']}")
    return [p for _, p in points]


def physical_service(case, hardware, log, label):
    full = dispatch(case, hardware)
    log(f"{label}-full", full)
    if full["status"] == "optimal":
        return {"full_status": "optimal", "max_vehicle_days": len(case["trucks"]),
                "ids": sorted(case["trucks"]), "failure_reasons": []}
    if full["status"] != "infeasible":
        raise RuntimeError(f"Unresolved full service: {full['status']}")
    partial = max_service(case, hardware)
    log(f"{label}-max", partial)
    return {"full_status": "infeasible", "max_vehicle_days": partial["completed_count"],
            "ids": partial["selected_ids"], "failure_reasons": failure_reasons(case, hardware)}


def costs(case, hardware, prices, earliest, log, label):
    optimal = dispatch(case, hardware, prices)
    if optimal["status"] != "optimal":
        raise ValueError("Price solve failed on a physically verified service")
    log(f"{label}-price", optimal)
    charged = {**earliest, "audit": audit(case, hardware, earliest["schedule"], prices)}
    log(f"{label}-arrival", charged)
    now = summarize_run(charged, prices, False)
    best = summarize_run(optimal, prices, True)
    return {"optimal_eur": best["purchase_eur"], "price_bound_eur": best["objective_bound_eur"],
            "price_gap": best["mip_gap"], "optimal_peaks_kw": best["site_peaks_kw"],
            "grid_kwh": best["grid_kwh"], "arrival_status": charged["status"],
            "arrival_completed": now["completed_vehicle_days"], "arrival_eur": now["purchase_eur"],
            "arrival_peaks_kw": now["site_peaks_kw"], "scheduling_gain_eur": paired_bill(now, best)}


def compare_day(day, group, builds, native, replay, log):
    base = {"date": day["date"], "group": group, "observations": day.get("availability", "complete_tasks"),
            "required_ids": [v["vehicle_id"] for v in day["vehicles"]],
            "required_trips": sum(len(v["trips"]) for v in day["vehicles"])}
    if not day["vehicles"]:
        return base
    case = build_case(day, RELEASE)
    def record(name, value):
        log(day["date"] + "-" + name, value)
    service = {n: physical_service(case, h, record, n) for n, h in builds.items()}
    # Choose whole vehicle-days once, before reading prices. The two-port build can use the one-port plan.
    common_ids = service["one"]["ids"]
    if common_ids and service["one"]["full_status"] == "infeasible":
        common_ids = common_trucks(case, [builds["one"]])
        if len(common_ids) != service["one"]["max_vehicle_days"]:
            raise ValueError("Common-service enumeration and maximum-service MILP disagree")
    if service["two"]["max_vehicle_days"] < len(common_ids):
        raise ValueError("Adding a connector reduced service")
    matched = subset_case(case, common_ids)
    row = {**base, "facilities": service, "matched_ids": common_ids,
           "matched_trips": sum(len(v["trips"]) for v in matched["trucks"].values()), "prices": {}}
    if not common_ids:
        return row
    direct = {n: immediate(matched, h) for n, h in builds.items()}
    old_date, old_prices = prices_for_day(replay, day["date"])
    for key, delivery, prices in (("concurrent", day["date"], hourly_curve(native, day)),
                                  ("january_replay", old_date, old_prices)):
        results = {n: costs(matched, h, prices, direct[n], record, f"{key}-{n}") for n, h in builds.items()}
        one, two = results["one"], results["two"]
        gain = one["optimal_eur"] - two["optimal_eur"]
        if gain < -TOL or abs(one["grid_kwh"] - two["grid_kwh"]) > TOL:
            raise ValueError("Unmatched energy or lost optimality across nested hardware")
        row["prices"][key] = {"delivery_date": delivery, **results, "hardware_gain_eur":gain}
    return row


def aggregate(rows, price_key):
    operating = [r for r in rows if "facilities" in r]
    priced = [r for r in operating if price_key in r["prices"]]
    summary = {"calendar_rows":len(rows), "modeled_dates": len(operating), "paired_dates": len(priced),
               "observations": {s:sum(r["observations"] == s for r in rows)
                                for s in sorted({r["observations"] for r in rows})},
               "required_vehicle_days":sum(len(r["required_ids"]) for r in rows),
               "required_trips":sum(r["required_trips"] for r in rows),
               "paired_vehicle_days":sum(len(r["matched_ids"]) for r in priced),
               "paired_trips":sum(r["matched_trips"] for r in priced)}
    for name in ("one","two"):
        full = sum(r["facilities"][name]["full_status"] == "optimal" for r in operating)
        bills = [r["prices"][price_key][name] for r in priced]
        paired = [b for b in bills if b["scheduling_gain_eur"] is not None]
        summary[name] = {"whole_fleet_dates": full, "max_vehicle_days":sum(
            r["facilities"][name]["max_vehicle_days"] for r in operating),
            "optimal_eur_matched_tasks":math.fsum(b["optimal_eur"] for b in bills) if bills else None,
            "arrival_comparable_dates":len(paired),
            "arrival_eur_policy_pairs":math.fsum(b["arrival_eur"] for b in paired) if paired else None,
            "optimal_eur_policy_pairs":math.fsum(b["optimal_eur"] for b in paired) if paired else None,
            "scheduling_gain_eur":math.fsum(b["scheduling_gain_eur"] for b in paired) if paired else None,
            "peak_kw_returned":{s:max(b["optimal_peaks_kw"][s] for b in bills)
                                for s in ("PORT","WAREHOUSE")} if bills else None}
    summary["hardware_gain_eur"] = (math.fsum(r["prices"][price_key]["hardware_gain_eur"] for r in priced)
                                    if priced else None)
    return summary


def experiment(full=False, output=None):
    if output:
        output = checked_output(output, ROOT)
        output.mkdir(parents=True)
    def log(name, value):
        if output:
            write_json(output / f"{name}.json", value)
    source = FLEET / "duties.json"
    original_days = read_json(source)["days"]
    held = [d for d in original_days if d["split"] == "holdout"]
    selection = read_json(FLEET/"selected.json")
    if sha256(source.read_bytes()).hexdigest() != selection["duties_sha256"]:
        raise ValueError("Frozen build and trip inputs differ")
    one = selection["designs"]["shared_release_design"]["hardware"]
    if one != {"PORT":{"interfaces":1,"power_kw":100},"WAREHOUSE":{"interfaces":1,"power_kw":75}}:
        raise ValueError("The registered connector comparison requires the original frozen hardware")
    builds = {"one":one, "two":{**one,"PORT":{**one["PORT"],"interfaces":2}}}
    native, replay = csv_rows(NATIVE), csv_rows(WEEK)
    def compare(d, g):
        return compare_day(d, g, builds, native, replay, log)
    rows = [compare(d,"original") for d in held]
    keys = ("concurrent","january_replay")
    original = {k:aggregate(rows,k) for k in keys}
    historical = read_json(MARKET/"fleet_market.json")
    previous, = [r["bill_reduction_eur"] for r in historical["resource_comparison"]
                 if r["release_min"] == RELEASE and r["variant"] == "PORT_interfaces"]
    if abs(original["january_replay"]["hardware_gain_eur"]-previous)>TOL:
        raise ValueError("January same-service comparison differs from published bill")
    files = [source, FLEET/"selected.json", NATIVE, WEEK, MARKET/"fleet_market.json",
             ROOT/"configs/port_warehouse_investment.json"]
    result = {"warehouse_release_min":RELEASE, "hardware":builds, "original":original}
    if full:
        path = FLEET/"operating_weeks.json"
        files.extend((path, MARKET/"connector_cost.json"))
        days = read_json(path)["days"]
        start = date(2021,9,27)
        expected = [(start + timedelta(days=i)).isoformat() for i in range(42)]
        if [d["date"] for d in days] != expected or set(expected) & {d["date"] for d in original_days}:
            raise ValueError("Expected 42 consecutive new dates, disjoint from design and original holdout")
        if any(d["week_start"] != expected[(i//7)*7] for i,d in enumerate(days)):
            raise ValueError("Wrong Monday for an operating date")
        extra = [compare(d,d["week_start"]) for d in days]
        weeks = sorted({r["group"] for r in extra})
        by_week = {w:{k:aggregate([r for r in extra if r["group"]==w],k) for k in keys} for w in weeks}
        if any(not summary["paired_dates"] for week in by_week.values() for summary in week.values()):
            raise ValueError("An unobserved week cannot supply a zero saving to the annual scenario")
        result["weeks"] = by_week
        result["extension"] = {k:aggregate(extra,k) for k in keys}
        result["threshold"] = {k:break_even([by_week[w][k]["hardware_gain_eur"] for w in weeks],
                                            price_year=year)
                               for k,year in zip(keys,(2021,2025))}
        rows.extend(extra)
    result["inputs_sha256"] = {p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in files}
    result["days"] = rows
    if output:
        write_json(output/"result.json", result)
        log("environment", {"source_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                            "python":sys.executable,"scipy":scipy.__version__,
                            "module_sha256":sha256(Path(__file__).read_bytes()).hexdigest()})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full",action="store_true",help="Also evaluate the next six calendar weeks")
    parser.add_argument("--output",type=Path,help="Fresh directory in the offline records Git")
    args=parser.parse_args()
    result=experiment(args.full,args.output)
    for key, row in result["original"].items():
        print(f"{key}: {row['paired_vehicle_days']}/{row['required_vehicle_days']} vehicle-days, "
              f"one EUR {row['one']['optimal_eur_matched_tasks']:.5f}, two EUR {row['two']['optimal_eur_matched_tasks']:.5f}, "
              f"second port saves EUR {row['hardware_gain_eur']:.5f}")
    for key, threshold in result.get("threshold",{}).items():
        print(key, json.dumps(threshold,ensure_ascii=False))


if __name__ == "__main__":
    main()
