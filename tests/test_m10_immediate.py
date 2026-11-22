from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from um_charging import m10_immediate as immediate
from um_charging.fleet_service import VehicleSpec
from um_charging.site_sizing import Design, meter_replay


PORT, WAREHOUSE = immediate.SITES


def truck(trips, windows):
    return dict(trips=[(a,b,energy,str(i)) for i,(a,b,energy) in enumerate(trips)], windows=windows)


def period(cases, *, rates=None, linked=True):
    dates = [(date(2021, 1, 4) + timedelta(days=i)).isoformat() for i in range(len(cases))]
    offsets = {d:i*1440 for i,d in enumerate(dates)}
    duties = {(d,v) for d,case in zip(dates,cases,strict=True) for v in case}
    windows = defaultdict(list)
    for d,case in zip(dates,cases,strict=True):
        for v,record in case.items():
            for a,b,site in record["windows"]:
                spans = windows[v,site,"arrival"]
                if spans and spans[-1][1] == offsets[d]+a:
                    spans[-1] = (spans[-1][0],offsets[d]+b)
                else:
                    spans.append((offsets[d]+a,offsets[d]+b))
    chains = [[key for key in sorted(duties) if key[1]==v] for v in sorted({v for _,v in duties})]
    return SimpleNamespace(days=[dict(date=d,week_start=dates[0]) for d in dates],
                           cases={d:dict(trucks=t) for d,t in zip(dates,cases,strict=True)},
                           prices=dict(zip(dates, rates or [[100.]*24 for _ in dates],strict=True)),
                           offset=offsets, chains=chains if linked else [[key] for key in sorted(duties)],
                           keys=duties, windows=windows, nights=[])


def price(result, port=0., warehouse=0., factor=1.):
    return immediate.surplus_costs(result, purchase_factor_to_2025=factor,
                                   volumetric_rates_eur_2025_per_kwh={PORT:port, WAREHOUSE:warehouse})


def test_full_meter_terminal_surplus_and_tariff_weighted_mean():
    curve = [0.]*24
    curve[1],curve[2] = -100.,50.
    p = period([{"1":truck([(0,60,9)],[(60,75,PORT),(120,165,WAREHOUSE)])}], rates=[curve])
    d = Design(1,20,20)
    replay = immediate.simulate_week(p,d,p.keys)
    assert replay["summary"]["same_service"]
    assert replay["audit"]["site_grid_kwh"] == {PORT:5.,WAREHOUSE:15.}
    assert replay["audit"]["site_quarter_peak_kw"] == {PORT:20.,WAREHOUSE:20.}
    assert replay["audit"]["purchase_eur"] == pytest.approx(.25)
    assert replay["days"][0]["end_soc_kwh"] == pytest.approx(159.)
    disclosure = price(replay,.2,.02,factor=2.)
    segment, = disclosure["segments"]
    assert segment["terminal_excess_kwh"] == pytest.approx(9.)
    assert segment["terminal_excess_grid_kwh"] == pytest.approx(10.)
    assert segment["weighted_mean_eur_2025_per_kwh"] == pytest.approx((.25*2 + 5*.2 + 15*.02)/20)
    assert disclosure["days"][0]["terminal_excess_cost_eur_2025"] == pytest.approx(.9)
    assert disclosure["summary"]["terminal_excess_purchase_eur_2025"] == pytest.approx(.25)
    assert disclosure["summary"]["terminal_excess_volumetric_eur_2025"] == pytest.approx(.65)
    assert immediate.replay_week(p,d,p.keys,replay["schedule"]) == replay
    assert replay["audit"]["purchase_eur"] == pytest.approx(.25)


def test_numeric_fifo_and_no_new_vehicle_on_the_same_quarter_plug():
    p = period([{"10":truck([(0,15,0)],[(60,90,PORT)]), "2":truck([(0,15,0)],[(60,65,PORT)])}])
    result = immediate.simulate_week(p,Design(1,20,0),p.keys)
    assert [(r["vehicle_id"],r["start_min"],r["end_min"]) for r in result["schedule"]] == [
        ("2",60,65),("10",75,90)]
    bad = deepcopy(result["schedule"])
    bad[1].update(start_min=65,end_min=70,reservation_slot=4)
    with pytest.raises(ValueError,match="two trucks on one plug"):
        immediate.replay_week(p,Design(1,20,0),p.keys,bad)


def test_two_plugs_split_from_remaining_power_and_redistribute_at_full_soc():
    p = period([{"1":truck([(0,15,0)],[(60,75,PORT)]),"2":truck([(0,15,0)],[(60,75,PORT)])}])
    spec = VehicleSpec(capacity_kwh=151)
    result = immediate.simulate_week(p,Design(2,50,0),p.keys,spec=spec)
    first,second = result["schedule"]
    assert first["vehicle_id"]=="1" and second["vehicle_id"]=="2"
    assert first["plug"] != second["plug"] and first["end_min"] == second["start_min"]
    assert first["power_kw"] == second["power_kw"] == 50.
    assert result["audit"]["used_plugs"][PORT] == 2
    assert result["audit"]["site_grid_kwh"][PORT] == pytest.approx(2/.9)


