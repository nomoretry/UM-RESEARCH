"""Independent arithmetic and feasibility checks for the V1 MILP output.

This module walks the directed routes again.  Cached plan summaries are checked
against the reconstructed values, never used to establish physical feasibility.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import math
from numbers import Real

from .data import validate_dataset


_PLAN_KEYS = {
    "plan_id", "job_id", "path_nodes", "edge_ids", "distance_km",
    "arrival_slot", "terminal_kwh", "events", "operating_cost_cny",
    "energy_used_kwh",
}
_EVENT_KEYS = {
    "site_id", "arrival_slot", "start_slot", "end_slot",
    "energy_before_kwh", "energy_after_kwh", "grid_energy_kwh",
}
_RESULT_KEYS = {
    "status", "objective_cny_per_year", "station_decisions",
    "selected_plan_ids", "investment_cny_per_year", "operation_cny_per_year",
    "mip_gap", "message",
}
_DECISION_KEYS = {"site_id", "build", "bays"}
_TOL = 1e-6


def _number(value):
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _integer(value):
    return _number(value) and value == int(value)


def _keys(value, expected, label, errors):
    if not isinstance(value, dict):
        errors.append(f"{label}: expected an object")
        return False
    missing = expected - value.keys()
    extra = value.keys() - expected
    if missing:
        errors.append(f"{label}: missing keys {sorted(missing)}")
    if extra:
        errors.append(f"{label}: unknown keys {sorted(extra, key=str)}")
    return not missing and not extra


def _close(actual, expected, label, errors):
    if not _number(actual) or not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=_TOL):
        errors.append(f"{label}: reported {actual!r}, recomputed {expected!r}")


def _plan_structure(plan, index, errors):
    label = f"plans[{index}]"
    if not _keys(plan, _PLAN_KEYS, label, errors):
        return False
    before = len(errors)
    for key in ("plan_id", "job_id"):
        if not isinstance(plan[key], str) or not plan[key]:
            errors.append(f"{label}.{key}: expected a nonempty string")
    for key in ("path_nodes", "edge_ids"):
        if not isinstance(plan[key], list) or any(not isinstance(v, str) for v in plan[key]):
            errors.append(f"{label}.{key}: expected an array of exact string identifiers")
    for key in ("distance_km", "terminal_kwh", "operating_cost_cny", "energy_used_kwh"):
        if not _number(plan[key]):
            errors.append(f"{label}.{key}: expected a finite number")
    if not _integer(plan["arrival_slot"]) or plan["arrival_slot"] < 0:
        errors.append(f"{label}.arrival_slot: expected a nonnegative integer")
    if not isinstance(plan["events"], list):
        errors.append(f"{label}.events: expected an array")
    else:
        for event_index, event in enumerate(plan["events"]):
            elabel = f"{label}.events[{event_index}]"
            if not _keys(event, _EVENT_KEYS, elabel, errors):
                continue
            if not isinstance(event["site_id"], str) or not event["site_id"]:
                errors.append(f"{elabel}.site_id: expected a nonempty string")
            for key in ("arrival_slot", "start_slot", "end_slot"):
                if not _integer(event[key]) or event[key] < 0:
                    errors.append(f"{elabel}.{key}: expected a nonnegative integer")
            for key in ("energy_before_kwh", "energy_after_kwh", "grid_energy_kwh"):
                if not _number(event[key]):
                    errors.append(f"{elabel}.{key}: expected a finite number")
    return len(errors) == before


def _walk_plan(data, plan, job, nodes, edges, sites, errors):
    """Rebuild a selected plan from input edges and explicit charging slots."""
    label = f"plan {plan['plan_id']}"
    path = plan["path_nodes"]
    edge_ids = plan["edge_ids"]
    before = len(errors)
    if len(path) < 2 or path[0] != job["origin"] or path[-1] != job["destination"]:
        errors.append(f"{label}: path must connect this job's exact origin and destination")
    if len(path) != len(set(path)):
        errors.append(f"{label}: V1 requires a simple path without repeated nodes")
    if any(node_id not in nodes for node_id in path):
        errors.append(f"{label}: path references an unknown node")
    if len(edge_ids) != len(path) - 1:
        errors.append(f"{label}: edge_ids length must equal path_nodes length minus one")
    else:
        for position, edge_id in enumerate(edge_ids):
            edge = edges.get(edge_id)
            if edge is None:
                errors.append(f"{label}: unknown edge_id {edge_id!r}")
            elif (edge["from_node"], edge["to_node"]) != (path[position], path[position + 1]):
                errors.append(f"{label}: directed edge {edge_id!r} does not match path adjacency")

    events_at_node = {}
    event_positions = []
    for event in plan["events"]:
        site = sites.get(event["site_id"])
        if site is None:
            errors.append(f"{label}: unknown event site_id {event['site_id']!r}")
            continue
        node_id = site["node_id"]
        if node_id not in path[1:-1]:
            errors.append(f"{label}: charging site {site['site_id']!r} is not an intermediate path node")
            continue
        if node_id in events_at_node:
            errors.append(f"{label}: duplicate charging event at node {node_id!r}")
        events_at_node[node_id] = event
        event_positions.append(path.index(node_id))
    if event_positions != sorted(event_positions):
        errors.append(f"{label}: charging events are not in route order")
    if len(errors) != before:
        return None

    settings = data["settings"]
    vehicle = data["vehicle"]
    slot_minutes = settings["slot_minutes"]
    current_slot = job["departure_slot"]
    energy = job["initial_kwh"]
    distance = 0.0
    energy_used = 0.0
    occupancy = []
    for edge_id, to_node in zip(edge_ids, path[1:]):
        edge = edges[edge_id]
        # Every edge is conservatively rounded, not only the final journey time.
        current_slot += math.ceil(edge["travel_minutes"] / slot_minutes)
        leg_energy = edge["distance_km"] * vehicle["consumption_kwh_per_km"]
        distance += edge["distance_km"]
        energy_used += leg_energy
        energy -= leg_energy
        if energy < vehicle["minimum_kwh"] - _TOL:
            errors.append(f"{label}: battery below minimum after edge {edge_id!r}")
        if energy > vehicle["battery_kwh"] + _TOL:
            errors.append(f"{label}: battery above capacity after edge {edge_id!r}")
        event = events_at_node.get(to_node)
        if event is None:
            continue
        site = sites[event["site_id"]]
        elabel = f"{label}, event {site['site_id']}"
        _close(event["arrival_slot"], current_slot, f"{elabel}.arrival_slot", errors)
        _close(event["energy_before_kwh"], energy, f"{elabel}.energy_before_kwh", errors)
        start, end = int(event["start_slot"]), int(event["end_slot"])
        if start < current_slot:
            errors.append(f"{elabel}: charging starts before the recomputed arrival")
        if end <= start:
            errors.append(f"{elabel}: charging must have positive duration")
        if start < site["open_slot"] or end > site["close_slot"]:
            errors.append(f"{elabel}: charging outside station opening window")
        if end > settings["horizon_slots"]:
            errors.append(f"{elabel}: charging exceeds the time horizon")
        if end <= start or start < current_slot or end > settings["horizon_slots"]:
            return None
        grid_energy = site["charger_kw"] * (end - start) * slot_minutes / 60
        energy += grid_energy * vehicle["charge_efficiency"]
        _close(event["grid_energy_kwh"], grid_energy, f"{elabel}.grid_energy_kwh", errors)
        _close(event["energy_after_kwh"], energy, f"{elabel}.energy_after_kwh", errors)
        if energy > vehicle["battery_kwh"] + _TOL:
            errors.append(f"{elabel}: charging exceeds battery capacity")
        if energy < vehicle["minimum_kwh"] - _TOL:
            errors.append(f"{elabel}: battery below minimum after charging")
        current_slot = end
        occupancy.extend((site["site_id"], slot) for slot in range(start, end))

    if current_slot > job["deadline_slot"]:
        errors.append(f"{label}: recomputed arrival exceeds job deadline")
    if current_slot > settings["horizon_slots"]:
        errors.append(f"{label}: recomputed arrival exceeds time horizon")
    if energy < job["terminal_minimum_kwh"] - _TOL:
        errors.append(f"{label}: terminal energy below job requirement")
    elapsed_hours = (current_slot - job["departure_slot"]) * slot_minutes / 60
    cost = (
        distance * settings["vehicle_cny_per_km"]
        + energy_used / vehicle["charge_efficiency"] * settings["electricity_cny_per_kwh"]
        + elapsed_hours * settings["driver_cny_per_hour"]
    )
    for key, value in (
        ("distance_km", distance), ("arrival_slot", current_slot),
        ("terminal_kwh", energy), ("energy_used_kwh", energy_used),
        ("operating_cost_cny", cost),
    ):
        _close(plan[key], value, f"{label}.{key}", errors)
    return {
        "plan_id": plan["plan_id"], "job_id": job["job_id"],
        "distance_km": distance, "arrival_slot": current_slot,
        "terminal_kwh": energy, "energy_used_kwh": energy_used,
        "operating_cost_cny": cost, "occupancy": occupancy,
    }


def verify_solution(data, plans, result):
    """Return strict feasibility/consistency errors and independently computed metrics.

    Solver termination alone is not evidence of feasibility.  The service-relaxed
    diagnostic is checked against full physical bay capacity by this verifier too.
    """
    errors = []
    metrics = {}

    def finish():
        return {"valid": not errors, "errors": errors, "metrics": metrics}

    try:
        validate_dataset(data)
    except (ValueError, TypeError, OverflowError) as exc:
        errors.append(f"dataset validation failed: {exc}")
        return finish()
    if not isinstance(plans, list):
        errors.append("plans: expected an array")
        return finish()
    if not _keys(result, _RESULT_KEYS, "result", errors):
        return finish()
    if result["status"] not in ("optimal", "feasible_limit"):
        errors.append(f"result.status: no verifiable feasible solution ({result['status']!r})")
        return finish()
    if not isinstance(result["message"], str):
        errors.append("result.message: expected a string")
    if result["mip_gap"] is not None and (not _number(result["mip_gap"]) or result["mip_gap"] < 0):
        errors.append("result.mip_gap: expected null or a nonnegative finite number")
    for key in ("objective_cny_per_year", "investment_cny_per_year", "operation_cny_per_year"):
        if not _number(result[key]):
            errors.append(f"result.{key}: expected a finite number")
    if not isinstance(result["selected_plan_ids"], list) or any(
        not isinstance(v, str) for v in result["selected_plan_ids"]
    ):
        errors.append("result.selected_plan_ids: expected an array of exact string identifiers")
    if not isinstance(result["station_decisions"], list):
        errors.append("result.station_decisions: expected an array")
    if errors:
        return finish()

    jobs = {job["job_id"]: job for job in data["jobs"]}
    sites = {site["site_id"]: site for site in data["sites"]}
    nodes = {node["node_id"]: node for node in data["nodes"]}
    edges = {edge["edge_id"]: edge for edge in data["edges"]}
    plans_by_id = {}
    for index, plan in enumerate(plans):
        if not _plan_structure(plan, index, errors):
            continue
        if plan["plan_id"] in plans_by_id:
            errors.append(f"plans: duplicate plan_id {plan['plan_id']!r}")
        if plan["job_id"] not in jobs:
            errors.append(f"plans[{index}]: unknown job_id {plan['job_id']!r}")
        plans_by_id[plan["plan_id"]] = plan
    if errors:
        return finish()

    decisions = {}
    for index, decision in enumerate(result["station_decisions"]):
        label = f"result.station_decisions[{index}]"
        if not _keys(decision, _DECISION_KEYS, label, errors):
            continue
        site_id = decision["site_id"]
        if not isinstance(site_id, str) or site_id not in sites:
            errors.append(f"{label}: unknown or non-string site_id {site_id!r}")
            continue
        if site_id in decisions:
            errors.append(f"{label}: duplicate site_id {site_id!r}")
        if not _integer(decision["build"]) or decision["build"] not in (0, 1):
            errors.append(f"{label}.build: expected integer 0 or 1")
            continue
        if not _integer(decision["bays"]) or decision["bays"] < 0:
            errors.append(f"{label}.bays: expected a nonnegative integer")
            continue
        build, bays = int(decision["build"]), int(decision["bays"])
        if not build <= bays <= sites[site_id]["max_bays"] * build:
            errors.append(f"{label}: build <= bays <= max_bays * build violated")
        decisions[site_id] = {"build": build, "bays": bays}
    missing_sites = sites.keys() - decisions.keys()
    if missing_sites:
        errors.append(f"result.station_decisions: missing sites {sorted(missing_sites)}")
    selected = result["selected_plan_ids"]
    if len(selected) != len(set(selected)):
        errors.append("result.selected_plan_ids: duplicate plan selections")
    selected_jobs = Counter()
    for plan_id in selected:
        if plan_id not in plans_by_id:
            errors.append(f"result.selected_plan_ids: unknown plan_id {plan_id!r}")
        else:
            selected_jobs[plans_by_id[plan_id]["job_id"]] += 1
    for job_id in jobs:
        if selected_jobs[job_id] != 1:
            errors.append(f"job {job_id!r}: expected exactly one selected plan, found {selected_jobs[job_id]}")
    if errors:
        return finish()

    occupancy = Counter()
    recomputed = []
    for plan_id in selected:
        plan = plans_by_id[plan_id]
        checked = _walk_plan(data, plan, jobs[plan["job_id"]], nodes, edges, sites, errors)
        if checked is not None:
            occupancy.update(checked.pop("occupancy"))
            recomputed.append(checked)
    metrics["selected_jobs_recomputed"] = len(recomputed)
    metrics["plans_recomputed"] = recomputed
    if len(recomputed) != len(selected):
        return finish()

    maximum_occupancy = defaultdict(int)
    for (site_id, slot), occupied in sorted(occupancy.items()):
        site, decision = sites[site_id], decisions[site_id]
        maximum_occupancy[site_id] = max(maximum_occupancy[site_id], occupied)
        if decision["build"] != 1:
            errors.append(f"site {site_id!r}, slot {slot}: charging uses an unbuilt station")
        if occupied > decision["bays"]:
            errors.append(f"site {site_id!r}, slot {slot}: occupied bays {occupied} exceed installed bays {decision['bays']}")
        if occupied * site["charger_kw"] > site["site_power_kw"] * decision["build"] + _TOL:
            errors.append(f"site {site_id!r}, slot {slot}: charging power exceeds site_power_kw")
    settings = data["settings"]
    investment = settings["annualization_factor"] * sum(
        site["fixed_cost_cny"] * decisions[site_id]["build"]
        + site["bay_cost_cny"] * decisions[site_id]["bays"]
        for site_id, site in sites.items()
    )
    operation = settings["operating_days_per_year"] * sum(p["operating_cost_cny"] for p in recomputed)
    objective = investment + operation
    for key, value in (
        ("investment_cny_per_year", investment),
        ("operation_cny_per_year", operation),
        ("objective_cny_per_year", objective),
    ):
        _close(result[key], value, f"result.{key}", errors)
        metrics[key] = value
    metrics["maximum_occupied_bays_by_site"] = {
        site_id: maximum_occupancy[site_id] for site_id in sites
    }
    return finish()
