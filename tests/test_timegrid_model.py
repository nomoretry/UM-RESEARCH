"""Explicit transit boundaries and analytic connection-policy checks for v2."""
import copy

import pytest

from um_charging.model import solve, validate_input
from um_charging.validation import check_solution


@pytest.fixture
def timegrid_input():
    # Both trucks physically traverse P -> OUT -> W -> BACK -> P. Their only
    # charging opportunity is the same final hour at P, represented by 2 slots.
    # Each needs 20 kWh: one 40 kW interface can serve them sequentially in that
    # hour, but holding each connection for the full dwell requires 2 interfaces.
    timeline = [
        {"from": "P", "to": "OUT", "activity": "drive", "plug_allowed": False},
        {"from": "OUT", "to": "W", "activity": "drive", "plug_allowed": False},
        {"from": "W", "to": "W", "activity": "dwell", "plug_allowed": False},
        {"from": "W", "to": "W", "activity": "dwell", "plug_allowed": False},
        {"from": "W", "to": "BACK", "activity": "drive", "plug_allowed": False},
        {"from": "BACK", "to": "P", "activity": "drive", "plug_allowed": False},
        {"from": "P", "to": "P", "activity": "dwell", "plug_allowed": True},
        {"from": "P", "to": "P", "activity": "dwell", "plug_allowed": True},
    ]
    return {
        "schema_version": "capacity-investment-v2", "instance_id": "two_truck_connection_test",
        "description": "Synthetic analytic test of time boundaries and connection occupancy.",
        "provenance": {"observed": [], "derived": [], "assumed": [], "simulated": ["All inputs"]},
        "units": {"energy": "kWh", "power": "kW", "time": "hour",
                  "price": "synthetic_currency/kWh", "objective": "synthetic_currency"},
        "slot_hours": 0.5, "slot_count": 8, "representative_weight": 1.0,
        "cost_basis": "synthetic_cycle_equivalent",
        "transit_locations": ["OUT", "BACK"], "connector_policy": "slot_boundary_switching",
        "sites": [
            {"id": "P", "active": True, "interfaces": 1, "available_power_kw": [80.0] * 8,
             "price_per_kwh": [1.0] * 8, "max_new_interfaces": 1, "interface_cost": 10.0,
             "upgrade_options": []},
            {"id": "W", "active": False, "interfaces": 0, "available_power_kw": [0.0] * 8,
             "price_per_kwh": [1.0] * 8, "max_new_interfaces": 0, "interface_cost": 10.0,
             "upgrade_options": []},
        ],
        "vehicles": [
            {"id": vehicle_id, "energy_min_kwh": 0.0, "energy_max_kwh": 40.0,
             "initial_energy_kwh": 40.0, "efficiency": 1.0,
             "power_limit_kw": {"P": 40.0, "W": 40.0},
             "drive_energy_kwh": [5.0, 5.0, 0.0, 0.0, 5.0, 5.0, 0.0, 0.0],
             "charging_site": [None, None, None, None, None, None, "P", "P"],
             "timeline": copy.deepcopy(timeline)}
            for vehicle_id in ("T1", "T2")
        ],
    }


def coarse_investment_v1(data):
    """An explicit hourly version of this test fixture, not a generic converter."""
    coarse = copy.deepcopy(data)
    coarse["schema_version"] = "capacity-investment-v1"
    del coarse["transit_locations"]
    del coarse["connector_policy"]
    coarse["slot_hours"], coarse["slot_count"] = 1.0, 4
    for site in coarse["sites"]:
        site["available_power_kw"] = site["available_power_kw"][::2]
        site["price_per_kwh"] = site["price_per_kwh"][::2]
    for vehicle in coarse["vehicles"]:
        vehicle["drive_energy_kwh"] = [10.0, 0.0, 10.0, 0.0]
        vehicle["charging_site"] = [None, None, None, "P"]
        vehicle["timeline"] = [
            {"from": "P", "to": "W", "activity": "drive", "plug_allowed": False},
            {"from": "W", "to": "W", "activity": "dwell", "plug_allowed": False},
            {"from": "W", "to": "P", "activity": "drive", "plug_allowed": False},
            {"from": "P", "to": "P", "activity": "dwell", "plug_allowed": True},
        ]
    return coarse


@pytest.mark.parametrize("policy,added,cost,locked_rows", [
    ("slot_boundary_switching", 0.0, 40.0, 0),
    ("fixed_dwell_connection", 1.0, 50.0, 4),
])
def test_analytic_connection_policy(timegrid_input, policy, added, cost, locked_rows):
    timegrid_input["connector_policy"] = policy
    original = copy.deepcopy(timegrid_input)
    result = solve(timegrid_input)
    assert timegrid_input == original
    assert result["status"] == "optimal"
    assert result["objective"] == pytest.approx(cost)
    assert result["dual_bound"] == pytest.approx(cost)
    assert result["mip_gap"] == pytest.approx(0.0)
    assert result["solution"]["new_interfaces"] == pytest.approx([added, 0.0])
    assert result["constraint_counts"]["C08"] == locked_rows
    checked = check_solution(timegrid_input, result)
    assert checked["passed"], checked
    assert checked["max_violation_by_constraint"]["C08"] == pytest.approx(0.0)
    assert checked["grid_energy_kwh"] == pytest.approx(40.0)
    assert checked["operating_cost"] == pytest.approx(40.0)
    assert checked["investment_cost"] == pytest.approx(cost - 40.0)


