from pathlib import Path

import pytest

from run import scenario_data
from truckplan.data import load_dataset
from truckplan.plans import generate_plans
from truckplan.model import solve
from truckplan.verify import verify_solution


@pytest.mark.parametrize("scenario", ["base", "no_charge_needed", "site_power_limited", "reverse_access_blocked"])
def test_full_pipeline(scenario):
    data = scenario_data(load_dataset(Path(__file__).parents[1]/"data/synthetic/demo.json"), scenario)
    plans = generate_plans(data)
    result = solve(data, plans)
    assert result["status"] == "optimal"
    assert verify_solution(data, plans, result)["valid"]
    if scenario == "base":
        assert result["objective_cny_per_year"] == pytest.approx(462000)
        assert next(s for s in result["station_decisions"] if s["site_id"] == "SA")["bays"] == 2
    if scenario == "no_charge_needed":
        assert sum(s["bays"] for s in result["station_decisions"]) == 0
        assert result["objective_cny_per_year"] == pytest.approx(315000)


def test_infeasible_not_hidden():
    data = scenario_data(load_dataset(Path(__file__).parents[1]/"data/synthetic/demo.json"), "tight_deadline_one_bay")
    result = solve(data, generate_plans(data))
    assert result["status"] == "infeasible"
    assert result["objective_cny_per_year"] is None


def test_relaxation_is_not_a_feasible_plan():
    data = load_dataset(Path(__file__).parents[1]/"data/synthetic/demo.json")
    plans = generate_plans(data)
    result = solve(data, plans, enforce_service_capacity=False)
    assert result["status"] == "optimal"
    assert result["objective_cny_per_year"] < solve(data, plans)["objective_cny_per_year"]
    assert not verify_solution(data, plans, result)["valid"]
