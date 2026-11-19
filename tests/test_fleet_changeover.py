from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math

import pytest
from scipy.optimize import OptimizeResult

from um_charging import energy_boundary as eb
from um_charging import fleet_changeover as fc


ORIGIN = datetime(2021, 1, 4, tzinfo=timezone.utc)
SPEC = eb.SPECS["S300"]
ONE = {"PORT": {"interfaces": 1, "power_kw": 100},
       "WAREHOUSE": {"interfaces": 1, "power_kw": 75}}


def stamp(minute):
    return (ORIGIN + timedelta(minutes=minute)).isoformat()


def trip(start, end, energy, name):
    return dict(start=stamp(start), end=stamp(end), energy_kwh=energy, track_id=name)


def stop(start, end, source, destination, *, arrival=None, departure=None):
    return dict(site="PORT", arrival_track_id=source, next_track_id=destination,
                arrival=stamp(start if arrival is None else arrival),
                next_departure=stamp(end if departure is None else departure),
                start=stamp(start), end=stamp(end))


def truck(name, trips, stops):
    return dict(vehicle_id=name, trips=trips, stops=stops, unmapped_gaps=[])


def day(start, *trucks):
    return dict(date=stamp(start)[:10], start=stamp(start), end=stamp(start + 1440),
                availability="complete_tasks", vehicles=trucks)


def period(*days):
    prices = [0., 0., 100.] + [200.] * 21
    return eb.Period(days, {d["date"]: prices for d in days})


def grid_kwh(result, name, quarter):
    return math.fsum(r["power_kw"] * (r["end_min"] - r["start_min"]) / 60
                     for r in result["schedule"]
                     if r["vehicle_id"] == name and r["reservation_slot"] == quarter)


def adjacent_trucks(previous_start):
    a = truck("a", [trip(0, 15, 11.25, "a0")], [stop(previous_start, previous_start + 15, "a0", "a1")])
    b = truck("b", [trip(0, 60, 11.25, "b0"), trip(75, 120, 0, "b1")],
              [stop(60, 75, "b0", "b1"), stop(120, 135, "b1", "b2")])
    return period(day(0, a, b))


def test_five_minutes_loses_one_third_of_adjacent_quarter():
    p = adjacent_trucks(45)
    result = fc.solve(p, ONE, SPEC, 5, p.keys)
    assert result["stats"]["status"] == "certified"
    assert grid_kwh(result, "a", 3) == pytest.approx(12.5)
    assert grid_kwh(result, "b", 4) == pytest.approx(12.5 * 10 / 15)
    assert grid_kwh(result, "b", 8) == pytest.approx(12.5 * 5 / 15)
    assert result["audit"]["minute_purchase_eur"] == pytest.approx(5 / 12)
    assert result["audit"]["adjacent_change_count"] == 1

    forged = deepcopy(result)
    early, = [r for r in forged["schedule"] if r["reservation_slot"] == 4]
    early["start_min"] = 60.
    early["power_kw"] *= 10 / 15   # Keep energy and bill unchanged.
    with pytest.raises(ValueError, match="changeover gap"):
        fc.replay(p, ONE, SPEC, 5, forged)


def test_idle_quarter_covers_changeover():
    p = adjacent_trucks(30)
    result = fc.solve(p, ONE, SPEC, 5, p.keys)
    assert grid_kwh(result, "b", 4) == pytest.approx(12.5)
    assert result["audit"]["change_count"] == 1
    assert result["audit"]["adjacent_change_count"] == 0
    assert result["audit"]["minute_purchase_eur"] == 0


def test_same_truck_keeps_the_same_plug():
    sole = truck("a", [trip(0, 45, 22.5, "a0")], [stop(45, 75, "a0", "a1")])
    p = period(day(0, sole))
    result = fc.solve(p, ONE, SPEC, 5, p.keys)
    assert grid_kwh(result, "a", 3) == pytest.approx(12.5)
    assert grid_kwh(result, "a", 4) == pytest.approx(12.5)
    assert result["audit"]["change_count"] == 0


