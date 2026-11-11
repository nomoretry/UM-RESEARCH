"""Regression checks for the exact A/B operating-point reuse."""
import copy
import json
from pathlib import Path

import pytest

from um_charging.eligibility_reuse import frozen_operating_reuse
from um_charging.eligibility_stress import build_case, make_reference
from um_charging.investment_experiment import enumerate_facilities


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def history():
    def load(path):
        return json.loads((ROOT / path).read_text(encoding="utf-8"))
    study = load("configs/eligibility_stress.json")
    metrics = load("results/eligibility_stress_20261111/metrics.json")
    return make_reference(load(study["base_config"])), study, metrics


def inputs(reference, study, facility, delay):
    fixed = build_case(reference, facility, delay, study["delayed_vehicle_ids"])
    allocation = [{"site_id": s["id"], "new_interfaces": facility[s["id"]] - s["interfaces"], "upgrade_id": None}
                  for s in reference["sites"]]
    return fixed, allocation


@pytest.mark.parametrize("delay", [15, 30, 45, 60])
def test_two_fixed_points_retain_prior_status_certificate_and_cost(history, delay):
    reference, study, metrics = history
    reuse = frozen_operating_reuse(reference, study, metrics, delay)
    for name, facility in study["facilities"].items():
        historical = next(row for row in metrics["cases"] if row["facility"] == name and row["delay_minutes"] == delay)
        fixed, allocation = inputs(reference, study, facility, delay)
        frozen_investment = historical["planning_investment"]
        op = reuse(fixed, allocation, frozen_investment)
        assert op["status"] == historical["status"] and op["reused_from"]["input_sha256"] == historical["input_sha256"]
        assert op["total_cost"] == (None if historical["operating_cost"] is None else historical["operating_cost"] + frozen_investment)
        assert op["operating_dual_bound"] == historical["dual_bound"]
        assert op["validation_passed"] == historical["validation_passed"]


def test_reject_other_operating_masks_base_costs_and_modified_prior_metrics(history):
    reference, study, metrics = history
    reuse = frozen_operating_reuse(reference, study, metrics, 45)
    fixed, alloc = inputs(reference, study, study["facilities"]["B"], 45)
    with pytest.raises(ValueError, match="investment"):
        reuse(fixed, alloc, 0)
    modified = copy.deepcopy(fixed)
    modified["vehicles"][2]["charging_site"][4] = None
    with pytest.raises(ValueError, match="inputs"):
        reuse(modified, alloc, 40)
    reference["sites"][0]["price_per_kwh"][0] += 1
    with pytest.raises(ValueError, match="input differs"):
        frozen_operating_reuse(reference, study, metrics, 45)
    metrics["cases"][-1]["status"] = "optimal"
    with pytest.raises(ValueError, match="digest"):
        frozen_operating_reuse(reference, study, metrics, 45)


def test_cached_facilities_are_enumerated_but_skipped_by_the_raw_solve_callback(history):
    reference, study, metrics = history
    reuse = frozen_operating_reuse(reference, study, metrics, 45)
    planning = copy.deepcopy(reference)
    planning["vehicles"] = inputs(reference, study, study["facilities"]["A"], 45)[0]["vehicles"]
    fresh = set()
    result = enumerate_facilities(planning, reuse_operating=reuse,
                                  on_combination=lambda index, *_: fresh.add(index))
    old = {r["combination"] for r in result["combinations"] if "reused_from" in r}
    assert len(result["combinations"]) == 54 and len(fresh) == 52 and len(old) == 2
    assert old.isdisjoint(fresh)
    assert {r["reused_from"]["facility"] for r in result["combinations"] if "reused_from" in r} == {"A", "B"}
    assert result["best_total_cost"] == pytest.approx(40 + 400 / 3)
