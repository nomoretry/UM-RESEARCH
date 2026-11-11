"""Re-dispatch frozen facilities after a known delay in warehouse plug eligibility."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform

import numpy
import scipy

from .__main__ import digest, write_json
from .boundary import build_boundary_case
from .model import solve, validate_input
from .timegrid_cli import load_json
from .validation import check_solution


def make_reference(base):
    return build_boundary_case(base, 100, 60, "two_sites", "slot_boundary_switching")


def delayed_reference(reference, delay_minutes, delayed_vehicle_ids):
    """Copy the common planning input and delay only the two warehouse plug masks."""
    if type(delay_minutes) is not int or delay_minutes not in (0, 15, 30, 45, 60):
        raise ValueError("Delay must be a 15-minute grid point in [0, 60].")
    if set(delayed_vehicle_ids) != {"V1", "V2"} or len(delayed_vehicle_ids) != 2:
        raise ValueError("The registered delay applies to V1 and V2.")
    data = copy.deepcopy(reference)
    for vehicle in data["vehicles"]:
        if vehicle["id"] in delayed_vehicle_ids:
            for t in range(4, 4 + delay_minutes // 15):
                vehicle["charging_site"][t] = None
                vehicle["timeline"][t]["plug_allowed"] = False
    return data


def build_case(reference, facility, delay_minutes, delayed_vehicle_ids):
    """Freeze the specified hardware on the delayed transport task."""
    if set(facility) != {"PORT", "WAREHOUSE"} or any(type(n) is not int for n in facility.values()):
        raise ValueError("Specify integer total interfaces at PORT and WAREHOUSE.")
    data = delayed_reference(reference, delay_minutes, delayed_vehicle_ids)
    data["instance_id"] = f"frozen_p{facility['PORT']}_w{facility['WAREHOUSE']}_delay{delay_minutes}"
    for site in data["sites"]:
        site.update(interfaces=facility[site["id"]], max_new_interfaces=0, interface_cost=0, upgrade_options=[])
    # Replace the boundary generator's declarations of investment freedom and a common full window.
    assumptions = data["provenance"]["assumed"]
    data["provenance"]["assumed"] = [line for line in assumptions if not line.startswith((
        "PORT existing available power is ", "WAREHOUSE physical dwell remains ", "Charging scope is "))]
    data["provenance"]["assumed"].extend([
        "Two active sites with fixed hardware and unchanged physical stops. Prior investment is accounted separately.",
        f"V1 and V2 may plug in at the warehouse in [{60 + delay_minutes},120); V3 in [60,120) minutes. The dispatcher knows the delay.",
    ])
    validate_input(data)
    return data


def audit_case(reference, case, facility, delay_minutes, delayed_vehicle_ids):
    """Compare all physical/service inputs, and reconstruct the authorized mask in clock minutes."""
    errors = []
    def compare(actual, expected, label):
        if actual != expected:
            errors.append(label)

    unchanged = set(reference) - {"instance_id", "provenance", "vehicles", "sites"}
    for key in unchanged:
        compare(case[key], reference[key], key)
    compare([s["id"] for s in case["sites"]], ["PORT", "WAREHOUSE"], "site identities")
    for original, actual in zip(reference["sites"], case["sites"]):
        expected = original if facility is None else dict(
            original, interfaces=facility[original["id"]], max_new_interfaces=0,
            interface_cost=0, upgrade_options=[])
        compare(actual, expected, f"{original['id']} equipment, investment options, power and prices")
    hardware = [(s["id"], s["active"], s["interfaces"], s["available_power_kw"], s["max_new_interfaces"],
                 s["upgrade_options"]) for s in case["sites"]]
    hardware_hash = hashlib.sha256(json.dumps(hardware, separators=(",", ":")).encode()).hexdigest()

    compare([v["id"] for v in case["vehicles"]], [v["id"] for v in reference["vehicles"]], "vehicle identities")
    for original, actual in zip(reference["vehicles"], case["vehicles"]):
        vehicle_id = original["id"]
        for key in set(original) - {"timeline", "charging_site"}:
            compare(actual[key], original[key], f"{vehicle_id}/{key}")
        expected_sites, expected_timeline = [], []
        for slot, (event, site) in enumerate(zip(original["timeline"], original["charging_site"])):
            if site == "WAREHOUSE" and vehicle_id in delayed_vehicle_ids and 15 * slot < 60 + delay_minutes:
                site = None
            expected_sites.append(site)
            expected_timeline.append(dict(event, plug_allowed=site is not None))
        compare(actual["timeline"], expected_timeline, f"{vehicle_id}/timeline")
        compare(actual["charging_site"], expected_sites, f"{vehicle_id}/charging_site")
    return {"passed": not errors, "errors": errors, "hardware_sha256": hardware_hash}


def run_study(config_path, output):
    root = Path(__file__).resolve().parents[2]
    output = Path(output).resolve()
    if output == root or root in output.parents or output.exists():
        raise ValueError("Use a fresh output directory outside the source repository for raw records.")
    config_path = Path(config_path).resolve()
    study = load_json(config_path)
    facilities = study["facilities"]
    delays = study["delays_minutes"]
    delayed = study["delayed_vehicle_ids"]
    if (study["schema_version"] != "fixed-eligibility-delay-v1" or delays != [0, 15, 30, 45, 60]
            or facilities != {"A": {"PORT": 2, "WAREHOUSE": 1}, "B": {"PORT": 3, "WAREHOUSE": 1}}
            or delayed != ["V1", "V2"]):
        raise ValueError("Config must match the two registered builds, five delay levels and affected vehicles.")
    base_path = root / study["base_config"]
    base = load_json(base_path)
    reference = make_reference(base)
    history_path = root / "results/boundary_20261110/mechanisms.json"
    historical = next(row["fixed_hardware_enumeration"] for row in load_json(history_path)["interface_slot_counterexample"]
                      if row["scenario"] == "boundary_slot_boundary_switching_p100_w60_two_sites")
    output.mkdir(parents=True)
    write_json(output / "manifest.json", {
        "created_utc": datetime.now(timezone.utc).isoformat(), "config_sha256": digest(config_path),
        "base_sha256": digest(base_path), "history_sha256": digest(history_path),
        "python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
        "solver": "scipy.optimize.milp / HiGHS", "mip_rel_gap": 0, "time_limit_seconds": 60,
        "source_sha256": {p.name: digest(p) for p in sorted((root / "src/um_charging").glob("*.py"))},
    })
    rows = []
    grid_requirement = sum(sum(v["drive_energy_kwh"]) / v["efficiency"] for v in base["vehicles"])
    for name, facility in facilities.items():
        investment = sum((facility[s["id"]] - s["interfaces"]) * s["interface_cost"] for s in reference["sites"])
        for delay in delays:
            case = build_case(reference, facility, delay, delayed)
            folder = output / case["instance_id"]
            folder.mkdir()
            write_json(folder / "input.json", case)
            audit = audit_case(reference, case, facility, delay, delayed)
            write_json(folder / "audit.json", audit)
            if not audit["passed"]:
                raise ValueError(audit["errors"])
            result = solve(case)
            check = check_solution(case, result)
            write_json(folder / "result.json", result)
            write_json(folder / "validation.json", check)
            if result["status"] not in ("optimal", "infeasible"):
                raise RuntimeError(f"{case['instance_id']}: unresolved solve: {result['status']}")
            if result["status"] == "optimal" and (
                    check["passed"] is not True or not math.isclose(check["grid_energy_kwh"], grid_requirement, abs_tol=1e-7)):
                raise RuntimeError(f"{case['instance_id']}: failed primal or energy check")
            rows.append({"facility": name, "delay_minutes": delay, "status": result["status"],
                         "planning_investment": investment, "operating_cost": check.get("operating_cost"),
                         "grid_energy_kwh": check.get("grid_energy_kwh"), "dual_bound": result["dual_bound"],
                         "mip_gap": result["mip_gap"], "validation_passed": check["passed"],
                         "validation_checks": check.get("checks"), "hardware_sha256": audit["hardware_sha256"],
                         "input_sha256": digest(folder / "input.json")})
    thresholds = {}
    properties = {}
    for name in facilities:
        group = [r for r in rows if r["facility"] == name]
        valid = [r["delay_minutes"] for r in group if r["status"] == "optimal"]
        invalid = [r["delay_minutes"] for r in group if r["status"] == "infeasible"]
        thresholds[name] = {"last_feasible_minutes": max(valid, default=None),
                            "first_infeasible_minutes": min(invalid, default=None)}
        properties[f"{name}_nested_feasibility"] = not valid or not invalid or max(valid) < min(invalid)
        properties[f"{name}_hardware_unchanged"] = len({r["hardware_sha256"] for r in group}) == 1
    statuses = {(r["facility"], r["delay_minutes"]): r["status"] for r in rows}
    properties["B_feasible_when_A_feasible"] = all(
        statuses["A", d] != "optimal" or statuses["B", d] == "optimal" for d in delays)
    zero = next(r for r in rows if r["facility"] == "A" and r["delay_minutes"] == 0)
    properties["A_zero_matches_historical_enumeration"] = (
        zero["status"] == historical["status"] == "optimal"
        and historical["hardware"] == [
            {"site_id": s["id"], "new_interfaces": facilities["A"][s["id"]] - s["interfaces"], "upgrade_id": None}
            for s in reference["sites"]]
        and math.isclose(zero["planning_investment"], historical["investment_cost"], abs_tol=1e-7)
        and math.isclose(zero["operating_cost"], historical["operating_cost"], abs_tol=1e-7))
    summary = {"cases": rows, "thresholds": thresholds, "properties": properties, "passed": all(properties.values())}
    write_json(output / "metrics.json", summary)
    if not summary["passed"]:
        raise RuntimeError(f"Stress properties failed: {properties}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Fresh external directory for local run evidence")
    args = parser.parse_args()
    summary = run_study(args.config, args.output)
    print(json.dumps(summary["thresholds"], ensure_ascii=False))


if __name__ == "__main__":
    main()
