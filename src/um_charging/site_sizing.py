"""Size the two fleet charging sites and scan independent quarter-hour limits."""
import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import gzip
from itertools import product
import json
import math
from pathlib import Path
import platform
import subprocess
from time import perf_counter
import warnings
from zoneinfo import ZoneInfo

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, OptimizeResult, milp
from scipy.sparse import coo_matrix

from . import energy_boundary as eb
from . import fleet_changeover as fc
from .__main__ import checked_output, digest, write_json
from .cabinet_audit import audit_settlement, close
from .cabinet_model import _balance, _levels
from .cabinet_tariff import NETWORK_INPUT, annual_factors, load_network, settle
from .connector_cost import COST_INPUT, break_even
from .fleet_service import EPS, SITES, subset_case


COARSE_KW = (0, 20, 30, 40, 50)
FINE_KW = (0, 10, 15, 20, 25, 30, 35, 40, 45, 50)
TIMEOUT_COST_GAP_EUR = .05
ENERGY_ACCEPTED = {"certified", "bounded"}
PORT, WAREHOUSE = SITES
EXISTING_KW = (100, 75)
CONNECTION_INPUT = eb.ROOT / "studies/day-ahead/connection_cost.json"
DEMAND_REFERENCE = eb.WEEKS.with_name("cabinet_demand.json")


@dataclass(frozen=True, order=True)
class Design:
    port_plugs: int
    port_kw: int
    warehouse_kw: int

    def __post_init__(self):
        if not (0 <= self.warehouse_kw <= 50 and (
                self.port_plugs == 0 and self.port_kw == 0 or
                self.port_plugs == 1 and 0 < self.port_kw <= 50 or
                self.port_plugs == 2 and 0 < self.port_kw <= 100)):
            raise ValueError("Invalid port and warehouse build")

    @property
    def label(self):
        return f"p{self.port_plugs}-{self.port_kw}-w{self.warehouse_kw}"

    @property
    def caps(self):
        return self.port_kw, self.warehouse_kw

    def hardware(self):
        return {PORT: dict(interfaces=self.port_plugs, power_kw=self.port_kw),
                WAREHOUSE: dict(interfaces=int(self.warehouse_kw > 0), power_kw=self.warehouse_kw)}

    def chargers(self):
        port_rating = 50 if self.port_plugs == 2 else self.port_kw
        return [port_rating] * self.port_plugs + ([self.warehouse_kw] if self.warehouse_kw else [])


BASELINE = Design(1, 50, 50)
LARGEST = Design(2, 100, 50)


def _levels_with_preference(period, spec, fixed, prefer):
    physical = fixed is None
    active = period.keys if physical else set(fixed)
    if not (active <= period.keys and (not prefer or physical and prefer <= active)):
        raise ValueError("Unknown duty or incompatible service preference")
    model = eb.Matrix()
    levels = _levels(model, period, spec, eb.B, active, physical)
    weight = len(prefer) + 1
    if physical:
        for key, (serve, _, _) in levels.items():
            model.cost[serve] = -weight - int(key in prefer)
    if not levels:
        model.var(0, 0)
    return model, levels, active, weight


