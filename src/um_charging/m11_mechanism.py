"""Classify registered truck-days using the union of released windows in each segment."""
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction
import json

from . import holdout_inputs, m10_immediate, service_gap


SITE_CLASS = {
    frozenset(): "neither",
    frozenset(["PORT"]): "port_only",
    frozenset(["WAREHOUSE"]): "warehouse_only",
    frozenset(["PORT", "WAREHOUSE"]): "both",
}


def warehouse_threshold(truck):
    def feasible(power):
        return service_gap.reachable(
            truck, service_gap.DEFAULT_SPEC, site_power_kw={"PORT": 0, "WAREHOUSE": power}
        )[0]

    maximum = service_gap.DEFAULT_SPEC.truck_kw
    if feasible(0):
        return 0., 0.
    if not feasible(maximum):
        return maximum, None
    return service_gap._bisect(feasible, 0., maximum)


def census(periods, reference):
    rows = []
    for period in periods:
        for segment in m10_immediate._segments(period, reference):
            truck = holdout_inputs._segment_truck(period, segment)
            sites = frozenset(site for a, b, site in truck["windows"] if b > a)
            category = SITE_CLASS[sites]
            lower, upper = warehouse_threshold(truck) if category == "warehouse_only" else (None, None)
            for date, vehicle in segment:
                rows.append(dict(date=date, vehicle_id=vehicle, first_date=segment[0][0],
                                 last_date=segment[-1][0], site_class=category,
                                 warehouse_lower_kw=lower, warehouse_upper_kw=upper))
    if Counter((r["date"], r["vehicle_id"]) for r in rows) != Counter(list(reference)):
        raise ValueError("Segment census differs from the original registration")
    return sorted(rows, key=lambda row: (row["date"], int(row["vehicle_id"])))


def rolling_terminal_bound(source, cohort):
    """Optimistic energy conservation for the Jan 19 rolling day, in exact kWh."""
    date, vehicle = "2022-01-19", "1"
    if (date, vehicle) not in cohort:
        raise ValueError("The diagnostic truck-day is absent from the archived registration")
    raw = json.loads(source.read_bytes(), parse_float=Decimal)
    day, = [d for d in raw["days"] if d["date"] == date and d["week_start"] == "2022-01-17"]
    truck, = [t for t in day["vehicles"] if t["vehicle_id"] == vehicle]
    draw = sum(Fraction(t["energy_kwh"]) for t in truck["trips"])
    windows = []
    for stop in truck["stops"]:
        site = stop["site"]
        power = {"PORT": 40, "WAREHOUSE": 20}[site]
        release = timedelta(minutes=45 if site == "WAREHOUSE" else 0)
        left = max(datetime.fromisoformat(stop["start"]), datetime.fromisoformat(stop["arrival"]) + release)
        right = datetime.fromisoformat(stop["end"])
        if right > left:
            hours = Fraction((right-left) // timedelta(microseconds=1), 3600000000)
            windows.append(dict(site=site, start=left.isoformat(), end=right.isoformat(),
                                max_grid_kwh=str(hours * power)))
    charge = sum(Fraction(w["max_grid_kwh"]) for w in windows)
    upper = 150 - draw + Fraction(9, 10) * charge
    return dict(date=date, vehicle_id=vehicle, trip_ids=[t["track_id"] for t in truck["trips"]],
                required_kwh=150, signed_draw_kwh=str(draw), relaxed_grid_kwh=str(charge),
                windows=windows, upper_kwh=str(upper), deficit_kwh=str(150-upper),
                upper_decimal_kwh=float(upper), independently_infeasible=upper < 150)
