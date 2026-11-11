"""Independent checker tests.  All fixtures are mathematical, not city records."""

from copy import deepcopy

import pytest

from truckplan.verify import verify_solution


@pytest.fixture
def case():
    data = {
        "schema_version": "1.0",
        "metadata": {
            "dataset_id": "verification_fixture", "data_kind": "synthetic",
            "description": "Mathematical unit-test fixture, not observed demand.",
            "sources": [{"source_id": "test", "citation": "Internal arithmetic fixture", "evidence_type": "synthetic"}],
        },
        "settings": {
            "slot_minutes": 30, "horizon_slots": 8, "operating_days_per_year": 300,
            "annualization_factor": 0.1, "electricity_cny_per_kwh": 1,
            "driver_cny_per_hour": 60, "vehicle_cny_per_km": 2,
            "max_paths_per_job": 10, "max_plans_per_job": 100,
            "solver_time_limit_seconds": 10,
        },
        "vehicle": {"battery_kwh": 30, "minimum_kwh": 2, "consumption_kwh_per_km": 1, "charge_efficiency": 0.8},
        "nodes": [{"node_id": n, "label": n, "source_id": "test"} for n in ("A", "S", "D")],
        "edges": [
            {"edge_id": "AS", "from_node": "A", "to_node": "S", "distance_km": 10, "travel_minutes": 20, "source_id": "test"},
            {"edge_id": "SD", "from_node": "S", "to_node": "D", "distance_km": 10, "travel_minutes": 31, "source_id": "test"},
        ],
        "sites": [{
            "site_id": "S_site", "node_id": "S", "max_bays": 2, "charger_kw": 20,
            "site_power_kw": 40, "fixed_cost_cny": 1000, "bay_cost_cny": 500,
            "open_slot": 0, "close_slot": 8, "source_id": "test",
        }],
        "jobs": [{
            "job_id": "J1", "origin": "A", "destination": "D", "departure_slot": 0,
            "deadline_slot": 7, "initial_kwh": 15, "terminal_minimum_kwh": 2, "source_id": "test",
        }],
    }
    plans = [{
        "plan_id": "P1", "job_id": "J1", "path_nodes": ["A", "S", "D"],
        "edge_ids": ["AS", "SD"], "distance_km": 20, "arrival_slot": 4,
        "terminal_kwh": 3, "energy_used_kwh": 20, "operating_cost_cny": 185,
        "events": [{
            "site_id": "S_site", "arrival_slot": 1, "start_slot": 1, "end_slot": 2,
            "energy_before_kwh": 5, "energy_after_kwh": 13, "grid_energy_kwh": 10,
        }],
    }]
    result = {
        "status": "optimal", "objective_cny_per_year": 55650,
        "station_decisions": [{"site_id": "S_site", "build": 1, "bays": 1}],
        "selected_plan_ids": ["P1"], "investment_cny_per_year": 150,
        "operation_cny_per_year": 55500, "mip_gap": 0, "message": "test output",
    }
    return data, plans, result


def test_recomputes_valid_case_without_mutation(case):
    original = deepcopy(case)
    checked = verify_solution(*case)
    assert checked["valid"], checked["errors"]
    assert checked["metrics"]["objective_cny_per_year"] == 55650
    assert checked["metrics"]["plans_recomputed"][0]["arrival_slot"] == 4
    assert case == original


@pytest.mark.parametrize("field", ["distance_km", "arrival_slot", "terminal_kwh", "energy_used_kwh", "operating_cost_cny"])
def test_rejects_forged_plan_summaries(case, field):
    case[1][0][field] += 1
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert any(field in error for error in checked["errors"])


@pytest.mark.parametrize("field", ["arrival_slot", "energy_before_kwh", "energy_after_kwh", "grid_energy_kwh"])
def test_rejects_forged_event_summaries(case, field):
    case[1][0]["events"][0][field] += 1
    assert not verify_solution(*case)["valid"]


