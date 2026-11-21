from datetime import datetime, timedelta, timezone
import math

import pytest

from um_charging import energy_boundary as eb
from um_charging.holdout_service import _integer_certificate, audit_service_certificate, solve_service_day
from um_charging.site_sizing import Design


def overnight(draws):
    """Two quarters on opposite sides of midnight; all trucks share one plug."""
    origin = datetime(2021, 1, 4, tzinfo=timezone.utc)

    def at(minute):
        return (origin + timedelta(minutes=minute)).isoformat()

    days = []
    for i, (start, end) in enumerate(((1395, 1425), (1455, 1485))):
        trucks = []
        for truck, draw in draws.items():
            trip = dict(start=at(start), end=at(end), energy_kwh=draw if i == 0 else 0.,
                        track_id=f"{truck}-{i}")
            stop = dict(site="PORT", arrival_track_id=f"{truck}-0", next_track_id=f"{truck}-1",
                        arrival=at(1425), next_departure=at(1455), start=at(max(1425, i * 1440)),
                        end=at(min(1455, (i + 1) * 1440)))
            trucks.append(dict(vehicle_id=truck, trips=[trip], stops=[stop], unmapped_gaps=[]))
        days.append(dict(date=at(1440 * i)[:10], start=at(1440 * i), end=at(1440 * (i + 1)),
                         availability="complete_tasks", vehicles=trucks))
    return eb.Period(days, {d["date"]: [1.] * 24 for d in days})


def test_daily_order_retains_weekly_feasible_extension_and_all_locks():
    period = overnight({"10": 22.5, "2": 22.5})
    first, second = sorted(period.cases)
    design = Design(1, 50, 0)
    result = solve_service_day(period, design, first, {}, set(), math.inf)
    assert result["audit"]["passed"] and result["stats"]["status"] == "certified"
    assert result["stats"]["completed_bounds"] == [1, 1]
    assert result["stats"]["integer_score_bounds"] == [6, 6]
    assert audit_service_certificate(period, first, {}, set(), result)["status"] == "certified"
    assert (first, "2") in eb.selected(result) and (first, "10") not in eb.selected(result)
    assert (second, "2") in eb.selected(result)  # day one alone has insufficient energy
    assert result["audit"]["site_grid_kwh"]["PORT"] == pytest.approx(25.)
    locked = {key: key in eb.selected(result) for key in period.keys if key[0] == first}
    last = solve_service_day(period, design, second, locked, {(first, "10")}, math.inf)
    assert eb.selected(last) == {(first, "2"), (second, "2"), (second, "10")}
    assert last["stats"]["completed_bounds"] == [2, 2]
    with pytest.raises(ValueError, match="all earlier"):
        solve_service_day(period, design, second, {(first, "2"): True}, set(), math.inf)
    result["stats"]["integer_score_bounds"][1] += 1
    with pytest.raises(ValueError, match="certificate"):
        audit_service_certificate(period, first, {}, set(), result)


def test_daily_overlap_precedes_numeric_id_and_ignores_prices():
    period = overnight({"10": 22.5, "2": 22.5})
    first = min(period.cases)
    for price in (-500., 200.):
        period.prices = {date: [price] * 24 for date in period.cases}
        result = solve_service_day(period, Design(1, 50, 0), first, {}, {(first, "10")}, math.inf)
        assert result["stats"]["integer_score_bounds"] == [13, 13]
        assert {k for k in eb.selected(result) if k[0] == first} == {(first, "10")}
        assert result["audit"]["purchase_eur"] == pytest.approx(25. * price / 1000)


def test_completion_count_precedes_overlap_and_requires_native_bounds():
    period = overnight({"10": 22.5, "2": 11.25, "3": 11.25})
    first = min(period.cases)
    result = solve_service_day(period, Design(1, 50, 0), first, {}, {(first, "10")}, math.inf)
    assert result["stats"]["completed_bounds"] == [2, 2]
    assert {k for k in eb.selected(result) if k[0] == first} == {(first, "2"), (first, "3")}
    expired = solve_service_day(period, Design(1, 50, 0), first, {}, set(), 0.)
    assert expired["stats"]["status"] == "unresolved" and expired["audit"] is None
    assert expired["stats"]["integer_score_bounds"] == [None, None]
    assert _integer_certificate(None, 7) == [7, None]
    assert _integer_certificate(-7.8, 7) == [7, 7]
