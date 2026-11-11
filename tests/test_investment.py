"""Analytic cross-node investment case, exhaustive hardware verification and tampering."""
import copy
import json
from pathlib import Path

import pytest

from um_charging.investment_experiment import compare_joint_to_enumeration, enumerate_facilities, make_investment_scenarios
from um_charging.model import solve
from um_charging.validation import check_solution


@pytest.fixture
def investment_input():
    return json.loads((Path(__file__).resolve().parents[1] / "configs" / "port_warehouse_investment.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,cost,investment", [
    ("port_only_no_investment", None, None),
    ("port_only_interfaces_only", None, None),
    ("port_only_power_only", None, None),
    ("port_only_joint", 715 / 3, 105),
    ("two_sites_no_investment", None, None),
    ("two_sites_interfaces_only", 700 / 3, 100),
    ("two_sites_power_only", None, None),
    ("two_sites_joint", 625 / 3, 75),
    ("two_sites_joint_redundant_warehouse_power", 625 / 3, 75),
])
def test_analytic_optimum_matches_all_fixed_facility_combinations(investment_input, name, cost, investment):
    data = make_investment_scenarios(investment_input)[name]
    result = solve(data)
    checked = check_solution(data, result)
    enumeration = enumerate_facilities(data)
    assert compare_joint_to_enumeration(result, checked, enumeration)["passed"]
    if cost is None:
        assert result["status"] == "infeasible"
        assert enumeration["feasible_count"] == 0
        assert checked["applicable"] is False
        assert checked["passed"] is None
    else:
        assert result["status"] == "optimal"
        assert result["objective"] == pytest.approx(cost)
        assert result["dual_bound"] == pytest.approx(cost)
        assert result["mip_gap"] == pytest.approx(0)
        assert checked["passed"]
        assert checked["investment_cost"] == pytest.approx(investment)
        assert checked["operating_cost"] == pytest.approx(400 / 3)
        assert checked["grid_energy_kwh"] == pytest.approx(400 / 3)
        assert enumeration["best_total_cost"] == pytest.approx(cost)
        for trajectory in checked["energy_kwh_recomputed"]:
            assert trajectory[0] == pytest.approx(100)
            assert trajectory[-1] == pytest.approx(100)
        if name == "two_sites_joint":
            assert enumeration["combination_count"] == 54
            assert result["solution"]["new_interfaces"] == pytest.approx([2, 0])
            assert result["solution"]["upgrade_selected"][0] == pytest.approx([1, 0])
            assert result["solution"]["upgrade_selected"][1] == pytest.approx([0])


def test_transport_and_initial_energy_identical_across_comparisons(investment_input):
    before = copy.deepcopy(investment_input)
    for data in make_investment_scenarios(investment_input).values():
        assert data["vehicles"] == investment_input["vehicles"]
        assert data["representative_weight"] == investment_input["representative_weight"] == 1
        assert data["slot_hours"] == investment_input["slot_hours"]
        assert data["slot_count"] == investment_input["slot_count"]
    assert investment_input == before


@pytest.mark.parametrize("mutation,expected", [
    ("fractional_interfaces", "C01"), ("excess_interfaces", "C01"),
    ("negative_interfaces", "C01"), ("fractional_upgrade", "C01"),
    ("multiple_upgrades", "C01"), ("negative_upgrade", "C01"),
    ("inactive_investment", "C01"), ("removed_interfaces", "C04"),
    ("removed_upgrade", "C05"), ("investment_price", "OBJECTIVE"),
    ("operating_price", "OBJECTIVE"), ("objective", "OBJECTIVE"),
    ("energy", "C06"), ("terminal", "C07"),
])
def test_independent_investment_checker_rejects_corruption(investment_input, mutation, expected):
    data = make_investment_scenarios(investment_input)["two_sites_joint"]
    result = solve(data)
    s = result["solution"]
    if mutation == "fractional_interfaces": s["new_interfaces"][0] = 1.5
    elif mutation == "excess_interfaces": s["new_interfaces"][0] = 3
    elif mutation == "negative_interfaces": s["new_interfaces"][1] = -1
    elif mutation == "fractional_upgrade": s["upgrade_selected"][0][0] = 0.5
    elif mutation == "multiple_upgrades": s["upgrade_selected"][0] = [1, 1]
    elif mutation == "negative_upgrade": s["upgrade_selected"][1][0] = -1
    elif mutation == "inactive_investment":
        data["sites"][1]["active"] = False
        s["new_interfaces"][1] = 1
    elif mutation == "removed_interfaces": s["new_interfaces"][0] = 0
    elif mutation == "removed_upgrade": s["upgrade_selected"][0] = [0, 0]
    elif mutation == "investment_price": data["sites"][0]["interface_cost"] += 1
    elif mutation == "operating_price": data["sites"][0]["price_per_kwh"][3] += 1
    elif mutation == "objective": result["objective"] += 1
    elif mutation == "energy": s["energy_kwh"][0][2] += 1
    elif mutation == "terminal":
        for v in range(3):
            s["power_kw"][v][0][3] = 0
    checked = check_solution(data, result)
    assert checked["passed"] is False
    assert expected in {error["constraint"] for error in checked["errors"]}


@pytest.mark.parametrize("field,value", [
    ("new_interfaces", [float("nan"), 0]),
    ("new_interfaces", [True, 0]),
    ("new_interfaces", [2]),
    ("upgrade_selected", [[1, 0]]),
    ("upgrade_selected", [[1, float("inf")], [0]]),
    ("upgrade_selected", [[True, 0], [0]]),
])
def test_investment_primal_shape_and_nonfinite_rejected(investment_input, field, value):
    result = solve(investment_input)
    result["solution"][field] = value
    assert check_solution(investment_input, result)["passed"] is False


def test_enumeration_does_not_accept_a_suboptimal_joint_claim(investment_input):
    result = solve(investment_input)
    checked = check_solution(investment_input, result)
    enumeration = enumerate_facilities(investment_input)
    fake = copy.deepcopy(checked)
    fake["objective_recomputed"] += 20
    assert not compare_joint_to_enumeration(result, fake, enumeration)["passed"]
    result["status"] = "limit_reached"
    assert not compare_joint_to_enumeration(result, checked, enumeration)["passed"]