def test_independent_checker_rejects_mid_dwell_reassignment(timegrid_input):
    switched_result = solve(timegrid_input)
    timegrid_input["connector_policy"] = "fixed_dwell_connection"
    checked = check_solution(timegrid_input, switched_result)
    assert not checked["passed"]
    assert checked["max_violation_by_constraint"]["C08"] == pytest.approx(1.0)
    assert {error["constraint"] for error in checked["errors"]} == {"C08"}


def test_held_connection_allows_zero_and_variable_power(timegrid_input):
    timegrid_input["connector_policy"] = "fixed_dwell_connection"
    result = solve(timegrid_input)
    for v, final_powers in enumerate(([40.0, 0.0], [0.0, 40.0])):
        result["solution"]["occupancy"][v][0][6:] = [1.0, 1.0]
        result["solution"]["power_kw"][v][0][6:] = final_powers
    result["solution"]["energy_kwh"][0] = [40, 35, 30, 30, 30, 25, 20, 40, 40]
    result["solution"]["energy_kwh"][1] = [40, 35, 30, 30, 30, 25, 20, 20, 40]
    checked = check_solution(timegrid_input, result)
    assert checked["passed"], checked


def test_no_new_interface_leaves_locked_case_infeasible(timegrid_input):
    timegrid_input["sites"][0]["max_new_interfaces"] = 0
    assert solve(timegrid_input)["status"] == "optimal"
    timegrid_input["connector_policy"] = "fixed_dwell_connection"
    result = solve(timegrid_input)
    assert result["status"] == "infeasible"
    assert check_solution(timegrid_input, result)["applicable"] is False


def test_null_eligibility_ends_connection_window(timegrid_input):
    timegrid_input["connector_policy"] = "fixed_dwell_connection"
    for vehicle in timegrid_input["vehicles"]:
        vehicle["charging_site"][6] = None
        vehicle["timeline"][6]["plug_allowed"] = False
    result = solve(timegrid_input)
    assert result["status"] == "optimal"
    assert result["constraint_counts"]["C08"] == 0
    assert check_solution(timegrid_input, result)["passed"]


@pytest.mark.parametrize("policy", ["slot_boundary_switching", "fixed_dwell_connection"])
def test_empty_transit_v2_matches_v1_without_multislot_dwell(timegrid_input, policy):
    v1 = coarse_investment_v1(timegrid_input)
    v1_result = solve(v1)
    assert "C08" not in v1_result["constraint_counts"]
    assert "C08" not in check_solution(v1, v1_result)["max_violation_by_constraint"]
    v2 = copy.deepcopy(v1)
    v2.update(schema_version="capacity-investment-v2", transit_locations=[], connector_policy=policy)
    v2_result = solve(v2)
    assert v1_result["status"] == v2_result["status"] == "optimal"
    assert v1_result["objective"] == v2_result["objective"] == pytest.approx(50.0)
    assert v1_result["solution"]["new_interfaces"] == v2_result["solution"]["new_interfaces"]
    assert v2_result["constraint_counts"]["C08"] == 0
    assert check_solution(v2, v2_result)["passed"]


@pytest.mark.parametrize("path,value", [
    (("transit_locations",), "OUT"),
    (("transit_locations",), ["OUT", "OUT", "BACK"]),
    (("transit_locations",), ["OUT", "BACK", ""]),
    (("transit_locations",), ["OUT", "BACK", " "]),
    (("transit_locations",), ["OUT", "BACK", 1]),
    (("transit_locations",), ["OUT", "BACK", "P"]),
    (("transit_locations",), ["OUT", "BACK", "UNUSED"]),
    (("transit_locations",), ["OUT"]),
    (("connector_policy",), "Fixed_Dwell_Connection"),
    (("connector_policy",), None),
    (("vehicles", 0, "timeline", 0, "to"), "UNKNOWN"),
    (("vehicles", 0, "timeline", 1, "from"), "P"),
    (("vehicles", 0, "charging_site", 0), "OUT"),
    (("representative_weight",), 2),
])
def test_rejects_invalid_v2_contract(timegrid_input, path, value):
    target = timegrid_input
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_input(timegrid_input)


def test_transit_cannot_be_a_dwell_even_without_plug_permission(timegrid_input):
    vehicle = timegrid_input["vehicles"][0]
    vehicle["timeline"][1] = {"from": "OUT", "to": "OUT", "activity": "dwell", "plug_allowed": False}
    vehicle["drive_energy_kwh"][1] = 0.0
    with pytest.raises(ValueError, match="dwell requires an actual site"):
        validate_input(timegrid_input)


def test_closed_cycle_cannot_start_in_transit(timegrid_input):
    vehicle = timegrid_input["vehicles"][0]
    for key in ("timeline", "charging_site", "drive_energy_kwh"):
        vehicle[key] = vehicle[key][1:] + vehicle[key][:1]
    with pytest.raises(ValueError, match="start and end at an actual site"):
        validate_input(timegrid_input)


def test_v1_does_not_silently_accept_v2_fields(timegrid_input):
    timegrid_input["schema_version"] = "capacity-investment-v1"
    with pytest.raises(ValueError, match="exact keys"):
        validate_input(timegrid_input)


@pytest.mark.parametrize("field", ["transit_locations", "connector_policy"])
def test_v2_requires_both_explicit_new_fields(timegrid_input, field):
    del timegrid_input[field]
    with pytest.raises(ValueError, match="exact keys"):
        validate_input(timegrid_input)