def _zero_delay_matrix(period, hardware, spec, limits, fixed, prefer):
    """Original ungrouped zero-delay model, retained for equivalence checks."""
    physical = fixed is None
    model, levels, active, weight = _levels_with_preference(period, spec, fixed, prefer)
    dispatch = []
    charged = defaultdict(list)
    for quarter, intervals in sorted(fc._physical_quarters(period, active).items()):
        trucks = {site: sorted({v for _, _, _, available in intervals for v in available[site]})
                  for site in SITES if limits[site]}
        across = defaultdict(list)
        for site, vehicles in trucks.items():
            plugs = hardware[site]["interfaces"]
            limit = hardware[site]["power_kw"]
            rate = min(spec.truck_kw, limit)
            reservations = {}
            for truck in vehicles:
                if len(vehicles) > plugs or any(truck in others for s, others in trucks.items() if s != site):
                    reserve = model.var(0, 1, integer=True)
                    reservations[truck] = reserve
                    across[truck].append((reserve, 1.))
            if len(vehicles) > plugs:
                model.add([(i, 1.) for i in reservations.values()], high=plugs)
            quarter_energy = []
            for day, left, right, available in intervals:
                hours = (right - left) / 60
                maximum = min(rate * hours, limits[site] / 4)
                price = 0. if physical else period.prices[day][int(left // 60)] / 1000
                simultaneous = []
                for truck in available[site]:
                    energy = model.var(0., maximum, price)
                    if truck in reservations:
                        model.add([(energy, 1.), (reservations[truck], -maximum)], high=0.)
                    charged[day, truck].append((right, energy))
                    dispatch.append((day, truck, site, quarter, left, right, energy))
                    simultaneous.append((energy, 1.))
                if plugs * rate > limit and simultaneous:
                    model.add(simultaneous, high=limit * hours)
                quarter_energy.extend(simultaneous)
            if limits[site] < limit and quarter_energy:
                model.add(quarter_energy, high=limits[site] / 4)
        for reservations in across.values():
            if len(reservations) > 1:
                model.add(reservations, high=1.)
    for day, case in period.cases.items():
        subset = subset_case(case, [v for v in case["trucks"] if (day, v) in active])
        _balance(model, subset, day, levels, charged, spec)
    return model, levels, dispatch, weight


def _grouped_zero_delay_matrix(period, hardware, spec, limits, fixed, prefer):
    """Pool identical whole quarters using the energy-boundary model's grouping.

    Grouped plugs can all run at their effective full-quarter rate together.
    An internal event, a binding common feed, or a cross-site reservation keeps
    its original quarter. The reconstruction then preserves every minute cap.
    """
    physical = fixed is None
    model, levels, active, weight = _levels_with_preference(period, spec, fixed, prefer)
    crossings = defaultdict(dict)
    if all(limits.values()):
        for quarter, intervals in fc._physical_quarters(period, active).items():
            eligible = [{v for _, _, _, by_site in intervals for v in by_site[s]} for s in SITES]
            overlap = eligible[0] & eligible[1]
            if overlap:
                day = intervals[0][0]
                crossings[day][quarter - period.offset[day] // 15] = overlap
    dispatch = []
    charged = defaultdict(list)
    for day, original in period.cases.items():
        case = subset_case(original, [v for v in original["trucks"] if (day, v) in active])
        across = defaultdict(list)
        for site in SITES:
            cap = limits[site]
            if cap == 0:
                continue
            h = hardware[site]
            plugs, limit = h["interfaces"], h["power_kw"]
            rate = min(spec.truck_kw, limit)
            pool_spec = replace(spec, truck_kw=min(rate, cap))
            pool_feed = {**h, "power_kw": cap}
            for count, parts in eb.blocks(case, site, pool_feed, pool_spec, unpooled=crossings[day]):
                trucks = sorted({truck for _, _, eligible in parts for truck in eligible})
                if not trucks:
                    continue
                quarter = int(parts[0][0] // 15)
                overlap = crossings[day].get(quarter, set())
                reservations = {}
                for truck in trucks:
                    if len(trucks) > plugs or truck in overlap:
                        reserve = model.var(0, count, integer=True)
                        reservations[truck] = reserve
                        if truck in overlap:
                            across[quarter, truck].append((reserve, 1.))
                if len(trucks) > plugs:
                    model.add([(i, 1.) for i in reservations.values()], high=plugs * count)
                block_energy, pieces = [], []
                for left, right, eligible in parts:
                    hours = (right - left) / 60
                    maximum = min(rate * hours, cap / 4)
                    price = 0. if physical else period.prices[day][int(left // 60)] / 1000
                    simultaneous = []
                    for truck in eligible:
                        energy = model.var(0., maximum * count, price)
                        if truck in reservations:
                            model.add([(energy, 1.), (reservations[truck], -maximum)], high=0.)
                        charged[day, truck].append((right + 15 * (count - 1), energy))
                        pieces.append((truck, left, right, energy))
                        simultaneous.append((energy, 1.))
                    if plugs * rate > limit and simultaneous:
                        model.add(simultaneous, high=limit * hours * count)
                    block_energy.extend(simultaneous)
                if cap < limit and block_energy:
                    model.add(block_energy, high=cap * count / 4)
                dispatch.append((day, site, count, reservations, pieces))
        for terms in across.values():
            model.add(terms, high=1.)
        _balance(model, case, day, levels, charged, spec)
    return model, levels, dispatch, weight


def _expand_grouped(period, dispatch, solution):
    """Convert each pooled energy variable back to physical quarter intervals."""
    for day, site, count, reservations, pieces in dispatch:
        slots = eb.reservation_slots(count, reservations, solution)
        for truck, left, right, col in pieces:
            energy = solution[col]
            if energy <= fc.ENERGY_ROUNDOFF_KWH:
                continue
            assigned = slots.get(truck, range(count))
            if not assigned:
                if energy > eb.UNRESERVED_ENERGY_TOLERANCE_KWH:
                    raise ValueError(("positive energy without a reservation", day, site, truck, energy))
                continue
            for q in assigned:
                start, end = left + 15 * q, right + 15 * q
                yield (day, truck, site, (period.offset[day] + int(start)) // 15,
                       start, end, energy / len(assigned))


def meter_replay(period, hardware, spec, caps, result, *, physical=False, delay=0):
    """Independently replay events, minutes, native-price hours and quarter meters."""
    limit = dict(zip(SITES, caps, strict=True))
    audit = fc.replay(period, hardware, spec, delay, result, physical=physical)
    quarters = defaultdict(float)
    reservations = defaultdict(set)
    for row in result["schedule"]:
        key = row["site"], row["reservation_slot"]
        reservations[key].add(row["vehicle_id"])
        quarters[key] += (
            row["power_kw"] * (row["end_min"] - row["start_min"]) / 60)
    kwh = {s: math.fsum(v for (site, _), v in quarters.items() if site == s) for s in SITES}
    peaks = {s: 4 * max((v for (site, _), v in quarters.items() if site == s), default=0.) for s in SITES}
    for s in SITES:
        if peaks[s] > limit[s] + EPS:
            raise ValueError(("quarter peak cap", s, peaks[s], limit[s]))
    max_plugs = {s: max((len(v) for (site, _), v in reservations.items() if site == s), default=0)
                 for s in SITES}
    return dict(**audit, site_grid_kwh=kwh, site_quarter_peak_kw=peaks, used_plugs=max_plugs)


def solve(period, design, *, caps=None, fixed=None, prefer=(), spec=eb.DEFAULT_SPEC,
          deadline=math.inf, exact_energy=False, grouped=True):
    """Certify maximum service or minimize wholesale cost on a fixed duty set."""
    began = perf_counter()
    caps = design.caps if caps is None else caps
    if any(not 0 <= p <= k for p, k in zip(caps, design.caps, strict=True)):
        raise ValueError("A quarter cap must be between zero and the installed kW")
    hardware = design.hardware()
    physical = fixed is None
    build = _grouped_zero_delay_matrix if grouped else _zero_delay_matrix
    model, levels, decisions, weight = build(
        period, hardware, spec, dict(zip(SITES, caps, strict=True)), fixed, set(prefer))
    constraint = coo_matrix((model.data, (model.row, model.col)),
                            shape=(len(model.lb), len(model.cost))).tocsr()
    relative = 0. if physical or exact_energy else fc.RELATIVE_COST_GAP
    absolute = 0. if physical or exact_energy else fc.ABSOLUTE_COST_GAP
    remaining = min(deadline, began + fc.SOLVE_SECONDS) - perf_counter()
    if remaining <= 0:
        native = OptimizeResult(status=1, message="wall-clock budget before solver", fun=None, x=None)
    else:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Unrecognized options detected.*", category=RuntimeWarning)
            native = milp(model.cost, integrality=model.integer, bounds=Bounds(model.lower, model.upper),
                          constraints=LinearConstraint(constraint, model.lb, model.ub),
                          options={"time_limit": remaining, "mip_rel_gap": relative, "mip_abs_gap": absolute,
                                   "mip_feasibility_tolerance": 1e-9, "primal_feasibility_tolerance": 1e-9})
    stats = fc._solve_stats(native, False, len(period.keys), perf_counter() - began, relative, absolute)
    result = dict(stats=stats, schedule=[], states=[], audit=None)
    if native.x is not None:
        assigned = defaultdict(dict)
        pieces = (_expand_grouped(period, decisions, native.x) if grouped else
                  ((d, v, s, q, a, b, native.x[col]) for d, v, s, q, a, b, col in decisions))
        for day, truck, site, quarter, left, right, energy in pieces:
            if energy <= fc.ENERGY_ROUNDOFF_KWH:
                continue
            plugs = assigned[site, quarter]
            plug = plugs.setdefault(truck, len(plugs) + 1)
            result["schedule"].append(dict(date=day, vehicle_id=truck, site=site, plug=plug,
                reservation_slot=quarter, start_min=period.offset[day] + left,
                end_min=period.offset[day] + right, power_kw=float(energy * 60 / (right - left))))
        result["states"] = [dict(date=d, vehicle_id=v, served=bool(native.x[s] > .5),
                                 x=float(native.x[x]), y=float(native.x[y]))
                            for (d, v), (s, x, y) in levels.items()]
    if physical:
        served = eb.selected(result)
        stats["score_bounds"] = [stats["objective_lower"], stats["objective_upper"]]
        score_lower = stats["objective_lower"]
        max_count = len(period.keys) if score_lower is None else math.floor((-score_lower + EPS) / weight)
        stats["completed_bounds"] = [len(served), min(max_count, len(period.keys))]
        if native.x is not None:
            close(-weight * len(served) - len(served & set(prefer)), native.fun, "service preference")
            stats["objective"] = -len(served)
        if stats["status"] == "certified" and len(set(stats["completed_bounds"])) != 1:
            raise ValueError(("maximum service was not proved", stats))
    if native.x is not None:
        result["audit"] = meter_replay(period, hardware, spec, caps, result, physical=physical)
    stats["seconds"] = perf_counter() - began
    return result


def best_dispatch(rows, design, scenario):
    """Select the lowest replayed invoice among eligible grid settings."""
    choices = [r for r in rows if all(p <= k for p, k in zip(r["caps_kw"], design.caps, strict=True))]
    return min(choices, key=lambda r: (r["bills"][scenario]["annual_total_eur_2025"], r["caps_kw"]),
               default=None)


def _progress(path, message):
    print(message, flush=True)
    if path is not None:
        timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"\n- {timestamp} {message}\n")


class Evidence:
    """Apply the registered budget and archive each actual solver result."""
    def __init__(self, output, began, trial):
        self.output = output
        self.deadline = math.inf if trial else began + fc.STUDY_SECONDS
        self.trial = trial
        self.calls = []
        self.unresolved = set()

    def check(self):
        if len(self.unresolved) > fc.MAX_UNRESOLVED:
            raise fc.StudyLimit("more than three unresolved groups")
        if perf_counter() >= self.deadline:
            raise fc.StudyLimit("formal wall-clock budget exhausted")

    def call(self, period, design, phase, caps, fixed=None, prefer=(), exact=False, delay=0, grouped=True):
        self.check()
        if delay:
            result = fc.solve(period, design.hardware(), eb.DEFAULT_SPEC, delay, fixed,
                              deadline=self.deadline, peak_limits=dict(zip(SITES, caps, strict=True)))
            if result["audit"] is not None:
                result["audit"] = meter_replay(period, design.hardware(), eb.DEFAULT_SPEC, caps, result,
                                               physical=fixed is None, delay=delay)
        else:
            result = solve(period, design, caps=caps, fixed=fixed, prefer=prefer,
                           deadline=self.deadline, exact_energy=exact, grouped=grouped)
        stats = result["stats"]
        timed_out = stats["status_code"] == 1 and "time limit" in stats["message"].lower()
        if (timed_out and fixed is not None and not exact and result["audit"] is not None
                and stats["absolute_gap"] is not None and stats["absolute_gap"] <= TIMEOUT_COST_GAP_EUR + 1e-9):
            stats["status"] = "bounded"
        label = f"{len(self.calls) + 1:05d}"
        week = period.days[0]["week_start"]
        record = dict(id=label, week=week, design=design.label, phase=phase, caps_kw=caps,
                      delay_min=delay, model="named_plugs" if delay else "grouped" if grouped else "ungrouped",
                      audited=result["audit"] is not None, **stats)
        self.calls.append(record)
        if self.output is not None:
            with gzip.open(self.output / f"{label}.json.gz", "wt", encoding="utf-8", compresslevel=1) as stream:
                json.dump(dict(**record, result=result), stream, ensure_ascii=False, allow_nan=False)
            with (self.output / "solves.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        bounds = stats.get("completed_bounds", [stats["objective_lower"], stats["objective_upper"]])
        print(f"{label} {week} {phase} {design.label} {caps} {stats['status']} "
              f"bounds={bounds} seconds={stats['seconds']:.3f}", flush=True)
        if stats["status"] == "unresolved":
            self.unresolved.add((week, design.label, caps, delay))
            if self.trial and (stats["seconds"] >= fc.SOLVE_SECONDS or timed_out):
                raise fc.StudyLimit("a weekly trial solve hit the five-minute gate")
        if self.trial and stats["seconds"] > fc.SOLVE_SECONDS and stats["status"] != "bounded":
            raise fc.StudyLimit("a weekly trial solve exceeded the five-minute gate")
        return label, result


def design_grid(grid):
    singles = [Design(int(p > 0), p, w) for p, w in product(grid, repeat=2)]
    doubles = [Design(2, p, w) for p, w in product((50, 100), grid)]
    return singles + doubles


def _dominates(large, small):
    return (large.port_plugs >= small.port_plugs and
            large.port_kw >= small.port_kw and large.warehouse_kw >= small.warehouse_kw)


def _service_grid(periods, reference, designs, evidence, records):
    for design in sorted(designs, key=lambda d: (d != LARGEST, d)):
        if design in records:
            continue
        records[design] = weeks = []
        for i, period in enumerate(periods):
            evidence.check()
            keys = reference & period.keys
            upper = records[LARGEST][i] if design != LARGEST else None
            if upper is not None and upper["bounds"] == [len(keys)] * 2:
                for small, known in records.items():
                    if small != design and _dominates(design, small) and i < len(known):
                        witness = known[i]
                        if witness["status"] == "certified" and set(witness["served"]) == keys:
                            weeks.append({**witness, "monotone_upper_solve": upper["solve"]})
                            break
                if i < len(weeks):
                    continue
            label, result = evidence.call(period, design, "service", design.caps, prefer=keys)
            stats = result["stats"]
            weeks.append(dict(status=stats["status"], bounds=stats["completed_bounds"],
                              served=sorted(eb.selected(result)), solve=label))


def _service_summary(records, reference):
    selected = {d: set().union(*(set(w["served"]) for w in weeks)) for d, weeks in records.items()}
    summary = {}
    for design, weeks in records.items():
        keys = selected[design]
        bounds = [sum(w["bounds"][i] for w in weeks) for i in (0, 1)]
        exact = all(w["status"] == "certified" for w in weeks)
        lost, added = reference - keys, keys - reference
        if len(keys) != len(reference) - len(lost) + len(added) or len(keys) != bounds[0]:
            raise ValueError(("duty accounting", design.label))
        row = dict(design=design.label, **asdict(design), completed=len(keys) if exact else None,
                   completion_bounds=bounds, same_service=exact and not lost and not added,
                   added_vs_reference=sorted(added), lost_vs_reference=sorted(lost),
                   weeks=weeks)
        if lost and exact:
            port = Design(max(1, design.port_plugs), 100 if design.port_plugs == 2 else 50, design.warehouse_kw)
            warehouse = Design(design.port_plugs, design.port_kw, 50)
            # One-site interventions use complete certified optimal witnesses.
            # A day omitted by an alternative witness is not an infeasibility proof.
            groups = defaultdict(list)
            for key in sorted(lost):
                recovered = [s for s, option in zip(SITES, (port, warehouse), strict=True)
                             if option != design and option in records
                             and all(w["status"] == "certified" for w in records[option])
                             and key in selected[option]]
                groups["+".join(recovered) or "joint_or_alternate_set"].append(key)
            row["one_site_release"] = dict(
                port_design=port.label, warehouse_design=warehouse.label, restored_in=groups,
                port_limit=("connection_kw" if design.port_plugs == 2 else
                            "no_port_charger" if not design.port_plugs else "connection_and_charger_kw"),
                warehouse_limit="connection_and_charger_kw" if design.warehouse_kw else "no_warehouse_charger")
        summary[design] = row
    return summary


def _check_service_order(service):
    checks = 0
    for small, old in service.items():
        for large, new in service.items():
            if small == large or not _dominates(large, small):
                continue
            if old["completed"] is None or new["completed"] is None:
                continue
            checks += 1
            if new["completed"] < old["completed"]:
                raise ValueError(("larger hardware lost service", small, large))
            if old["same_service"] and new["completed"] == old["completed"] and not new["same_service"]:
                raise ValueError(("larger hardware lost identical maximum set", small, large))
    return checks


def _active_build(design, caps):
    return Design(design.port_plugs if caps[0] else 0, design.port_kw if caps[0] else 0,
                  design.warehouse_kw if caps[1] else 0)


class DispatchGrid:
    def __init__(self, periods, reference, network, evidence):
        self.periods = periods
        self.reference = reference
        self.network = network
        self.evidence = evidence
        self.cache = defaultdict(dict)
        self.reused = 0
        self.energy_checks = 0
        self.settlement_checks = 0

    def weekly(self, period, design, caps, delay, exact):
        design = _active_build(design, caps)
        cache = self.cache[period.days[0]["week_start"], caps, delay]
        if design in cache:
            return cache[design]
        if not exact:
            for wider, row in cache.items():
                plug_fit = (wider.port_plugs == design.port_plugs or
                            delay == 0 and row.get("used_plugs", {}).get(PORT, math.inf) <= design.port_plugs)
                if (row["status"] in ENERGY_ACCEPTED and plug_fit and _dominates(wider, design) and all(
                            row["site_peak_kw"][s] <= k + EPS for s, k in zip(SITES, design.caps, strict=True))):
                    # The audited optimal schedule of the wider build fits this build.
                    cache[design] = row
                    self.reused += 1
                    return row
            for smaller, row in cache.items():
                if row["status"] == "infeasible" and _dominates(smaller, design):
                    cache[design] = row
                    self.reused += 1
                    return row
        label, result = self.evidence.call(period, design, "energy", caps,
                                          fixed=self.reference & period.keys, delay=delay, exact=exact)
        stats = result["stats"]
        row = dict(status=stats["status"], solve=label, lower_eur=stats["objective_lower"],
                   upper_eur=stats["objective_upper"])
        if result["audit"] is not None:
            row.update({k: result["audit"][k] for k in
                        ("purchase_eur", "site_peak_kw", "site_grid_kwh", "site_quarter_peak_kw", "used_plugs")})
        cache[design] = row
        return row

    def dispatch(self, design, caps, *, delay=0, exact=False):
        weeks = []
        for period in self.periods:
            row = self.weekly(period, design, caps, delay, exact)
            weeks.append(row)
            if row["status"] not in ENERGY_ACCEPTED:
                return dict(design=design.label, caps_kw=caps, status=row["status"], weeks=weeks,
                            delay_min=delay)
        euro = math.fsum(row["purchase_eur"] for row in weeks)
        kwh = {s: math.fsum(row["site_grid_kwh"][s] for row in weeks) for s in SITES}
        peaks = {s: max(row["site_quarter_peak_kw"][s] for row in weeks) for s in SITES}
        bills = {}
        if not self.evidence.trial:
            for scenario in ("N0", *self.network["tariffs"], *self.network["capacity_sensitivities_eur_per_kw_year"]):
                bill = settle(self.network, euro, kwh, peaks, scenario)
                audit_settlement(self.network, euro, kwh, peaks, scenario, bill)
                self.settlement_checks += 1
                bills[scenario] = bill
        status = "bounded" if any(row["status"] == "bounded" for row in weeks) else "certified"
        return dict(design=design.label, caps_kw=caps, status=status, weeks=weeks, delay_min=delay,
                    purchase_eur=euro, lower_eur=math.fsum(row["lower_eur"] for row in weeks),
                    site_grid_kwh=kwh, site_quarter_peak_kw=peaks, bills=bills)

    def options(self, design, grid):
        ports = (*grid, 60, 70, 80, 90, 100) if design.port_kw == 100 else grid
        return list(product([p for p in ports if p <= design.port_kw],
                            [w for w in grid if w <= design.warehouse_kw]))

    def check_order(self, rows):
        solved = [(design, row) for design, choices in rows.items() for row in choices
                  if row["status"] in ENERGY_ACCEPTED]
        for i, (d1, a) in enumerate(solved):
            for d2, b in solved[i + 1:]:
                if _dominates(d2, d1) and all(y >= x for y, x in zip(b["caps_kw"], a["caps_kw"], strict=True)):
                    small, large = a, b
                elif _dominates(d1, d2) and all(x >= y for x, y in zip(a["caps_kw"], b["caps_kw"], strict=True)):
                    small, large = b, a
                else:
                    continue
                self.energy_checks += 1
                if large["lower_eur"] > small["purchase_eur"] + EPS:
                    raise ValueError(("larger upper limits increased the minimum wholesale bill",
                                      small["design"], small["caps_kw"], large["design"], large["caps_kw"]))


def _regression(periods, service, dispatch):
    refs = {r["facility"]: r for r in eb.read_json(fc.BASELINE)["full"]
            if r["spec"] == "S300" and r["rule"] == eb.B}
    names = ("one", "two")
    all_weeks = {week: i for i, (week,) in enumerate(eb.read_json(fc.BASELINE)["components"])}
    result = {}
    for name, design in zip(names, (BASELINE, LARGEST), strict=True):
        if service[design]["completed"] is None:
            result[name] = dict(status="unresolved", design=design.label, phase="service")
            continue
        actual = dispatch.dispatch(design, design.caps, exact=True)
        if actual["status"] == "unresolved":
            result[name] = actual
            continue
        if not service[design]["same_service"] or actual["status"] != "certified":
            raise ValueError(("baseline must retain the registered duty set", design.label, actual["status"]))
        expected = [refs[name]["week_common_eur"][all_weeks[p.days[0]["week_start"]]] for p in periods]
        for a, b in zip(actual["weeks"], expected, strict=True):
            close(a["purchase_eur"], b, "prior weekly wholesale bill")
        close(actual["purchase_eur"], math.fsum(expected), "prior total wholesale bill")
        result[name] = dict(status="passed", design=design.label, expected_eur=math.fsum(expected),
                            actual_eur=actual["purchase_eur"], completed=service[design]["completed"],
                            solve_ids=[w["solve"] for w in actual["weeks"]])
    return result


def _load_costs(path, network):
    data = eb.read_json(path)
    bkz = data["connection"]
    rate = bkz["discount_rate"]
    life = bkz["economic_life_years"]
    factor = network["price_level"]["cpi"]["2025"] / data["price_level"]["index_2026_oct"]
    connection = bkz["eur_per_kw_net"] * factor * rate / (1 - (1 + rate) ** -life)
    charger = break_even([0.] * network["annualization"]["sample_weeks"])["benchmark"]
    ref = eb.read_json(COST_INPUT)["whole_charger_reference"]
    annual_equipment = (1 + ref["installation_share_of_equipment"]) * charger["capital_recovery_factor"]
    annual_equipment += ref["maintenance_share_of_equipment_per_year"]
    equipment = {int(p): row["equipment_eur_net"] * factor * annual_equipment
                 for p, row in data["charger_equipment_prices"].items()}
    equipment[50] = charger["annual_cost_2025_eur"]
    return dict(annual_bkz_eur_2025_per_kw=connection, annual_charger_eur_2025_by_kw=equipment)


def annual_capital_costs(design, materials):
    """Return known equipment, unquoted ratings, and both connection charges."""
    equipment = materials["annual_charger_eur_2025_by_kw"]
    ratings = design.chargers()
    missing = sorted(p for p in ratings if p not in equipment)
    known = math.fsum(equipment.get(p, 0.) for p in ratings)
    capacity = dict(new=sum(design.caps),
                    existing=sum(max(0, k - old) for k, old in zip(design.caps, EXISTING_KW, strict=True)))
    connection = {basis: k * materials["annual_bkz_eur_2025_per_kw"] for basis, k in capacity.items()}
    return known, missing, connection


def annual_tables(rows, materials, scenarios):
    """Compute both capacity bases and price ceilings for unquoted ratings."""
    values = {}
    for design, options in rows.items():
        known, missing, connection = annual_capital_costs(design, materials)
        for scenario in scenarios:
            best = best_dispatch([r for r in options if r["status"] in ENERGY_ACCEPTED], design, scenario)
            if best is None:
                continue
            bill = best["bills"][scenario]
            values[design.label, scenario] = dict(
                caps_kw=best["caps_kw"], peaks_kw=[bill["sites"][s]["peak_kw"] for s in SITES],
                bands=[bill["sites"][s]["band"] for s in SITES], purchase_eur_2021=best["purchase_eur"],
                purchase_eur_2021_bounds=[best["lower_eur"], best["purchase_eur"]],
                dispatch_status=best["status"],
                known_chargers_eur=known, unpriced_chargers_kw=missing,
                energy_eur=bill["annual_energy_eur_2025"],
                network_energy_eur=bill["annual_network_energy_eur_2025"],
                demand_eur=bill["annual_capacity_eur_2025"],
                connection_eur=dict(connection),
                solve_ids=[w["solve"] for w in best["weeks"]])
    winners = {}
    for scenario in scenarios:
        base = values.get((BASELINE.label, scenario))
        if base is None:
            continue
        reference = {**base, "connection_eur": dict(new=sum(EXISTING_KW) * materials["annual_bkz_eur_2025_per_kw"],
                                                    existing=0.)}
        for basis in ("new", "existing"):
            key = scenario, basis
            def parts(row):
                return dict(chargers=row["known_chargers_eur"], connection=row["connection_eur"][basis],
                            demand=row["demand_eur"], energy=row["energy_eur"] + row["network_energy_eur"])
            ref = parts(reference)
            ref_total = math.fsum(ref.values())
            known = {}
            for (label, bill_scenario), row in values.items():
                if bill_scenario != scenario:
                    continue
                costs = parts(row)
                subtotal = math.fsum(costs.values())
                if not row["unpriced_chargers_kw"]:
                    known[label] = subtotal
                row.setdefault("total_eur", {})[basis] = (
                    subtotal if not row["unpriced_chargers_kw"] else None)
                row.setdefault("unpriced_ceiling_vs_legacy_eur", {})[basis] = (
                    ref_total - subtotal if row["unpriced_chargers_kw"] else None)
            winner = min(known, key=lambda label: (known[label], label))
            row = values[winner, scenario]
            best_total = known[winner]
            for (label, bill_scenario), option in values.items():
                if bill_scenario == scenario and option["unpriced_chargers_kw"]:
                    option.setdefault("unpriced_ceiling_vs_best_eur", {})[basis] = (
                        best_total - math.fsum(parts(option).values()))
            costs = parts(row)
            winners[key] = dict(design=winner, annual_total_eur=best_total, components_eur=costs,
                                legacy_total_eur=ref_total, legacy_components_eur=ref,
                                change_eur={k: costs[k] - ref[k] for k in costs},
                                caps_kw=row["caps_kw"], peaks_kw=row["peaks_kw"],
                                purchase_eur_2021_bounds=row["purchase_eur_2021_bounds"],
                                dispatch_status=row["dispatch_status"],
                                priced_options=len(known))
    return values, winners


def _check_demand_reference(rows, network, grid):
    """Use the preceding P2 objective and invoice definitions on matching bases."""
    refs = {r["scenario"]: r for r in eb.read_json(DEMAND_REFERENCE)["main"]
            if r["equipment"] == "one" and r["policy"] == "P2"}
    available = [r for r in rows if r["status"] in ENERGY_ACCEPTED]
    by_caps = {r["caps_kw"]: r for r in available}
    scenarios = refs.keys()
    results = {}
    for scenario in scenarios:
        ref = refs[scenario]
        best = best_dispatch(available, BASELINE, scenario)
        rounded_caps = tuple(next(p for p in grid if p + EPS >= ref["sites"][s]["peak_kw"]) for s in SITES)
        rounded = by_caps.get(rounded_caps)
        if best is None or rounded is None:
            results[scenario] = dict(status="unresolved", rounded_caps_kw=rounded_caps)
            continue
        raw = ref["annual_total_interval_eur_2025"]
        current = best["bills"][scenario]["annual_total_eur_2025"]
        amounts_agree = {"frank", "official", "N0"}
        capacity_rates = network["capacity_sensitivities_eur_per_kw_year"]
        if scenario in capacity_rates:
            # P2 optimized wholesale plus peak. The volume rate was applied to
            # that schedule afterwards, and can change when grid caps move the band.
            lower, upper = ref["objective_lower_eur_2025"], ref["objective_upper_eur_2025"]
            def comparable(row):
                bill = row["bills"][scenario]
                return bill["annual_energy_eur_2025"] + bill["annual_capacity_eur_2025"]
            compared = min(comparable(r) for r in available)
            comparable_rounded = comparable(rounded)
        elif scenario in amounts_agree:
            lower, upper = raw
            compared = current
            comparable_rounded = rounded["bills"][scenario]["annual_total_eur_2025"]
        else:
            raise ValueError(f"Unregistered demand reference {scenario}")
        demand_allowance = math.fsum(
            max(0., cap - ref["sites"][site]["peak_kw"]) * ref["sites"][site]["capacity_eur_per_kw_year"]
            for site, cap in zip(SITES, rounded_caps, strict=True)) * annual_factors(network)[1]
        solve_allowance = (rounded["purchase_eur"] - rounded["lower_eur"]) * annual_factors(network)[0]
        if compared < lower - EPS or comparable_rounded > upper + demand_allowance + solve_allowance + EPS:
            raise ValueError(("grid and continuous reference disagree", scenario, compared, lower,
                              comparable_rounded, upper, demand_allowance, solve_allowance))
        results[scenario] = dict(
            status="passed", comparable_objective_prior_interval_eur=[lower, upper],
            comparable_objective_grid_eur=compared,
            comparable_objective_grid_minus_prior_eur=[compared - upper, compared - lower],
            rounded_caps_kw=rounded_caps, rounded_demand_allowance_eur=demand_allowance,
            rounded_solver_allowance_eur=solve_allowance, prior_invoice_interval_eur=raw,
            grid_invoice_eur=current, grid_invoice_minus_prior_eur=[current - raw[1], current - raw[0]],
            comparison_scope="prior wholesale plus demand" if scenario in capacity_rates else "full invoice")
    return results


def _changeover(winners, designs, dispatch, evidence):
    checked = {}
    for (scenario, basis), row in winners.items():
        name, caps = row["design"], row["caps_kw"]
        key = name, caps
        if key not in checked:
            design = designs[name]
            replayed = dispatch.dispatch(design, caps, delay=5)
            if replayed["status"] == "infeasible" and caps != design.caps:
                replayed["at_hardware_caps"] = dispatch.dispatch(design, design.caps, delay=5)
            tested = replayed.get("at_hardware_caps", replayed)
            if tested["status"] in ENERGY_ACCEPTED:
                replayed["completed_at_hardware"] = len(dispatch.reference)
                replayed["maximum_proof"] = "matched zero-delay maximum replayed with five-minute changeovers"
            elif tested["status"] == "infeasible":
                rows = [evidence.call(p, design, "service", design.caps, delay=5) for p in dispatch.periods]
                replayed["service_solves"] = [label for label, _ in rows]
                replayed["completion_bounds"] = [
                    sum(out["stats"]["completed_bounds"][i] for _, out in rows) for i in (0, 1)]
                replayed["lost_vs_reference"] = sorted(dispatch.reference - set().union(
                    *(eb.selected(out) for _, out in rows)))
            checked[key] = replayed
        tested = checked[key].get("at_hardware_caps", checked[key])
        if tested["status"] in ENERGY_ACCEPTED:
            revised = tested["bills"][scenario]["annual_total_eur_2025"]
            row["delta_5_annual_total_eur"] = row["components_eur"]["chargers"] + row["components_eur"]["connection"] + revised
            row["delta_5_change_eur"] = row["delta_5_annual_total_eur"] - row["annual_total_eur"]
            row["delta_5_caps_kw"] = tested["caps_kw"]
            row["delta_5_status"] = tested["status"]
            row["delta_5_purchase_eur_2021_bounds"] = [tested["lower_eur"], tested["purchase_eur"]]
    return list(checked.values())


def _scan(operations, service, dispatch, grid):
    for design in sorted(service, reverse=True):
        dispatch.evidence.check()
        if not service[design]["same_service"]:
            continue
        options = operations.setdefault(design, [])
        excluded = [r["caps_kw"] for r in options if r["status"] == "infeasible"]
        visited = {r["caps_kw"] for r in options}
        for caps in reversed(dispatch.options(design, grid)):
            if caps in visited:
                continue
            p, w = caps
            if any(p <= a and w <= b for a, b in excluded):
                continue
            row = dispatch.dispatch(design, caps)
            options.append(row)
            if row["status"] == "infeasible":
                excluded.append(caps)


def _refinements(service, operations, materials, scenarios):
    """Add 5 kW steps through coarse service crossings and around priced minima."""
    added = set()
    for lo, hi in zip(COARSE_KW, COARSE_KW[1:]):
        power = [k for k in FINE_KW if lo < k < hi]
        for w in COARSE_KW:
            low, high = Design(int(lo > 0), lo, w), Design(1, hi, w)
            if service[high]["same_service"] and not service[low]["same_service"]:
                added.update(Design(1, k, w) for k in power)
        for p in [Design(int(k > 0), k, 0) for k in COARSE_KW] + [Design(2, 50, 0), Design(2, 100, 0)]:
            low, high = Design(p.port_plugs, p.port_kw, lo), Design(p.port_plugs, p.port_kw, hi)
            if service[high]["same_service"] and not service[low]["same_service"]:
                added.update(Design(p.port_plugs, p.port_kw, k) for k in power)
    _, winners = annual_tables(operations, materials, scenarios)
    labels = {r["design"] for r in winners.values()}
    for design in service:
        if design.label not in labels:
            continue
        if design.port_plugs == 1:
            added.update(Design(1, k, design.warehouse_kw)
                         for k in FINE_KW if 0 < abs(k - design.port_kw) <= 5 and k > 0)
        added.update(Design(design.port_plugs, design.port_kw, k)
                     for k in FINE_KW if 0 < abs(k - design.warehouse_kw) <= 5)
        if design.warehouse_kw == 0:
            added.update(Design(design.port_plugs, design.port_kw, k) for k in (10, 15))
    # The unpriced port-only ratings are useful comparisons against a quoted build.
    added.update(Design(1, k, 0) for k in FINE_KW if k > 0)
    for d in tuple(added):
        added.add(Design(max(1, d.port_plugs), 100 if d.port_plugs == 2 else 50, d.warehouse_kw))
        added.add(Design(d.port_plugs, d.port_kw, 50))
    return sorted(added - service.keys())


def retry_trial(previous, output=None, progress_path=None):
    """Compare rated builds against the old model, then retry the logged cap pair."""
    began = perf_counter()
    old = eb.read_json(previous / "summary.json")
    rows = [json.loads(line) for line in (previous / "solves.jsonl").read_text(encoding="utf-8").splitlines()]
    pending, = old["unresolved_groups"]
    week, build, caps, delay = pending
    timed_out, = [r for r in rows if r["status"] == "unresolved" and
                  (r["week"], r["design"], r["caps_kw"], r["delay_min"]) == tuple(pending)]
    period, = fc._periods("trial")
    if (week != period.days[0]["week_start"] or delay != 0 or timed_out["phase"] != "energy"):
        raise ValueError("The recovery input must identify the logged zero-delay trial cost timeout")
    designs = {d.label: d for d in design_grid(COARSE_KW)}
    if set(designs) != {r["design"] for r in old["service"]}:
        raise ValueError("The logged trial and coarse hardware menu differ")
    gate = designs[build]
    caps = tuple(caps)
    excluded = Design(gate.port_plugs, *caps)
    if excluded.label not in designs:
        raise ValueError("The timed-out peak pair does not identify a build on the coarse menu")
    reference = set(map(tuple, old["reference_service"]))
    if not reference <= period.keys:
        raise ValueError("The archived trial duties differ from the current calendar")
    evidence = Evidence(output, began, True)
    checks, retry, stop = [], None, None
    try:
        for design in sorted(d for d in designs.values() if d != excluded):
            sets, charges, ids = [], [], []
            for grouped in (False, True):
                sid, service = evidence.call(period, design, "equivalence-service", design.caps,
                                             prefer=reference, grouped=grouped)
                if service["stats"]["status"] != "certified":
                    raise fc.StudyLimit(f"unproved equivalence service at {design.label}")
                keys = eb.selected(service)
                eid, energy = evidence.call(period, design, "equivalence-energy", design.caps,
                                             fixed=keys, exact=True, grouped=grouped)
                if energy["stats"]["status"] != "certified":
                    raise fc.StudyLimit(f"unproved equivalence electricity at {design.label}")
                sets.append(keys)
                charges.append(energy["audit"]["purchase_eur"])
                ids.append([sid, eid])
            delta = charges[1] - charges[0]
            passed = sets[0] == sets[1] and abs(delta) <= EPS
            checks.append(dict(design=design.label, caps_kw=design.caps, passed=passed, solve_ids=ids,
                               selected=[sorted(keys) for keys in sets], purchase_eur_2021=charges,
                               difference_eur=delta))
            if not passed:
                raise fc.StudyLimit(f"the zero-delay models differ at {design.label}")
        max_error = max(abs(row["difference_eur"]) for row in checks)
        _progress(progress_path, f"刻钟分组等价性通过。{len(checks)} 个硬件设计的完成集合一致，"
                  f"最大购电费差 {max_error:.3g} 欧元。")
        label, result = evidence.call(period, gate, "retry-timeout", caps, fixed=reference)
        retry = dict(design=gate.label, caps_kw=caps, original_solve=timed_out["id"],
                     solve=label, **result["stats"])
        if retry["status"] not in ENERGY_ACCEPTED:
            raise fc.StudyLimit("the originally timed-out trial point remains unresolved")
    except fc.StudyLimit as exc:
        stop = str(exc)
    wall = perf_counter() - began
    _progress(progress_path, f"一周重试{'通过' if stop is None else '停止'}。"
              f"{len(checks)} 个等价性对照，{len(evidence.calls)} 次求解，"
              f"原超时点状态 {retry['status'] if retry else '未判定'}，"
              f"墙钟 {wall:.2f} 秒，未判定 {len(evidence.unresolved)} 组。")
    return dict(status="complete" if stop is None else "stopped", stop_reason=stop, trial=True, week=week,
                source=source_state(), excluded_rated_build=excluded.label, comparisons=checks,
                retry=retry, wall_seconds=wall, solver_calls=len(evidence.calls),
                maximum_comparison_delta_eur=max((abs(r["difference_eur"]) for r in checks), default=None),
                audited_schedules=sum(r["audited"] for r in evidence.calls),
                slowest_solve_seconds=max((r["seconds"] for r in evidence.calls), default=0.),
                bounded_solve_count=sum(r["status"] == "bounded" for r in evidence.calls),
                unresolved_groups=sorted(evidence.unresolved))


def source_state():
    return dict(commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=eb.ROOT,
                                                encoding="utf-8").strip(),
                dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=eb.ROOT).strip()))


def run(trial, output=None, progress_path=None, connection_input=CONNECTION_INPUT):
    began = perf_counter()
    source = source_state()
    if not trial and source["dirty"]:
        raise ValueError("Commit the source before the formal run")
    periods = fc._periods("trial" if trial else "full")
    universe = set().union(*(p.keys for p in periods))
    reference, = [set(map(tuple, r["selected"])) for r in eb.read_json(fc.BASELINE)["full"]
                  if r["spec"] == "S300" and r["rule"] == eb.B and r["facility"] == "one"]
    reference &= universe
    if not trial and (len(reference), len(universe)) != (54, 73):
        raise ValueError("The registered six-week fleet or reference cohort changed")
    network = load_network()
    scenarios = ("N0", *network["tariffs"], *network["capacity_sensitivities_eur_per_kw_year"])
    evidence = Evidence(output, began, trial)
    dispatch = DispatchGrid(periods, reference, network, evidence)
    records, operations, demand, costs, winners, materials = {}, {}, {}, {}, {}, {}
    changeover, regression, service = [], {}, {}
    stop = None
    paths = [eb.WEEKS, eb.NATIVE, fc.BASELINE, DEMAND_REFERENCE, COST_INPUT, NETWORK_INPUT]
    if not trial:
        materials = _load_costs(connection_input, network)
        _progress(progress_path, f"正式运行开始。源码 {source['commit']}，{len(periods)} 周，目标 {len(reference)}/{len(universe)} 车日。")
    try:
        _service_grid(periods, reference, design_grid(COARSE_KW), evidence, records)
        service = _service_summary(records, reference)
        regression = _regression(periods, service, dispatch)
        _scan(operations, service, dispatch, COARSE_KW)
        if not trial:
            refined = _refinements(service, operations, materials, scenarios)
            _service_grid(periods, reference, refined, evidence, records)
            service = _service_summary(records, reference)
            _scan(operations, service, dispatch, FINE_KW)
            demand = _check_demand_reference(operations.get(BASELINE, []), network, FINE_KW)
            costs, winners = annual_tables(operations, materials, scenarios)
            _progress(progress_path, f"年成本表完成。{len(costs)} 个设计与网费组合，{len(winners)} 个口径最低有报价方案。")
            changeover = _changeover(winners, {d.label: d for d in service}, dispatch, evidence)
        dispatch.check_order(operations)
        service_checks = _check_service_order(service)
        evidence.check()
    except fc.StudyLimit as exc:
        stop = str(exc)
        service = _service_summary({d: w for d, w in records.items() if len(w) == len(periods)}, reference)
        service_checks = _check_service_order(service)
    elapsed = perf_counter() - began
    audited = sum(row["audited"] for row in evidence.calls)
    slowest = max((row["seconds"] for row in evidence.calls), default=0.)
    unresolved = sorted(evidence.unresolved)
    if trial:
        _progress(progress_path, f"一周试跑{'通过' if not stop and not unresolved else '待查'}。"
                  f"{len(service)} 个设计，{len(evidence.calls)} 次求解，最慢 {slowest:.3f} 秒，"
                  f"墙钟 {elapsed:.2f} 秒，未判定 {len(unresolved)} 组。")
    else:
        _progress(progress_path, f"独立审计完成。{audited} 份可行排程，{dispatch.settlement_checks} 份年网费账单。")
        _progress(progress_path, f"正式运行{'结束' if stop is None else '停止'}。"
                  f"墙钟 {elapsed:.2f} 秒，未判定 {len(unresolved)} 组，最慢 {slowest:.3f} 秒。")
    status = "stopped" if stop else "partial" if unresolved else "complete"
    summary = dict(
        status=status, stop_reason=stop, trial=trial, source=source,
        versions=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__),
        inputs_sha256={p.relative_to(eb.ROOT).as_posix(): digest(p) for p in paths},
        market=dict(area="DE-LU", timezone="Europe/Berlin", prices="EUR/MWh, native hourly delivery",
                    dates=sorted({d for p in periods for d in p.cases}),
                    foresight="All tasks and native prices within the solved week are known."),
        warehouse_release_min=eb.RELEASE, boundary=eb.B, vehicle_spec=asdict(eb.DEFAULT_SPEC),
        reference_service=sorted(reference), sample_truck_days=len(universe),
        regression=regression, service=list(service.values()),
        cost_rows=[dict(design=d, scenario=s, **row) for (d, s), row in costs.items()],
        winners=[dict(scenario=s, connection_basis=b, **row) for (s, b), row in winners.items()],
        benchmarks=demand, investment=materials, changeover=changeover,
        wall_seconds=elapsed, slowest_solve_seconds=slowest, solver_calls=len(evidence.calls),
        unresolved_groups=unresolved, audited_schedules=audited, audited_invoices=dispatch.settlement_checks,
        bounded_solve_count=sum(r["status"] == "bounded" for r in evidence.calls),
        monotone_service_checks=service_checks, monotone_energy_checks=dispatch.energy_checks,
        reused_dispatches=dispatch.reused)
    if not trial:
        summary["inputs_sha256"]["studies/day-ahead/connection_cost.json"] = digest(connection_input)
    if output is not None:
        write_json(output / "operations.json", [row for options in operations.values() for row in options])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--trial", action="store_true", help="Run the coarse grid for the registered October trial week")
    modes.add_argument("--retry-trial", type=Path, help="Previous trial directory containing the timed-out point")
    parser.add_argument("--connection-cost", type=Path, default=CONNECTION_INPUT)
    parser.add_argument("--output", type=Path, help="Fresh directory inside the offline Git archive")
    parser.add_argument("--progress", type=Path, help="Progress.md in the parent offline run directory")
    args = parser.parse_args()
    output = checked_output(args.output, eb.ROOT) if args.output else None
    log = args.progress.resolve() if args.progress else None
    if log is not None and (output is None or log.parent != output.parent):
        parser.error("--progress must belong to the parent of --output")
    if output is not None:
        output.mkdir(parents=True)
    summary = (retry_trial(args.retry_trial, output, log) if args.retry_trial else
               run(args.trial, output, log, args.connection_cost))
    if output is not None:
        write_json(output / "summary.json", summary)
    if args.retry_trial is None:
        count = sum(row["same_service"] for row in summary["service"])
        print(f"status={summary['status']} same_service_designs={count} "
              f"reference={len(summary['reference_service'])}/{summary['sample_truck_days']} "
              f"one_EUR={summary['regression'].get('one', {}).get('actual_eur')} "
              f"two_EUR={summary['regression'].get('two', {}).get('actual_eur')} "
              f"wall_seconds={summary['wall_seconds']:.2f}", flush=True)
    if summary["status"] == "stopped":
        raise SystemExit(summary["stop_reason"])


if __name__ == "__main__":
    main()
