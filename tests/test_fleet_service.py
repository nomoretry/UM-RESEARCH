from copy import deepcopy
from itertools import combinations

import pytest

from um_charging.fleet_service import audit, build_case, dispatch, immediate, max_service, menu
from um_charging.fleet_design import failure_reasons, select_build


def duty(energy=5, stop_end="09:15", vehicles=("A", "B")):
    def stamp(wall):
        return "2021-09-14T"+wall+":00+02:00"

    return {
        "date": "2021-09-14", "start": stamp("00:00"),
        "end": "2021-09-15T00:00:00+02:00", "split": "design",
        "vehicles": [
            {"vehicle_id": v, "trips": [{"track_id": v+"1", "start": stamp("08:00"),
                                          "end": stamp("09:00"), "energy_kwh": energy}],
             "stops": [{"site": "WAREHOUSE", "arrival": stamp("09:00"),
                        "start": stamp("09:00"), "end": stamp(stop_end)}]} for v in vehicles],
    }


def test_exhaustive_single_quarter_assignments_and_all_facilities():
    day = duty()
    case = build_case(day)
    grid_per_truck = 5 / .9
    allowed = []
    for cost, hardware in menu():
        wh = hardware["WAREHOUSE"]
        # Independent explicit subset enumeration for one physical quarter.
        subsets = [group for n in range(3) for group in combinations(("A", "B"), n)
                   if n <= wh["interfaces"] and n*grid_per_truck <= wh["power_kw"]/4]
        best = max(map(len, subsets))
        assert max_service(case, hardware)["completed_count"] == best
        assert (dispatch(case, hardware)["status"] == "optimal") == (best == 2)
        if best == 2:
            allowed.append(cost)
    design = select_build([day], [0])
    assert design["investment"] == min(allowed) == 30
    assert design["ties"] == [dict(PORT=dict(interfaces=1, power_kw=100), WAREHOUSE=dict(interfaces=2, power_kw=75))]
    assert select_build([day], [0], port_additions_only=True)["covered_vehicle_day_scenarios"] == 1
    with pytest.raises(ValueError, match="design"):
        select_build([{**day, "split":"holdout"}], [0])


def test_release_overlap_power_and_audit():
    hardware = menu()[0][1]
    day = duty(energy=5, vehicles=("A",))
    assert dispatch(build_case(day, 9), hardware)["status"] == "infeasible"  # 6 min at 50 kW x .9 = 4.5
    assert dispatch(build_case(day, 8), hardware)["audit"]["passed"]
    case = build_case(duty(energy=5))
    both = dispatch(case, menu()[-1][1])["schedule"]
    assert any("designated" in issue for issue in audit(case, hardware, both)["errors"])
    cap = deepcopy(menu()[-1][1])
    cap["WAREHOUSE"]["power_kw"] = 10
    assert any("capacity" in issue for issue in audit(case, cap, both)["errors"])


def test_negative_price_is_settled_against_same_task_energy():
    case = build_case(duty(energy=9, stop_end="11:00", vehicles=("A",)))
    prices = [0.]*24
    prices[9], prices[10] = 200, -20
    hardware = menu()[0][1]
    first = immediate(case, hardware, prices)
    timed = dispatch(case, hardware, prices)
    assert first["audit"]["purchase_eur"] == pytest.approx(2)
    assert timed["objective"] == timed["dual_bound"] == pytest.approx(-.2)
    assert timed["mip_gap"] == 0


def test_event_bounds_signed_energy_and_no_synthetic_midnight_delay():
    day = duty(energy=135, vehicles=("A",))
    vehicle = day["vehicles"][0]
    early = {"site":"WAREHOUSE","arrival":"2021-09-13T23:00:00+02:00",
             "start":day["start"], "end":vehicle["trips"][0]["start"]}
    vehicle["stops"].insert(0,early)
    case = build_case(day, 45)
    assert case["trucks"]["A"]["windows"][0][0] == 0
    assert dispatch(case, menu()[0][1])["audit"]["passed"]
    vehicle["stops"].clear()
    bad = build_case(day)
    assert failure_reasons(bad,menu()[0][1])[0]["track_id"] == "A1"
    assert max_service(bad,menu()[0][1])["completed_count"] == 0
    vehicle["trips"][0]["energy_kwh"] = -15
    assert dispatch(build_case(day),menu()[0][1])["status"] == "infeasible"
