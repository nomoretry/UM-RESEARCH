"""Bill the two priced warehouse repairs and test the registered charging-window sensitivity."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
from time import perf_counter

from . import holdout
from . import site_sizing as ss
from .__main__ import checked_output, digest, write_json
from .holdout_evidence import Certificates, WallLimit
from .holdout_gap_sensitivity import run_sensitivity
from .holdout_inputs import annual_grid_kwh, load_periods
from .holdout_repair_costs import REPAIRS, costs


PREVIOUS_SUMMARY_SHA256 = "f0437cb92c31b125ce0ff124798b04c2cce21c90d93ab859959500ef3597d93a"


def verified_previous(path):
    if digest(path / "summary.json") != PREVIOUS_SUMMARY_SHA256:
        raise ValueError("The previous formal summary differs from the registered archive")
    return holdout.run(path, replay=True)


def registered_duties(periods, previous):
    main = previous["main"]
    reference = {(row["date"], vehicle) for row in main["daily"] for vehicle in row["registered"]}
    counts = [len(reference & p.keys) for p in periods]
    outside = {(r["date"], r["vehicle_id"]) for r in main["outside"]
               if r["classification"] == "infeasible_unlimited_power"}
    if (counts != [7, 13, 7, 8, 8, 9] or len(reference) != 52 or len(outside) != 11 or
            outside != set.union(*(p.keys for p in periods)) - reference):
        raise ValueError("The registered duties or outside-set proof changed")
    ss.close(annual_grid_kwh(periods, reference), main["annual_grid_kwh"], "registered grid energy")
    return reference


def dispatch_repairs(log, periods, reference, runs, progress, first_call):
    # First check both rated facilities, then the service-derived software caps.
    for warehouse_cap in (20, 15):
        for design in REPAIRS:
            caps = design.port_kw, warehouse_cap
            weeks = runs[design.label, caps] = {}
            for period in periods:
                week = holdout.week_of(period)
                if not log.records:
                    first_call()
                result = log.call("rated_dispatch" if caps == design.caps else "cap_reference_dispatch",
                                  period, design, caps, fixed=reference & period.keys)
                weeks[week] = result
                if caps == design.caps and result["stats"]["status_code"] == 2:
                    return dict(week=week, design=design.label, caps_kw=list(caps),
                                certificate=log.records[-1]["file"])
            progress(f"购电 {design.label} {list(caps)} 逐周证书已归档")
    return None


def run(path, previous_path, *, replay=False, wall_seconds=7200, progress_path=None):
    began = perf_counter()
    if not 0 < wall_seconds <= 7200:
        raise ValueError("The wall-clock limit must be positive and no greater than 7200 seconds")
    previous_path, path = previous_path.resolve(), path.resolve()
    if not replay and (path.is_relative_to(previous_path.parent) or
                       (progress_path and progress_path.resolve().is_relative_to(previous_path.parent))):
        raise ValueError("Keep the original offline run read-only")
    previous = verified_previous(previous_path)
    periods = load_periods()
    reference = registered_duties(periods, previous)
    manifest_path = path / "manifest.json"
    if replay:
        manifest = ss.eb.read_json(manifest_path)
    else:
        path = checked_output(path, ss.eb.ROOT)
        source = ss.source_state()
        if source["dirty"]:
            raise ValueError("Commit the source before the formal repair run")
        path.mkdir(parents=True)
        (path / "solves.jsonl").touch(exist_ok=False)
        manifest = dict(source_commit=source["commit"], source_dirty=False,
                        environment=dict(python=platform.python_version(), scipy=ss.scipy.__version__,
                                         numpy=ss.np.__version__, platform=platform.platform()),
                        wall_limit_seconds=wall_seconds, previous_summary_sha256=PREVIOUS_SUMMARY_SHA256,
                        previous_ledger_sha256=previous["ledger_sha256"],
                        inputs_sha256=previous["inputs_sha256"], cost_inputs_sha256=previous["cost_inputs_sha256"],
                        first_solve_utc=None)
        write_json(manifest_path, manifest)
    if (manifest["previous_summary_sha256"] != PREVIOUS_SUMMARY_SHA256 or
            manifest["previous_ledger_sha256"] != previous["ledger_sha256"] or
            manifest["inputs_sha256"] != previous["inputs_sha256"] or
            manifest["cost_inputs_sha256"] != previous["cost_inputs_sha256"]):
        raise ValueError("Registered parent evidence or study inputs differ")
    log = Certificates(path, began + wall_seconds - min(3., wall_seconds / 10), replay=replay)

    def progress(message):
        if not replay:
            ss._progress(progress_path, message)

    def checkpoint(name, value):
        if replay:
            if ss.eb.read_json(path / name) != json.loads(json.dumps(value, allow_nan=False)):
                raise ValueError(f"Replayed evidence differs for {name}")
        else:
            write_json(path / name, value)

    summary = dict(source_commit=manifest["source_commit"], first_solve_utc=manifest["first_solve_utc"],
                   previous_summary_sha256=PREVIOUS_SUMMARY_SHA256, inputs_sha256=manifest["inputs_sha256"],
                   cost_inputs_sha256=manifest["cost_inputs_sha256"], billing=None, sensitivity=None)
    def first_call():
        if not replay:
            manifest["first_solve_utc"] = datetime.now(timezone.utc).isoformat()
            write_json(manifest_path, manifest)
        summary["first_solve_utc"] = manifest["first_solve_utc"]
        progress(f"首次正式购电调用 UTC {manifest['first_solve_utc']}，旧档案 170 份证书已通过复核")

    runs = {}
    try:
        contradiction = dispatch_repairs(log, periods, reference, runs, progress, first_call)
        if contradiction:
            summary.update(stop_reason="rated_service_infeasible", contradiction=contradiction)
        else:
            summary["billing"] = costs([holdout.week_of(p) for p in periods], runs, previous,
                                       previous["main"]["annual_grid_kwh"])
            checkpoint("bills.json", summary["billing"])
            progress("两套有价修复的主账单、限峰参照和基准的十二个口径已结算")
            summary["sensitivity"] = run_sensitivity(log, previous, progress)
            checkpoint("sensitivity.json", summary["sensitivity"])
            summary["stop_reason"] = "wall_limit" if summary["sensitivity"]["wall_limit_reached"] else "completed"
    except WallLimit:
        summary["stop_reason"] = "wall_limit"
        progress("达到墙钟上限，保留所有已完成的逐次证书")
    summary.update(solve_count=len(log.records), status_counts=dict(Counter(r["status"] for r in log.records)),
                   call_counts=dict(Counter(r["request"]["sample"] for r in log.records)),
                   audited_primals=sum(r["audited"] for r in log.records),
                   ledger_sha256=digest(path / "solves.jsonl"))
    if replay:
        summary["formal_seconds"] = ss.eb.read_json(path / "summary.json")["formal_seconds"]
        if len(log.expected) != len(log.records):
            raise ValueError("Replayed certificate count differs")
    else:
        summary["formal_seconds"] = perf_counter() - began
    checkpoint("summary.json", summary)
    print(f"{summary['stop_reason']}; {len(log.records)} repair-study certificates; {perf_counter()-began:.2f} s")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--verify", type=Path)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--wall-seconds", type=float, default=7200)
    args = parser.parse_args()
    result = run(args.output or args.verify, args.previous, replay=args.verify is not None,
                 wall_seconds=args.wall_seconds, progress_path=args.progress)
    return 0 if result["stop_reason"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
