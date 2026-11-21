"""Reproduce the fixed-facility holdout or audit its offline certificates."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import platform
from time import perf_counter

from . import site_sizing as ss
from .__main__ import checked_output, digest, write_json
from .holdout_bills import FIXED, annual_bills
from .holdout_evidence import Certificates, WallLimit
from .holdout_inputs import INPUT_HASHES, annual_grid_kwh, diagnose, diagnose_fixed, load_periods
from .holdout_repairs import repairs


def week_of(period):
    return period.days[0]["week_start"]


def pairs(keys):
    return [list(k) for k in sorted(keys)]


def service_week(log, sample, period, design, reference):
    locked = {}
    rows = {}
    for day in sorted(period.cases):
        duty = {key for key in period.keys if key[0] == day}
        result = log.call(sample, period, design, design.caps, day=day,
                          locked=locked, reference=reference & period.keys)
        if result["stats"]["status"] != "certified" or not result["audit"]:
            break
        chosen = duty & ss.eb.selected(result)
        rows[day] = sorted(v for _, v in chosen)
        locked.update({k: k in chosen for k in duty})
    return rows


def register(log, sample, periods, progress):
    rows = []
    for d in (ss.BASELINE, *FIXED[:2]):
        choices = {}
        for p in periods:
            if d != ss.BASELINE and any(rows_by_date[day]["registered"] is None for day in p.cases):
                continue
            ref = set() if d == ss.BASELINE else reference
            choices.update(service_week(log, sample, p, d, ref))
        if d == ss.BASELINE:
            reference = {(day, v) for day, selected in choices.items() for v in selected}
            for p in periods:
                for day in p.days:
                    date = day["date"]
                    eligible = sorted(v for dt, v in p.keys if dt == date)
                    registered = choices.get(date) if eligible else []
                    rows.append(dict(date=date, eligible=eligible, registered=registered, facilities={}))
            rows_by_date = {row["date"]: row for row in rows}
        for row in rows:
            row["facilities"][d.label] = choices.get(row["date"]) if row["eligible"] else []
        progress(f"{sample} {d.label}: {sum(map(len, choices.values()))} served on "
                 f"{len(choices)} certified active dates")
    weekly = []
    for p in periods:
        week_rows = [rows_by_date[day["date"]] for day in p.days]
        counts = {}
        for d in FIXED:
            choices = [r["facilities"][d.label] for r in week_rows]
            counts[d.label] = sum(map(len, choices)) if None not in choices else None
        weekly.append(dict(week=week_of(p), eligible=len(p.keys), registered=counts[ss.BASELINE.label],
                           served=counts))
    missing, added, status = {}, {}, {}
    for d in FIXED:
        both = [r for r in rows if r["registered"] is not None and r["facilities"][d.label] is not None]
        missing[d.label] = pairs((r["date"], v) for r in both
                                 for v in set(r["registered"]) - set(r["facilities"][d.label]))
        added[d.label] = pairs((r["date"], v) for r in both
                               for v in set(r["facilities"][d.label]) - set(r["registered"]))
        status[d.label] = ("service_gap" if missing[d.label] else
                           "matched" if len(both) == len(rows) else "unresolved")
    return dict(daily=rows, weekly=weekly, missing=missing, added=added, service_status=status), reference


def physical_status(result):
    if result["audit"] and result["audit"]["passed"]:
        return "feasible"
    if result["stats"]["status_code"] == 2:
        return "infeasible"
    return "unresolved"


def compact_diagnosis(detail, fields):
    reasons = sorted({segment[field]["reason"] for segment in detail["segments"]
                      for field in fields if not segment[field]["feasible"]})
    return dict(date=detail["date"], vehicle_id=detail["vehicle_id"],
                classification=detail["classification"], reasons=reasons)


def main_comparisons(log, periods, main, ref, save, progress):
    weeks = [week_of(p) for p in periods]
    reference_complete = main["service_status"][ss.BASELINE.label] == "matched"
    by_date = {d["date"]: p for p in periods for d in p.days}
    outside = []
    for p in periods:
        if any(main_row["registered"] is None for main_row in main["daily"] if main_row["date"] in p.cases):
            continue
        outside.extend(diagnose(p, k) for k in sorted(p.keys - ref))
    save("outside.json", outside)
    main["outside"] = [compact_diagnosis(row, ("unlimited",) if not row["unlimited_feasible"]
                                         else ("truck_50kw",)) for row in outside]
    main["annual_grid_kwh"] = annual_grid_kwh(periods, ref) if reference_complete else None
    main["m8_annual_grid_kwh"] = 58387.79
    main["fixed_diagnostics"] = {}
    if not reference_complete:
        return None, None
    dispatches = defaultdict(dict)

    def dispatch(design, period, caps, purpose):
        key, week = (design.label, caps), week_of(period)
        if week not in dispatches[key]:
            dispatches[key][week] = log.call(purpose, period, design, caps, fixed=ref & period.keys)
        return dispatches[key][week]

    def verify(design, period):
        return physical_status(dispatch(design, period, design.caps, "fixed_R"))

    # Each tariff uses one frozen strategy for all six weeks. Keep even a failed week's proof.
    m8 = ss.eb.read_json(ss.eb.WEEKS.with_name("site_sizing.json"))
    baseline_caps = {tuple(r["caps_kw"]) for r in m8["cost_rows"] if r["design"] == ss.BASELINE.label}
    for d in (ss.BASELINE, *FIXED[:2]):
        if main["service_status"][d.label] == "matched":
            caps_set = sorted(baseline_caps - {d.caps}) if d == ss.BASELINE else []
            for caps in [d.caps, *caps_set]:
                for p in periods:
                    dispatch(d, p, caps, "main_dispatch")
                progress(f"main dispatch {d.label} {caps}: six weeks recorded")
    billing = annual_bills(weeks, dispatches, main["service_status"], annual_grid_kwh=main["annual_grid_kwh"])
    save("bills.json", billing)
    checks, daily_checks, missing_weeks, detailed = {}, {}, {}, {}
    for d in FIXED:
        missed = [tuple(k) for k in main["missing"][d.label]]
        missing_weeks[d.label] = sorted({week_of(by_date[dt]) for dt, _ in missed})
        daily_checks[d.label] = {
            r["week"]: ("infeasible" if r["week"] in missing_weeks[d.label] else
                        "unresolved" if r["registered"] is None or r["served"][d.label] is None else "feasible")
            for r in main["weekly"]}
        checks[d.label] = {w: physical_status(r) for w, r in dispatches[d.label, d.caps].items()}
        for p in periods:
            if week_of(p) in missing_weeks[d.label]:
                checks[d.label][week_of(p)] = verify(d, p)
        detailed[d.label] = [diagnose_fixed(by_date[k[0]], k, d) for k in missed]
        main["fixed_diagnostics"][d.label] = [
            dict(**compact_diagnosis(row, ("single_truck",)),
                 fixed_R_week=checks[d.label][week_of(by_date[row["date"]])])
            for row in detailed[d.label]]
    save("fixed_diagnostics.json", detailed)

    def verify_daily(design, period):
        choices = service_week(log, "repair_service", period, design, ref)
        if len(choices) != len(period.cases):
            return "unresolved"
        selected = {(date, v) for date, ids in choices.items() for v in ids}
        return "feasible" if (ref & period.keys) <= selected else "infeasible"

    repair = repairs(periods, ref, checks, verify, missing_weeks=missing_weeks,
                     daily_checks=daily_checks, verify_daily=verify_daily)
    save("repairs.json", repair)
    return billing, repair


def research(log, summary, save, progress):
    periods = load_periods()
    main, ref = register(log, "main", periods, progress)
    summary["main"] = main
    save("main_service.json", main)
    billing, repair = main_comparisons(log, periods, main, ref, save, progress)
    summary.update(billing=billing, repairs=repair)
    changed = ("service_gap" in main["service_status"].values() or
               (billing and any(r["recommendation_status"] == "changed" for r in billing["cases"])))
    if changed:
        summary.update(stop_reason="recommendation_changed", sensitivity=dict(status="stopped_recommendation_changed"))
        progress("Main evidence changes the M8 recommendation; registered repair diagnostics closed")
        return
    sens, sensitive_r = register(log, "sensitivity", load_periods(sensitivity=True), progress)
    complete = "unresolved" not in sens["service_status"].values()
    sens["status"] = "complete" if complete else "unresolved"
    if all(s["service_status"][ss.BASELINE.label] == "matched" for s in (sens, main)):
        sens.update(registration_lost=pairs(ref - sensitive_r), registration_gained=pairs(sensitive_r - ref))
    summary.update(sensitivity=sens, stop_reason="completed" if complete else "unresolved")


def run(path, *, replay=False, wall_seconds=7200, progress_path=None):
    began = perf_counter()
    if not 0 < wall_seconds <= 7200:
        raise ValueError("The formal wall budget must be positive and at most two hours")
    manifest_path = path / "manifest.json"
    if replay:
        manifest = ss.eb.read_json(manifest_path)
    else:
        path = checked_output(path, ss.eb.ROOT)
        source = ss.source_state()
        if source["dirty"]:
            raise ValueError("Commit the source before the formal holdout run")
        path.mkdir(parents=True)
        manifest = dict(source_commit=source["commit"], source_dirty=False, started_utc=datetime.now(timezone.utc).isoformat(),
                        environment=dict(python=platform.python_version(), scipy=ss.scipy.__version__,
                                         numpy=ss.np.__version__, platform=platform.platform()),
                        wall_limit_seconds=wall_seconds, input_hashes={p.name: h for p, h in INPUT_HASHES.items()},
                        cost_inputs={p.name: digest(p) for p in (ss.CONNECTION_INPUT, ss.NETWORK_INPUT,
                                    ss.COST_INPUT, ss.eb.WEEKS.with_name("site_sizing.json"))})
        write_json(manifest_path, manifest)
    for p in (ss.CONNECTION_INPUT, ss.NETWORK_INPUT, ss.COST_INPUT, ss.eb.WEEKS.with_name("site_sizing.json")):
        if digest(p) != manifest["cost_inputs"][p.name]:
            raise ValueError(f"Cost input changed: {p.name}")
    if manifest["input_hashes"] != {p.name: h for p, h in INPUT_HASHES.items()}:
        raise ValueError("Registered input hash mismatch")
    log = Certificates(path, began + wall_seconds - min(3., wall_seconds / 10), replay=replay)
    def save(name, value):
        if replay:
            if value != ss.eb.read_json(path / name):
                raise ValueError(f"Replayed evidence differs: {name}")
        else:
            write_json(path / name, value)
    def progress(message):
        if not replay:
            ss._progress(progress_path, message)
    summary = dict(source_commit=manifest["source_commit"], inputs_sha256=manifest["input_hashes"],
                   cost_inputs_sha256=manifest["cost_inputs"], billing=None, repairs=None, main=None)
    try:
        research(log, summary, save, progress)
    except WallLimit:
        summary.update(stop_reason="wall_limit", sensitivity=dict(status="wall_limit"))
    summary.update(solve_count=len(log.records), status_counts=dict(Counter(r["status"] for r in log.records)),
                   call_counts=dict(Counter(r["request"]["sample"] for r in log.records)),
                   audited_primals=sum(r["audited"] for r in log.records),
                   ledger_sha256=digest(path / "solves.jsonl") if log.records else None)
    if replay:
        archived = ss.eb.read_json(path / "summary.json")
        summary["formal_seconds"] = archived["formal_seconds"]
        if len(log.records) != len(log.expected) or summary != archived:
            raise ValueError("Final summary or number of archived calls differs")
    else:
        summary["formal_seconds"] = perf_counter() - began
        write_json(path / "summary.json", summary)
    print(f"{summary['stop_reason']}; {len(log.records)} certificates; {perf_counter() - began:.2f} s")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--verify", type=Path)
    parser.add_argument("--wall-seconds", type=float, default=7200)
    parser.add_argument("--progress", type=Path)
    args = parser.parse_args()
    run(args.output or args.verify, replay=args.verify is not None, wall_seconds=args.wall_seconds,
        progress_path=args.progress)


if __name__ == "__main__":
    main()
