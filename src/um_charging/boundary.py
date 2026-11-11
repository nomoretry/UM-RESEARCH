"""Controlled existing-power and plug-window changes on an unchanged physical chain."""
from __future__ import annotations

import copy

from .model import validate_input
from .timegrid import POLICIES, physical_event_ledger, refine_physical_cycle

POWERS = (50, 75, 100, 125, 150)
WINDOWS = (0, 15, 30, 45, 60)
SCOPES = ("port_only", "two_sites")


def _coordinates(power, window, scope, policy):
    if (type(power) is not int or power not in POWERS or type(window) is not int or window not in WINDOWS
            or scope not in SCOPES or policy not in POLICIES):
        raise ValueError("Use the exact declared power/window/scope/policy coordinates")


def _base(base):
    validate_input(base)
    if (base["schema_version"] != "capacity-investment-v1" or base["slot_hours"] != 1
            or base["slot_count"] != 4 or [s["id"] for s in base["sites"]] != ["PORT", "WAREHOUSE"]):
        raise ValueError("This study requires the existing explicit four-hour PORT/WAREHOUSE investment chain")
    expected = [("PORT", "WAREHOUSE", "drive", False), ("WAREHOUSE", "WAREHOUSE", "dwell", True),
                ("WAREHOUSE", "PORT", "drive", False), ("PORT", "PORT", "dwell", True)]
    for v in base["vehicles"]:
        if [(s["from"], s["to"], s["activity"], s["plug_allowed"]) for s in v["timeline"]] != expected:
            raise ValueError("Physical events must match the declared original task chain")


def build_boundary_case(base, port_available_power_kw, warehouse_window_minutes, charging_scope, connector_policy):
    _base(base)
    _coordinates(port_available_power_kw, warehouse_window_minutes, charging_scope, connector_policy)
    data = refine_physical_cycle(base, 15, connector_policy)
    data["instance_id"] = f"boundary_{connector_policy}_p{port_available_power_kw}_w{warehouse_window_minutes}_{charging_scope}"
    data["sites"][0]["available_power_kw"] = [port_available_power_kw] * 16
    data["sites"][1]["active"] = charging_scope == "two_sites"
    for vehicle in data["vehicles"]:
        for t, slot in enumerate(vehicle["timeline"]):
            if slot["activity"] == "dwell" and slot["from"] == "WAREHOUSE":
                allowed = 60 <= 15 * t and 15 * (t + 1) <= 60 + warehouse_window_minutes
                slot["plug_allowed"] = allowed
                vehicle["charging_site"][t] = "WAREHOUSE" if allowed else None
    data["provenance"]["assumed"].extend([
        f"PORT existing available power is {port_available_power_kw} kW; paid additional capacity options are unchanged.",
        f"WAREHOUSE physical dwell remains [60,120) minutes; plug eligibility is [60,{60 + warehouse_window_minutes}) minutes.",
        f"Charging scope is {charging_scope}; inactive WAREHOUSE eligibility cannot be used. Existing facilities are sunk, with no station-opening charge.",
    ])
    validate_input(data)
    return data


def transport_ledger(data):
    """Collapse physical stops without allowing qualification changes to hide a moved event."""
    physical = copy.deepcopy(data)
    for vehicle in physical["vehicles"]:
        vehicle["charging_site"] = [None] * physical["slot_count"]
        for slot in vehicle["timeline"]:
            slot["plug_allowed"] = False
    return physical_event_ledger(physical)


