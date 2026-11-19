"""Compare independent fleet plugs with quarter-boundary changeover downtime."""
import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
import math
from pathlib import Path
import platform
import subprocess
from time import perf_counter
import warnings

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from . import energy_boundary as eb
from .__main__ import checked_output, digest, write_json
from .cabinet_model import _balance, _levels
from .connector_cost import COST_INPUT, break_even
from .connector_value import FLEET
from .fleet_service import EPS, SITES, _events, subset_case


DUTIES = FLEET / "duties.json"
BASELINE = FLEET / "energy_boundary.json"
SPEC = eb.SPECS["S300"]
FACILITIES = ("one", "two")
DELAYS = (0, 2, 5)
STRESS = (10, 15)
SOLVE_SECONDS = 300.
STUDY_SECONDS = 90 * 60.
ABSOLUTE_COST_GAP = .01
RELATIVE_COST_GAP = 1e-6
MAX_UNRESOLVED = 3
ENERGY_ROUNDOFF_KWH = 1e-9
PILOT_DATES = ("2021-09-21", "2021-09-22", "2021-09-23")
TRIAL_WEEK = "2021-10-18"


def _physical_quarters(period, active):
    quarters = defaultdict(list)
    for day, original in period.cases.items():
        case = subset_case(original, [v for v in original["trucks"] if (day, v) in active])
        offset = period.offset[day]
        for start, end, by_site in _events(case):
            if any(by_site.values()):
                quarters[(offset + int(start)) // 15].append((day, start, end, by_site))
    return quarters


def _dispatch_matrix(period, hardware, spec, delay, fixed, rule, required):
    physical = fixed is None
    active = period.keys if physical else set(fixed)
    if not required <= active <= period.keys or rule not in (eb.A, eb.B):
        raise ValueError("Unknown duty or boundary rule")
    model = eb.Matrix()
    levels = _levels(model, period, spec, rule, active, physical)
    for key in sorted(required):
        model.add([(levels[key][0], 1.)], low=1.)
    occupied = defaultdict(dict)
    charged = defaultdict(list)
    dispatch = []
    for quarter, intervals in sorted(_physical_quarters(period, active).items()):
        by_truck = defaultdict(list)
        for site in SITES:
            plugs = hardware[site]["interfaces"]
            limit = hardware[site]["power_kw"]
            trucks = sorted({v for _, _, _, available in intervals for v in available[site]})
            if not trucks or not plugs or not limit:
                continue
            rate = min(spec.truck_kw, limit)
            site_dispatch = []
            for plug in range(1, plugs + 1):
                now = occupied[site, plug, quarter]
                previous = occupied.get((site, plug, quarter - 1), {})
                for truck in trucks:
                    now[truck] = model.var(0, 1, integer=True)
                    by_truck[truck].append((now[truck], 1.))
                if len(now) > 1:
                    model.add([(col, 1.) for col in now.values()], high=1.)
                for day, start, end, available in intervals:
                    offset = period.offset[day]
                    setup_end = quarter * 15 + delay - offset
                    price = 0. if physical else period.prices[day][int(start // 60)] / 1000
                    for truck in available[site]:
                        reserved = now[truck]
                        # Only an earlier different truck on this plug can block the prefix.
                        blockers = [col for v, col in previous.items() if v != truck]
                        cut = min(end, setup_end) if blockers and start < setup_end else start
                        for left, right in ((start, cut), (cut, end)):
                            if left >= right:
                                continue
                            maximum = rate * (right - left) / 60
                            energy = model.var(0., maximum, price)
                            model.add([(energy, 1.), (reserved, -maximum)], high=0.)
                            if right == cut and blockers:
                                model.add([(energy, 1.)] + [(col, maximum) for col in blockers],
                                          high=maximum)
                            charged[day, truck].append((right, energy))
                            site_dispatch.append((day, truck, site, plug, quarter, left, right, energy))
            if plugs * rate > limit + EPS:
                # Split at every exact availability/setup edge for a constrained common feed.
                edges = sorted({edge for row in site_dispatch for edge in row[5:7]})
                for left, right in zip(edges, edges[1:]):
                    simultaneous = [(r[7], 60 / (r[6] - r[5])) for r in site_dispatch
                                    if r[5] <= left and right <= r[6]]
                    if simultaneous:
                        model.add(simultaneous, high=limit)
            dispatch.extend(site_dispatch)
        for assignments in by_truck.values():
            if len(assignments) > 1:
                model.add(assignments, high=1.)
    for day, case in period.cases.items():
        active_case = subset_case(case, [v for v in case["trucks"] if (day, v) in active])
        _balance(model, active_case, day, levels, charged, spec)
    if not levels:
        model.var(0, 0)
    return model, levels, dispatch


def _reservations(schedule):
    """Read only positive charging rows. Each reservation occupies its whole quarter."""
    plugs, trucks = {}, {}
    for row in schedule:
        site, plug, quarter, truck = (row[k] for k in ("site", "plug", "reservation_slot", "vehicle_id"))
        key = site, plug, quarter
        if plugs.setdefault(key, truck) != truck:
            raise ValueError(("two trucks on one plug", key))
        if trucks.setdefault((truck, quarter), (site, plug)) != (site, plug):
            raise ValueError(("one truck on two plugs", truck, quarter))
    return plugs


def _transitions(schedule):
    occupied = _reservations(schedule)
    starts = defaultdict(list)
    for row in schedule:
        starts[row["site"], row["plug"], row["reservation_slot"]].append(row["start_min"])
    prior = {}
    for (site, plug, quarter), vehicle in sorted(occupied.items()):
        key = site, plug
        old = prior.get(key)
        if old and old[1] != vehicle:
            released = 15 * (old[0] + 1)
            start = min(starts[site, plug, quarter])
            yield dict(site=site, plug=plug, previous_vehicle=old[1], next_vehicle=vehicle,
                       previous_quarter=old[0], next_quarter=quarter,
                       release_min=released, start_min=start, gap_minutes=start - released,
                       adjacent=(quarter == old[0] + 1))
        prior[key] = quarter, vehicle


def replay(period, hardware, spec, delay, result, *, rule=eb.B, physical=False):
    """Replay the named plugs by the minute and SOC at exact events. No solve is called."""
    schedule = result["schedule"]
    for row in schedule:
        site, plug, quarter = (row[k] for k in ("site", "plug", "reservation_slot"))
        if (site not in hardware or type(plug) is not int or not 1 <= plug <= hardware[site]["interfaces"]
                or type(quarter) is not int or not all(math.isfinite(row[k]) for k in
                                                       ("start_min", "end_min", "power_kw"))):
            raise ValueError(("invalid physical plug or charge segment", row))
    changes = list(_transitions(schedule))
    for change in changes:
        if change["gap_minutes"] + EPS < delay:
            raise ValueError(("changeover gap", change, delay))
    # The existing solver-independent energy replay checks released windows, instantaneous
    # caps, trip endpoints, chain starts/ends, and the charge total against the objective.
    checked = eb.audit(period, hardware, spec, rule, result, physical=physical)
    by_site, by_truck, bills = defaultdict(float), defaultdict(float), defaultdict(float)
    for row in schedule:
        a, b, power = (row[k] for k in ("start_min", "end_min", "power_kw"))
        day = row["date"]
        for minute in range(math.floor(a), math.ceil(b)):
            energy = power * (min(b, minute + 1) - max(a, minute)) / 60
            by_site[row["site"], minute] += energy
            by_truck[row["vehicle_id"], minute] += energy
            hour = (minute - period.offset[day]) // 60
            bills[day] += energy * period.prices[day][hour] / 1000
    if any(energy * 60 > hardware[site]["power_kw"] + EPS for (site, _), energy in by_site.items()):
        raise ValueError("minute site cap")
    if any(energy * 60 > spec.truck_kw + EPS for energy in by_truck.values()):
        raise ValueError("minute truck cap")
    euro = math.fsum(bills.values())
    if abs(euro - checked["purchase_eur"]) > EPS:
        raise ValueError(("minute bill differs from event ledger", euro, checked["purchase_eur"]))
    return dict(**checked, minute_purchase_eur=euro, changes=changes, change_count=len(changes),
                adjacent_change_count=sum(c["adjacent"] for c in changes))


def _solve_stats(native, physical, active_count, seconds, relative_target, absolute_target):
    upper = None if native.fun is None else float(native.fun)
    lower = getattr(native, "mip_dual_bound", None)
    gap = getattr(native, "mip_gap", None)
    if lower is None and native.status == 0:
        lower = upper
    lower = float(lower) if lower is not None and math.isfinite(lower) else None
    if gap is not None and not math.isfinite(gap):
        gap = None
    absolute = None if upper is None or lower is None else max(0., upper - lower)
    accepted = native.status == 0 and absolute is not None and (
        absolute <= absolute_target + 1e-9 or (gap is not None and gap <= relative_target + 1e-12))
    result = dict(status="certified" if accepted else "infeasible" if native.status == 2 else "unresolved",
                  status_code=int(native.status), message=native.message, seconds=seconds, objective=upper,
                  objective_lower=lower, objective_upper=upper, absolute_gap=absolute, relative_gap=gap,
                  native_mip_dual_bound=getattr(native, "mip_dual_bound", None) if lower is not None else None)
    if physical:
        result["completed_bounds"] = None if native.status == 2 else [
            round(-upper) if upper is not None else 0,
            min(active_count, math.floor(-lower + EPS)) if lower is not None else active_count]
        if accepted and result["completed_bounds"][0] != result["completed_bounds"][1]:
            raise ValueError(("service not proven optimal", result))
    return result


def solve(period, hardware, spec, delay, fixed=None, *, rule=eb.B, deadline=math.inf, required=()):
    """Maximize whole truck-days, or minimize energy for an exactly fixed service set."""
    started = perf_counter()
    if not math.isfinite(delay) or not 0 <= delay <= 15:
        raise ValueError("Expected changeover minutes in [0, 15]")
    if set(hardware) != set(SITES) or any(
        type(site["interfaces"]) is not int or site["interfaces"] < 0
        or not math.isfinite(site["power_kw"]) or site["power_kw"] < 0 for site in hardware.values()
    ):
        raise ValueError("Invalid fixed hardware")
    physical = fixed is None
    if not physical:
        fixed = set(fixed)
    model, levels, decisions = _dispatch_matrix(period, hardware, spec, delay, fixed, rule, set(required))
    matrix = coo_matrix((model.data, (model.row, model.col)),
                        shape=(len(model.lb), len(model.cost))).tocsr()
    # Use zero monetary tolerance for the registered baseline regression. Positive
    # delays use either of the specified weekly cost tolerances.
    exact = physical or delay == 0
    relative, absolute = (0., 0.) if exact else (RELATIVE_COST_GAP, ABSOLUTE_COST_GAP)
    remaining = max(0., min(deadline, started + SOLVE_SECONDS) - perf_counter())
    if remaining <= 0.:
        native = scipy.optimize.OptimizeResult(status=1, message="wall-clock budget before solver",
                                               fun=None, x=None)
    else:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Unrecognized options detected.*", category=RuntimeWarning)
            native = milp(model.cost, integrality=model.integer, bounds=Bounds(model.lower, model.upper),
                          constraints=LinearConstraint(matrix, model.lb, model.ub),
                          options={"time_limit":remaining, "mip_rel_gap":relative, "mip_abs_gap":absolute,
                                   "mip_feasibility_tolerance":1e-9, "primal_feasibility_tolerance":1e-9})
    stats = _solve_stats(native, physical, len(period.keys), perf_counter() - started, relative, absolute)
    result = dict(stats=stats, schedule=[], states=[], audit=None)
    if native.x is not None:
        for day, truck, site, plug, quarter, left, right, col in decisions:
            energy = native.x[col]
            if energy > ENERGY_ROUNDOFF_KWH:
                result["schedule"].append(dict(date=day, vehicle_id=truck, site=site, plug=plug,
                    reservation_slot=quarter, start_min=period.offset[day] + left,
                    end_min=period.offset[day] + right, power_kw=float(energy * 60 / (right - left))))
        result["states"] = [dict(date=day, vehicle_id=truck, served=bool(native.x[s] > .5),
                                 x=float(native.x[x]), y=float(native.x[y]))
                            for (day, truck), (s,x,y) in levels.items()]
        result["audit"] = replay(period, hardware, spec, delay, result, rule=rule, physical=physical)
    stats["seconds"] = perf_counter() - started
    return result


class StudyLimit(RuntimeError):
    """A registered stop rule limits which groups can be completed."""


class Evidence:
    def __init__(self, output, started, budget):
        self.output = output
        self.deadline = started + budget
        self.calls = []
        self.unresolved = set()
        self.audited = 0

    def check_budget(self):
        if len(self.unresolved) > MAX_UNRESOLVED:
            raise StudyLimit("more than three unresolved period/delay/facility groups")
        if perf_counter() >= self.deadline:
            raise StudyLimit("formal wall-clock budget exhausted")

    def record(self, period, name, hardware, delay, phase, rule, fixed=None, required=()):
        self.check_budget()
        scope = (period.days[0]["date"], delay, name)
        label = f"{scope[0]}-delta{delay}-{name}-{phase}"
        result = solve(period, hardware, SPEC, delay, fixed, rule=rule, deadline=self.deadline, required=required)
        stats = result["stats"]
        if self.output:
            write_json(self.output / f"{label}.json", result)
        self.audited += int(result["audit"] is not None)
        if stats["status"] == "unresolved":
            self.unresolved.add(scope)
        self.calls.append(dict(period=scope[0], delay_minutes=delay, facility=name,
                               phase=phase, evidence=label + ".json", **stats))
        bounds = stats.get("completed_bounds", [stats["objective_lower"], stats["objective_upper"]])
        print(f"{label} {stats['status']} bounds={bounds} seconds={stats['seconds']:.3f}", flush=True)
        return result


def _periods(mode):
    native = eb.csv_rows(eb.NATIVE)
    if mode == "pilot":
        held = [row for row in eb.read_json(DUTIES)["days"] if row["split"] == "holdout"]
        if tuple(d["date"] for d in held) != PILOT_DATES:
            raise ValueError("Unexpected original holdout dates")
        groups = [[dict(d, availability="complete_tasks")] for d in held]
    else:
        days = eb.read_json(eb.WEEKS)["days"]
        groups = eb.components(days, eb.calendar(days)[1])
        if len(groups) != 6 or any(len({row["week_start"] for row in group}) != 1 for group in groups):
            raise ValueError("The registered six weeks must be disjoint across carry-over chains")
        if mode == "trial":
            groups = [group for group in groups if group[0]["week_start"] == TRIAL_WEEK]
            if len(groups) != 1:
                raise ValueError("Registered trial week missing")
    return [eb.Period(group, {d["date"]:eb.hourly_curve(native,d) for d in group
                              if d["availability"] == "complete_tasks"}) for group in groups]


def _certified(result):
    return result is not None and result["stats"]["status"] == "certified"


def _weekly_pair(period, facilities, delay, rule, evidence, baseline):
    runs = {}
    for name, hardware in facilities.items():
        service = evidence.record(period, name, hardware, delay, "service", rule)
        entry = runs[name] = dict(service=service, keys=None, priced=None)
        if not _certified(service):
            if service["stats"]["status"] == "infeasible":
                raise ValueError("The service model must allow the empty service set")
            continue
        keys = eb.selected(service)
        count = service["stats"]["completed_bounds"][0]
        if len(keys) != count:
            raise ValueError(("service audit count", count, keys))
        preferred = baseline[name]["keys"] if baseline is not None else None
        # Compare equal maxima on the one-plug cohort. Where possible retain the
        # zero-delay optimum cohort across delays to avoid reporting tie changes as losses.
        if name == "two" and runs["one"]["keys"] is not None and len(runs["one"]["keys"]) == count:
            preferred = runs["one"]["keys"]
        primary = None
        if preferred is not None and len(preferred) == count and preferred != keys:
            probe = evidence.record(period, name, hardware, delay, "retain-service", rule, preferred)
            if probe["stats"]["status"] != "infeasible":
                primary = probe
                if _certified(probe):
                    keys = preferred
        if primary is None:
            primary = evidence.record(period, name, hardware, delay, "energy", rule, keys)
            if primary["stats"]["status"] == "infeasible":
                raise ValueError(("proved service became infeasible in price solve", name, sorted(keys)))
        entry.update(keys=keys, priced=primary)
    runs["one"]["matched"] = runs["one"]["priced"]
    low, high = runs["one"], runs["two"]
    high["matched"] = None
    if low["keys"] is not None and high["keys"] is not None:
        if len(high["keys"]) < len(low["keys"]):
            raise ValueError(("adding a plug reduced service", period.days[0]["date"], delay,
                              sorted(low["keys"]), sorted(high["keys"])))
        if _certified(low["priced"]) and _certified(high["priced"]):
            high["matched"] = high["priced"]
            if high["keys"] != low["keys"]:
                high["matched"] = evidence.record(period, "two", facilities["two"], delay,
                                                  "matched", rule, low["keys"])
                if high["matched"]["stats"]["status"] == "infeasible":
                    raise ValueError("Dual plugs did not retain the verified single-plug cohort")
    return runs


def _lost_service(period, baseline, current, delay, facility, evidence, dual_hardware, rule):
    zero = baseline[facility]
    now = current[facility]
    if now["keys"] is None or zero["keys"] is None:
        return None
    removed = zero["keys"] - now["keys"]
    added = now["keys"] - zero["keys"]
    difference = len(zero["keys"]) - len(now["keys"])
    if len(removed) - len(added) != difference:
        raise ValueError("Service changes do not conserve counts")
    report = dict(net_lost=difference, lost=[], added=sorted(added))
    if not removed:
        return report
    witness = zero["priced"] if _certified(zero["priced"]) else zero["service"]
    by_offset = {off:d for d,off in period.offset.items()}
    conflicts = []
    for c in witness["audit"]["changes"]:
        if c["gap_minutes"] + EPS >= delay:
            continue
        day_before = by_offset[(c["previous_quarter"] * 15 // 1440) * 1440]
        day_after = by_offset[(c["next_quarter"] * 15 // 1440) * 1440]
        conflicts.append(dict(**c, previous_duty=(day_before,c["previous_vehicle"]),
                              next_duty=(day_after,c["next_vehicle"])))
    if difference > 0 and not conflicts:
        raise ValueError(("loss despite zero-delay witness passing the new delay", facility, delay))
    ref = f"{period.days[0]['date']}-delta{delay}-{facility}-attribution.json"
    for duty in sorted(removed):
        related = [i for i,c in enumerate(conflicts) if duty in (c["previous_duty"], c["next_duty"])]
        dual = current["two"]["keys"]
        single = current["one"]["keys"]
        recovers, recovery_ref = None, None
        if single is not None and dual is not None:
            required = single | {duty}
            if required <= dual:
                recovers = True
            elif len(required) > len(dual):
                recovers = False
            else:
                phase = f"recover-{facility}-{duty[0]}-{duty[1]}"
                probe = evidence.record(period, "two", dual_hardware, delay, phase, rule, required=required)
                recovers = {"certified": True, "infeasible": False, "unresolved": None}[probe["stats"]["status"]]
                recovery_ref = evidence.calls[-1]["evidence"] if evidence.output else None
        involved = [conflicts[i] for i in related] if related else conflicts
        # A failed zero-delay schedule shows where and which trucks conflict. It
        # does not identify a unique cause across every possible reassignment.
        pairs = sorted({(c["site"], c["plug"], c["previous_duty"], c["next_duty"]) for c in involved})
        report["lost"].append(dict(duty=duty,
            completed_in_two_maximum=(duty in dual if dual is not None else None),
            recoverable_with_all_single_plug_duties=recovers, recovery_evidence=recovery_ref,
            witness_scope="directly involves omitted duty" if related else "same period, indirect",
            competing_switches=[dict(site=s,plug=k,previous_duty=a,next_duty=b) for s,k,a,b in pairs],
            conflicts_in_baseline_witness=len(conflicts), evidence=ref if evidence.output else None))
    if evidence.output:
        write_json(evidence.output / ref, dict(**report, zero_delay_witness_conflicts=conflicts))
    return report


def _service_row(periods, weeks, name):
    entries = [w[name] for w in weeks]
    complete = len(entries) == len(periods)
    certified = complete and all(r["keys"] is not None for r in entries)
    priced = complete and all(_certified(r["priced"]) for r in entries)
    audited = [e["priced"]["audit"] for e in entries if _certified(e["priced"])]
    return dict(status="certified" if certified and priced else "unresolved",
                completed=sum(len(r["keys"]) for r in entries) if certified else None,
                selected=sorted(k for r in entries for k in r["keys"]) if certified else None,
                energy_eur_2021=math.fsum(a["purchase_eur"] for a in audited) if priced else None,
                energy_bounds_eur_2021=[
                    math.fsum(e["priced"]["stats"][f"objective_{bound}"] for e in entries)
                    for bound in ("lower", "upper")] if priced else None,
                changes=sum(a["change_count"] for a in audited) if priced else None,
                adjacent_changes=sum(a["adjacent_change_count"] for a in audited) if priced else None)


def _pair_value(delta, periods, weeks, mode):
    data = {name:_service_row(periods,weeks,name) for name in FACILITIES}
    one, two = (data[name] for name in FACILITIES)
    extra = two["completed"] - one["completed"] if None not in (one["completed"],two["completed"]) else None
    value = dict(common_completed=None, paired_energy_eur_2021=None, savings_eur_2021=None,
                 savings_bounds_eur_2021=None, annual_savings_eur_2025=None,
                 annual_savings_bounds_eur_2025=None, extra_truck_days=extra,
                 annual_extra_truck_days=None, break_even_eur_2025_per_extra_day=None,
                 break_even_bounds_eur_2025_per_extra_day=None)
    all_matched = len(weeks) == len(periods) and all(
        _certified(w[name]["matched"]) for w in weeks for name in FACILITIES)
    if not all_matched:
        return dict(delay_minutes=delta, stress=delta in STRESS, **data, **value)
    weekly, lower, upper = [], [], []
    pair_energy = dict.fromkeys(FACILITIES, 0.)
    for w in weeks:
        single, dual = (w[n]["matched"] for n in FACILITIES)
        costs = [r["audit"]["purchase_eur"] for r in (single, dual)]
        sold, bought = (r["stats"] for r in (single, dual))
        for name, amount in zip(FACILITIES, costs):
            pair_energy[name] += amount
        lo, hi = sold["objective_lower"] - bought["objective_upper"], sold["objective_upper"] - bought["objective_lower"]
        if hi < -EPS or (delta == 0 and costs[0] < costs[1] - EPS):
            raise ValueError(("adding a plug increased certified matched cost", delta, costs, lo, hi))
        weekly.append(max(0., costs[0] - costs[1]))
        lower.append(max(0., lo))
        upper.append(max(0., hi))
    value.update(common_completed=one["completed"], paired_energy_eur_2021=pair_energy,
                 savings_eur_2021=math.fsum(weekly),
                 savings_bounds_eur_2021=[math.fsum(lower),math.fsum(upper)])
    if mode == "full":
        annual = break_even(weekly)
        factor = annual["repeat_weeks_per_year"] * annual["conversion_to_2025_eur"] / len(weeks)
        bounds = [b * factor for b in value["savings_bounds_eur_2021"]]
        value.update(annual_savings_eur_2025=annual["annual_cost_ceiling_2025_eur"],
                     annual_savings_bounds_eur_2025=bounds)
        if extra is not None:
            annual_extra = extra * annual["repeat_weeks_per_year"] / len(weeks)
            value["annual_extra_truck_days"] = annual_extra
            if annual_extra:
                cost = annual["benchmark"]["annual_cost_2025_eur"]
                value["break_even_eur_2025_per_extra_day"] = (cost - value["annual_savings_eur_2025"]) / annual_extra
                value["break_even_bounds_eur_2025_per_extra_day"] = [
                    (cost - point) / annual_extra for point in reversed(bounds)]
    return dict(delay_minutes=delta, stress=delta in STRESS, **data, **value)


def _regression(mode, row, periods, weeks, reference):
    if mode == "pilot":
        previous = reference["original"]["concurrent"]
        expected = {name:(previous["paired_vehicle_days"], previous[name]["optimal_eur_matched_tasks"])
                    for name in FACILITIES}
    else:
        old = {r["facility"]:r for r in eb.read_json(BASELINE)["full"] if r["rule"] == eb.B and r["spec"] == "S300"}
        expected = {name:(r["completed"],r["common_eur"]) for name,r in old.items()}
        for name, data in old.items():
            if row[name]["selected"] != sorted(map(tuple, data["selected"])):
                raise ValueError(("zero delay selected duties differ", name))
            for p,w,e in zip(periods,weeks,data["week_common_eur"],strict=True):
                bill = w[name]["matched"]["audit"]["purchase_eur"]
                if abs(bill - e) > EPS:
                    raise ValueError(("zero delay weekly bill differs", name, p.days[0]["date"], e, bill))
    checks = {}
    for name, (count, bill) in expected.items():
        actual = row[name]
        if actual["completed"] != count or abs(actual["energy_eur_2021"] - bill) > EPS:
            raise ValueError(("zero delay differs from the registered result", name, count, bill, actual))
        checks[name] = dict(completed=actual["completed"], expected_eur_2021=bill,
                            actual_eur_2021=actual["energy_eur_2021"], difference_eur=actual["energy_eur_2021"]-bill)
    return checks


def progress(path, message):
    if path is not None:
        with path.open("a",encoding="utf-8") as stream:
            if stream.tell() == 0:
                stream.write("# 车队换车时间研究进度\n\n")
            stream.write(f"- {datetime.now().astimezone().isoformat(timespec='seconds')} {message}\n")


def run(mode, output=None, progress_path=None):
    began = perf_counter()
    source = dict(commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=eb.ROOT,encoding="utf-8").strip(),
                  dirty=bool(subprocess.check_output(["git","status","--porcelain"],cwd=eb.ROOT).strip()))
    if mode == "full" and output is not None and source["dirty"]:
        raise ValueError("Commit the exact source before starting a formal run")
    periods = _periods(mode)
    reference = eb.read_json(eb.REFERENCE)
    facilities = {name:reference["hardware"][name] for name in FACILITIES}
    rule = eb.A if mode == "pilot" else eb.B
    log = Evidence(output,began,STUDY_SECONDS if mode == "full" else math.inf)
    measured = []
    attribution, regression = [], {}
    baseline, previous, stopped = None, None, None
    delays = [5] if mode == "trial" else list(DELAYS)
    inputs = [eb.NATIVE, eb.REFERENCE, DUTIES if mode == "pilot" else eb.WEEKS]
    if mode == "full":
        inputs.extend([BASELINE,COST_INPUT])
        progress(progress_path, f"六周正式运行开始。源码 {source['commit']}，单次上限 300 秒、全程上限 90 分钟。")
    summary = dict(mode=mode, source=source, module_sha256=digest(Path(__file__)),
                   versions=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__),
                   inputs_sha256={f.relative_to(eb.ROOT).as_posix():digest(f) for f in inputs},
                   hardware=facilities,spec=asdict(SPEC),boundary=rule,warehouse_release_min=eb.RELEASE,
                   market=dict(delivery_zone="DE-LU",timezone="Europe/Berlin",price_unit="EUR/MWh",
                               foresight="Known native hourly day-ahead prices across each solve period.",
                               cost_scope="Wholesale electricity only, no network charges.",
                               dates=sorted({d for p in periods for d in p.cases})),
                   observed_vehicle_ids=sorted({v for p in periods for _,v in p.keys}),
                   sample_truck_days=sum(len(p.keys) for p in periods),
                   solver_policy=dict(time_limit_seconds=SOLVE_SECONDS, full_wall_seconds=STUDY_SECONDS,
                       service_exact=True, zero_delay_regression_exact=True,
                       energy_relative_gap=RELATIVE_COST_GAP, energy_absolute_gap_weekly_eur=ABSOLUTE_COST_GAP,
                       maximum_unresolved_groups=MAX_UNRESOLVED))
    for delay in delays:
        weeks = []
        try:
            for i,period in enumerate(periods):
                log.check_budget()
                zero = baseline[i] if baseline is not None else None
                week = _weekly_pair(period,facilities,delay,rule,log,zero)
                weeks.append(week)
                if previous is not None:
                    for name in FACILITIES:
                        prior, current = previous[i][name]["keys"], week[name]["keys"]
                        if prior is not None and current is not None and len(current) > len(prior):
                            raise ValueError(("service grew with setup time", period.days[0]["date"],
                                              delay, name, sorted(prior), sorted(current)))
                if zero is not None:
                    for name in FACILITIES:
                        info = _lost_service(period,zero,week,delay,name,log,facilities["two"],rule)
                        attribution.append(dict(period=period.days[0]["date"],delay_minutes=delay,
                                                facility=name, service_difference=info))
        except StudyLimit as exc:
            stopped = str(exc)
        row = _pair_value(delay,periods,weeks,mode)
        measured.append(row)
        print(f"delta={delay} one={row['one']['completed']}/{summary['sample_truck_days']} "
              f"two={row['two']['completed']}/{summary['sample_truck_days']} "
              f"savings_EUR={row['savings_eur_2021']} unresolved_groups={len(log.unresolved)}",flush=True)
        if stopped is not None:
            break
        if len(log.unresolved) > MAX_UNRESOLVED:
            stopped = "more than three unresolved period/delay/facility groups"
            break
        if delay == 0 and row["savings_eur_2021"] is not None:
            regression = _regression(mode,row,periods,weeks,reference)
        if delay == 0:
            baseline = weeks
        if (mode == "full" and delay == 5 and all(row[n]["completed"] is not None
                and row[n]["completed"] == measured[0][n]["completed"] for n in FACILITIES)):
            delays.extend(STRESS)
        previous = weeks
    summary.update(results=measured, attribution=attribution, regression_zero=regression,
                   status="complete" if stopped is None else "stopped",stop_reason=stopped,
                   unresolved_group_count=len(log.unresolved),unresolved_groups=sorted(log.unresolved),
                   audited_schedules=log.audited,solver_calls=log.calls,
                   wall_seconds=perf_counter()-began,
                   benchmark=break_even([0.] * 6)["benchmark"] if mode == "full" else None)
    if mode == "pilot" and regression:
        print(f"concurrent: 8/8 vehicle-days, second port saves EUR {measured[0]['savings_eur_2021']:.5f}",flush=True)
    if mode == "full":
        counts = "、".join(f"δ={r['delay_minutes']} 分钟单／双接口 "
                         f"{r['one']['completed']}/{r['two']['completed']} 车日" for r in measured)
        progress(progress_path, f"独立审计完成。通过 {log.audited} 份可行排程的逐枪、分钟电费和跨日电量复算。")
        progress(progress_path, f"六周正式运行结束。状态 {summary['status']}，"
                 f"用时 {summary['wall_seconds']:.2f} 秒，未判定组 {len(log.unresolved)}。{counts}。")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    stages = parser.add_mutually_exclusive_group()
    stages.add_argument("--pilot",action="store_true",help="Original three concurrent holdout dates")
    stages.add_argument("--trial",action="store_true",help="5-minute changeover, week of 18 October")
    parser.add_argument("--output",type=Path,help="Fresh offline archive run directory")
    parser.add_argument("--progress",type=Path,help="Progress log in the parent of the offline run directory")
    args = parser.parse_args()
    mode = "pilot" if args.pilot else "trial" if args.trial else "full"
    output = checked_output(args.output,eb.ROOT) if args.output else None
    if args.progress is not None and (output is None or args.progress.resolve().parent != output.parent):
        parser.error("--progress must point to the parent of the archive run directory")
    if output is not None:
        output.mkdir(parents=True)
    result = run(mode,output,args.progress)
    if output is not None:
        write_json(output/"summary.json",result)
    if result["status"] == "stopped":
        raise SystemExit(result["stop_reason"])


if __name__ == "__main__":
    main()
