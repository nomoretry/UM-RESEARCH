"""Task-chain invariance, controlled windows, and analytic applicability boundaries."""
import copy
import json
from pathlib import Path

import pytest

from um_charging.boundary import audit_boundary_case, build_boundary_case, transport_ledger
from um_charging.boundary_cli import facility_details, study_inputs
from um_charging.investment_experiment import compare_joint_to_enumeration, enumerate_facilities
from um_charging.model import solve
from um_charging.timegrid import POLICIES
from um_charging.validation import check_solution

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def base():
    return json.loads((ROOT / "configs/port_warehouse_investment.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("window", [0, 15, 30, 45, 60])
@pytest.mark.parametrize("policy", POLICIES)
def test_window_changes_eligibility_only_not_transport(base, window, policy):
    original = copy.deepcopy(base)
    data = build_boundary_case(base, 50, window, "two_sites", policy)
    checked = audit_boundary_case(base, data, 50, window, "two_sites", policy)
    assert checked["passed"]
    assert base == original
    assert transport_ledger(data) == transport_ledger(base)
    for vehicle in data["vehicles"]:
        assert vehicle["drive_energy_kwh"] == [5] * 4 + [0] * 4 + [5] * 4 + [0] * 4
        assert [s["activity"] for s in vehicle["timeline"]][4:8] == ["dwell"] * 4
        assert checked["eligible_minutes_per_vehicle"][vehicle["id"]] == {"PORT": 60, "WAREHOUSE": window}
        assert vehicle["charging_site"][4:8] == ["WAREHOUSE"] * (window // 15) + [None] * (4 - window // 15)


@pytest.mark.parametrize("mutation", ["window", "power", "cost", "option", "initial", "drive", "scope", "policy"])
def test_independent_input_audit_rejects_uncontrolled_changes(base, mutation):
    data = build_boundary_case(base, 100, 30, "two_sites", POLICIES[0])
    if mutation == "window":
        data["vehicles"][0]["charging_site"][6] = "WAREHOUSE"
        data["vehicles"][0]["timeline"][6]["plug_allowed"] = True
    elif mutation == "power": data["sites"][0]["available_power_kw"][0] += 1
    elif mutation == "cost": data["sites"][1]["interface_cost"] += 1
    elif mutation == "option": data["sites"][0]["upgrade_options"][0]["additional_power_kw"] += 1
    elif mutation == "initial": data["vehicles"][0]["initial_energy_kwh"] -= 1
    elif mutation == "drive": data["vehicles"][0]["drive_energy_kwh"][0] += 1
    elif mutation == "scope": data["sites"][1]["active"] = False
    elif mutation == "policy": data["connector_policy"] = POLICIES[1]
    assert not audit_boundary_case(base, data, 100, 30, "two_sites", POLICIES[0])["passed"]


@pytest.mark.parametrize("power,window", [(True, 0), (60, 0), (75, 10), (75, -15), (75, 75)])
def test_unrequested_coordinates_rejected(base, power, window):
    with pytest.raises(ValueError): build_boundary_case(base, power, window, "two_sites", POLICIES[0])


def test_zero_window_cannot_repair_insufficient_port_capacity(base):
    # Even the largest paid port upgrade gives only 125 kW < 400/3 kWh / 1h.
    for scope in ("port_only", "two_sites"):
        data = build_boundary_case(base, 50, 0, scope, POLICIES[0])
        result = solve(data)
        assert result["status"] == "infeasible"
        assert check_solution(data, result)["passed"] is None


def test_enumeration_retains_two_tied_hardware_optima(base):
    data = build_boundary_case(base, 50, 30, "two_sites", POLICIES[1])
    result = solve(data)
    checked = check_solution(data, result)
    enumeration = enumerate_facilities(data)
    assert compare_joint_to_enumeration(result, checked, enumeration)["passed"]
    assert enumeration["best_total_cost"] == pytest.approx(105 + 400 / 3)
    hardware = {tuple((s["new_interfaces"], s["upgrade_id"]) for s in allocation) for allocation in enumeration["best_hardware"]}
    assert hardware == {((2, "port_plus_75"), (0, None)), ((2, "port_plus_50"), (1, None))}
    for details in facility_details(data, enumeration["best_hardware"]):
        assert sum(s["interface_cost"] + s["expansion_cost"] for s in details) == 105
        assert details[0]["existing_power_kw"] == 50
        assert details[0]["total_available_power_kw"] in (100, 125)


def test_interface_slot_bottleneck_despite_aggregate_energy_bound(base):
    # P=2 connectors at 100kW for 1h, W=1 connector for .75h: aggregate
    # 100+37.5 exceeds 400/3, yet at most 3 W connector-slots cannot reduce
    # the required P connector-slots from 12 to its available 8.
    data = build_boundary_case(base, 100, 45, "two_sites", POLICIES[0])
    for j, site in enumerate(data["sites"]):
        site.update(interfaces=2 if j == 0 else 1, max_new_interfaces=0, interface_cost=0, upgrade_options=[])
    assert 100 + 50 * .75 > 400 / 3
    assert solve(data)["status"] == "infeasible"
    longer = build_boundary_case(base, 100, 60, "two_sites", POLICIES[0])
    for j, site in enumerate(longer["sites"]):
        site.update(interfaces=2 if j == 0 else 1, max_new_interfaces=0, interface_cost=0, upgrade_options=[])
    result = solve(longer)
    assert result["status"] == "optimal"
    assert check_solution(longer, result)["passed"]


def test_study_contract():
    study, paths = study_inputs(ROOT / "configs/power_window_study.json", ROOT)
    assert study["slot_minutes"] == 15 and len(paths) == 2
