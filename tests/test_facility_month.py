import math

import pytest

from um_charging.facility_month import fixed_cases, solve_day
from um_charging.model import solve


def test_design_preserves_service_and_only_changes_energy_and_plugs():
    cases = list(fixed_cases())
    assert len(cases) == 4
    for leg, investment, data in cases:
        assert data["slot_hours"] == .25
        port, wh = data["sites"]
        assert (port["available_power_kw"], wh["available_power_kw"]) == ([100] * 16, [75] * 16)
        assert investment == (40 if port["interfaces"] == 3 else 50)
        for v in data["vehicles"]:
            assert sum(v["drive_energy_kwh"]) == pytest.approx(2 * leg)
            assert v["initial_energy_kwh"] == v["energy_max_kwh"] == 100
            assert [i for i,s in enumerate(v["charging_site"]) if s == "PORT"] == [12,13,14,15]
            assert [i for i,s in enumerate(v["charging_site"]) if s == "WAREHOUSE"] == (
                [4,5,6,7] if v["id"] == "V3" else [7])


@pytest.mark.parametrize("wh,port", [(100,200), (200,100), (-10,-10)])
def test_single_day_endpoints_and_capacity_shortfall(wh, port):
    rates = [0]*4 + [wh]*4 + [0]*4 + [port]*4
    curve = [{"price_eur_per_mwh": r} for r in rates]
    for leg, _, case in fixed_cases():
        wp = case["sites"][1]["interfaces"]
        total = 6 * leg / .9
        max_wh = leg / .9 + (12.5 if wp == 1 else 18.75)
        if wp == 1 and leg > 20:
            assert total - max_wh - 100 == pytest.approx(2.1479383664)
            assert solve(case)["status"] == "infeasible"
            continue
        _, _, bill, peaks = solve_day(case, curve)
        allocation = max_wh if wh <= port else total - 100
        assert peaks["trips_completed"] == 6 and peaks["checks_passed"]
        assert all(math.isclose(e,100) for e in peaks["terminal_kwh"].values())
        assert bill["purchase_eur"] == pytest.approx((wh * allocation + port * (total-allocation)) / 1000)
        lower_peak = total - allocation  # Port window is one hour.
        if wp == 2:
            # Late trucks each need >=3 port slots. Together they receive
            # <=18.75 kWh at the warehouse. While V3 uses its two port
            # slots they can take only 25 kWh on the other connector.
            late_pair_bound = (4 * leg / .9 - 18.75 - 25) / .5
            lower_peak = max(lower_peak, late_pair_bound)
        assert peaks["site_peak_kw"]["PORT"] == pytest.approx(lower_peak)
