"""Replay a four-hour cycle against hand-calculated service, power and price bounds."""
from datetime import datetime, timedelta, timezone

import pytest

from um_charging.day_ahead import (
    STUDY, aligned_prices, charge_on_arrival, evaluate, frozen_case, read_json,
)
from um_charging.model import solve


@pytest.fixture
def case():
    return frozen_case(read_json(STUDY / "case.json"))


def market(prices):
    origin = datetime(2025, 1, 6, 8, tzinfo=timezone(timedelta(hours=1)))
    return {"market_area": "test", "timezone": "synthetic", "source_url": "synthetic test vector",
            "currency_unit": "EUR/MWh", "intervals": [
                {"start": (origin + timedelta(hours=i)).isoformat(),
                 "end": (origin + timedelta(hours=i+1)).isoformat(), "price_eur_per_mwh": rate}
                for i, rate in enumerate(prices)]}


def test_policies_exact_energy_cost_and_peak_bounds(case):
    # Synthetic unit-test prices only: the final port hour pays for grid draw.
    curve = aligned_prices(market([80, 30, 100, -10]), case)
    rates = [r["price_eur_per_mwh"] for r in curve]
    assert rates == [80] * 4 + [30] * 4 + [100] * 4 + [-10] * 4
    immediate = evaluate(case, curve, "immediate", charge_on_arrival(case))
    peak = evaluate(case, curve, "peak_shaving", solve(case, minimize_site_peak=True))
    priced = evaluate(case, curve, "day_ahead", solve(case, market_prices_eur_per_mwh=rates))
    for row in [immediate, peak, priced]:
        assert row["trips_completed"] == 6 and row["vehicles_completed"] == 3
        assert row["terminal_kwh"] == pytest.approx({"V1": 100, "V2": 100, "V3": 100})
        assert row["grid_energy_kwh"] == pytest.approx(120 / .9)
        assert row["checks_passed"]
    assert immediate["site_peak_kw"] == pytest.approx({"PORT": 150, "WAREHOUSE": 50})
    assert immediate["purchase_eur"] == pytest.approx((20 * 30 - 100 * 10) / .9 / 1000)
    # At most V3's first-leg 20 kWh battery deficit can be filled at the
    # warehouse. At least 100/.9 kWh must therefore pass through PORT in 1 h.
    assert peak["objective"] == pytest.approx(100 / .9)
    assert priced["objective"] == pytest.approx(-10 * 120 / .9 / 1000)
    assert priced["site_energy_kwh"]["WAREHOUSE"] == pytest.approx(0)
    for row in [peak, priced]:
        assert row["status"] == "optimal"
        assert row["dual_bound"] == pytest.approx(row["objective"])
        assert row["mip_gap"] == pytest.approx(0)


@pytest.mark.parametrize("mutation", ["overlap", "gap", "missing_offset", "nonfinite", "quarter_split", "short"])
def test_reject_unusable_price_intervals(case, mutation):
    data = market([0, 1, 2, 3])
    intervals = data["intervals"]
    if mutation == "overlap":
        intervals[1]["start"] = intervals[0]["start"]
    elif mutation == "gap":
        del intervals[1]
    elif mutation == "missing_offset":
        intervals[0]["start"] = "2025-01-06T08:00:00"
    elif mutation == "nonfinite":
        intervals[0]["price_eur_per_mwh"] = float("inf")
    elif mutation == "quarter_split":
        intervals[0]["end"] = "2025-01-06T08:25:00+01:00"
    else:
        del intervals[-1]
    with pytest.raises(ValueError):
        aligned_prices(data, case)


def test_checker_rejects_bad_dispatch_and_bad_objective(case):
    curve = aligned_prices(market([1, 2, 3, 4]), case)
    immediate = charge_on_arrival(case)
    immediate["solution"]["energy_kwh"][0][-1] -= 1
    with pytest.raises(ValueError, match="physical audit"):
        evaluate(case, curve, "immediate", immediate)
    result = solve(case, minimize_site_peak=True)
    result["objective"] += 1
    with pytest.raises(ValueError, match="objective differs"):
        evaluate(case, curve, "peak_shaving", result)
