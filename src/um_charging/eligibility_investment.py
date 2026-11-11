"""Replan port/warehouse investment given a known delay for V1 and V2."""
import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path

import numpy
import scipy

from .__main__ import checked_output, digest, write_json
from .boundary_cli import facility_details
from .eligibility_reuse import frozen_operating_reuse
from .eligibility_stress import audit_case, delayed_reference, make_reference
from .investment_experiment import compare_joint_to_enumeration, enumerate_facilities
from .model import solve, validate_input
from .timegrid import schedule_rows
from .timegrid_cli import load_json
from .validation import check_solution

ROOT = Path(__file__).resolve().parents[2]
BOUNDARY = ROOT / "results/boundary_20261110/metrics.json"
FROZEN = ROOT / "results/eligibility_stress_20261111/metrics.json"
TOL = 1e-7


def planning_case(reference, delay, delayed_vehicles):
    case = delayed_reference(reference, delay, delayed_vehicles)
    if delay:
        case["instance_id"] = f"known_eligibility_delay_{delay}_joint"
        assumptions = case["provenance"]["assumed"]
        case["provenance"]["assumed"] = [
            a for a in assumptions if not a.startswith("WAREHOUSE physical dwell remains ")]
        case["provenance"]["assumed"].append(
            f"Three warehouse dwells [60,120); V1/V2 may plug in from minute {60 + delay}, "
            "V3 from minute 60. This delay is known before choosing facilities and operations.")
    validate_input(case)
    audit = audit_case(reference, case, None, delay, delayed_vehicles)
    if not audit["passed"]:
        raise ValueError(audit["errors"])
    return case


