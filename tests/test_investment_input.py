"""Input contract and small analytic investment cases; no production fixture reuse."""
import copy

import pytest

from um_charging.model import solve, validate_input


@pytest.fixture
def investment_input():
    def site(site_id, active):
        return {"id": site_id, "active": active, "interfaces": 0,
                "available_power_kw": [0.0] * 4, "price_per_kwh": [1.0] * 4,
                "max_new_interfaces": 2, "interface_cost": 10.0,
                "upgrade_options": [{"id": "small", "additional_power_kw": 30.0, "cost": 5.0},
                                    {"id": "large", "additional_power_kw": 60.0, "cost": 100.0}]}
    return {
        "schema_version": "capacity-investment-v1", "instance_id": "single_truck_investment_test",
        "description": "One fixed closed trip with only return charging; all costs synthetic per cycle.",
        "provenance": {"observed": [], "derived": [], "assumed": [], "simulated": ["All inputs"]},
        "units": {"energy": "kWh", "power": "kW", "time": "hour",
                  "price": "synthetic_currency/kWh", "objective": "synthetic_currency"},
        "slot_hours": 1.0, "slot_count": 4, "representative_weight": 1.0,
        "cost_basis": "synthetic_cycle_equivalent",
        "sites": [site("P", True), site("W", False)],
        "vehicles": [{"id": "T1", "energy_min_kwh": 20.0, "energy_max_kwh": 100.0,
                      "initial_energy_kwh": 100.0, "efficiency": 1.0,
                      "power_limit_kw": {"P": 100.0, "W": 100.0},
                      "drive_energy_kwh": [30.0, 0.0, 30.0, 0.0],
                      "charging_site": [None, "W", None, "P"],
                      "timeline": [{"from": "P", "to": "W", "activity": "drive", "plug_allowed": False},
                                   {"from": "W", "to": "W", "activity": "dwell", "plug_allowed": True},
                                   {"from": "W", "to": "P", "activity": "drive", "plug_allowed": False},
                                   {"from": "P", "to": "P", "activity": "dwell", "plug_allowed": True}]}],
    }


def test_investment_has_analytic_objective_and_preserves_input(investment_input):
    original = copy.deepcopy(investment_input)
    result = solve(investment_input)
    assert investment_input == original
    assert result["status"] == "optimal"
    # One interface (10), the only sufficient upgrade (100), and 60 kWh (60).
    assert result["objective"] == pytest.approx(170.0)
    assert result["dual_bound"] == pytest.approx(170.0)
    assert result["mip_gap"] == pytest.approx(0.0)
    assert result["solution"]["new_interfaces"] == pytest.approx([1.0, 0.0])
    assert result["solution"]["upgrade_selected"][0] == pytest.approx([0.0, 1.0])
    assert result["solution"]["upgrade_selected"][1] == pytest.approx([0.0, 0.0])
    assert result["solution"]["energy_kwh"][0] == pytest.approx([100.0, 70.0, 70.0, 40.0, 100.0])


def test_upgrade_options_are_alternatives_not_additive(investment_input):
    # Neither 35 nor 25 supplies the required 60 kW; choosing both is forbidden.
    options = investment_input["sites"][0]["upgrade_options"]
    options[0]["additional_power_kw"] = 35.0
    options[1]["additional_power_kw"] = 25.0
    assert solve(investment_input)["status"] == "infeasible"


def test_no_new_interfaces_allowed_remains_infeasible(investment_input):
    investment_input["sites"][0]["max_new_interfaces"] = 0
    assert solve(investment_input)["status"] == "infeasible"


def test_empty_upgrades_allowed_when_existing_capacity_suffices(investment_input):
    for site in investment_input["sites"]:
        site["upgrade_options"] = []
    investment_input["sites"][0]["available_power_kw"] = [60.0] * 4
    result = solve(investment_input)
    assert result["status"] == "optimal"
    assert result["objective"] == pytest.approx(70.0)
    assert result["solution"]["upgrade_selected"] == [[], []]


