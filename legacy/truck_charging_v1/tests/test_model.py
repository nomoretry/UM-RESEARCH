"""Mathematical synthetic fixtures; these are not observed Guangdong records."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from truckplan import model


def dataset(job_count=1, *, max_bays=2, power=120.0):
    return {
        "schema_version": "1.0",
        "metadata": {
            "dataset_id": "model-unit-test",
            "data_kind": "synthetic",
            "description": "Mathematical solver unit test only",
            "sources": [{"source_id": "test", "citation": "Constructed unit test", "evidence_type": "synthetic"}],
        },
        "settings": {
            "slot_minutes": 30,
            "horizon_slots": 8,
            "operating_days_per_year": 100,
            "annualization_factor": 0.1,
            "electricity_cny_per_kwh": 1.0,
            "driver_cny_per_hour": 10.0,
            "vehicle_cny_per_km": 1.0,
            "max_paths_per_job": 3,
            "max_plans_per_job": 100,
            "solver_time_limit_seconds": 20.0,
        },
        "vehicle": {
            "battery_kwh": 100.0,
            "minimum_kwh": 10.0,
            "consumption_kwh_per_km": 1.0,
            "charge_efficiency": 1.0,
        },
        "nodes": [
            {"node_id": value, "label": value, "source_id": "test"} for value in ("A", "S", "B")
        ],
        "edges": [
            {"edge_id": "AS", "from_node": "A", "to_node": "S", "distance_km": 20.0, "travel_minutes": 30.0, "source_id": "test"},
            {"edge_id": "SB", "from_node": "S", "to_node": "B", "distance_km": 20.0, "travel_minutes": 30.0, "source_id": "test"},
        ],
        "sites": [{
            "site_id": "S1", "node_id": "S", "max_bays": max_bays,
            "charger_kw": 60.0, "site_power_kw": power,
            "fixed_cost_cny": 1000.0, "bay_cost_cny": 100.0,
            "open_slot": 0, "close_slot": 8, "source_id": "test",
        }],
        "jobs": [{
            "job_id": f"J{i + 1}", "origin": "A", "destination": "B",
            "departure_slot": 0, "deadline_slot": 8,
            "initial_kwh": 40.0, "terminal_minimum_kwh": 10.0, "source_id": "test",
        } for i in range(job_count)],
    }


def plan(job_id="J1", plan_id="P1", *, start=1, cost=55.0, charging=True):
    return {
        "plan_id": plan_id, "job_id": job_id,
        "path_nodes": ["A", "S", "B"], "edge_ids": ["AS", "SB"],
        "distance_km": 40.0,
        "arrival_slot": start + 2 if charging else 2,
        "terminal_kwh": 30.0 if charging else 0.0,
        "events": [{
            "site_id": "S1", "arrival_slot": 1, "start_slot": start, "end_slot": start + 1,
            "energy_before_kwh": 20.0, "energy_after_kwh": 50.0, "grid_energy_kwh": 30.0,
        }] if charging else [],
        "operating_cost_cny": cost, "energy_used_kwh": 40.0,
    }


def test_annual_capital_and_operation_are_separate():
    result = model.solve(dataset(), [plan()])
    assert result["status"] == "optimal"
    assert result["station_decisions"] == [{"site_id": "S1", "build": 1, "bays": 1}]
    assert result["investment_cny_per_year"] == pytest.approx(110.0)
    assert result["operation_cny_per_year"] == pytest.approx(5500.0)
    assert result["objective_cny_per_year"] == pytest.approx(5610.0)
    assert result["selected_plan_ids"] == ["P1"]


def test_simultaneous_jobs_require_two_bays():
    result = model.solve(dataset(2), [plan(), plan("J2", "P2")])
    assert result["status"] == "optimal"
    assert result["station_decisions"][0]["bays"] == 2


def test_missing_bay_capacity_is_infeasible_not_dropped_demand():
    result = model.solve(dataset(2, max_bays=1), [plan(), plan("J2", "P2")])
    assert result["status"] == "infeasible"
    assert result["objective_cny_per_year"] is None
    assert result["selected_plan_ids"] == []


def test_service_relaxation_is_labelled_and_does_not_drop_power_limit():
    plans = [plan(), plan("J2", "P2")]
    relaxed = model.solve(dataset(2, max_bays=1), plans, enforce_service_capacity=False)
    assert relaxed["status"] == "optimal"
    assert relaxed["station_decisions"][0]["bays"] == 1
    assert "not a deployable" in relaxed["message"]
    assert "site power limits remain" in relaxed["message"]
    power_limited = model.solve(dataset(2, max_bays=1, power=60.0), plans, enforce_service_capacity=False)
    assert power_limited["status"] == "infeasible"


def test_staggered_schedule_restores_feasibility():
    plans = [plan(), plan("J2", "P2"), plan("J2", "P2_later", start=2, cost=60.0)]
    result = model.solve(dataset(2, max_bays=1, power=60.0), plans)
    assert result["status"] == "optimal"
    assert set(result["selected_plan_ids"]) == {"P1", "P2_later"}
    assert result["station_decisions"][0]["bays"] == 1


def test_half_open_intervals_do_not_overlap_at_boundary():
    result = model.solve(
        dataset(2, max_bays=1, power=60.0),
        [plan(), plan("J2", "P2", start=2, cost=60.0)],
    )
    assert result["status"] == "optimal"


def test_no_charging_plan_can_avoid_investment():
    # Model-only fixture: physical feasibility is the independent verifier's job.
    result = model.solve(dataset(), [plan(), plan(plan_id="P0", cost=55.5, charging=False)])
    assert result["status"] == "optimal"
    assert result["selected_plan_ids"] == ["P0"]
    assert result["station_decisions"] == [{"site_id": "S1", "build": 0, "bays": 0}]


def test_missing_job_plan_is_explicitly_infeasible():
    result = model.solve(dataset(2), [plan()])
    assert result["status"] == "infeasible"
    assert "J2" in result["message"]
    assert "finite plan set" in result["message"]
    assert result["objective_cny_per_year"] is None


def test_no_sites_with_no_charging_plan():
    data = dataset()
    data["sites"] = []
    result = model.solve(data, [plan(charging=False)])
    assert result["status"] == "optimal"
    assert result["station_decisions"] == []


def test_no_jobs_is_rejected_before_solver_call(monkeypatch):
    monkeypatch.setattr(model, "milp", lambda **kwargs: pytest.fail("Solver should not run"))
    with pytest.raises(ValueError, match="at least one explicit trip"):
        model.solve(dataset(0), [])


def test_solve_rejects_unknown_dataset_key():
    data = dataset()
    data["Settings"] = deepcopy(data["settings"])
    with pytest.raises(ValueError, match="unknown"):
        model.solve(data, [plan()])


def test_zero_power_prevents_station_use():
    assert model.solve(dataset(power=0.0), [plan()])["status"] == "infeasible"


@pytest.mark.parametrize("status,expected", [(0, "optimal"), (1, "feasible_limit")])
def test_solver_status_and_gap_are_preserved(monkeypatch, status, expected):
    monkeypatch.setattr(model, "milp", lambda **kwargs: SimpleNamespace(
        status=status, x=np.array([1.0, 1.0, 1.0]), message="Synthetic solver status", mip_gap=0.25,
    ))
    result = model.solve(dataset(), [plan()])
    assert result["status"] == expected
    assert result["mip_gap"] == 0.25


def test_time_limit_without_incumbent_is_not_infeasibility(monkeypatch):
    monkeypatch.setattr(model, "milp", lambda **kwargs: SimpleNamespace(
        status=1, x=None, message="Time limit reached", mip_gap=None,
    ))
    result = model.solve(dataset(), [plan()])
    assert result["status"] == "solver_error"
    assert "not an infeasibility proof" in result["message"]
    assert result["objective_cny_per_year"] is None


@pytest.mark.parametrize("status,expected", [(2, "infeasible"), (3, "unbounded"), (4, "solver_error")])
def test_unusable_solver_states_do_not_expose_solution_vector(monkeypatch, status, expected):
    monkeypatch.setattr(model, "milp", lambda **kwargs: SimpleNamespace(
        status=status, x=np.array([1.0, 1.0, 1.0]), message="Synthetic solver status", mip_gap=0.0,
    ))
    result = model.solve(dataset(), [plan()])
    assert result["status"] == expected
    assert result["station_decisions"] == []
    assert result["objective_cny_per_year"] is None


@pytest.mark.parametrize("vector", [[0.5, 1.0, 1.0], [0.0, 1.0, 1.0], [float("nan"), 1.0, 1.0]])
def test_invalid_solver_incumbent_is_rejected(monkeypatch, vector):
    monkeypatch.setattr(model, "milp", lambda **kwargs: SimpleNamespace(
        status=1, x=np.array(vector), message="Synthetic solver status", mip_gap=0.5,
    ))
    assert model.solve(dataset(), [plan()])["status"] == "solver_error"


def test_duplicate_plan_id_is_rejected():
    with pytest.raises(ValueError, match="Duplicate plan_id"):
        model.solve(dataset(), [plan(), plan()])


def test_unknown_ids_are_not_guessed_or_case_matched():
    with pytest.raises(ValueError, match="Unknown job_id"):
        model.solve(dataset(), [plan(job_id="j1")])
    bad = plan()
    bad["events"][0]["site_id"] = "s1"
    with pytest.raises(ValueError, match="Unknown site_id"):
        model.solve(dataset(), [bad])


def test_event_outside_station_opening_is_rejected():
    data = dataset()
    data["sites"][0]["open_slot"] = 2
    with pytest.raises(ValueError, match="outside station opening"):
        model.solve(data, [plan()])


def test_overlapping_events_in_same_plan_are_rejected():
    bad = plan()
    bad["events"].append(deepcopy(bad["events"][0]))
    with pytest.raises(ValueError, match="Overlapping charging events"):
        model.solve(dataset(), [bad])
