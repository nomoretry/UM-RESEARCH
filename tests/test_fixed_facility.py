"""Analytic examples and corrupted-primal tests, not copies of matrix construction."""
import copy
import json
from pathlib import Path

import pytest

from um_charging.model import make_scenarios, solve, validate_input
from um_charging.validation import check_solution
from um_charging.__main__ import reject_duplicate_keys


@pytest.fixture
def base():
    return json.loads((Path(__file__).resolve().parents[1] / "configs" / "minimal_three_trucks.json").read_text(encoding="utf-8"))


@pytest.fixture
def optimal(base):
    return solve(base)


def test_hand_calculated_two_cycle_energy_and_cost(base, optimal):
    assert optimal["status"] == "optimal"
    assert optimal["objective"] == pytest.approx(300.0)
    assert optimal["dual_bound"] == pytest.approx(300.0)
    assert optimal["mip_gap"] == pytest.approx(0.0)
    check = check_solution(base, optimal)
    assert check["passed"], check
    assert check["grid_energy_kwh"] == pytest.approx(180.0 / 0.9)
    assert check["site_peak_kw"] == pytest.approx({"A": 60.0 / 0.9, "B": 30.0 / 0.9})
    for energy in check["energy_kwh_recomputed"]:
        assert energy == pytest.approx([100.0, 70.0, 100.0, 70.0, 100.0])


@pytest.mark.parametrize("name", ["interface_bottleneck", "power_bottleneck", "window_bottleneck"])
def test_analytic_infeasible_cases(base, name):
    data = make_scenarios(base)[name]
    result = solve(data)
    assert result["status"] == "infeasible"
    assert not result["has_solution"]
    assert result["objective"] is None
    assert check_solution(data, result)["applicable"] is False


def test_more_grid_capacity_has_zero_cost_benefit(base, optimal):
    data = make_scenarios(base)["higher_power_no_benefit"]
    result = solve(data)
    assert result["status"] == "optimal"
    assert result["objective"] == pytest.approx(optimal["objective"])
    assert check_solution(data, result)["passed"]


def test_zero_demand_requires_no_grid_energy(base):
    data = make_scenarios(base)["zero_demand"]
    result = solve(data)
    checked = check_solution(data, result)
    assert result["status"] == "optimal"
    assert checked["passed"]
    assert result["objective"] == pytest.approx(0.0)
    assert checked["grid_energy_kwh"] == pytest.approx(0.0)


def test_energy_is_not_reset_between_cycles(base):
    # Second cycle cannot borrow a new full battery: every vehicle ends 30 kWh short.
    for vehicle in base["vehicles"]:
        vehicle["charging_site"][3] = None
    assert solve(base)["status"] == "infeasible"


def test_initial_soc_cannot_hide_intra_cycle_underflow(base):
    base["vehicles"][0]["drive_energy_kwh"][0] = 90.0
    assert solve(base)["status"] == "infeasible"


def test_inactive_site_cannot_charge(base):
    base["sites"][1]["active"] = False
    assert solve(base)["status"] == "infeasible"


@pytest.mark.parametrize("mutation", ["missing_slot", "nonfinite", "driving_charge", "duplicate_id", "wrong_units", "unknown_field", "fractional_interfaces", "bad_efficiency", "multiple_locations", "unknown_site"])
def test_rejects_invalid_input_without_inference(base, mutation):
    vehicle = base["vehicles"][0]
    if mutation == "missing_slot": vehicle["drive_energy_kwh"].pop()
    elif mutation == "nonfinite": vehicle["initial_energy_kwh"] = float("nan")
    elif mutation == "driving_charge": vehicle["charging_site"][0] = "A"
    elif mutation == "duplicate_id": base["vehicles"][1]["id"] = "V1"
    elif mutation == "wrong_units": base["units"]["power"] = "MW"
    elif mutation == "unknown_field": vehicle["Initial_Energy"] = 100.0
    elif mutation == "fractional_interfaces": base["sites"][0]["interfaces"] = 1.5
    elif mutation == "bad_efficiency": vehicle["efficiency"] = 1.1
    elif mutation == "multiple_locations": vehicle["charging_site"][1] = ["A", "B"]
    elif mutation == "unknown_site": vehicle["charging_site"][1] = "a"
    with pytest.raises(ValueError):
        validate_input(base)


@pytest.mark.parametrize("mutation,expected", [("soc", "C06"), ("power_without_interface", "C03"), ("fractional_occupancy", "C02"), ("outside_window", "C02"), ("interface_limit", "C04"), ("grid_limit", "C05"), ("terminal_energy", "C07"), ("cost", "OBJECTIVE")])
def test_independent_checker_rejects_corrupted_primal(base, optimal, mutation, expected):
    result = copy.deepcopy(optimal)
    if mutation == "soc": result["solution"]["energy_kwh"][0][1] += 1.0
    elif mutation == "power_without_interface": result["solution"]["occupancy"][0][0][1] = 0.0
    elif mutation == "fractional_occupancy": result["solution"]["occupancy"][0][0][1] = 0.5
    elif mutation == "outside_window": result["solution"]["occupancy"][0][0][0] = 1.0
    elif mutation == "interface_limit": base["sites"][0]["interfaces"] = 1
    elif mutation == "grid_limit": base["sites"][0]["available_power_kw"][1] = 60.0
    elif mutation == "terminal_energy":
        result["solution"]["power_kw"][0][0][3] = 0.0
        result["solution"]["energy_kwh"][0][4] = 70.0
    elif mutation == "cost": result["objective"] += 10.0
    checked = check_solution(base, result)
    assert checked["passed"] is False
    assert expected in {error["constraint"] for error in checked["errors"]}


def test_checker_rejects_nonfinite_solution(base, optimal):
    optimal["solution"]["power_kw"][0][0][1] = float("nan")
    assert check_solution(base, optimal)["passed"] is False


@pytest.mark.parametrize("tolerance", [float("nan"), float("inf"), -1.0, 0.0, True])
def test_checker_rejects_invalid_tolerance(base, optimal, tolerance):
    with pytest.raises(ValueError):
        check_solution(base, optimal, tolerance=tolerance)


def test_checker_rejects_nonfinite_input_before_physical_recomputation(base, optimal):
    base["vehicles"][0]["drive_energy_kwh"][0] = float("nan")
    with pytest.raises(ValueError):
        check_solution(base, optimal)


def test_json_duplicate_keys_are_not_silently_overwritten():
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        json.loads('{"id":"V1","id":"V2"}', object_pairs_hook=reject_duplicate_keys)


def test_suite_rejects_changed_physical_fixture_with_same_ids(base):
    base["vehicles"][0]["drive_energy_kwh"][0] = 25.0
    validate_input(base)  # A valid single-instance input, but not this analytic suite.
    with pytest.raises(ValueError, match="minimal_three_trucks"):
        make_scenarios(base)
