"""Finite facility enumeration using the original fixed-facility operating model."""
from __future__ import annotations

import copy
import itertools
import math

from .model import solve, validate_input
from .validation import check_solution


def make_investment_scenarios(base):
    """Keep all transport inputs identical; only restrict facilities/investment."""
    validate_input(base)
    if base["schema_version"] != "capacity-investment-v1" or [s["id"] for s in base["sites"]] != ["PORT", "WAREHOUSE"]:
        raise ValueError("This experiment requires explicit PORT, WAREHOUSE investment sites in that order")
    cases = {}
    for scope in ("port_only", "two_sites"):
        for mode in ("no_investment", "interfaces_only", "power_only", "joint"):
            data = copy.deepcopy(base)
            name = f"{scope}_{mode}"
            data["instance_id"] = name
            data["sites"][1]["active"] = scope == "two_sites"
            for site in data["sites"]:
                if mode in ("no_investment", "power_only"):
                    site["max_new_interfaces"] = 0
                if mode in ("no_investment", "interfaces_only"):
                    site["upgrade_options"] = []
            cases[name] = data
    data = copy.deepcopy(cases["two_sites_joint"])
    data["instance_id"] = "two_sites_joint_redundant_warehouse_power"
    data["sites"][1]["available_power_kw"] = [value + 25.0 for value in data["sites"][1]["available_power_kw"]]
    cases[data["instance_id"]] = data
    return cases


def enumerate_facilities(data, *, display=False, time_limit=60.0, on_combination=None,
                         reuse_operating=None):
    """Fix each discrete facility choice, solve original operations, add its cost.

    No joint-investment solution, matrix, objective coefficients or selected
    hardware is consulted. Every permitted hardware tuple is enumerated.
    An optional reuse_operating(fixed, allocations, investment_cost) supplies
    a checked historical operating summary or None. on_combination receives
    only fresh solves, which have raw primal/solver output.
    """
    validate_input(data)
    if data["schema_version"] not in ("capacity-investment-v1", "capacity-investment-v2"):
        raise ValueError("Enumeration requires an explicit capacity-investment schema")
    retain_policy = data["schema_version"] == "capacity-investment-v2"
    choices = []
    for site in data["sites"]:
        choices.append(list(itertools.product(
            range(site["max_new_interfaces"] + 1) if site["active"] else [0],
            range(-1, len(site["upgrade_options"])) if site["active"] else [-1])))
    records = []
    best = None
    best_choices = []
    for index, hardware in enumerate(itertools.product(*choices)):
        fixed = copy.deepcopy(data)
        if not retain_policy:
            fixed["schema_version"] = "fixed-facility-v1"
            fixed.pop("cost_basis")
        investment_cost = 0.0
        allocations = []
        for site, (n, level) in zip(fixed["sites"], hardware):
            options = site.pop("upgrade_options")
            site.pop("max_new_interfaces")
            connector_cost = site.pop("interface_cost")
            upgrade = options[level] if level >= 0 else None
            increment = upgrade["additional_power_kw"] if upgrade else 0.0
            investment_cost += connector_cost * n + (upgrade["cost"] if upgrade else 0.0)
            site["interfaces"] += n
            site["available_power_kw"] = [value + increment for value in site["available_power_kw"]]
            if retain_policy:
                # No investment freedom remains. Preserve transit and C08 policy
                # rather than dropping them in a fixed-facility-v1 conversion.
                site.update(max_new_interfaces=0, interface_cost=0.0, upgrade_options=[])
            allocations.append({"site_id": site["id"], "new_interfaces": n,
                                "upgrade_id": upgrade["id"] if upgrade else None})
        if not retain_policy:
            for vehicle in fixed["vehicles"]:
                vehicle.pop("timeline")
        operating = reuse_operating(fixed, allocations, investment_cost) if reuse_operating else None
        if operating is None:
            result = solve(fixed, display=display, time_limit=time_limit)
            validation = check_solution(fixed, result)
            if on_combination is not None:
                on_combination(index, fixed, result, validation)
            if result["status"] not in {"optimal", "infeasible"} or (result["has_solution"] and not validation["passed"]):
                raise RuntimeError(f"Enumeration combination {index} is unresolved or failed independent checks")
            operating = {"status": result["status"], "operating_cost": result["objective"],
                         "operating_dual_bound": result["dual_bound"], "operating_mip_gap": result["mip_gap"],
                         "validation_passed": validation["passed"], "validation_checks": validation.get("checks"),
                         "total_cost": (investment_cost + validation["operating_cost"]
                                        if result["has_solution"] and validation["passed"] else None)}
        record = {"combination": index, "hardware": allocations, "investment_cost": investment_cost, **operating}
        records.append(record)
        if record["status"] == "optimal":
            value = record["total_cost"]
            if best is None or value < best - 1e-7:
                best, best_choices = value, [allocations]
            elif math.isclose(value, best, rel_tol=0, abs_tol=1e-7):
                best_choices.append(allocations)
    return {"complete": True, "combination_count": len(records),
            "feasible_count": sum(r["status"] == "optimal" for r in records),
            "infeasible_count": sum(r["status"] == "infeasible" for r in records),
            "best_total_cost": best, "best_hardware": best_choices, "combinations": records}


def compare_joint_to_enumeration(joint, independent, enumeration, tolerance=1e-7):
    if not enumeration["complete"]:
        return {"passed": False, "reason": "Enumeration incomplete"}
    if joint["status"] == "infeasible":
        return {"passed": enumeration["feasible_count"] == 0,
                "reason": "All finite facility combinations infeasible" if enumeration["feasible_count"] == 0 else "Feasible combination contradicts joint infeasibility"}
    if joint["status"] != "optimal" or independent["passed"] is not True or enumeration["best_total_cost"] is None:
        return {"passed": False, "reason": "Joint result is not independently checked optimal"}
    difference = abs(independent["objective_recomputed"] - enumeration["best_total_cost"])
    return {"passed": difference <= tolerance, "objective_difference": difference,
            "reason": "Joint optimum versus exhaustive hardware choices with optimal operations"}

