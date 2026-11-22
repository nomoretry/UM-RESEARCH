from copy import deepcopy

import pytest

from test_site_sizing import two_sites
from um_charging import m10_rolling as rolling
from um_charging import site_sizing as ss


def _week():
    first = two_sites(9)
    left = first.days[0]
    d1, d2 = left["date"], "2021-01-05"
    right = deepcopy(left)
    right = _shift_day(right, d1, d2)
    left["week_start"] = right["week_start"] = d1
    right["vehicles"][0]["trips"][0]["track_id"] = "day2-first"
    left["vehicles"][0]["stops"][-1]["next_track_id"] = "day2-first"
    # The true next departure is present in the source field for the weekly audit.
    left["vehicles"][0]["stops"][-1]["next_departure"] = right["vehicles"][0]["trips"][0]["start"]
    return ss.eb.Period([left, right], {d1:first.prices[d1], d2:first.prices[d1]})


def _shift_day(value, left, right):
    if isinstance(value, dict):
        return {k:_shift_day(v, left, right) for k,v in value.items()}
    if isinstance(value, list):
        return [_shift_day(v, left, right) for v in value]
    if isinstance(value, str) and value.startswith("2021-01-05T"):
        return value.replace("2021-01-05", "2021-01-06")
    return value.replace(left, right) if isinstance(value, str) else value


def test_daily_information_and_weekly_meter_replay():
    week = _week()
    d1,d2 = week.cases
    reference = set(week.keys)
    one = rolling.rolling_day_period(week, d1, reference)
    original = deepcopy(one.__dict__)
    week.days[1]["vehicles"] = []
    week.prices[d2] = [-10_000.] * 24
    week.days[0]["vehicles"][0]["stops"][-1]["next_track_id"] = "future-identifier"
    assert rolling.rolling_day_period(week,d1,reference).__dict__ == original
    assert set(one.prices) == {d1} and "next_departure" not in repr(one)
    design = ss.Design(1,50,0)
    jobs = rolling.rolling_requests(week,design,design.caps,reference)
    pairs = []
    for r in jobs:
        day = r.week[4:]
        local = rolling.rolling_day_period(week,day,reference)
        solved = ss.solve(local,design,caps=r.caps,fixed=r.fixed)
        pairs.append((day,solved))
    result = rolling.rolling_week(week,design,design.caps,reference,pairs)
    assert result["status"] == "certified"
    assert result["audit"]["site_grid_kwh"]["PORT"] == pytest.approx(20)
    assert result["audit"]["site_quarter_peak_kw"]["PORT"] == pytest.approx(40)
    assert len(result["audit"]["segments"]) == 1
    assert all(r["x"] == pytest.approx(150) and r["y"] == pytest.approx(150) for r in result["states"])
    assert result["purchase_upper"] == pytest.approx(sum(p["audit"]["purchase_eur"] for _,p in pairs))
    for _,p in pairs:
        p["stats"]["objective_lower"] = p["audit"]["purchase_eur"] - .06
    precise = rolling.rolling_week(week,design,design.caps,reference,pairs)
    assert precise["status"] == "certified" and precise["absolute_gap"] == pytest.approx(.12)
    pairs[0][1]["stats"]["status"] = "bounded"
    wide = rolling.rolling_week(week,design,design.caps,reference,pairs)
    assert wide["status"] == "unresolved" and wide["absolute_gap"] == pytest.approx(.12)
    assert wide["audit"]["passed"]


def test_empty_week_has_no_calls_and_fixed_infeasible_is_joint_failure():
    week = _week()
    design = ss.Design(0,0,0)
    assert rolling.rolling_requests(week,design,design.caps,set()) == []
    zero = rolling.rolling_week(week,design,design.caps,set(),[])
    assert zero["status"] == "certified" and zero["purchase_upper"] == 0
    jobs = rolling.rolling_requests(week,design,design.caps,week.keys)
    pairs=[(r.week, dict(stats=dict(status="infeasible",objective_lower=None,objective_upper=None),audit=None))
           for r in jobs]
    out = rolling.rolling_week(week,design,design.caps,week.keys,pairs)
    assert out["status"] == "infeasible" and out["audit"] is None and out["purchase_upper"] is None
