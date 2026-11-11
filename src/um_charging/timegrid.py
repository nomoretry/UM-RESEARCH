"""Exact subdivision of a declared physical cycle; no new stops or charging windows."""
from __future__ import annotations
import copy
import math

from .model import validate_input

POLICIES = ("slot_boundary_switching", "fixed_dwell_connection")
MINUTES = (60, 30, 15)


def refine_physical_cycle(base, slot_minutes, connector_policy):
    """Split each one-hour physical event. Transit labels are not facilities."""
    validate_input(base)
    if base["schema_version"] != "capacity-investment-v1" or base["slot_hours"] != 1:
        raise ValueError("Refinement starts from the explicit one-hour capacity-investment-v1 cycle")
    if type(slot_minutes) is not int or slot_minutes not in MINUTES or connector_policy not in POLICIES:
        raise ValueError("Use an explicit supported time step and connector policy")
    factor = 60 // slot_minutes
    data = copy.deepcopy(base)
    data.update(schema_version="capacity-investment-v2", slot_hours=slot_minutes / 60,
                slot_count=base["slot_count"] * factor, transit_locations=[], connector_policy=connector_policy)
    old_assumption = "All slots are complete one-hour intervals; one occupied connector cannot serve multiple vehicles within a slot."
    data["provenance"]["assumed"] = [item for item in data["provenance"]["assumed"] if item != old_assumption]
    data["provenance"]["assumed"].extend([
        f"Original physical events last one hour; model slots last {slot_minutes} minutes, without extending any stop or plug window.",
        "Driving energy is distributed uniformly within each original journey; no charging is possible in transit.",
        ("Connections may be reassigned at model slot boundaries; unplugging, moving and reconnecting take zero time and energy."
         if connector_policy == "slot_boundary_switching" else
         "A chosen connection occupies its interface for the whole continuous plug-eligible dwell, including slots with zero power."),
    ])
    for site in data["sites"]:
        for field in ("available_power_kw", "price_per_kwh"):
            site[field] = [value for value in site[field] for _ in range(factor)]
    for v, (original, vehicle) in enumerate(zip(base["vehicles"], data["vehicles"])):
        energy, eligibility, timeline = [], [], []
        for t, slot in enumerate(original["timeline"]):
            if slot["activity"] == "drive":
                internal = [f"transit_vehicle_{v}_event_{t}_boundary_{b}_of_{factor}" for b in range(1, factor)]
                if any(label in [site["id"] for site in data["sites"]] for label in internal):
                    raise ValueError("Generated transit identifier collides with a facility")
                data["transit_locations"].extend(internal)
                boundaries = [slot["from"], *internal, slot["to"]]
                for b in range(factor):
                    timeline.append({"from": boundaries[b], "to": boundaries[b + 1], "activity": "drive", "plug_allowed": False})
                    energy.append(original["drive_energy_kwh"][t] / factor)
                    eligibility.append(None)
            else:
                timeline.extend(copy.deepcopy(slot) for _ in range(factor))
                energy.extend([0.0] * factor)
                eligibility.extend([original["charging_site"][t]] * factor)
        vehicle["timeline"], vehicle["drive_energy_kwh"], vehicle["charging_site"] = timeline, energy, eligibility
    validate_input(data)
    return data


def physical_event_ledger(data):
    """Independently collapse in-transit pieces and continuous dwell into events."""
    validate_input(data)
    sites = {site["id"] for site in data["sites"]}
    dt = data["slot_hours"] * 60
    ledger = {}
    for vehicle in data["vehicles"]:
        events, t = [], 0
        while t < data["slot_count"]:
            first = vehicle["timeline"][t]
            start = t
            if first["activity"] == "drive":
                if first["from"] not in sites:
                    raise ValueError("Physical journey must depart from a real site")
                energy = 0.0
                while True:
                    part = vehicle["timeline"][t]
                    if part["activity"] != "drive":
                        raise ValueError("A stop was inserted inside a physical journey")
                    energy += vehicle["drive_energy_kwh"][t]
                    t += 1
                    if part["to"] in sites:
                        break
                    if t == data["slot_count"]:
                        raise ValueError("Unfinished physical journey")
                events.append({"start_minute": start * dt, "end_minute": t * dt,
                               "from": first["from"], "to": part["to"], "activity": "drive",
                               "drive_energy_kwh": energy, "charging_site": None, "plug_allowed": False})
            else:
                eligibility = vehicle["charging_site"][t]
                while t < data["slot_count"]:
                    part = vehicle["timeline"][t]
                    if (part["activity"] != "dwell" or part["from"] != first["from"]
                            or part["plug_allowed"] != first["plug_allowed"] or vehicle["charging_site"][t] != eligibility):
                        break
                    t += 1
                events.append({"start_minute": start * dt, "end_minute": t * dt,
                               "from": first["from"], "to": first["to"], "activity": "dwell",
                               "drive_energy_kwh": 0.0, "charging_site": eligibility, "plug_allowed": first["plug_allowed"]})
        ledger[vehicle["id"]] = events
    return ledger