def test_failure_retains_meter_and_other_trucks_no_restart_until_next_segment():
    day1 = {"1":truck([(0,15,9),(120,150,170)],[(15,75,PORT),(150,225,PORT)]),
            "2":truck([(0,15,0)],[(150,225,WAREHOUSE)])}
    later = {"1":truck([(0,15,0)],[(30,45,PORT)])}
    p = period([day1,later,later,later])
    # Omit the third date from R. Fourth date starts a new independent segment.
    fixed = {key for key in p.keys if key[0] != p.days[2]["date"]}
    result = immediate.simulate_week(p,Design(1,20,20),fixed)
    one = [r for r in result["days"] if r["vehicle_id"] == "1"]
    assert [r["status"] for r in one] == ["trip_infeasible","blocked_by_failed_trip","complete"]
    assert one[0]["last_observed_soc_kwh"] == pytest.approx(159.)
    assert one[0]["failure"]["projected_arrival_soc_kwh"] == pytest.approx(-11.)
    assert one[1]["terminal_excess_kwh"] is None
    assert one[2]["start_soc_kwh"] == pytest.approx(150.)
    assert result["audit"]["site_grid_kwh"] == {PORT:25.,WAREHOUSE:25.}
    assert not result["summary"]["same_service"]
    fees = price(result)["summary"]
    assert fees["unobserved_segments"] == 1
    assert fees["terminal_excess_cost_eur_2025"] is None
    assert fees["known_terminal_excess_cost_eur_2025"] == pytest.approx(3.)


def test_midnight_actual_soc_and_day_attribution_only_once():
    p = period([{"1":truck([(1320,1380,9)],[(1380,1440,PORT)])},
                {"1":truck([(60,90,9)],[(0,60,PORT)])}], rates=[[-100.]*24,[-200.]*24])
    result = immediate.simulate_week(p,Design(1,20,0),p.keys)
    previous,following = result["days"]
    assert previous["end_soc_kwh"] == following["start_soc_kwh"] == 159.
    assert previous["terminal_excess_kwh"] == 0 and following["terminal_excess_kwh"] == 18.
    fees = price(result)
    assert [r["terminal_excess_cost_eur_2025"] for r in fees["days"]] == [0.,-3.]
    assert fees["summary"]["terminal_excess_cost_eur_2025"] == -3.


def test_short_terminal_zero_meter_and_regenerative_above_cap():
    p = period([{"1":truck([(0,15,9)],[]), "2":truck([(0,15,-9)],[]),
                 "3":truck([(0,15,0)],[]), "4":truck([(0,15,-155)],[])}])
    result = immediate.simulate_week(p,Design(0,0,0),p.keys)
    assert [r["status"] for r in result["days"]] == [
        "terminal_shortfall","complete","complete","trip_infeasible"]
    fees = price(result)["days"]
    assert fees[0]["terminal_excess_cost_eur_2025"] == 0
    assert fees[1]["terminal_excess_cost_eur_2025"] is None and fees[1]["unattributed_grid_kwh"] == 10.
    assert fees[2]["terminal_excess_cost_eur_2025"] == 0
    assert fees[3]["attribution_status"] == "terminal_unobserved"


def test_closed_segment_matches_existing_boundary_b_meter_and_native_hour_bill():
    curve = [10.]*24
    curve[2] = -30.
    p = period([{"1":truck([(0,60,18)],[(90,150,PORT)])}], rates=[curve])
    d = Design(1,20,0)
    result = immediate.simulate_week(p,d,p.keys)
    legacy_input = dict(schedule=result["schedule"],
                        states=[dict(date=p.days[0]["date"],vehicle_id="1",served=True,x=150.,y=150.)],
                        stats=dict(objective=-.2))
    legacy = meter_replay(p,d.hardware(),immediate.eb.DEFAULT_SPEC,d.caps,legacy_input)
    for field in ("purchase_eur","site_grid_kwh","site_quarter_peak_kw","site_peak_kw","used_plugs"):
        assert result["audit"][field] == pytest.approx(legacy[field])


def test_actual_purchase_weighted_mean_and_disclosed_regeneration_above_purchases():
    p = period([{"1":truck([(0,15,-9)],[(15,30,PORT)])}])
    result = immediate.simulate_week(p,Design(1,20,0),p.keys)
    row, = price(result)["segments"]
    assert row["metered_grid_kwh"] == 5.
    assert row["terminal_excess_grid_kwh"] == pytest.approx(15.)
    assert row["above_metered_grid_kwh"] == pytest.approx(10.)
    assert row["attribution_status"] == "weighted_mean_with_net_regeneration"
    assert row["terminal_excess_cost_eur_2025"] == pytest.approx(1.5)
