import copy
import json
from collections import Counter

import pytest

from reduced_milan import HERE, solve, timelines
from verify_reduced import check_solution, enumerate_facilities, reachable_energy


@pytest.fixture
def case():
    data = json.loads((HERE / "reduced_milan.json").read_text(encoding="utf-8"))
    return data, timelines(data)


def test_task_chain(case):
    _, routes = case
    assert set(routes) == {"1", "2"}
    for slots in routes.values():
        assert Counter(place for action, place in slots if action == "service") == {1: 1, 4: 5, 5: 3, 6: 3}
        assert [leg for action, leg in slots if action == "travel"] == [(1, 4), (4, 5), (5, 6), (6, 1)]
        assert slots[16:] == [("idle", 1)] * 4


@pytest.mark.parametrize("window,ac,dc,annual", [
    ("two_hours", 2, 0, 388), ("ninety_minutes", 1, 1, 1746), ("one_hour", 0, 2, 3104)
])
def test_hardware_and_certificate(case, window, ac, dc, annual):
    data, routes = case
    slots = data["plug_slots"][window]
    result = solve(data, slots, routes)
    options = enumerate_facilities(data, slots, routes)
    check_solution(data, slots, routes, result, options)
    assert result["units"] == {"ac_units": ac, "dc_units": dc}
    assert result["annual_eur"] == pytest.approx(annual)
    assert len(options) == 9


def test_no_plug_and_energy_shortfall(case):
    data, routes = case
    for slots, initial in [([], data["initial_kwh"]), (data["plug_slots"]["thirty_minutes"], data["initial_kwh"]),
                           (data["plug_slots"]["two_hours"], data["min_kwh"])]:
        params = {**data, "initial_kwh": initial}
        result = solve(params, slots, routes)
        assert result["status"] == "infeasible"
        check_solution(params, slots, routes, result, enumerate_facilities(params, slots, routes))
    with pytest.raises(ValueError, match="intersects service"):
        solve(data, [0], routes)


def test_checker_rejects_invalid_dispatch(case):
    data, routes = case
    slots = data["plug_slots"]["two_hours"]
    result = solve(data, slots, routes)
    options = enumerate_facilities(data, slots, routes)
    for field, new_value, reason in [("slot", 0, "conflicts"), ("grid_kw", 9999, "power")]:
        changed = copy.deepcopy(result)
        changed["connections"][0][field] = new_value
        with pytest.raises(ValueError, match=reason):
            check_solution(data, slots, routes, changed, options)
    changed = copy.deepcopy(result)
    changed["energy_kwh"]["1"][4] += 1
    with pytest.raises(ValueError, match="SOC trajectory"):
        check_solution(data, slots, routes, changed, options)


def test_figure4_equipment_windows(case):
    data, routes = case
    curves = json.loads((HERE / "figure4_power.json").read_text())["soc_fraction_and_grid_kw"]
    for name, slots in data["plug_slots"].items():
        result = solve(data, slots, routes, curves)
        choices = enumerate_facilities(data, slots, routes, curves)
        check_solution(data, slots, routes, result, choices, curves)
        if name in ("two_hours", "ninety_minutes"):
            assert result["units"] == {"ac_units": 1, "dc_units": 1}
            assert result["annual_eur"] == pytest.approx(1746)
        else:
            assert result["status"] == "infeasible"


def test_low_soc_charging_limit_and_graph_resolution(case):
    data, routes = case
    curves = json.loads((HERE / "figure4_power.json").read_text())["soc_fraction_and_grid_kw"]
    slots = data["plug_slots"]["two_hours"]
    choices = enumerate_facilities(data, slots, routes, curves)
    result = solve(data, slots, routes, curves)
    first = next(row for row in result["connections"] if row["slot"] == slots[0])
    first["grid_kw"] = data["equipment_grid_kw"][first["kind"]]
    with pytest.raises(ValueError, match="SOC-dependent"):
        check_solution(data, slots, routes, result, choices, curves)
    ac = dict.fromkeys(slots, "ac_units")
    assert reachable_energy(data, routes["1"], ac, curves)[1] == pytest.approx(42.289325, abs=1e-6)
    curves["ac_units"][1][0] = 0.09
    assert reachable_energy(data, routes["1"], ac, curves)[1] == pytest.approx(42.749205, abs=1e-6)