def test_directed_edges_are_not_reversed(case):
    case[0]["edges"][0]["from_node"] = "S"
    case[0]["edges"][0]["to_node"] = "A"
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert any("directed edge" in e for e in checked["errors"])


def test_missing_edge_is_not_invented(case):
    case[1][0]["edge_ids"][0] = "SA"
    assert not verify_solution(*case)["valid"]


def test_battery_minimum_checked_before_charge(case):
    case[0]["jobs"][0]["initial_kwh"] = 11
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert any("battery below minimum after edge" in e for e in checked["errors"])


def test_battery_overcharge(case):
    case[0]["vehicle"]["battery_kwh"] = 15
    case[1][0]["events"][0]["end_slot"] = 3
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert any("exceeds battery capacity" in e for e in checked["errors"])


def test_terminal_requirement_checked(case):
    case[0]["jobs"][0]["terminal_minimum_kwh"] = 4
    assert any("terminal energy below" in e for e in verify_solution(*case)["errors"])


def test_charging_before_arrival_rejected(case):
    case[1][0]["events"][0]["start_slot"] = 0
    assert any("before the recomputed arrival" in e for e in verify_solution(*case)["errors"])


def test_opening_window_checked(case):
    case[0]["sites"][0]["open_slot"] = 2
    assert any("opening window" in e for e in verify_solution(*case)["errors"])


def test_deadline_checked_after_edgewise_rounding(case):
    case[0]["jobs"][0]["deadline_slot"] = 3
    assert any("job deadline" in e for e in verify_solution(*case)["errors"])


def test_waiting_is_permitted_and_costed(case):
    data, plans, result = case
    event = plans[0]["events"][0]
    event["start_slot"], event["end_slot"] = 2, 3
    plans[0]["arrival_slot"] = 5
    plans[0]["operating_cost_cny"] = 215
    result["operation_cny_per_year"] = 64500
    result["objective_cny_per_year"] = 64650
    checked = verify_solution(data, plans, result)
    assert checked["valid"], checked["errors"]


def test_arrival_at_deadline_and_charge_ending_at_close_are_inclusive(case):
    case[0]["jobs"][0]["deadline_slot"] = 4
    case[0]["sites"][0]["close_slot"] = 2
    checked = verify_solution(*case)
    assert checked["valid"], checked["errors"]


def test_no_charging_and_zero_build_is_valid_when_initial_energy_suffices(case):
    data, plans, result = case
    data["jobs"][0]["initial_kwh"] = 25
    plans[0].update(events=[], arrival_slot=3, terminal_kwh=5, operating_cost_cny=155)
    result["station_decisions"][0].update(build=0, bays=0)
    result.update(investment_cny_per_year=0, operation_cny_per_year=46500, objective_cny_per_year=46500)
    checked = verify_solution(*case)
    assert checked["valid"], checked["errors"]


def _add_second_job(case, delay):
    data, plans, result = case
    job = deepcopy(data["jobs"][0])
    job["job_id"] = "J2"
    job["departure_slot"] += delay
    data["jobs"].append(job)
    plan = deepcopy(plans[0])
    plan["job_id"], plan["plan_id"] = "J2", "P2"
    plan["arrival_slot"] += delay
    for key in ("arrival_slot", "start_slot", "end_slot"):
        plan["events"][0][key] += delay
    plans.append(plan)
    result["selected_plan_ids"].append("P2")
    result["operation_cny_per_year"] *= 2
    result["objective_cny_per_year"] = result["operation_cny_per_year"] + result["investment_cny_per_year"]


def test_half_open_occupancy_allows_adjacent_charging(case):
    _add_second_job(case, delay=1)
    checked = verify_solution(*case)
    assert checked["valid"], checked["errors"]
    assert checked["metrics"]["maximum_occupied_bays_by_site"] == {"S_site": 1}


def test_full_capacity_verifier_rejects_relaxed_solution(case):
    _add_second_job(case, delay=0)
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert any("occupied bays 2 exceed installed bays 1" in e for e in checked["errors"])


