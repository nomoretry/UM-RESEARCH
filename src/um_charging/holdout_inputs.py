"""M9 held-out service inputs and price-independent carry-over diagnostics."""

from dataclasses import replace
import math

from . import energy_boundary as eb
from .__main__ import digest
from .cabinet_tariff import annual_repeats, load_network
from .connector_value import FLEET, MARKET, csv_rows, hourly_curve
from .day_ahead import read_json
from .fleet_service import DEFAULT_SPEC
from .service_gap import reachable


WEEKS = FLEET / "holdout_weeks.json"
PRICES = MARKET / "native_2021_holdout_prices.csv"
INPUT_HASHES = {
    WEEKS: "6c4c4483961f957604b564ee7b1b423895d016526535e807d384be60cde69413",
    PRICES: "28e3f8a242625ddd59338ec340e756d49c07d0d7ca8b6bbfb627906ee0c908dc",
}


def _exclude_mapped_intervals(days, registered, *, expected_count=20, expected_vehicles=frozenset({"5"})):
    def interval(day, vehicle, stop):
        return day, vehicle, stop["site"], stop["arrival_track_id"], stop["next_track_id"]

    blocked = {interval(row["date"], row["vehicle_id"], row) for row in registered}
    if (len(blocked) != expected_count or len(registered) != expected_count
            or {key[1] for key in blocked} != expected_vehicles):
        raise ValueError("Unexpected registered mapped intervals")
    remaining = blocked.copy()
    for day in days:
        for truck in day["vehicles"]:
            valid = []
            for stop in truck["stops"]:
                key = interval(day["date"], truck["vehicle_id"], stop)
                if key in blocked:
                    remaining.remove(key)
                    # In this in-memory model view only, an ineligible stop
                    # supplies link evidence exactly as a noncharging gap does.
                    truck["unmapped_gaps"].append(stop)
                else:
                    valid.append(stop)
            truck["stops"] = valid
    if remaining:
        raise ValueError(f"Unmatched registered intervals: {sorted(remaining)}")


def load_periods(sensitivity=False):
    """Build the six predeclared weeks, optionally removing the far-gap windows."""
    for path, expected in INPUT_HASHES.items():
        if digest(path) != expected:
            raise ValueError(f"Registered input changed: {path.name}")
    data = read_json(WEEKS)
    days = data["days"]
    chains, links, _ = eb.calendar(days)
    if sensitivity:
        _exclude_mapped_intervals(days, data["parking_bounds"]["mapped_intervals_at_least_1km"])
        if eb.calendar(days)[:2] != (chains, links):
            raise ValueError("Disabling a charging window changed carry-over continuity")
    groups = eb.components(days, links)
    if len(groups) != 6 or any(len(group) != 7 or len({d["week_start"] for d in group}) != 1
                               for group in groups):
        raise ValueError("Holdout service is not separable into six complete weeks")
    native = csv_rows(PRICES)
    return [eb.Period(group, {d["date"]: hourly_curve(native, d) for d in group})
            for group in groups]


def _segment_truck(period, segment):
    trips, windows = [], []
    for date, vehicle in segment:
        truck = period.cases[date]["trucks"][vehicle]
        offset = period.offset[date]
        trips.extend((a + offset, b + offset, energy, track)
                     for a, b, energy, track in truck["trips"])
        windows.extend((a + offset, b + offset, site) for a, b, site in truck["windows"])
    return {"trips": trips, "windows": windows}


def _propagate(truck, spec, site_power_kw=None):
    feasible, failure = reachable(truck, spec, site_power_kw=site_power_kw)
    if feasible:
        return {"feasible": True}
    if failure["cause"] == "single_truck_leg_boundary":
        trip, = [t for t in truck["trips"] if t[3] == failure["track_id"]]
        failure = {**failure, "trip_energy_kwh": trip[2]}
        if abs(trip[2]) > spec.capacity_kwh - spec.reserve_kwh:
            reason = "trip_exceeds_usable_battery"
        elif not truck["windows"]:
            reason = "no_charging_window"
        else:
            reason = "trip_soc_boundary"
    else:
        reason = "terminal_soc_unreachable" if truck["windows"] else "no_charging_window"
    return {"feasible": False, "reason": reason, **failure}


def _segments_containing(period, key):
    if key not in period.keys:
        raise ValueError(f"Unknown vehicle-day {key}")
    chain, = [chain for chain in period.chains if key in chain]
    middle = chain.index(key)
    for left in range(middle + 1):
        for right in range(middle, len(chain)):
            yield chain[left][0], chain[right][0], _segment_truck(period, chain[left:right + 1])


def diagnose(period, key):
    """Test every possible B segment containing one omitted reference vehicle-day."""
    segments = [{"first_date": first, "last_date": last, "charging_windows": len(truck["windows"]),
                 "unlimited": _propagate(truck, replace(DEFAULT_SPEC, truck_kw=math.inf)),
                 "truck_50kw": _propagate(truck, DEFAULT_SPEC)}
                for first, last, truck in _segments_containing(period, key)]
    unlimited = any(row["unlimited"]["feasible"] for row in segments)
    capped = any(row["truck_50kw"]["feasible"] for row in segments)
    if not unlimited:
        classification = "infeasible_unlimited_power"
    elif not capped:
        classification = "truck_power_limit"
    else:
        classification = "joint_fleet_constraints_or_equal_service_tie"
    return {"date": key[0], "vehicle_id": key[1], "classification": classification,
            "unlimited_feasible": unlimited, "truck_50kw_feasible": capped, "segments": segments}


def diagnose_fixed(period, key, design):
    """Relax all competition and quarter reservations at the facility's rated power."""
    rates = {site: row["power_kw"] if row["interfaces"] else 0
             for site, row in design.hardware().items()}
    segments = []
    for first, last, truck in _segments_containing(period, key):
        windows = [window for window in truck["windows"] if rates[window[2]] > 0]
        relaxed = _propagate({"windows": windows, "trips": truck["trips"]}, DEFAULT_SPEC, rates)
        segments.append({"first_date": first, "last_date": last, "charging_windows": len(windows),
                         "single_truck": relaxed})
    possible = any(row["single_truck"]["feasible"] for row in segments)
    return {"date": key[0], "vehicle_id": key[1], "design": design.label,
            "site_power_kw": rates, "single_truck_relaxation_feasible": possible,
            "classification": ("joint_fleet_constraints_or_equal_service_tie" if possible
                               else "single_truck_infeasible_at_facility"), "segments": segments}


def annual_grid_kwh(periods, reference):
    """Repeat six weeks of registered signed battery energy at the fixed efficiency."""
    reference = set(reference)
    if len(periods) != 6 or not reference <= set.union(*(p.keys for p in periods)):
        raise ValueError("Expected a reference set drawn from the six holdout weeks")
    energy = math.fsum(trip[2] for p in periods for date, vehicle in sorted(reference & p.keys)
                       for trip in p.cases[date]["trucks"][vehicle]["trips"])
    return energy / DEFAULT_SPEC.efficiency * annual_repeats(load_network())
