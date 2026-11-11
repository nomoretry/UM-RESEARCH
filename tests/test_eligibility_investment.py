from copy import deepcopy
from pathlib import Path

import pytest

from um_charging.eligibility_investment import (
    BOUNDARY, FROZEN, fixed_comparison, historical_zero, planning_case,
)
from um_charging.eligibility_stress import make_reference
from um_charging.timegrid_cli import load_json


ROOT = Path(__file__).resolve().parents[1]
STUDY = load_json(ROOT / "configs/eligibility_stress.json")


@pytest.fixture
def reference():
    return make_reference(load_json(ROOT / STUDY["base_config"]))


@pytest.mark.parametrize("delay", STUDY["delays_minutes"])
def test_delay_preserves_investment_and_the_third_trucks_full_window(reference, delay):
    before = deepcopy(reference)
    plan = planning_case(reference, delay, STUDY["delayed_vehicle_ids"])
    assert before == reference
    assert plan["sites"] == reference["sites"]
    for vehicle, old in zip(plan["vehicles"], reference["vehicles"], strict=True):
        count = delay // 15 if vehicle["id"] in {"V1", "V2"} else 0
        assert vehicle["charging_site"][4:8] == [None] * count + ["WAREHOUSE"] * (4 - count)
        assert vehicle["drive_energy_kwh"] == old["drive_energy_kwh"]
        assert vehicle["charging_site"][12:16] == ["PORT"] * 4


def test_zero_reuse_checks_the_whole_input(reference):
    history = load_json(BOUNDARY)
    zero = historical_zero(reference, history)
    assert zero["enumeration_reused"] == 54 and zero["enumeration_new"] == 0
    reference["sites"][1]["interface_cost"] += 1
    with pytest.raises(ValueError, match="Zero-delay reference"):
        historical_zero(reference, history)


def test_frozen_operating_cost_requires_prior_investment_for_a_valid_ceiling():
    frozen = load_json(FROZEN)
    row = {"status": "optimal", "objective": 40 + 400 / 3}
    limits = fixed_comparison(STUDY, frozen, 45, row)
    assert {r["facility"]: r["total_cost"] for r in limits} == {
        "A": None, "B": pytest.approx(40 + 400 / 3)}
    with pytest.raises(ValueError, match="upper bound"):
        fixed_comparison(STUDY, frozen, 45, dict(row, objective=41 + 400 / 3))