def historical_zero(case, history):
    row, = (r for r in history if r["scenario"] == case["instance_id"])
    # The old hash covered the bytes written by write_json on the running OS.
    serialized = json.dumps(case, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    hashes = {hashlib.sha256(serialized.replace("\n", nl).encode()).hexdigest() for nl in ("\n", "\r\n")}
    if (row["input_sha256"] not in hashes or row["status"] != "optimal"
            or not row["task_audit_passed"] or not row["validation_passed"]
            or not row["enumeration_comparison"]["passed"] or row["enumeration_count"] != 54
            or abs(row["objective"] - row["enumeration_best"]) > TOL):
        raise ValueError("Zero-delay reference does not match the verified boundary run")
    keys = ("status", "objective", "dual_bound", "mip_gap", "investment_cost", "operating_cost",
            "optimal_facilities", "site_energy_kwh", "validation_checks", "input_sha256",
            "enumeration_count", "enumeration_feasible")
    return {**{key: row[key] for key in keys}, "delay_minutes": 0,
            "source": "boundary_20261110/" + row["scenario"], "joint_new": False,
            "enumeration_new": 0, "enumeration_reused": row["enumeration_count"]}


def fixed_comparison(study, frozen, delay, row):
    bounds = []
    for item in frozen["cases"]:
        if item["delay_minutes"] != delay:
            continue
        total = None
        if item["status"] == "optimal":
            total = item["planning_investment"] + item["operating_cost"]
            if row["status"] != "optimal" or row["objective"] > total + TOL:
                raise ValueError(f"Replanning exceeds the fixed {item['facility']} upper bound at {delay}")
        elif item["status"] != "infeasible":
            raise ValueError("Unresolved historical fixed case")
        bounds.append({"facility": item["facility"], "total_interfaces": study["facilities"][item["facility"]],
                       "status": item["status"], "investment_cost": item["planning_investment"],
                       "operating_cost": item["operating_cost"], "total_cost": total})
    if {b["facility"] for b in bounds} != {"A", "B"} or len(bounds) != 2:
        raise ValueError("Missing fixed facility comparison")
    return bounds


def run_delay(reference, study, frozen, delay, folder):
    data = planning_case(reference, delay, study["delayed_vehicle_ids"])
    folder.mkdir()
    write_json(folder / "input.json", data)
    joint = solve(data)
    checked = check_solution(data, joint)
    write_json(folder / "result.json", joint)
    write_json(folder / "validation.json", checked)
    write_json(folder / "schedule.json", schedule_rows(data, joint))

    def archive(index, fixed, result, validation):
        dest = folder / "enumeration" / f"{index:03d}"
        dest.mkdir(parents=True)
        for name, obj in (("input", fixed), ("result", result), ("validation", validation)):
            write_json(dest / (name + ".json"), obj)

    lookup = frozen_operating_reuse(reference, study, frozen, delay)
    enum = enumerate_facilities(data, on_combination=archive, reuse_operating=lookup)
    write_json(folder / "enumeration.json", enum)
    comparison = compare_joint_to_enumeration(joint, checked, enum)
    records = enum["combinations"]
    reused = [r for r in records if "reused_from" in r]
    if not comparison["passed"] or len(reused) != 2 or len(records) != 54:
        raise ValueError(f"Incomplete hardware verification at delay {delay}: {comparison}")
    row = {"delay_minutes": delay, "source": "new_joint_and_enumeration", "joint_new": True,
           "input_sha256": digest(folder / "input.json"), "status": joint["status"],
           "objective": joint["objective"], "dual_bound": joint["dual_bound"], "mip_gap": joint["mip_gap"],
           "investment_cost": checked.get("investment_cost"), "operating_cost": checked.get("operating_cost"),
           "optimal_facilities": facility_details(data, enum["best_hardware"]),
           "site_energy_kwh": checked.get("site_energy_kwh"), "validation_checks": checked.get("checks"),
           "enumeration_count": len(records), "enumeration_feasible": enum["feasible_count"],
           "enumeration_new": len(records) - len(reused), "enumeration_reused": len(reused)}
    if delay == 45:
        # Condition the same full enumeration on keeping at most two port plugs.
        available = [r for r in records if r["status"] == "optimal"
                     and data["sites"][0]["interfaces"] + r["hardware"][0]["new_interfaces"] <= 2]
        best = min((r["total_cost"] for r in available), default=None)
        tied = [r for r in available if abs(r["total_cost"] - best) <= TOL]
        row["at_most_two_port_interfaces"] = {
            "minimum_total_cost": best, "investment_cost": tied[0]["investment_cost"] if tied else None,
            "optimal_facilities": facility_details(data, [r["hardware"] for r in tied]),
            "combinations_at_minimum": [r["combination"] for r in tied],
            "feasible_count": len(available)}
        if tied:
            alternative = folder / "enumeration" / f"{tied[0]['combination']:03d}"
            dispatch = {}
            for label, solution in (("joint", joint), ("two_port", load_json(alternative / "result.json"))):
                dispatch[label] = [
                    {key: item[key] for key in ("vehicle", "start_minute", "end_minute", "power_kw")}
                    for item in schedule_rows(data, solution) if any(p > TOL for p in item["power_kw"].values())]
            write_json(folder / "selected_dispatch.json", dispatch)
    return row


def run_study(config_path, output):
    output = checked_output(Path(output), ROOT)
    config_path = Path(config_path)
    study = load_json(config_path)
    if (study["schema_version"] != "fixed-eligibility-delay-v1"
            or study["delays_minutes"] != [0, 15, 30, 45, 60]
            or study["delayed_vehicle_ids"] != ["V1", "V2"]):
        raise ValueError("Use the registered five known eligibility delays")
    base_path = ROOT / study["base_config"]
    reference = make_reference(load_json(base_path))
    frozen = load_json(FROZEN)
    rows = [historical_zero(planning_case(reference, 0, study["delayed_vehicle_ids"]), load_json(BOUNDARY))]
    output.mkdir(parents=True)
    for delay in study["delays_minutes"][1:]:
        rows.append(run_delay(reference, study, frozen, delay, output / f"delay_{delay}"))
    first_change = None
    for i, row in enumerate(rows):
        row["fixed_facility_comparisons"] = fixed_comparison(study, frozen, row["delay_minutes"], row)
        if i:
            previous = rows[i - 1]
            if previous["status"] == "infeasible" and row["status"] == "optimal":
                raise ValueError("Tighter eligibility restored feasibility")
            changed_cost = previous["status"] != row["status"]
            if previous["status"] == row["status"] == "optimal":
                difference = row["objective"] - previous["objective"]
                if difference < -TOL:
                    raise ValueError("Cost decreased when plug access was delayed")
                changed_cost = difference > TOL
            if first_change is None and (changed_cost or previous["optimal_facilities"] != row["optimal_facilities"]):
                first_change = [previous["delay_minutes"], row["delay_minutes"]]
    summary = {"delay_known_before_investment": True, "cost_basis": reference["cost_basis"],
               "first_change_between_tested_minutes": first_change, "cases": rows}
    write_json(output / "metrics.json", summary)
    paths = [config_path.resolve(), base_path, BOUNDARY, FROZEN]
    manifest = {"source_commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
                "source_dirty": bool(subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"])),
                "input_sha256": {str(p.relative_to(ROOT).as_posix()): digest(p) for p in paths},
                "python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
                "solver": "scipy.optimize.milp / HiGHS", "time_limit_seconds": 60, "requested_mip_rel_gap": 0,
                "seed": None, "sampling": "deterministic finite grid", "new_joint_solves": 4,
                "new_operating_solves": sum(r["enumeration_new"] for r in rows),
                "reused_operating_results": sum(r["enumeration_reused"] for r in rows)}
    write_json(output / "manifest.json", manifest)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/eligibility_stress.json", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    summary = run_study(args.config, args.output)
    for row in summary["cases"]:
        print(row["delay_minutes"], row["status"], row["investment_cost"], row["operating_cost"], row["objective"])