def test_site_power_checked_independently_of_bay_capacity(case):
    _add_second_job(case, delay=0)
    case[0]["sites"][0]["site_power_kw"] = 20
    case[2]["station_decisions"][0]["bays"] = 2
    case[2]["investment_cny_per_year"] = 200
    case[2]["objective_cny_per_year"] = case[2]["operation_cny_per_year"] + 200
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert any("charging power exceeds" in e for e in checked["errors"])


@pytest.mark.parametrize("key,value", [("build", 0.5), ("bays", 1.2), ("build", True), ("bays", -1)])
def test_station_decisions_must_be_integers(case, key, value):
    case[2]["station_decisions"][0][key] = value
    assert not verify_solution(*case)["valid"]


def test_charging_at_unbuilt_station(case):
    case[2]["station_decisions"][0].update(build=0, bays=0)
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert any("unbuilt station" in e for e in checked["errors"])


@pytest.mark.parametrize("selection", [[], ["P1", "P1"], ["missing"]])
def test_exactly_one_known_plan_per_job(case, selection):
    case[2]["selected_plan_ids"] = selection
    assert not verify_solution(*case)["valid"]


@pytest.mark.parametrize("target", ["result", "plan", "event", "decision", "dataset"])
def test_unknown_keys_fail_explicitly(case, target):
    data, plans, result = case
    obj = {"result": result, "plan": plans[0], "event": plans[0]["events"][0], "decision": result["station_decisions"][0], "dataset": data}[target]
    obj["Unexpected_Key"] = 1
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert checked["errors"]


@pytest.mark.parametrize("target,key", [("result", "status"), ("plan", "events"), ("event", "end_slot"), ("decision", "bays")])
def test_missing_keys_return_errors(case, target, key):
    _, plans, result = case
    obj = {"result": result, "plan": plans[0], "event": plans[0]["events"][0], "decision": result["station_decisions"][0]}[target]
    del obj[key]
    assert not verify_solution(*case)["valid"]


@pytest.mark.parametrize("field", ["objective_cny_per_year", "investment_cny_per_year", "operation_cny_per_year"])
def test_objective_components_recomputed(case, field):
    case[2][field] += 100
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert any(field in e for e in checked["errors"])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "185", True])
def test_invalid_numeric_plan_values_are_rejected(case, value):
    case[1][0]["operating_cost_cny"] = value
    assert not verify_solution(*case)["valid"]


def test_infeasible_status_is_not_certified(case):
    case[2]["status"] = "infeasible"
    case[2]["selected_plan_ids"] = []
    case[2]["objective_cny_per_year"] = None
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert "no verifiable feasible solution" in checked["errors"][0]


def test_duplicate_station_decision_is_rejected(case):
    case[2]["station_decisions"].append(deepcopy(case[2]["station_decisions"][0]))
    assert not verify_solution(*case)["valid"]


def test_duplicate_plan_id_is_rejected(case):
    case[1].append(deepcopy(case[1][0]))
    assert not verify_solution(*case)["valid"]


def test_charging_at_origin_is_rejected(case):
    case[0]["sites"][0]["node_id"] = "A"
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert any("not an intermediate path node" in e for e in checked["errors"])


def test_non_object_result_returns_errors(case):
    checked = verify_solution(case[0], case[1], [])
    assert not checked["valid"]
    assert "expected an object" in checked["errors"][0]


def test_non_array_plans_returns_errors(case):
    checked = verify_solution(case[0], None, case[2])
    assert not checked["valid"]
    assert "expected an array" in checked["errors"][0]


def test_duplicate_event_at_same_site_rejected(case):
    case[1][0]["events"].append(deepcopy(case[1][0]["events"][0]))
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert any("duplicate charging event" in e for e in checked["errors"])


def test_extreme_charging_end_is_rejected_before_expanding_occupancy(case):
    case[1][0]["events"][0]["end_slot"] = 10**12
    checked = verify_solution(*case)
    assert not checked["valid"]
    assert any("exceeds the time horizon" in e for e in checked["errors"])
