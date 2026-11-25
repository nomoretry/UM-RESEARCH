"""Fixed boundary-B service and single-truck sizing rules for the two M11 cohorts."""
from copy import deepcopy
from itertools import combinations
import json

from . import holdout_inputs as hi, m10_final_run, m10_immediate, m10_inputs, service_gap, site_sizing as ss


def week(period):
    return period.days[0]["week_start"]


def cohorts(outcome):
    train = m10_inputs.load_inputs()
    extra = m10_final_run._sealed_periods()[0]
    frozen = json.loads(outcome.read_bytes())
    second = set(map(tuple, frozen["reference"]))
    periods = [*train.periods, *extra]
    ref = set(train.main_reference) | second
    if not frozen["reference_complete"] or len(ref) != 155:
        raise ValueError("The two cohort calendars or registrations differ")
    if len(periods) != 19 or len(set(map(week, periods))) != 19:
        raise ValueError("Expected 19 independent weeks")
    return periods, ref


def scaled(period, factor):
    if factor == 1:
        return period
    days = deepcopy(period.days)
    for day in days:
        for truck in day["vehicles"]:
            for trip in truck["trips"]:
                trip["energy_kwh"] = float(trip["energy_kwh"]) * factor
    result = ss.eb.Period(days, period.prices)
    if result.keys != period.keys or result.chains != period.chains:
        raise ValueError("Scaling changed the service calendar")
    return result


def order(design):
    return (sum(design.caps), design.port_plugs + int(design.warehouse_kw > 0),
            design.warehouse_kw, design.port_kw, design.port_plugs)


GRID = sorted(ss.design_grid(ss.COARSE_KW), key=order)


def reachable(truck, design):
    return service_gap.reachable(truck, ss.eb.DEFAULT_SPEC,
                                 site_power_kw=dict(zip(ss.SITES,design.caps)))[0]


def trucks(period, fixed):
    for segment in m10_immediate._segments(period, fixed):
        yield segment, hi._segment_truck(period,segment)


def relaxed(period, fixed, design):
    return all(reachable(t,design) for _,t in trucks(period,fixed))


def single_rules(periods, ref):
    segments = [(s,t) for p in periods for s,t in trucks(p,ref & p.keys)]
    first = next((d for d in GRID if all(reachable(t,d) for _,t in segments)),None)
    thresholds = []
    for s,t in segments:
        if not any(site == "WAREHOUSE" and b>a for a,b,site in t["windows"]):
            continue
        ratings = sorted({d.warehouse_kw for d in GRID})
        threshold = next((k for k in ratings if reachable(t,ss.Design(0,0,k))),None)
        thresholds.append(dict(segment=s,warehouse_kw=threshold))
    return first, thresholds


def feasible_subsets(period, fixed, design):
    """Enumerate per-truck subsets; retain every maximal-cardinality tie."""
    alternatives = {}
    for truck in sorted({v for _,v in fixed}):
        days = sorted(k for k in fixed if k[1]==truck)
        for size in range(len(days),-1,-1):
            options = [list(kept) for kept in combinations(days,size)
                       if relaxed(period,set(kept),design)]
            if options:
                alternatives[truck]=options
                break
    return alternatives
