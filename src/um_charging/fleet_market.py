"""Settle frozen fleet designs against the same held-out services and wholesale prices."""
import argparse
import copy
import csv
from datetime import date, datetime, timedelta
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import subprocess
import sys

import scipy

from .__main__ import checked_output, write_json
from .day_ahead import ROOT
from .fleet_design import failure_reasons, select_build, typical_day
from .fleet_service import EFFICIENCY, TRUCK_KW, build_case, dispatch, immediate, max_service, menu, subset_case

WEEK = ROOT / "studies/day-ahead/fleet_week_prices.csv"
PRICE_MONDAY = date(2025, 1, 6)


def prices_for_day(records, day):
    """Apply prices by local weekday and wall-clock hour (an explicit scenario mapping)."""
    delivery = PRICE_MONDAY + timedelta(days=date.fromisoformat(day).weekday())
    chosen = [r for r in records if datetime.fromisoformat(r["start_berlin"]).date() == delivery]
    if [datetime.fromisoformat(r["start_berlin"]).hour for r in chosen] != list(range(24)):
        raise ValueError("Missing, duplicate, or out-of-order delivery hours")
    return delivery.isoformat(), [float(r["eur_per_mwh"]) for r in chosen]


def summarize_run(result, prices, bought):
    """Cross-settle positive powers, including ties at the cheap-hour cutoff."""
    audit = result["audit"]
    cheap_cut = sorted(prices)[5]
    hourly = [0.0] * 24
    for r in result["schedule"]:
        left, right = r["start_min"], r["end_min"]
        for h in range(int(left // 60), min(24, math.ceil(right / 60))):
            minutes = min(right, 60 * (h + 1)) - max(left, 60*h)
            hourly[h] += r["power_kw"] * minutes / 60
    cost = math.fsum(kwh * rate for kwh, rate in zip(hourly, prices)) / 1000
    if not math.isclose(cost, audit["purchase_eur"], abs_tol=1e-6, rel_tol=0):
        raise ValueError("Independent hourly settlement differs")
    if bought and (not audit["passed"] or result["status"] != "optimal"):
        raise ValueError("Price optimization must have a checked optimum")
    return {"status": result["status"], "service_complete": audit["passed"],
            "completed_vehicle_days": audit["vehicles_completed"], "completed_trips": audit["trips_completed"],
            "purchase_eur": cost if audit["passed"] else None,
            "site_peaks_kw": audit["site_peak_kw"] if audit["passed"] else None,
            "cheap_hour_cutoff_eur_mwh": cheap_cut,
            "cheap_hours": [h for h,r in enumerate(prices) if r <= cheap_cut],
            "cheap_kwh": math.fsum(kwh for kwh, rate in zip(hourly, prices) if rate <= cheap_cut) if audit["passed"] else None,
            "grid_kwh": math.fsum(hourly) if audit["passed"] else None,
            "objective_bound_eur": result.get("dual_bound"), "mip_gap": result.get("mip_gap")}


def hardware_key(hardware):
    return tuple((s, v["interfaces"], v["power_kw"]) for s, v in sorted(hardware.items()))


def next_hardware(base, options):
    """Test one extra menu step in each dimension; keep all other dimensions fixed."""
    for site in sorted(base):
        for dimension in ("interfaces", "power_kw"):
            values = sorted({h[site][dimension] for _, h in options if h[site][dimension] > base[site][dimension]})
            if values:
                change = copy.deepcopy(base)
                change[site][dimension] = values[0]
                yield f"{site}_{dimension}", change


def cheap_window_bound(case, prices):
    """Independent optimistic grid-energy bound, ignoring shared equipment and SOC timing."""
    cheap = [h for h,p in enumerate(prices) if p<=sorted(prices)[5]]
    total = 0.
    for truck in case["trucks"].values():
        minutes = sum(max(0., min(b,60*(h+1))-max(a,60*h))
                      for a,b,_ in truck["windows"] for h in cheap)
        total += min(sum(e for _,_,e,_ in truck["trips"])/EFFICIENCY,TRUCK_KW*minutes/60)
    return total


def common_trucks(case, hardware_list):
    """Largest identical complete-truck set feasible for all builds; IDs break cardinality ties."""
    ids = sorted(case["trucks"])
    for n in range(len(ids) - 1, -1, -1):
        for group in combinations(ids, n):
            sub = subset_case(case, group)
            if not group or all(dispatch(sub, h)["status"] == "optimal" for h in hardware_list):
                return list(group)
    raise AssertionError("Empty service should always be feasible")


def run_market(days, designs, price_rows, log):
    held = [d for d in days if d["split"] == "holdout"]
    cache, results, marginal, common_rows = {}, [], [], []
    def evaluate(day, release, hardware, ids, prices, *, greedy=False):
        key = day["date"], release, hardware_key(hardware), tuple(sorted(ids)), greedy
        if key not in cache:
            case = subset_case(build_case(day, release), ids)
            raw = (immediate if greedy else dispatch)(case, hardware, prices)
            log("schedule", key, raw)
            if raw["status"] == "infeasible":
                partial = max_service(case, hardware)
                log("maximum_service", key, partial)
                cache[key] = {"status": raw["status"], "service_complete": False,
                              "completed_vehicle_days": partial["completed_count"], "selected_ids": partial["selected_ids"],
                              "purchase_eur": None, "site_peaks_kw": None, "cheap_kwh": None, "grid_kwh": None,
                              "failure_reasons":failure_reasons(case,hardware)}
            else:
                cell = summarize_run(raw, prices, bought=not greedy)
                cell["cheap_window_upper_kwh"] = cheap_window_bound(case, prices)
                if cell["service_complete"] and cell["cheap_kwh"] > cell["cheap_window_upper_kwh"] + 1e-5:
                    raise ValueError("Cheap energy exceeds the unshared, dwell-limited upper bound")
                cache[key] = cell
        return cache[key]
    builds = {s: d["hardware"] for s,d in designs.items()}
    distinct = {hardware_key(h):h for h in builds.values()}
    options = menu()
    investments = {hardware_key(h): cost for cost, h in options}
    for day in held:
        date_string = day["date"]
        delivery, prices = prices_for_day(price_rows, date_string)
        ids = sorted(v["vehicle_id"] for v in day["vehicles"])
        for release in (0,45):
            case = build_case(day, release)
            row = {"date": date_string, "price_delivery": delivery, "release_min": release,
                   "required_vehicle_days": len(ids), "designs": {}}
            for label, h in builds.items():
                priced = evaluate(day, release, h, ids, prices)
                early = evaluate(day, release, h, ids, prices, greedy=True)
                paired = paired_bill(early, priced)
                row["designs"][label] = {"price_dispatch": priced, "immediate": early, "paired_eur_difference": paired}
            results.append(row)
            common = ids if all(x["price_dispatch"]["service_complete"] for x in row["designs"].values()) else common_trucks(case, list(distinct.values()))
            if common:
                compare = {}
                for label, h in builds.items():
                    price = evaluate(day,release,h,common,prices)
                    now = evaluate(day,release,h,common,prices,greedy=True)
                    compare[label] = {"price_dispatch":price,"immediate":now,"paired_eur_difference":paired_bill(now,price)}
                common_rows.append({"date":date_string,"release_min":release,"ids":common,
                                    "full_fleet":common==ids,"designs":compare})
            # Investments and opening times are perturbed one at a time on the SAME common tasks.
            variants = [("shared_build", release, builds["shared"])]
            variants += [(name, release, h) for name,h in next_hardware(builds["shared"],options)]
            if release:
                variants += [("warehouse_release_0", 0, builds["shared"])]
            baseline = evaluate(day, release, builds["shared"], common, prices) if common else None
            for name, delay, h in variants:
                full = evaluate(day,delay,h,ids,prices)
                partial = evaluate(day,delay,h,common,prices) if common else None
                saving = None
                if partial is not None:
                    if not partial["service_complete"]:
                        raise ValueError("Single-resource relaxation lost feasible service")
                    saving = baseline["purchase_eur"] - partial["purchase_eur"]
                    if saving < -1e-6:
                        raise ValueError("Single-resource relaxation increased the optimum bill")
                marginal.append({"date":date_string, "base_release_min":release, "variant":name, "hardware":h,
                                 "additional_investment":investments[hardware_key(h)]-designs["shared"]["investment"],
                                 "same_service_bill_reduction_eur":saving,
                                 "release_min":delay,"full_status":full["status"],
                                 "full_vehicle_days_possible":full["completed_vehicle_days"],
                                 "same_task_ids":common,"same_task_price_dispatch":partial})
    return {"holdout":results, "common_service":common_rows, "one_factor":marginal}


def paired_bill(early, priced):
    if not (early["service_complete"] and priced["service_complete"]):
        return None
    if not math.isclose(early["grid_kwh"],priced["grid_kwh"],abs_tol=1e-5,rel_tol=0):
        raise ValueError("Policies bought different energy for identical service")
    delta = early["purchase_eur"] - priced["purchase_eur"]
    if delta < -1e-6:
        raise ValueError("Greedy witness is cheaper than certified minimum")
    return delta


def totals(rows, label, release):
    cells = [r for r in rows if r["release_min"] == release]
    priced = [r["designs"][label]["price_dispatch"] for r in cells]
    served = [x for x in priced if x["service_complete"]]
    paired = [r for r in rows if r["release_min"] == release and r["designs"][label]["paired_eur_difference"] is not None]
    return {"observed_dates":len(cells),"fleet_dates_feasible":len(served),
            "required_vehicle_days":sum(r["required_vehicle_days"] for r in cells),
            "max_complete_vehicle_days":sum(x["completed_vehicle_days"] for x in priced),
            "feasible_dates":[r["date"] for r,p in zip(cells,priced) if p["service_complete"]],
            "price_eur_on_feasible_dates":sum(x["purchase_eur"] for x in served) if served else None,
            "max_site_peaks_kw_on_feasible_dates":{s:max(x["site_peaks_kw"][s] for x in served) for s in ("PORT","WAREHOUSE")} if served else None,
            "paired_full_fleet_dates":[r["date"] for r in paired],
            "immediate_eur_on_paired_dates":sum(r["designs"][label]["immediate"]["purchase_eur"] for r in paired) if paired else None,
            "immediate_max_site_peaks_kw_on_paired_dates":{
                s:max(r["designs"][label]["immediate"]["site_peaks_kw"][s] for r in paired)
                for s in ("PORT","WAREHOUSE")} if paired else None,
            "immediate_minus_price_eur_on_paired_dates":sum(r["designs"][label]["paired_eur_difference"] for r in paired) if paired else None}


def run(duties_path, week_path, shared_path, output=None):
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if output is not None:
        output = checked_output(output,ROOT)
        output.mkdir(parents=True)
    serial = 0
    def log(kind, key, obj):
        nonlocal serial
        if output is not None:
            serial += 1
            write_json(output / f"{serial:04d}_{kind}.json", {"condition":key,"result":obj})
    data = json.loads(duties_path.read_text(encoding="utf-8"))
    days = data["days"]
    training = [d for d in days if d["split"]=="design"]
    held = [d for d in days if d["split"]=="holdout"]
    if not held or max(d["date"] for d in training) >= min(d["date"] for d in held):
        raise ValueError("Expected chronologically held-out days")
    typical = typical_day(training)
    with week_path.open(encoding="utf-8",newline="") as f:
        price_rows = list(csv.DictReader(f))
    ref = json.loads(shared_path.read_text(encoding="utf-8"))
    if ref["duties_sha256"] != digest(duties_path) or ref["design_dates"] != [d["date"] for d in training]:
        raise ValueError("Shared design was selected on different duties")
    if ref["investment_config_sha256"] != digest(ROOT / "configs/port_warehouse_investment.json"):
        raise ValueError("Shared design used a different investment menu")
    if ref["assumptions"]["release_min"] != [0, 45] or ref["holdout_dates"] != [d["date"] for d in held]:
        raise ValueError("Frozen service conditions do not match the design experiment")
    raw = {
        "typical":select_build([typical], [0], evidence=output/"typical" if output else None),
        "shared":ref["designs"]["shared_release_design"],
        "port_only":select_build(training,[0,45],port_additions_only=True,evidence=output/"port_only" if output else None)}
    designs = {k:{field:v[field] for field in ("hardware","investment","ties","covered_vehicle_day_scenarios",
                        "requested_vehicle_day_scenarios","full_coverage_possible","max_reported_gap")} for k,v in raw.items()}
    result = run_market(days,designs,price_rows,log)
    summary = {label:{str(r):totals(result["holdout"],label,r) for r in (0,45)} for label in designs}
    marginal_totals = []
    for release in (0,45):
        for variant in sorted({r["variant"] for r in result["one_factor"] if r["base_release_min"] == release}):
            cells = [r for r in result["one_factor"] if r["base_release_min"] == release and r["variant"] == variant]
            covered = [c for c in cells if c["same_service_bill_reduction_eur"] is not None]
            marginal_totals.append({"release_min":release,"variant":variant,
                                    "observed_dates_with_paired_tasks":[c["date"] for c in covered],
                                    "vehicle_days":sum(len(c["same_task_ids"]) for c in covered),
                                    "investment_increment":cells[0]["additional_investment"],
                                    "bill_reduction_eur":math.fsum(c["same_service_bill_reduction_eur"] for c in covered)
                                    if covered else None})
    # Return each distinct physical and monetary outcome once when strategies buy identical hardware.
    lookup = {}
    def reference(value):
        signature=json.dumps(value,sort_keys=True)
        if signature not in lookup:
            lookup[signature]=len(lookup)
        return lookup[signature]
    for row in result["holdout"]+result["common_service"]:
        for policies in row["designs"].values():
            for k in ("immediate","price_dispatch"):
                policies[k]=reference(policies[k])
    for row in result["one_factor"]:
        if row["same_task_price_dispatch"] is not None:
            row["same_task_price_dispatch"]=reference(row["same_task_price_dispatch"])
    result.update(inputs={"duties_sha256":digest(duties_path),"prices_sha256":digest(week_path),
                          "shared_selection_sha256":digest(shared_path)},typical_design_date=typical["date"],
                  designs=designs,totals=summary,resource_comparison=marginal_totals,
                  dispatch_outcomes=[json.loads(s) for s in lookup])
    if output is not None:
        write_json(output/"metrics.json",result)
        write_json(output/"environment.json", {"source_commit":subprocess.check_output(
            ["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip(),
            "solver":"scipy.optimize.milp (HiGHS)", "scipy":scipy.__version__,
            "python":sys.version, "interpreter":sys.executable,
            "source_sha256":{name:digest(Path(__file__).with_name(name)) for name in
                             ("fleet_market.py","fleet_service.py","fleet_design.py")}})
    return result


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,help="Fresh directory inside the offline records Git")
    args=parser.parse_args()
    results=run(ROOT/"studies/fleet-service/duties.json",WEEK,ROOT/"studies/fleet-service/selected.json",args.output)
    print(json.dumps({"typical_design_date":results["typical_design_date"],
                      "designs":results["designs"], "totals":results["totals"],
                      "resource_comparison":results["resource_comparison"]},indent=2,allow_nan=False))
