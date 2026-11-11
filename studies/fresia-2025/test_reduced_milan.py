import copy
import json
from collections import Counter

import pytest

from reduced_milan import HERE, solve, timelines
from verify_reduced import check_solution, enumerate_facilities


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
