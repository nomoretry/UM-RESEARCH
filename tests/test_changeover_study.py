from um_charging.changeover_study import critical_minutes, facility_menu, hardware_key, recovery
from um_charging.day_ahead import ROOT, read_json
from um_charging.eligibility_stress import make_reference
from um_charging.facility_month import DELAY, fixed_cases
import pytest


def test_registered_hardware_menu_and_limits():
    reference = make_reference(read_json(ROOT / read_json(DELAY)["base_config"]))
    menu = facility_menu(reference)
    assert len(menu) == len({hardware_key(hardware) for _, hardware in menu}) == 54
    assert menu[0] == (0, {"PORT": {"interfaces": 1, "power_kw": 100},
                          "WAREHOUSE": {"interfaces": 1, "power_kw": 75}})
    registered = {(leg, cost): critical_minutes(leg, {
        s["id"]: {"interfaces": s["interfaces"], "power_kw": s["available_power_kw"][0]}
        for s in case["sites"]}, case) for leg, cost, case in fixed_cases()}
    high = max(leg for leg, _ in registered)
    assert registered[20, 40] == pytest.approx(50/3)
    assert registered[20, 50] == pytest.approx(10/3)
    assert registered[high, 40] is None
    assert registered[high, 50] == pytest.approx(2.43797916822588)


def test_retained_build_minimum_keeps_all_ties_and_stops_at_last_cost_tier():
    def hardware(n, m):
        return {"PORT": {"interfaces": n, "power_kw": 100}, "WAREHOUSE": {"interfaces": m, "power_kw": 75}}
    menu = [(40, hardware(3, 1)), (50, hardware(2, 2)), (60, hardware(2, 3)),
            (60, hardware(3, 2)), (70, hardware(3, 3))]
    def status(build, delay):
        assert delay == 5
        feasible = build != hardware(2, 2)
        return {"status": "optimal" if feasible else "infeasible"}
    result, tested = recovery(menu, 5, 50, status)
    assert [r["total_investment"] for r in result["from_initial_1_1"]] == [40]
    assert [r["additional_investment"] for r in result["retain_installed_2_2"]] == [10, 10]
    assert len(tested) == 4
    assert result["untested_strictly_costlier"] == 1
