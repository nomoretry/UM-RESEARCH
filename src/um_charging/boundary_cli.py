"""Canonical 15-minute existing-port-power by warehouse-window experiment."""
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

from .__main__ import checked_output, digest, write_json
from .boundary import POWERS, WINDOWS, SCOPES, audit_boundary_case, boundary_cases
from .boundary_validation import check_boundary_properties
from .investment_experiment import compare_joint_to_enumeration, enumerate_facilities
from .model import make_scenarios, solve
from .timegrid import POLICIES, schedule_rows
from .timegrid_cli import load_json
from .validation import check_solution


def study_inputs(path, root):
    study = load_json(path)
    fixed = {"schema_version": "power-window-study-v1", "slot_minutes": 15,
             "port_available_power_kw": list(POWERS), "warehouse_window_minutes": list(WINDOWS),
             "warehouse_window_start_minute": 60, "charging_scopes": list(SCOPES), "connector_policies": list(POLICIES),
             "cost_basis": "synthetic_cycle_equivalent", "changeover_minutes": 0, "changeover_energy_kwh": 0}
    if not isinstance(study, dict) or set(study) != set(fixed) | {"base_config", "fixed_regression_config"}:
        raise ValueError("Exact power-window-study-v1 fields are required")
    for field, value in fixed.items():
        if type(study[field]) is not type(value) or study[field] != value:
            raise ValueError(f"This study requires the declared {field}")
    if any(type(x) is not int for key in ("port_available_power_kw", "warehouse_window_minutes") for x in study[key]):
        raise ValueError("Power and window values must be exact integers")
    paths = []
    for field in ("base_config", "fixed_regression_config"):
        if not isinstance(study[field], str) or Path(study[field]).is_absolute():
            raise ValueError("Input paths must be explicit repository-relative files")
        resolved = (root / study[field]).resolve()
        if root not in resolved.parents or not resolved.is_file():
            raise ValueError("Input must be a file within this repository")
        paths.append(resolved)
    return study, paths


def facility_details(data, hardware_sets):
    """Describe every enumerated optimum, preserving existing/added/total capacity."""
    descriptions = []
    for hardware in hardware_sets:
        sites = []
        for site, allocation in zip(data["sites"], hardware):
            assert site["id"] == allocation["site_id"]
            options = {o["id"]: o for o in site["upgrade_options"]}
            option = options[allocation["upgrade_id"]] if allocation["upgrade_id"] is not None else None
            added = option["additional_power_kw"] if option else 0
            sites.append({"site_id": site["id"], "active": site["active"], "existing_interfaces": site["interfaces"],
                          "new_interfaces": allocation["new_interfaces"], "total_interfaces": site["interfaces"] + allocation["new_interfaces"],
                          "existing_power_kw": site["available_power_kw"][0], "upgrade_id": allocation["upgrade_id"],
                          "added_power_kw": added, "total_available_power_kw": site["available_power_kw"][0] + added,
                          "interface_cost": site["interface_cost"] * allocation["new_interfaces"],
                          "expansion_cost": option["cost"] if option else 0})
        descriptions.append(sites)
    return descriptions