def audit_physical_equivalence(base, refined):
    """Check events, total demand, eligibility durations, equipment and all costs."""
    original_events, refined_events = physical_event_ledger(base), physical_event_ledger(refined)
    errors = []
    if original_events != refined_events:
        errors.append("Physical departure/arrival/dwell/energy/eligibility events changed")
    if base["slot_count"] * base["slot_hours"] != refined["slot_count"] * refined["slot_hours"]:
        errors.append("Modeled duration changed")
    for field in ("units", "representative_weight", "cost_basis"):
        if base[field] != refined[field]:
            errors.append(f"Cost/unit convention changed: {field}")
    if len(base["vehicles"]) != len(refined["vehicles"]) or len(base["sites"]) != len(refined["sites"]):
        errors.append("Vehicle or real facility count changed")
    for before, after in zip(base["vehicles"], refined["vehicles"]):
        for field in set(before) - {"timeline", "drive_energy_kwh", "charging_site"}:
            if before[field] != after[field]:
                errors.append(f"Vehicle parameter changed: {before['id']}/{field}")
        if not math.isclose(sum(before["drive_energy_kwh"]), sum(after["drive_energy_kwh"]), abs_tol=1e-9, rel_tol=0):
            errors.append(f"Demand changed: {before['id']}")
    for before, after in zip(base["sites"], refined["sites"]):
        for field in set(before) - {"available_power_kw", "price_per_kwh"}:
            if before[field] != after[field]:
                errors.append(f"Facility or investment parameter changed: {before['id']}/{field}")
        for t in range(refined["slot_count"]):
            original_slot = math.floor((t * refined["slot_hours"]) / base["slot_hours"])
            for field in ("available_power_kw", "price_per_kwh"):
                if after[field][t] != before[field][original_slot]:
                    errors.append(f"Time-dependent facility parameter changed: {before['id']}/{field}/{t}")
    return {"passed": not errors, "errors": errors, "physical_events": refined_events,
            "total_duration_hours": refined["slot_count"] * refined["slot_hours"],
            "vehicle_count": len(refined["vehicles"]), "real_site_count": len(refined["sites"]),
            "energy_total_kwh": sum(sum(v["drive_energy_kwh"]) for v in refined["vehicles"]),
            "method": "Collapse journeys at real-site arrivals and dwell at actual eligibility boundaries, then compare with base events; independently check static equipment, costs and time profiles."}


def schedule_rows(data, result):
    """Human-readable selected optimal schedule; occupancy is not connector identity."""
    if not result["has_solution"]:
        return []
    rows = []
    s = result["solution"]
    for v, vehicle in enumerate(data["vehicles"]):
        for t, slot in enumerate(vehicle["timeline"]):
            rows.append({"vehicle": vehicle["id"], "start_minute": t * data["slot_hours"] * 60,
                         "end_minute": (t + 1) * data["slot_hours"] * 60,
                         "activity": slot["activity"], "from": slot["from"], "to": slot["to"],
                         "charging_site": vehicle["charging_site"][t], "drive_energy_kwh": vehicle["drive_energy_kwh"][t],
                         "occupancy": {site["id"]: s["occupancy"][v][j][t] for j, site in enumerate(data["sites"])},
                         "power_kw": {site["id"]: s["power_kw"][v][j][t] for j, site in enumerate(data["sites"])},
                         "energy_start_kwh": s["energy_kwh"][v][t], "energy_end_kwh": s["energy_kwh"][v][t + 1]})
    return rows