@pytest.mark.parametrize("mutation", [
    "wrong_schema_case", "unknown_top_key", "unknown_site_key", "unknown_option_key",
    "fractional_new_interfaces", "boolean_new_interfaces", "negative_interface_cost",
    "nonfinite_interface_cost", "nonfinite_upgrade_power", "zero_upgrade_power",
    "negative_upgrade_cost", "duplicate_option_id", "empty_option_id", "wrong_cost_basis",
    "annual_weight", "missing_timeline_slot", "wrong_endpoint_case", "unknown_timeline_key",
    "nonboolean_plug", "drive_with_same_endpoints", "drive_without_energy", "drive_with_plug",
    "dwell_with_energy", "dwell_with_different_endpoints", "dwell_wrong_charging_site",
    "ineligible_dwell_with_charging", "discontinuous_route", "nonclosed_route", "wrong_activity_case",
])
def test_rejects_invalid_investment_input(investment_input, mutation):
    data = investment_input
    site, vehicle = data["sites"][0], data["vehicles"][0]
    option, timeline = site["upgrade_options"][0], vehicle["timeline"]
    if mutation == "wrong_schema_case": data["schema_version"] = "Capacity-investment-v1"
    elif mutation == "unknown_top_key": data["cost_Basis"] = data["cost_basis"]
    elif mutation == "unknown_site_key": site["max_New_interfaces"] = 2
    elif mutation == "unknown_option_key": option["capacity"] = 30
    elif mutation == "fractional_new_interfaces": site["max_new_interfaces"] = 1.5
    elif mutation == "boolean_new_interfaces": site["max_new_interfaces"] = True
    elif mutation == "negative_interface_cost": site["interface_cost"] = -1.0
    elif mutation == "nonfinite_interface_cost": site["interface_cost"] = float("nan")
    elif mutation == "nonfinite_upgrade_power": option["additional_power_kw"] = float("inf")
    elif mutation == "zero_upgrade_power": option["additional_power_kw"] = 0.0
    elif mutation == "negative_upgrade_cost": option["cost"] = -1.0
    elif mutation == "duplicate_option_id": option["id"] = site["upgrade_options"][1]["id"]
    elif mutation == "empty_option_id": option["id"] = ""
    elif mutation == "wrong_cost_basis": data["cost_basis"] = "annual"
    elif mutation == "annual_weight": data["representative_weight"] = 365
    elif mutation == "missing_timeline_slot": timeline.pop()
    elif mutation == "wrong_endpoint_case": timeline[0]["from"] = "p"
    elif mutation == "unknown_timeline_key": timeline[0]["duration"] = 1
    elif mutation == "nonboolean_plug": timeline[1]["plug_allowed"] = 1
    elif mutation == "drive_with_same_endpoints": timeline[0]["to"] = "P"
    elif mutation == "drive_without_energy": vehicle["drive_energy_kwh"][0] = 0.0
    elif mutation == "drive_with_plug": timeline[0]["plug_allowed"] = True
    elif mutation == "dwell_with_energy":
        vehicle["drive_energy_kwh"][1] = 1.0
        vehicle["charging_site"][1] = None
        timeline[1]["plug_allowed"] = False
    elif mutation == "dwell_with_different_endpoints": timeline[1]["to"] = "P"
    elif mutation == "dwell_wrong_charging_site": vehicle["charging_site"][1] = "P"
    elif mutation == "ineligible_dwell_with_charging": timeline[1]["plug_allowed"] = False
    elif mutation == "discontinuous_route":
        timeline[1]["from"] = timeline[1]["to"] = "P"
        vehicle["charging_site"][1] = "P"
    elif mutation == "nonclosed_route":
        timeline[0] = {"from": "W", "to": "W", "activity": "dwell", "plug_allowed": False}
        vehicle["drive_energy_kwh"][0] = 0.0
    elif mutation == "wrong_activity_case": timeline[0]["activity"] = "Drive"
    with pytest.raises(ValueError):
        validate_input(data)


def test_fixed_version_rejects_investment_keys(investment_input):
    investment_input["schema_version"] = "fixed-facility-v1"
    with pytest.raises(ValueError, match="exact keys"):
        validate_input(investment_input)
