"""Physical invariance, analytic costs and policy-preserving enumeration."""
import copy
import json
from pathlib import Path

import pytest

from um_charging.investment_experiment import compare_joint_to_enumeration, enumerate_facilities, make_investment_scenarios
from um_charging.model import solve
from um_charging.timegrid import POLICIES, audit_physical_equivalence, physical_event_ledger, refine_physical_cycle
from um_charging.timegrid_cli import study_inputs
from um_charging.validation import check_solution

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def base():
    return json.loads((ROOT / "configs/port_warehouse_investment.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("minutes", [60, 30, 15])
@pytest.mark.parametrize("policy", POLICIES)
def test_same_physical_events_equipment_and_costs(base, minutes, policy):
    original = copy.deepcopy(base)
    fine = refine_physical_cycle(base, minutes, policy)
    assert base == original
    assert audit_physical_equivalence(base, fine)["passed"]
    for events in physical_event_ledger(fine).values():
        assert [(e["start_minute"], e["end_minute"]) for e in events] == [(0, 60), (60, 120), (120, 180), (180, 240)]
        assert [e["drive_energy_kwh"] for e in events] == [20, 0, 20, 0]
        assert [e["charging_site"] for e in events] == [None, "WAREHOUSE", None, "PORT"]
    real_sites = {s["id"] for s in fine["sites"]}
    assert real_sites == {"PORT", "WAREHOUSE"}
    assert real_sites.isdisjoint(fine["transit_locations"])
    assert not any("All slots are complete one-hour intervals" in s for s in fine["provenance"]["assumed"])


@pytest.mark.parametrize("mutation", ["window", "drive_energy", "initial_energy", "connector_power", "interface_cost", "site_power", "price"])
def test_physical_audit_rejects_hidden_changes(base, mutation):
    fine = refine_physical_cycle(base, 30, POLICIES[0])
    if mutation == "window":
        fine["vehicles"][0]["timeline"][2]["plug_allowed"] = False
        fine["vehicles"][0]["charging_site"][2] = None
    elif mutation == "drive_energy": fine["vehicles"][0]["drive_energy_kwh"][0] += 1
    elif mutation == "initial_energy": fine["vehicles"][0]["initial_energy_kwh"] -= 1
    elif mutation == "connector_power": fine["vehicles"][0]["power_limit_kw"]["PORT"] -= 1
    elif mutation == "interface_cost": fine["sites"][0]["interface_cost"] += 1
    elif mutation == "site_power": fine["sites"][0]["available_power_kw"][0] += 1
    elif mutation == "price": fine["sites"][0]["price_per_kwh"][0] += 1
    assert not audit_physical_equivalence(base, fine)["passed"]


@pytest.mark.parametrize("minutes", [30, 15])
@pytest.mark.parametrize("policy,investment", [(POLICIES[0], 50), (POLICIES[1], 75)])
def test_analytic_two_site_optimum_and_enum_preserve_policy(base, minutes, policy, investment):
    data = refine_physical_cycle(make_investment_scenarios(base)["two_sites_joint"], minutes, policy)
    result = solve(data)
    checked = check_solution(data, result)
    assert checked["passed"]
    assert checked["investment_cost"] == pytest.approx(investment)
    assert checked["operating_cost"] == pytest.approx(400 / 3)
    assert result["objective"] == pytest.approx(investment + 400 / 3)
    seen = []
    def inspect(index, fixed, operating, validation):
        assert fixed["connector_policy"] == policy
        assert fixed["vehicles"] == data["vehicles"]
        assert all(s["max_new_interfaces"] == 0 and s["upgrade_options"] == [] for s in fixed["sites"])
        seen.append(index)
    enumeration = enumerate_facilities(data, on_combination=inspect)
    assert len(seen) == enumeration["combination_count"] == 54
    assert compare_joint_to_enumeration(result, checked, enumeration)["passed"]


@pytest.mark.parametrize("minutes", [30, 15])
def test_explicit_two_connector_witness_without_extra_parking(base, minutes):
    data = refine_physical_cycle(base, minutes, POLICIES[0])
    result = solve(data)
    s = result["solution"]
    # A hand-constructed half-hour witness, repeated twice for 15-minute slots.
    warehouse = [[400 / 9, 275 / 9, 0], [0, 125 / 9, 250 / 9]]
    port = [[400 / 9, 0, 275 / 9], [0, 400 / 9, 275 / 9]]
    s["new_interfaces"] = [1, 1]
    s["upgrade_selected"] = [[0, 0], [0]]
    for v, vehicle in enumerate(data["vehicles"]):
        s["energy_kwh"][v][0] = 100
        for t in range(data["slot_count"]):
            start = t * minutes
            for j in range(2):
                value = 0.0
                if j == 1 and 60 <= start < 120: value = warehouse[(start - 60) // 30][v]
                if j == 0 and 180 <= start < 240: value = port[(start - 180) // 30][v]
                s["power_kw"][v][j][t] = value
                s["occupancy"][v][j][t] = int(value > 0)
            s["energy_kwh"][v][t + 1] = (s["energy_kwh"][v][t] + 0.9 * minutes / 60
                * sum(s["power_kw"][v][j][t] for j in range(2)) - vehicle["drive_energy_kwh"][t])
    result["objective"] = 550 / 3
    assert check_solution(data, result)["passed"]
    locked = copy.deepcopy(data)
    locked["connector_policy"] = POLICIES[1]
    rejected = check_solution(locked, result)
    assert not rejected["passed"]
    assert rejected["max_violation_by_constraint"]["C08"] == pytest.approx(1)


def test_declared_study_config():
    study, paths = study_inputs(ROOT / "configs/timegrid_study.json", ROOT)
    assert study["slot_minutes"] == [60, 30, 15]
    assert len(paths) == 2
