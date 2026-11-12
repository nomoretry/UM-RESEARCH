"""Check nonzero physical connector changeover on the two registered UM truck duties."""
import argparse
import csv
from functools import lru_cache
from itertools import product
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

import scipy

from .__main__ import checked_output, digest, write_json
from .day_ahead import ROOT, STUDY, read_json
from .eligibility_stress import make_reference
from .facility_month import DELAY, ENERGY, fixed_cases
from .model import solve
from .validation import check_solution


def hardware_key(hardware):
    return tuple((site, spec["interfaces"], spec["power_kw"]) for site, spec in sorted(hardware.items()))


def facility_menu(reference):
    """All investment choices from the existing one-connector-per-site build."""
    site_choices = []
    for site in reference["sites"]:
        capacity, = set(site["available_power_kw"])
        upgrades = [(0, 0)] + [(u["additional_power_kw"], u["cost"]) for u in site["upgrade_options"]]
        site_choices.append([
            (site["id"], {"interfaces": site["interfaces"] + n, "power_kw": capacity + kw},
             n * site["interface_cost"] + upgrade_cost)
            for n in range(1 + site["max_new_interfaces"]) for kw, upgrade_cost in upgrades
        ])
    menu = []
    for selection in product(*site_choices):
        hardware = {site: spec for site, spec, _ in selection}
        menu.append((sum(cost for _, _, cost in selection), hardware))
    return sorted(menu, key=lambda item: (item[0], hardware_key(item[1])))


def critical_minutes(leg, hardware, case):
    """Closed-form limits for this three-truck, four-port-slot experiment."""
    eta = case["vehicles"][0]["efficiency"]
    kw = case["vehicles"][0]["power_limit_kw"]["PORT"]
    h = leg / eta * 60 / kw
    if hardware["PORT"]["interfaces"] == 2:
        # At the port the two late trucks require six slots and V3 needs the other two.
        return min(30 - h, 112.5 - 4*h)
    # V3 can take at most its first-leg deficit at the warehouse. The single
    # warehouse connector can serve only one of the late trucks in its last slot.
    late_minutes = (5*leg / eta - hardware["PORT"]["power_kw"]) * 60 / kw
    if late_minutes > 15:
        return None
    return 60 - math.ceil(h / 15) * 15 - late_minutes


def recovery(menu, delay, sunk, check):
    """Solve in increasing cost, through all ties of both minimum costs."""
    winners = []
    retained = []
    tested = []
    for cost, hardware in menu:
        if retained and cost > retained[0]["total_investment"]:
            break
        status = check(hardware, delay)["status"]
        preserves = all(hardware[s]["interfaces"] >= 2 for s in ("PORT", "WAREHOUSE"))
        entry = {"hardware": hardware, "total_investment": cost}
        tested.append({**entry, "retains_2_2": preserves, "status": status})
        if status == "optimal":
            if not winners or cost == winners[0]["total_investment"]:
                winners.append(entry)
            if preserves and (not retained or cost == retained[0]["total_investment"]):
                retained.append({**entry, "additional_investment": cost - sunk})
    return {"delay_minutes": delay, "menu_size": len(menu), "tested_builds": len(tested),
            "untested_strictly_costlier": len(menu) - len(tested),
            "from_initial_1_1": winners, "retain_installed_2_2": retained}, tested


