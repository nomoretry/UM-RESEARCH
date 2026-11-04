from copy import deepcopy
import json
from io import StringIO
from pathlib import Path

import pytest

from truckplan.data import load_dataset, validate_dataset
from truckplan.plans import generate_plans


@pytest.fixture
def data():
    return load_dataset(Path(__file__).parents[1]/"data/synthetic/demo.json")


def test_routes_require_charge(data):
    plans = generate_plans(data)
    assert plans and {p["job_id"] for p in plans} == {"T1", "T2"}
    assert all(p["events"] for p in plans)
    assert all(p["path_nodes"] != ["O", "D"] for p in plans)
    a = next(p for p in plans if p["path_nodes"] == ["O", "A", "D"] and p["arrival_slot"] == 4)
    assert a["terminal_kwh"] == pytest.approx(20)
    assert a["operating_cost_cny"] == pytest.approx(750)


@pytest.mark.parametrize("bad_value", [None, float("nan"), float("inf"), -1, True])
def test_invalid_numeric(data, bad_value):
    data["vehicle"]["battery_kwh"] = bad_value
    with pytest.raises(ValueError): validate_dataset(data)


def test_case_sensitive_keys(data):
    data["nodes"][0]["Node_id"] = data["nodes"][0].pop("node_id")
    with pytest.raises(ValueError, match="unknown"): validate_dataset(data)


def test_unknown_reference(data):
    data["edges"][0]["from_node"] = "o"
    with pytest.raises(ValueError): validate_dataset(data)


def test_source_required(data):
    data["jobs"][0]["source_id"] = "UNREGISTERED"
    with pytest.raises(ValueError): validate_dataset(data)


def test_no_reverse_direction_invented(data):
    data["jobs"][0].update(origin="D", destination="O")
    assert not any(p["job_id"] == "T1" for p in generate_plans(data))


def test_no_charge_needed(data):
    for j in data["jobs"]: j["initial_kwh"] = 180
    data["vehicle"]["consumption_kwh_per_km"] = 0.5
    assert any(not p["events"] for p in generate_plans(data))


def test_generation_limit_not_silent(data):
    data["settings"]["max_plans_per_job"] = 1
    with pytest.raises(ValueError, match="exceeded"): generate_plans(data)


def test_deadline_infeasibility(data):
    for j in data["jobs"]: j["deadline_slot"] = 2
    assert generate_plans(data) == []


def test_duplicate_json_keys_rejected(monkeypatch):
    monkeypatch.setattr(Path, "open", lambda *a, **k: StringIO('{"schema_version":"1.0","schema_version":"2.0"}'))
    with pytest.raises(ValueError, match="duplicate"): load_dataset("in_memory_test.json")
