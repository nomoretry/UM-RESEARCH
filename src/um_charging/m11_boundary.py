"""M11 weekly conservation and optimistic service boundaries on the existing charging grid."""
from collections import defaultdict
from functools import partial
from time import perf_counter
from unittest.mock import patch
import warnings

from scipy.optimize import Bounds, LinearConstraint
from scipy.sparse import coo_matrix

from . import holdout_service, m10_breakpoint, m10_evidence, m10_immediate, site_sizing as ss


def _levels(variant, model, period, spec, rule, active, physical):
    reserve, cap, target = spec.reserve_kwh, spec.capacity_kwh, spec.boundary_kwh
    span = cap - reserve
    levels = {}
    for key in sorted(active):
        s = model.var(int(not physical), 1, integer=physical)
        x, y = model.var(reserve, cap), model.var(reserve, cap)
        levels[key] = s, x, y
        if physical:
            # If omitted, drawing and charging both vanish (by daily balance).
            model.add([(y, 1), (x, -1), (s, -span)], high=0)

    if variant == "weekly":
        for truck in sorted({v for _, v in active}):
            chain = [levels[k] for k in sorted(active) if k[1] == truck]
            model.lower[chain[0][1]] = model.upper[chain[0][1]] = target
            for (_, _, y), (_, x, _) in zip(chain, chain[1:]):
                model.add([(y, 1), (x, -1)], 0, 0)
            model.lower[chain[-1][2]] = target
    elif variant == "open":
        for chain in period.chains:
            prev = None
            for key in chain:
                curr = levels.get(key)
                if curr is not None:
                    s, x, _ = curr
                    if prev is None:
                        model.lower[x] = model.upper[x] = target
                    elif physical:
                        t, _, y = prev
                        for sign in (-1, 1):
                            # Start at target when either adjacent duty was omitted.
                            for indicator in (s, t):
                                model.add([(x, sign), (indicator, -span)], high=sign*target)
                            model.add([(x, sign), (y, -sign), (s, span), (t, span)], high=2*span)
                    else:
                        model.add([(prev[2], 1), (x, -1)], 0, 0)
                prev = curr
    else:
        raise ValueError(variant)
    return levels


def _segments(period, variant, result):
    states = {(r["date"], r["vehicle_id"]): r for r in result["states"] if r["served"]}
    spec = ss.eb.DEFAULT_SPEC
    last = {}
    details = []
    for segment in sorted(m10_immediate._segments(period, states)):
        vehicle = segment[0][1]
        start = states[segment[0]]["x"]
        end = states[segment[-1]]["y"]
        expected = last.get(vehicle, spec.boundary_kwh) if variant == "weekly" else spec.boundary_kwh
        ss.close(start, expected, ("segment start", segment))
        for a, b in zip(segment, segment[1:]):
            ss.close(states[a]["y"], states[b]["x"], ("midnight", b))
        for k in segment:
            for edge in ("x", "y"):
                if not spec.reserve_kwh-ss.EPS <= states[k][edge] <= spec.capacity_kwh+ss.EPS:
                    raise ValueError(("SOC outside bounds", k, edge))
        last[vehicle] = end
        details.append(dict(vehicle_id=vehicle, first_date=segment[0][0], last_date=segment[-1][0],
                            start_kwh=start, end_kwh=end, difference_kwh=end-spec.boundary_kwh))
    if variant == "weekly" and any(v < spec.boundary_kwh-ss.EPS for v in last.values()):
        raise ValueError("Weekly closing reserve failed")
    return details


def replay(period, req, result):
    spec = ss.eb.DEFAULT_SPEC
    hardware, caps = _hardware(req)
    variant = req["variant"]
    physical = req["kind"] != "energy"
    audit = ss.fc.replay(period, hardware, spec, 0, result, rule=variant, physical=physical)
    quarters = defaultdict(float)
    for row in result["schedule"]:
        quarters[row["site"], row["reservation_slot"]] += row["power_kw"]*(row["end_min"]-row["start_min"])/60
    grid, peaks = {}, {}
    for site, limit in zip(ss.SITES, caps, strict=True):
        energy = [v for (s, _), v in quarters.items() if s == site]
        grid[site], peaks[site] = sum(energy), 4*max(energy, default=0)
        if peaks[site] > limit + ss.EPS:
            raise ValueError(("quarter cap", site))
    chosen = ss.eb.selected(result)
    if req["kind"] in ("energy", "service") and chosen != set(map(tuple, req["fixed"])):
        raise ValueError("Fixed service differs")
    if any((tuple(k[:2]) in chosen) != k[2] for k in req.get("locked", [])):
        raise ValueError("A previous registration changed")
    return dict(passed=True, segments=_segments(period, variant, result), site_grid_kwh=grid,
                site_quarter_peak_kw=peaks, **({} if physical else {"purchase_eur":audit["purchase_eur"]}))