def test_same_truck_keeps_the_same_plug_across_midnight():
    before = truck("a", [trip(1410, 1425, 22.5, "a0")],
                   [stop(1425, 1440, "a0", "a1", departure=1455)])
    after = truck("a", [trip(1455, 1470, 0., "a1")],
                  [stop(1440, 1455, "a0", "a1", arrival=1425)])
    p = period(day(0, before), day(1440, after))
    assert len(p.links) == 1
    result = fc.solve(p, ONE, SPEC, 5, p.keys)
    assert grid_kwh(result, "a", 95) == pytest.approx(12.5)
    assert grid_kwh(result, "a", 96) == pytest.approx(12.5)
    assert result["states"][0]["y"] == result["states"][1]["x"] == pytest.approx(138.75)
    assert result["audit"]["change_count"] == 0


def test_zero_changeover_agrees_with_energy_boundary():
    p = adjacent_trucks(45)
    baseline = eb.solve(p, ONE, SPEC, eb.B, p.keys)
    result = fc.solve(p, ONE, SPEC, 0, p.keys)
    assert result["audit"]["purchase_eur"] == pytest.approx(baseline["audit"]["purchase_eur"], abs=1e-6)
    assert result["audit"]["adjacent_change_count"] == 1


def test_per_plug_and_site_limits_in_a_shared_minute():
    a = truck("a", [trip(0, 15, 11.25, "a0")], [stop(15, 30, "a0", "a1")])
    b = truck("b", [trip(0, 15, 5.625, "b0")], [stop(15, 30, "b0", "b1")])
    p = period(day(0, a, b))
    two = {**ONE, "PORT": {"interfaces": 2, "power_kw": 75}}
    result = fc.solve(p, two, SPEC, 5, p.keys)
    assert result["audit"]["site_peak_kw"]["PORT"] == pytest.approx(75)
    assert fc.solve(p, ONE, SPEC, 5)["stats"]["completed_bounds"] == [1, 1]
    forged = deepcopy(result)
    forged["schedule"][0]["plug"] = forged["schedule"][1]["plug"]
    with pytest.raises(ValueError, match="two trucks on one plug"):
        fc.replay(p, two, SPEC, 5, forged)


def test_time_limit_is_unresolved_even_if_small_monetary_gap():
    native = OptimizeResult(status=1, message="time limit", fun=2., mip_dual_bound=1.995, mip_gap=.0025)
    stats = fc._solve_stats(native, False, 2, 300., 1e-6, .01)
    assert stats["status"] == "unresolved"
    assert stats["objective_upper"] == 2.
    assert stats["objective_lower"] == 1.995


@pytest.mark.parametrize("residual, accepted", [(1e-9, True), (1.01e-9, False)])
def test_energy_roundoff_does_not_book_the_plug(monkeypatch, residual, accepted):
    a = truck("a", [trip(0, 15, 11.25, "a0")], [stop(15, 30, "a0", "a1")])
    b = truck("b", [trip(0, 15, 0., "b0")], [stop(15, 30, "b0", "b1")])
    p = period(day(0, a, b))
    _, _, decisions = fc._dispatch_matrix(p, ONE, SPEC, 10, p.keys, eb.B, set())
    idle_energy, = [row[-1] for row in decisions if row[1] == "b"]
    actual_milp = fc.milp

    def add_residual(*args, **kwargs):
        native = actual_milp(*args, **kwargs)
        assert native.x[idle_energy] == 0
        native.x[idle_energy] = residual
        return native

    monkeypatch.setattr(fc, "milp", add_residual)
    if accepted:
        result = fc.solve(p, ONE, SPEC, 10, p.keys)
        assert result["audit"]["passed"]
        assert {row["vehicle_id"] for row in result["schedule"]} == {"a"}
    else:
        with pytest.raises(ValueError, match="two trucks on one plug"):
            fc.solve(p, ONE, SPEC, 10, p.keys)
