"""Compare identical physical cycles at 60/30/15 minutes with facility enumeration."""
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
from .timegrid import MINUTES, POLICIES, audit_physical_equivalence, refine_physical_cycle, schedule_rows
from .validation import check_solution


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)


def study_inputs(path, root):
    study = load_json(path)
    required = {"schema_version", "base_config", "fixed_regression_config", "slot_minutes", "connector_policies",
                "changeover_minutes", "changeover_energy_kwh", "drive_energy_interpolation", "cost_basis", "scope"}
    if not isinstance(study, dict) or set(study) != required:
        raise ValueError("Study must use the exact timegrid-study-v1 fields")
    if (study["schema_version"] != "timegrid-study-v1" or study["slot_minutes"] != list(MINUTES)
            or any(type(m) is not int for m in study["slot_minutes"])
            or study["connector_policies"] != list(POLICIES)
            or type(study["changeover_minutes"]) not in (int, float) or study["changeover_minutes"] != 0
            or type(study["changeover_energy_kwh"]) not in (int, float) or study["changeover_energy_kwh"] != 0
            or study["drive_energy_interpolation"] != "uniform_within_original_journey"
            or study["cost_basis"] != "synthetic_cycle_equivalent" or not isinstance(study["scope"], str)):
        raise ValueError("Only the declared 60/30/15-minute zero-changeover physical-cycle study is implemented")
    paths = []
    for field in ("base_config", "fixed_regression_config"):
        if not isinstance(study[field], str) or Path(study[field]).is_absolute():
            raise ValueError("Config paths must be explicit repository-relative paths")
        resolved = (root / study[field]).resolve()
        if root not in resolved.parents or not resolved.is_file():
            raise ValueError("Config must be an existing file within the source repository")
        paths.append(resolved)
    return study, paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = checked_output(args.output, root)
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], encoding="utf-8").strip()
    if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], encoding="utf-8").strip():
        raise ValueError("Canonical run requires a clean committed source")
    study, paths = study_inputs(args.config, root)
    cases = make_investment_scenarios(load_json(paths[0]))
    historical_path = root / "results/investment_20261110/metrics.json"
    historical = {r["scenario"]: r for r in load_json(historical_path)}
    output.mkdir(parents=True)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "source_commit": commit, "source_dirty": False,
        "command": [sys.executable, "-m", "um_charging.timegrid_cli", *sys.argv[1:]],
        "config_sha256": {p.relative_to(root).as_posix(): digest(p) for p in [args.config.resolve(), *paths]},
        "historical_reference": {"path": historical_path.relative_to(root).as_posix(), "sha256": digest(historical_path),
                                 "role": "Prior formal investment results; compared only to the new 60-minute runs"},
        "source_sha256": {p.relative_to(root).as_posix(): digest(p) for p in sorted((root / "src/um_charging").glob("*.py"))},
        "environment": {"python": sys.version, "platform": platform.platform(), "numpy": numpy.__version__, "scipy": scipy.__version__},
        "solver": {"name": "HiGHS through scipy.optimize.milp", "version": None, "version_evidence": "Captured solver banner",
                   "time_limit_seconds": 60.0, "mip_rel_gap": 0.0},
        "seed": None, "seed_reason": "Deterministic physical subdivision and exhaustive finite hardware enumeration",
        "study": study, "research_status": "Project model adaptation of Ye 2024 framework; not paper equation or numerical reproduction",
    }
    write_json(output / "manifest.json", manifest)
    summaries, regressions = [], []
    audit = {"feasible_solutions_checked": 0, "checks": 0, "max_violation_by_constraint": {}, "all_passed": True}

    def collect(checked):
        if checked["applicable"]:
            audit["feasible_solutions_checked"] += 1
            audit["checks"] += checked["checks"]
            audit["all_passed"] &= checked["passed"] is True
            for key, value in checked["max_violation_by_constraint"].items():
                audit["max_violation_by_constraint"][key] = max(value, audit["max_violation_by_constraint"].get(key, 0.0))

    failed = False
    for policy in study["connector_policies"]:
        for minutes in study["slot_minutes"]:
            for name, base in cases.items():
                data = refine_physical_cycle(base, minutes, policy)
                physical = audit_physical_equivalence(base, data)
                if not physical["passed"]:
                    raise ValueError(physical["errors"])
                folder = output / policy / str(minutes) / name
                folder.mkdir(parents=True)
                write_json(folder / "input.json", data)
                write_json(folder / "physical_audit.json", physical)
                print(f"Solving {policy}/{minutes}/{name}", flush=True)
                result = solve(data, display=True)
                checked = check_solution(data, result)
                collect(checked)
                write_json(folder / "result.json", result)
                write_json(folder / "validation.json", checked)
                write_json(folder / "schedule.json", schedule_rows(data, result))

                def save_combination(index, fixed, operating, validation):
                    target = folder / "enumeration" / f"{index:03d}"
                    target.mkdir(parents=True)
                    for filename, payload in (("input.json", fixed), ("result.json", operating), ("validation.json", validation)):
                        write_json(target / filename, payload)
                    collect(validation)

                enumeration = enumerate_facilities(data, on_combination=save_combination)
                comparison = compare_joint_to_enumeration(result, checked, enumeration)
                write_json(folder / "enumeration.json", enumeration)
                write_json(folder / "comparison.json", comparison)
                history_match = None
                if minutes == 60:
                    old = historical[name]
                    history_match = result["status"] == old["status"] and (
                        (old["objective"] is None and result["objective"] is None)
                        or (old["objective"] is not None and result["objective"] is not None
                            and abs(result["objective"] - old["objective"]) <= 1e-7))
                    failed |= not history_match
                summary = {
                    "connector_policy": policy, "slot_minutes": minutes, "scenario": name,
                    "input_sha256": digest(folder / "input.json"), "status": result["status"],
                    "objective": result["objective"], "dual_bound": result["dual_bound"], "mip_gap": result["mip_gap"],
                    "new_interfaces": result["solution"]["new_interfaces"] if result["has_solution"] else None,
                    "upgrade_selected": result["solution"]["upgrade_selected"] if result["has_solution"] else None,
                    "validation_passed": checked["passed"], "validation_checks": checked.get("checks"),
                    "max_violation_by_constraint": checked.get("max_violation_by_constraint"),
                    "investment_cost": checked.get("investment_cost"), "operating_cost": checked.get("operating_cost"),
                    "grid_energy_kwh": checked.get("grid_energy_kwh"), "site_energy_kwh": checked.get("site_energy_kwh"),
                    "site_peak_kw": checked.get("site_peak_kw"), "system_coincident_peak_kw": checked.get("system_coincident_peak_kw"),
                    "physical_equivalence_passed": physical["passed"], "historical_60_minute_objective_match": history_match,
                    "enumeration_count": enumeration["combination_count"], "enumeration_feasible": enumeration["feasible_count"],
                    "enumeration_best": enumeration["best_total_cost"], "enumeration_best_hardware": enumeration["best_hardware"],
                    "enumeration_comparison": comparison,
                }
                summaries.append(summary)
                failed |= not comparison["passed"]
                write_json(output / "timegrid_summary.json", summaries)
                print(json.dumps(summary, allow_nan=False), flush=True)

    expected = {"base": 300.0, "interface_bottleneck": None, "power_bottleneck": None,
                "window_bottleneck": None, "higher_power_no_benefit": 300.0, "zero_demand": 0.0}
    for name, data in make_scenarios(load_json(paths[1])).items():
        folder = output / "regression" / name
        folder.mkdir(parents=True)
        result = solve(data, display=True)
        checked = check_solution(data, result)
        collect(checked)
        for filename, payload in (("input.json", data), ("result.json", result), ("validation.json", checked)):
            write_json(folder / filename, payload)
        matched = (result["status"] == "infeasible" and not result["has_solution"]) if expected[name] is None else (
            result["status"] == "optimal" and checked["passed"] is True and abs(result["objective"] - expected[name]) <= 1e-7)
        regressions.append({"scenario": name, "status": result["status"], "objective": result["objective"],
                            "dual_bound": result["dual_bound"], "mip_gap": result["mip_gap"],
                            "validation_passed": checked["passed"], "checks": checked.get("checks"),
                            "matches_analytic_regression": matched, "input_sha256": digest(folder / "input.json")})
        failed |= not matched
    write_json(output / "regression_summary.json", regressions)
    write_json(output / "independent_audit.json", audit)
    write_json(output / "completion.json", {"completed": True, "passed": not failed and audit["all_passed"],
               "timegrid_scenarios": len(summaries), "enumerated_combinations": sum(s["enumeration_count"] for s in summaries),
               "physical_equivalence_checks": len(summaries), "original_fixed_regressions": len(regressions),
               "historical_60_minute_comparisons": sum(s["slot_minutes"] == 60 for s in summaries)})
    return int(failed or not audit["all_passed"])


if __name__ == "__main__":
    raise SystemExit(main())