def _hardware(req):
    if req["kind"] == "m8":
        hardware = m10_breakpoint._m8_hardware()
        return hardware, tuple(hardware[s]["power_kw"] for s in ss.SITES)
    return ss.Design(*req["design"]).hardware(), req["caps"]


def solve(period, req):
    began = perf_counter()
    kind = req["kind"]
    hardware, caps = _hardware(req)
    if kind == "m8":
        # M8's original separate-site reservation sets agree with this builder
        # precisely when no truck switches sites within a reservation quarter.
        for spans in ss.fc._physical_quarters(period, period.keys).values():
            groups = [{v for _, _, _, sites in spans for v in sites[s]} for s in ss.SITES]
            if groups[0] & groups[1]:
                raise ValueError("Original M8 site reservations require separate construction")
    register = kind in ("m8", "m9")
    fixed = None if register else set(map(tuple, req["fixed"]))
    with patch.object(ss, "_levels", partial(_levels, req["variant"])):
        model, levels, pieces, _ = ss._grouped_zero_delay_matrix(
            period, hardware, ss.eb.DEFAULT_SPEC, dict(zip(ss.SITES, caps)), fixed, set())
    weights = {}
    if kind != "energy":
        model.cost[:] = [0.] * len(model.cost)
        if kind == "m8":
            weights = m10_breakpoint._weights(period, set(map(tuple, req["preferred"])))
        if kind == "m9":
            today = {k for k in period.keys if k[0] == req["date"]}
            weights, _ = holdout_service._day_weights(today, set())
        for k, w in weights.items():
            model.cost[levels[k][0]] = -w
        for date, truck, keep in req.get("locked", []):
            i = levels[date, truck][0]
            model.lower[i] = model.upper[i] = int(keep)
    mat = coo_matrix((model.data, (model.row, model.col)), shape=(len(model.lb),len(model.cost))).tocsr()
    rel = ss.fc.RELATIVE_COST_GAP if kind == "energy" else 0.
    absolute = ss.fc.ABSOLUTE_COST_GAP if kind == "energy" else 0.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Unrecognized options detected.*", category=RuntimeWarning)
        native = m10_evidence._configured_milp(
            model.cost, integrality=model.integer, bounds=Bounds(model.lower, model.upper),
            constraints=LinearConstraint(mat, model.lb, model.ub),
            options=dict(time_limit=max(.001, ss.fc.SOLVE_SECONDS-(perf_counter()-began)),
                         mip_rel_gap=rel, mip_abs_gap=absolute, mip_feasibility_tolerance=1e-9,
                         primal_feasibility_tolerance=1e-9))
    stats = ss.fc._solve_stats(native, False, len(levels), perf_counter()-began, rel, absolute)
    result = dict(stats=stats, schedule=[], states=[], audit=None)
    if native.x is None:
        return result
    chosen = set()
    for (date, truck), (s, x, y) in levels.items():
        keep = bool(native.x[s] > .5)
        ss.close(native.x[s], int(keep), "service indicator")
        if keep:
            chosen.add((date, truck))
        result["states"].append(dict(date=date, vehicle_id=truck, served=keep,
                                     x=float(native.x[x]), y=float(native.x[y])))
    assigned = defaultdict(dict)
    for day, truck, site, q, a, b, energy in ss._expand_grouped(period, pieces, native.x):
        plugs = assigned[site,q]
        result["schedule"].append(dict(date=day, vehicle_id=truck, site=site,
            reservation_slot=q, plug=plugs.setdefault(truck,len(plugs)+1), start_min=period.offset[day]+a,
            end_min=period.offset[day]+b, power_kw=float(energy*60/(b-a))))
    if kind != "energy":
        stats["objective"] = -len(chosen)
    result["audit"] = replay(period, req, result)
    if register:
        score = sum(weights.get(k, 0) for k in chosen)
        ss.close(score, -native.fun, "service score")
        bounds = holdout_service._integer_certificate(stats["objective_lower"], score)
        stats["integer_score_bounds"] = bounds
        stats["status"] = "certified" if bounds == [score, score] else "unresolved"
    elif kind == "service":
        stats["status"] = "certified"
    elif stats["status_code"] == 1 and stats["absolute_gap"] is not None and stats["absolute_gap"] <= .10:
        stats["status"] = "bounded"
    return result