def run_study(output=None):
    from .changeover import solve_changeover
    from .changeover_check import replay

    base_path = ROOT / read_json(DELAY)["base_config"]
    reference = make_reference(read_json(base_path))
    menu = facility_menu(reference)
    duties = list(fixed_cases())
    cases = {leg: case for leg, _, case in duties}
    old_csv = STUDY / "january_2025_facilities.csv"
    with old_csv.open(encoding="utf-8", newline="") as file:
        old_rows = list(csv.DictReader(file))
    if output is not None:
        output = checked_output(Path(output), ROOT)
        output.mkdir(parents=True)
        for e, c in cases.items():
            write_json(output / f"fixed_transport_{e:.8f}.json", c)

    @lru_cache(maxsize=None)
    def evaluate(leg, key, delay):
        hardware = {site: {"interfaces": n, "power_kw": kw} for site, n, kw in key}
        raw = solve_changeover(cases[leg], hardware, delay)
        if raw["status"] not in ("optimal", "infeasible"):
            raise RuntimeError(f"Unresolved physical feasibility: {leg}, {key}, {delay}, {raw['status']}")
        audit = None
        if raw["status"] == "optimal":
            audit = replay(cases[leg], hardware, delay, raw["schedule"])
            if not audit["passed"]:
                raise ValueError(f"Physical schedule replay failed: {leg}, {key}, {delay}")
        if output is not None:
            name = f"e{leg:.8f}-d{delay:.8f}-" + "-".join(f"{s}-{n}-{kw}" for s,n,kw in key)
            write_json(output / f"{name}.json", {"leg_kwh": leg, "delay_minutes": delay, "hardware": hardware,
                                                "solver": raw, "independent_check": audit})
        result = {k: raw[k] for k in ("status", "objective", "dual_bound", "mip_gap")}
        result["schedule_replay_passed"] = audit["passed"] if audit else None
        return result, raw["schedule"] if audit else None

    out = {"assumptions": {"release_delay_minutes_V1_V2": 45, "slot_minutes": 15,
                           "changeover_sensitivity_minutes": [0, 2, 5, 10], "cost_unit": "synthetic cycle investment",
                           "first_connection_minutes": 0, "within_slot_reassignment": False},
           "source_commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                                     encoding="utf-8").strip(),
           "inputs_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in (base_path, DELAY, ENERGY, old_csv)},
           "baseline_and_sensitivity": [], "high_energy_recovery": []}
    for leg, cost, case in duties:
        hardware = {s["id"]: {"interfaces": s["interfaces"], "power_kw": s["available_power_kw"][0]}
                    for s in case["sites"]}
        key = hardware_key(hardware)
        prior_status, = {r["status"] for r in old_rows if float(r["leg_kwh"]) == leg
                         and int(r["port_plugs"]) == hardware["PORT"]["interfaces"]
                         and int(r["warehouse_plugs"]) == hardware["WAREHOUSE"]["interfaces"]}
        baseline = solve(case)
        base_audit = check_solution(case, baseline) if baseline["status"] == "optimal" else None
        zero = evaluate(leg, key, 0)[0]
        if prior_status != baseline["status"] or prior_status != zero["status"] or (base_audit and not base_audit["passed"]):
            raise ValueError("Zero-time model or baseline differs from the registered facility result")
        if output is not None:
            write_json(output / f"zero_baseline_{case['instance_id']}.json",
                       {"case": case, "original_model": baseline, "original_audit": base_audit})
        limit = critical_minutes(leg, hardware, case)
        minutes = sorted({0, 2, 5, 10} | ({limit, limit + .01} if limit is not None else set()))
        sensitivity = []
        witness = None
        for d in minutes:
            result, schedule = evaluate(leg, key, d)
            expected = "optimal" if limit is not None and d <= limit else "infeasible"
            if result["status"] != expected:
                raise ValueError(f"Threshold calculation and MILP disagree: {leg}, {key}, {d}, {result}")
            sensitivity.append({"delay_minutes": d, **result})
            if d == limit:
                witness = schedule
        out["baseline_and_sensitivity"].append({"leg_kwh": leg, "hardware": hardware, "investment": cost,
                                                "original_model_zero_status": baseline["status"],
                                                "critical_minutes": limit, "runs": sensitivity,
                                                "critical_schedule": witness})

    high = max(cases)
    _, sunk, selected_case = next((e, cost, c) for e, cost, c in duties
                                  if e == high and next(s for s in c["sites"] if s["id"] == "PORT")["interfaces"] == 2)
    truck = selected_case["vehicles"][0]
    h = high / truck["efficiency"] * 60 / truck["power_limit_kw"]["PORT"]
    original_limit = min(30 - h, 112.5 - 4*h)
    larger_warehouse_limit = 60 - 2*h
    def check(hardware, delay):
        return evaluate(high, hardware_key(hardware), delay)[0]
    for d in sorted({original_limit + .01, larger_warehouse_limit, larger_warehouse_limit + .01, 5, 10}):
        result, tested = recovery(menu, d, sunk, check)
        if output is not None:
            write_json(output / f"recovery_{d:.8f}.json", tested)
        out["high_energy_recovery"].append(result)
    out["distinct_changeover_solves"] = evaluate.cache_info().misses
    if output is not None:
        write_json(output / "environment.json", {"python": sys.version, "executable": sys.executable,
                                                "scipy": scipy.__version__, "platform": platform.platform()})
        write_json(output / "selected.json", out)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New directory inside the existing offline run Git")
    print(json.dumps(run_study(parser.parse_args().output), indent=2, allow_nan=False))
