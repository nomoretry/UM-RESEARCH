"""Canonical investment validation, exhaustive facilities, and fixed-model regression."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys

import numpy
import scipy

from .__main__ import checked_output, digest, reject_duplicate_keys, write_json
from .investment_experiment import compare_joint_to_enumeration, enumerate_facilities, make_investment_scenarios
from .model import make_scenarios, solve
from .validation import check_solution


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--regression-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2]
    output = checked_output(args.output, source)
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], encoding="utf-8").strip()
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], encoding="utf-8").strip():
        raise ValueError("Canonical run requires a clean committed source")
    def load(path):
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)
    investment_base = load(args.config)
    investment_cases = make_investment_scenarios(investment_base)
    regressions = make_scenarios(load(args.regression_config))
    output.mkdir(parents=True)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "source_commit": commit, "source_dirty": False,
        "seed": None, "seed_reason": "Explicit deterministic inputs and exhaustive finite facility enumeration",
        "config_sha256": {str(args.config): digest(args.config), str(args.regression_config): digest(args.regression_config)},
        "source_sha256": {p.relative_to(source).as_posix(): digest(p) for p in sorted((source / "src" / "um_charging").glob("*.py"))},
        "environment": {"python": sys.version, "platform": platform.platform(), "numpy": numpy.__version__, "scipy": scipy.__version__},
        "solver": {"name": "HiGHS through scipy.optimize.milp", "version": None,
                   "version_evidence": "Captured solver banner", "time_limit_seconds": 60.0, "mip_rel_gap": 0.0},
        "command": [sys.executable, "-m", "um_charging.investment_cli", *sys.argv[1:]],
        "modeled_cycle_hours": investment_base["slot_hours"] * investment_base["slot_count"],
        "cost_basis": "One modeled cycle; synthetic cycle-equivalent investment and same-cycle operating costs, weight 1",
        "research_status": "Project adaptation of Ye 2024 problem/investment framework, not equation or case reproduction",
    }
    write_json(output / "manifest.json", manifest)
    summaries, regression_summaries = [], []
    failed = False
    for name, data in investment_cases.items():
        case_dir = output / name
        case_dir.mkdir()
        write_json(case_dir / "input.json", data)
        print(f"Joint investment: {name}", flush=True)
        result = solve(data, display=True)
        validation = check_solution(data, result)
        write_json(case_dir / "result.json", result)
        write_json(case_dir / "validation.json", validation)
        def save_combination(index, fixed, operating, checked):
            folder = case_dir / "enumeration" / f"{index:03d}"
            folder.mkdir(parents=True)
            write_json(folder / "input.json", fixed)
            write_json(folder / "result.json", operating)
            write_json(folder / "validation.json", checked)
        enumeration = enumerate_facilities(data, on_combination=save_combination)
        comparison = compare_joint_to_enumeration(result, validation, enumeration)
        write_json(case_dir / "enumeration.json", enumeration)
        write_json(case_dir / "comparison.json", comparison)
        summary = {
            "scenario": name, "input_sha256": digest(case_dir / "input.json"),
            "status": result["status"], "objective": result["objective"],
            "dual_bound": result["dual_bound"], "mip_gap": result["mip_gap"],
            "validation_passed": validation["passed"], "validation_checks": validation.get("checks"),
            "max_violation_by_constraint": validation.get("max_violation_by_constraint"),
            "new_interfaces": result["solution"]["new_interfaces"] if result["has_solution"] else None,
            "upgrade_selected": result["solution"]["upgrade_selected"] if result["has_solution"] else None,
            "investment_cost": validation.get("investment_cost"), "operating_cost": validation.get("operating_cost"),
            "grid_energy_kwh": validation.get("grid_energy_kwh"), "site_energy_kwh": validation.get("site_energy_kwh"),
            "site_peak_kw": validation.get("site_peak_kw"), "system_coincident_peak_kw": validation.get("system_coincident_peak_kw"),
            "enumeration_count": enumeration["combination_count"], "enumeration_feasible": enumeration["feasible_count"],
            "enumeration_best": enumeration["best_total_cost"], "enumeration_comparison": comparison,
        }
        failed |= not comparison["passed"]
        summaries.append(summary)
        write_json(output / "investment_summary.json", summaries)
        print(json.dumps(summary, allow_nan=False), flush=True)
    expected_regression = {"base": 300.0, "interface_bottleneck": None, "power_bottleneck": None,
                           "window_bottleneck": None, "higher_power_no_benefit": 300.0, "zero_demand": 0.0}
    for name, data in regressions.items():
        case_dir = output / "regression" / name
        case_dir.mkdir(parents=True)
        result = solve(data, display=True)
        validation = check_solution(data, result)
        for filename, payload in (("input.json", data), ("result.json", result), ("validation.json", validation)):
            write_json(case_dir / filename, payload)
        expected = expected_regression[name]
        matched = (result["status"] == "infeasible" and not result["has_solution"]) if expected is None else (
            result["status"] == "optimal" and validation["passed"] is True and abs(result["objective"] - expected) <= 1e-7)
        failed |= not matched
        regression_summaries.append({"scenario": name, "status": result["status"], "objective": result["objective"],
                                     "dual_bound": result["dual_bound"], "mip_gap": result["mip_gap"],
                                     "validation_passed": validation["passed"], "checks": validation.get("checks"),
                                     "grid_energy_kwh": validation.get("grid_energy_kwh"), "matches_analytic_regression": matched,
                                     "input_sha256": digest(case_dir / "input.json")})
    write_json(output / "regression_summary.json", regression_summaries)
    write_json(output / "completion.json", {"completed": True, "passed": not failed,
               "investment_scenarios": len(summaries), "enumerated_combinations": sum(s["enumeration_count"] for s in summaries),
               "fixed_facility_regressions": len(regression_summaries)})
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())

