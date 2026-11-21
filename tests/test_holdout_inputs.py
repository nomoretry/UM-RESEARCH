from datetime import datetime
from types import SimpleNamespace

import pytest

from um_charging import holdout_inputs as hi
from um_charging.site_sizing import Design


def test_sensitivity_removes_only_registered_released_windows_and_keeps_links():
    source = hi.read_json(hi.WEEKS)
    blocked = {(r["date"], r["vehicle_id"], r["arrival_track_id"], r["next_track_id"])
               for r in source["parking_bounds"]["mapped_intervals_at_least_1km"]}
    main, sensitive = hi.load_periods(), hi.load_periods(sensitivity=True)
    assert [len(p.keys) for p in main] == [9, 16, 13, 8, 8, 9]
    removed = matched = 0
    for ordinary, strict in zip(main, sensitive, strict=True):
        assert ordinary.keys == strict.keys
        assert ordinary.chains == strict.chains
        assert ordinary.links == strict.links
        assert ordinary.prices == strict.prices
        assert sum(len(curve) for curve in ordinary.prices.values()) == 168
        for day in ordinary.days:
            stamp = day["date"]
            origin = datetime.fromisoformat(day["start"])
            for vehicle in day["vehicles"]:
                v = vehicle["vehicle_id"]
                main_truck = ordinary.cases[stamp]["trucks"][v]
                strict_truck = strict.cases[stamp]["trucks"][v]
                assert main_truck["trips"] == strict_truck["trips"]
                excluded = set()
                for stop in vehicle["stops"]:
                    if (stamp, v, stop["arrival_track_id"], stop["next_track_id"]) not in blocked:
                        continue
                    matched += 1
                    start, end, arrival = [(datetime.fromisoformat(stop[k]) - origin).total_seconds() / 60
                                           for k in ("start", "end", "arrival")]
                    start = max(start, arrival + (45 if stop["site"] == "WAREHOUSE" else 0))
                    if start < end:
                        excluded.add((start, end, stop["site"]))
                difference = sorted(set(main_truck["windows"]) - set(strict_truck["windows"]))
                for actual, expected in zip(difference, sorted(excluded), strict=True):
                    assert actual[:2] == pytest.approx(expected[:2], abs=1e-10, rel=0)
                    assert actual[2] == expected[2]
                assert set(strict_truck["windows"]) <= set(main_truck["windows"])
                removed += len(excluded)
    assert matched == 20
    assert 0 < removed <= matched


def _period(trucks):
    dates = [f"2021-11-{8 + i:02d}" for i in range(len(trucks))]
    chain = [(d, "5") for d in dates]
    return SimpleNamespace(
        cases={d: {"trucks": {"5": truck}} for d, truck in zip(dates, trucks)},
        offset={d: 1440 * i for i, d in enumerate(dates)}, keys=set(chain), chains=[chain])


def test_reachable_segment_across_midnight_can_restore_terminal_energy():
    period = _period([{"trips": [(100, 160, 45, "first")], "windows": []},
                      {"trips": [(110, 125, 10, "second")], "windows": [(0, 100, "PORT")]}])
    diagnosed = hi.diagnose(period, ("2021-11-08", "5"))
    assert diagnosed["classification"] == "joint_fleet_constraints_or_equal_service_tie"
    standalone, linked = diagnosed["segments"]
    assert standalone["unlimited"]["reason"] == "no_charging_window"
    assert standalone["unlimited"]["cause"] == "single_truck_terminal_energy"
    assert linked["truck_50kw"]["feasible"]


def test_diagnostics_distinguish_vehicle_power_and_unlimited_battery_failure():
    period = _period([{"trips": [(1, 15, 75, "a")], "windows": [(15, 16, "WAREHOUSE")]}])
    limited = hi.diagnose(period, ("2021-11-08", "5"))
    assert limited["classification"] == "truck_power_limit"
    assert limited["segments"][0]["truck_50kw"]["reason"] == "terminal_soc_unreachable"
    period = _period([{"trips": [(20, 90, 275, "b")], "windows": [(1, 20, "PORT")]}])
    unlimited = hi.diagnose(period, ("2021-11-08", "5"))
    failure = unlimited["segments"][0]["unlimited"]
    assert unlimited["classification"] == "infeasible_unlimited_power"
    assert (failure["reason"], failure["track_id"], failure["trip_end_min"]) == (
        "trip_exceeds_usable_battery", "b", 90)
    assert (failure["low_kwh"], failure["high_kwh"]) == (30, 25)


def test_registered_energy_counts_only_selected_signed_trip_energy():
    periods = hi.load_periods()
    date, vehicle = min(periods[0].keys)
    source = hi.read_json(hi.WEEKS)
    row, = [v for day in source["days"] if day["date"] == date
            for v in day["vehicles"] if v["vehicle_id"] == vehicle]
    expected = sum(trip["energy_kwh"] for trip in row["trips"]) / .9 * 52 / 6
    assert hi.annual_grid_kwh(periods, {(date, vehicle)}) == pytest.approx(expected)
    with pytest.raises(ValueError):
        hi.annual_grid_kwh(periods, {(date, "not-in-source")})


def test_fixed_facility_bounds_distinguish_port_rates_and_exclude_closed_warehouse():
    period = _period([{"trips": [(100, 160, 25, "first")], "windows": [(160, 250, "WAREHOUSE")]},
                      {"trips": [(120, 150, 4, "second")], "windows": [(0, 60, "PORT")]}])
    key = "2021-11-08", "5"
    small = hi.diagnose_fixed(period, key, Design(1, 20, 0))
    large = hi.diagnose_fixed(period, key, Design(1, 40, 0))
    assert small["classification"] == "single_truck_infeasible_at_facility"
    assert not small["single_truck_relaxation_feasible"]
    alone, linked = small["segments"]
    assert alone["single_truck"]["reason"] == "no_charging_window"
    assert linked["single_truck"]["high_kwh"] == pytest.approx(150 - 25 - 4 + 20 * .9)
    assert large["segments"][1]["single_truck"]["feasible"]
    assert large["classification"] == "joint_fleet_constraints_or_equal_service_tie"
    both = hi.diagnose_fixed(period, key, Design(1, 20, 40))
    assert both["segments"][0]["single_truck"]["feasible"]