def audit_boundary_case(base, data, port_available_power_kw, warehouse_window_minutes, charging_scope, connector_policy):
    """Independent task/eligibility/equipment audit; does not call the input generator."""
    _base(base)
    validate_input(data)
    _coordinates(port_available_power_kw, warehouse_window_minutes, charging_scope, connector_policy)
    errors, checks = [], 0
    def check(condition, label, detail):
        nonlocal checks
        checks += 1
        if not condition:
            errors.append({"constraint": label, "detail": detail})
    check(data["schema_version"] == "capacity-investment-v2" and data["slot_count"] == 16 and data["slot_hours"] == .25,
          "B01_TASK", "Exact fifteen-minute four-hour grid")
    check(data["connector_policy"] == connector_policy, "B02_ELIGIBILITY", "Declared connector policy")
    events = transport_ledger(data)
    check(events == transport_ledger(base), "B01_TASK", "Vehicle assignment, physical events, arrivals/departures and journey energy")
    check(len(data["vehicles"]) == len(base["vehicles"]), "B01_TASK", "Vehicle count")
    eligible_minutes = {}
    for before, after in zip(base["vehicles"], data["vehicles"]):
        for field in set(before) - {"timeline", "charging_site", "drive_energy_kwh"}:
            check(before[field] == after[field], "B03_RESOURCES", f"{before['id']}/{field}")
        totals = {"PORT": 0, "WAREHOUSE": 0}
        for t, slot in enumerate(after["timeline"]):
            original_slot = int(t * data["slot_hours"] / base["slot_hours"])
            if original_slot >= base["slot_count"]:
                check(False, "B01_TASK", "Slot outside original physical horizon")
                continue
            expected_site = before["charging_site"][original_slot]
            if expected_site == "WAREHOUSE" and not (t * 15 >= 60 and (t + 1) * 15 <= 60 + warehouse_window_minutes):
                expected_site = None
            check(after["charging_site"][t] == expected_site and slot["plug_allowed"] == (expected_site is not None),
                  "B02_ELIGIBILITY", f"{before['id']}/slot{t}: exact permitted subwindow")
            check(after["drive_energy_kwh"][t] == before["drive_energy_kwh"][original_slot] / 4,
                  "B01_TASK", f"{before['id']}/slot{t}: unchanged driving energy interpolation")
            if after["charging_site"][t] is not None:
                totals[after["charging_site"][t]] += 15
        eligible_minutes[after["id"]] = totals
    check(len(data["sites"]) == len(base["sites"]), "B03_RESOURCES", "Real facility count")
    for before, after in zip(base["sites"], data["sites"]):
        for field in set(before) - {"available_power_kw", "price_per_kwh", "active"}:
            check(before[field] == after[field], "B03_RESOURCES", f"{before['id']}/{field}: equipment and paid investment options")
        expected_active = charging_scope == "two_sites" if before["id"] == "WAREHOUSE" else before["active"]
        check(after["active"] == expected_active, "B03_RESOURCES", f"{before['id']}/active")
        for t in range(data["slot_count"]):
            original_slot = min(int(t * data["slot_hours"]), base["slot_count"] - 1)
            expected_power = port_available_power_kw if before["id"] == "PORT" else before["available_power_kw"][original_slot]
            check(after["available_power_kw"][t] == expected_power, "B03_RESOURCES", f"{before['id']}/slot{t}: existing power only")
            check(after["price_per_kwh"][t] == before["price_per_kwh"][original_slot], "B04_COSTS", f"{before['id']}/slot{t}: electricity price")
    for field in ("cost_basis", "representative_weight", "units"):
        check(data[field] == base[field], "B04_COSTS", field)
    return {"passed": not errors, "checks": checks, "errors": errors, "physical_transport_events": events,
            "eligible_minutes_per_vehicle": eligible_minutes,
            "note": "Eligibility can change only in the declared warehouse subwindow; physical dwell and transport remain unchanged. Energy/occupancy/power/cost solutions require the separate C01-C08 checker."}


def boundary_cases(base):
    for policy in POLICIES:
        for power in POWERS:
            for window in WINDOWS:
                for scope in SCOPES:
                    coordinates = {"port_available_power_kw": power, "warehouse_window_minutes": window,
                                   "charging_scope": scope, "connector_policy": policy}
                    yield coordinates, build_boundary_case(base, **coordinates)
