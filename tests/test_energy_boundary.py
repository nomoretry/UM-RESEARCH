import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from um_charging import energy_boundary as eb


def toy(vehicles=("1",)):
    origin = datetime(2021, 1, 4, tzinfo=timezone.utc)
    def stamp(hours):
        return (origin + timedelta(hours=hours)).isoformat()
    days = []
    for index, (start, end, draw) in enumerate(((19, 20, 45), (28, 29, 0))):
        d = stamp(24*index)[:10]
        trucks = []
        for v in vehicles:
            trip = dict(start=stamp(start), end=stamp(end), energy_kwh=draw, track_id=v+str(index))
            stop = dict(site="PORT", arrival_track_id=v+"0", next_track_id=v+"1",
                        arrival=stamp(20), next_departure=stamp(28), start=stamp(max(20,24*index)),
                        end=stamp(min(28,24*(index+1))))
            trucks.append(dict(vehicle_id=v,trips=[trip],stops=[stop],unmapped_gaps=[]))
        days.append(dict(date=d,start=stamp(index*24),end=stamp((index+1)*24),
                         availability="complete_tasks",vehicles=trucks))
    prices = {days[0]["date"]:[200.]*24, days[1]["date"]:[20.]*24}
    return eb.Period(days,prices)


def hardware(n=1, power=50):
    return {s:dict(interfaces=n,power_kw=power) for s in eb.SITES}


def test_manual_two_days():
    p = toy()
    for rule,bill,midnight in ((eb.A,10,150),(eb.B,1,105),(eb.C,10,None)):
        result = eb.solve(p,hardware(),eb.DEFAULT_SPEC,rule,p.keys)
        assert result["audit"]["purchase_eur"] == pytest.approx(bill)
        if midnight is not None:
            assert result["states"][0]["y"] == pytest.approx(midnight)
        assert all(abs(s["residual_kwh"])<=1e-6 for s in result["audit"]["segments"])
    broken = eb.solve(p,hardware(),eb.DEFAULT_SPEC,eb.B,{min(p.keys)})
    assert broken["audit"]["purchase_eur"] == pytest.approx(10)


def test_calendar_breaks():
    days = deepcopy(toy().days)
    days[0]["vehicles"][0]["stops"][0]["next_track_id"] = "other"
    chains,links,breaks = eb.calendar(days)
    assert list(map(len,chains))==[1,1] and not links
    assert breaks[0]["unmatched_next_track_ids"]==["other"]
    days[1]["date"] = "2021-01-06"
    chains,links,breaks = eb.calendar(days)
    assert not links and breaks[0]["intervening_dates"]==[["2021-01-05","outside supplied calendar"]]


def test_corrupted_midnight():
    p = toy()
    result = eb.solve(p,hardware(),eb.DEFAULT_SPEC,eb.B,p.keys)
    result["states"][1]["x"] += 1
    with pytest.raises(ValueError,match="Replay failed"):
        eb.audit(p,hardware(),eb.DEFAULT_SPEC,eb.B,result)


@pytest.mark.parametrize("h,reason", [(hardware(1,100),"connectors"),(hardware(2,50),"site kW")])
def test_corrupted_resources(h,reason):
    p = toy(("1","2"))
    result = eb.solve(p,hardware(2,100),eb.DEFAULT_SPEC,eb.A,p.keys)
    # Both trucks need 50 grid kWh. Force both to use the same four quarters.
    d = p.days[0]["date"]
    result["schedule"] = [dict(date=d,vehicle_id=v,site="PORT",start_min=q*15,
                               end_min=(q+1)*15,reservation_slot=q,power_kw=50.)
                          for v in ("1","2") for q in range(80,84)]
    with pytest.raises(ValueError,match=reason):
        eb.audit(p,h,eb.DEFAULT_SPEC,eb.A,result)


def test_registered_regressions():
    days = eb.read_json(eb.WEEKS)["days"]
    reference = eb.read_json(eb.REFERENCE)
    native = eb.csv_rows(eb.NATIVE)
    prices = {d["date"]:eb.hourly_curve(native,d) for d in days if d["availability"]=="complete_tasks"}
    refs = {r["date"]:r for r in reference["days"] if r["date"] in prices}
    periods = [eb.Period(g,prices) for g in eb.components(days,eb.calendar(days)[1])]
    historic = next(r for r in eb.read_json(eb.GAP)["fleet"] if r["capacity_kwh"]==900)
    for facility,h in reference["hardware"].items():
        total_300 = total_900 = 0
        for p in periods:
            first = eb.solve(p,h,eb.DEFAULT_SPEC,eb.A)
            keys = eb.selected(first)
            total_300 += len(keys)
            total_900 += len(eb.selected(eb.solve(p,h,eb.SPECS["S900c"],eb.A)))
            matched = {(d,v) for d in p.cases for v in refs[d]["matched_ids"]}
            fixed = eb.solve(p,h,eb.DEFAULT_SPEC,eb.A,matched)
            for d in p.cases:
                assert sum(k[0]==d for k in keys)==refs[d]["facilities"][facility]["max_vehicle_days"]
                bill = fixed["audit"]["daily_eur"].get(d,0.)
                expected = refs[d]["prices"]["concurrent"][facility]["optimal_eur"] if refs[d]["matched_ids"] else 0.
                assert abs(bill-expected)<=1e-6
        assert total_300==54
        assert total_900==historic[facility]=={"one":62,"two":63}[facility]


def test_real_pilots():
    result = eb.run(pilot=True)
    for rules in result["pilots"].values():
        assert all(abs(day["delta_eur"])<=1e-6 for day in rules[eb.A]["daily"])
        assert len(eb.selected(rules[eb.B]))>=len(eb.selected(rules[eb.A]))
        assert rules[eb.B]["audit"]["purchase_eur"]<=rules[eb.A]["audit"]["purchase_eur"]+1e-6
        for r in rules.values():
            assert r["stats"]["status_code"]==r["physical_stats"]["status_code"]==0
            assert r["audit"]["passed"]