def scope_comparisons(rows):
    pairs = []
    for policy in POLICIES:
        for power in POWERS:
            for window in WINDOWS:
                scope_rows = {r["charging_scope"]: r for r in rows if r["connector_policy"] == policy
                              and r["port_available_power_kw"] == power and r["warehouse_window_minutes"] == window}
                port, both = scope_rows["port_only"], scope_rows["two_sites"]
                delta = port["objective"] - both["objective"] if port["status"] == both["status"] == "optimal" else None
                if port["status"] == both["status"] == "infeasible": outcome = "both_infeasible"
                elif port["status"] == "infeasible" and both["status"] == "optimal": outcome = "cooperation_enables_service"
                elif delta is not None: outcome = "equal_total_cost" if abs(delta) <= 1e-7 else ("lower_total_cost" if delta > 0 else "higher_total_cost_error")
                else: outcome = "unresolved_or_dominance_error"
                pairs.append({"connector_policy": policy, "port_available_power_kw": power, "warehouse_window_minutes": window,
                              "port_status": port["status"], "two_sites_status": both["status"],
                              "port_objective": port["objective"], "two_sites_objective": both["objective"],
                              "total_cost_reduction": delta, "outcome": outcome})
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = checked_output(args.output, root)
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], encoding="utf-8").strip()
    if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], encoding="utf-8").strip():
        raise ValueError("Canonical run requires clean committed source")
    study, paths = study_inputs(args.config, root)
    base = load_json(paths[0])
    historical_path = root / "results/timegrid_20261110/metrics.json"
    historical = load_json(historical_path)
    output.mkdir(parents=True)
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "source_commit": commit, "source_dirty": False,
        "command": [sys.executable, "-m", "um_charging.boundary_cli", *sys.argv[1:]],
        "config_sha256": {p.relative_to(root).as_posix(): digest(p) for p in [args.config.resolve(), *paths]},
        "source_sha256": {p.relative_to(root).as_posix(): digest(p) for p in sorted((root / "src/um_charging").glob("*.py"))},
        "historical_reference": {"path": historical_path.relative_to(root).as_posix(), "sha256": digest(historical_path)},
        "environment": {"python": sys.version, "numpy": numpy.__version__, "scipy": scipy.__version__, "platform": platform.platform()},
        "solver": {"name": "HiGHS through scipy.optimize.milp", "version": None, "version_evidence": "Captured solver banner",
                   "time_limit_seconds": 60.0, "mip_rel_gap": 0.0},
        "seed": None, "seed_reason": "Explicit deterministic grid and exhaustive finite hardware enumeration", "study": study,
        "scope": "Ye 2024 framework adaptation; synthetic cycle-equivalent investment, existing facilities sunk; deterministic sensitivity, not uncertainty planning or paper reproduction."}
    write_json(output / "manifest.json", manifest)
    audit = {"feasible_solutions_checked": 0, "checks": 0, "max_violation_by_constraint": {}, "all_passed": True}
    def collect(checked):
        if checked["applicable"]:
            audit["feasible_solutions_checked"] += 1
            audit["checks"] += checked.get("checks", 0)
            audit["all_passed"] &= checked["passed"] is True
            for key, value in checked.get("max_violation_by_constraint", {}).items():
                audit["max_violation_by_constraint"][key] = max(value, audit["max_violation_by_constraint"].get(key, 0))
    rows, regressions, failed = [], [], False
    for coordinates, data in boundary_cases(base):
        task_audit = audit_boundary_case(base, data, **coordinates)
        if not task_audit["passed"]: raise ValueError(task_audit["errors"])
        folder = output / data["instance_id"]
        folder.mkdir()
        write_json(folder / "input.json", data)
        write_json(folder / "task_audit.json", task_audit)
        print(f"Solving {data['instance_id']}", flush=True)
        result = solve(data, display=True)
        checked = check_solution(data, result)
        collect(checked)
        for filename, payload in (("result.json", result), ("validation.json", checked), ("schedule.json", schedule_rows(data, result))):
            write_json(folder / filename, payload)
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
        if coordinates["port_available_power_kw"] == 75 and coordinates["warehouse_window_minutes"] == 60:
            old = next(r for r in historical if r["slot_minutes"] == 15 and r["connector_policy"] == coordinates["connector_policy"]
                       and r["scenario"] == coordinates["charging_scope"] + "_joint")
            history_match = result["status"] == old["status"] and abs(result["objective"] - old["objective"]) <= 1e-7
            failed |= not history_match
        row = {**coordinates, "scenario": data["instance_id"], "input_sha256": digest(folder / "input.json"),
               "status": result["status"], "objective": result["objective"], "dual_bound": result["dual_bound"], "mip_gap": result["mip_gap"],
               "validation_passed": checked["passed"], "validation_checks": checked.get("checks"),
               "max_violation_by_constraint": checked.get("max_violation_by_constraint"),
               "task_audit_passed": task_audit["passed"], "task_audit_checks": task_audit["checks"],
               "new_interfaces": result["solution"]["new_interfaces"] if result["has_solution"] else None,
               "upgrade_selected": result["solution"]["upgrade_selected"] if result["has_solution"] else None,
               "investment_cost": checked.get("investment_cost"), "interface_cost": checked.get("interface_cost"),
               "expansion_cost": checked.get("expansion_cost"), "operating_cost": checked.get("operating_cost"),
               "grid_energy_kwh": checked.get("grid_energy_kwh"), "site_energy_kwh": checked.get("site_energy_kwh"),
               "site_peak_kw": checked.get("site_peak_kw"), "system_coincident_peak_kw": checked.get("system_coincident_peak_kw"),
               "enumeration_count": enumeration["combination_count"], "enumeration_feasible": enumeration["feasible_count"],
               "enumeration_best": enumeration["best_total_cost"], "enumeration_best_hardware": enumeration["best_hardware"],
               "optimal_facilities": facility_details(data, enumeration["best_hardware"]),
               "enumeration_comparison": comparison, "historical_overlap_match": history_match}
        rows.append(row)
        failed |= not comparison["passed"]
        write_json(output / "boundary_summary.json", rows)
        print(json.dumps({**coordinates, "status": result["status"], "objective": result["objective"],
                          "investment_cost": checked.get("investment_cost"), "optimal_hardware_count": len(enumeration["best_hardware"])}), flush=True)
    properties = check_boundary_properties(rows)
    write_json(output / "properties.json", properties)
    write_json(output / "scope_comparisons.json", scope_comparisons(rows))
    failed |= not properties["passed"]
    expected = {"base": 300.0, "interface_bottleneck": None, "power_bottleneck": None,
                "window_bottleneck": None, "higher_power_no_benefit": 300.0, "zero_demand": 0.0}
    for name, data in make_scenarios(load_json(paths[1])).items():
        folder = output / "regression" / name
        folder.mkdir(parents=True)
        result, checked = solve(data, display=True), None
        checked = check_solution(data, result)
        collect(checked)
        for filename, payload in (("input.json", data), ("result.json", result), ("validation.json", checked)):
            write_json(folder / filename, payload)
        matched = result["status"] == "infeasible" if expected[name] is None else (
            result["status"] == "optimal" and checked["passed"] is True and abs(result["objective"] - expected[name]) <= 1e-7)
        regressions.append({"scenario": name, "status": result["status"], "objective": result["objective"],
                            "dual_bound": result["dual_bound"], "mip_gap": result["mip_gap"], "validation_passed": checked["passed"],
                            "checks": checked.get("checks"), "matches_analytic_regression": matched})
        failed |= not matched
    write_json(output / "regression_summary.json", regressions)
    write_json(output / "independent_audit.json", audit)
    write_json(output / "completion.json", {"completed": True, "passed": not failed and audit["all_passed"],
        "boundary_scenarios": len(rows), "enumerated_combinations": sum(r["enumeration_count"] for r in rows),
        "task_audits": len(rows), "property_comparisons": properties["checks"], "original_regressions": len(regressions),
        "historical_overlap_comparisons": sum(r["historical_overlap_match"] is not None for r in rows)})
    return int(failed or not audit["all_passed"])


if __name__ == "__main__":
    raise SystemExit(main())
