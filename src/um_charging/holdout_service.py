"""Chronological, price-independent service registration on a full boundary-B week."""
from collections import defaultdict
import math
from time import perf_counter
import warnings

from scipy.optimize import Bounds, LinearConstraint, OptimizeResult, milp
from scipy.sparse import coo_matrix

from . import energy_boundary as eb
from . import fleet_changeover as fc
from . import site_sizing as ss
from .cabinet_audit import close
from .fleet_service import EPS, SITES


def _day_weights(keys, reference):
    ordered = sorted(keys, key=lambda key: int(key[1]))
    if len({int(truck) for _, truck in ordered}) != len(ordered):
        raise ValueError("Numeric vehicle IDs must be unique within the day")
    # One overlap outranks all ID bits, one completion outranks all overlaps and bits.
    overlap_weight = 1 << len(ordered)
    count_weight = (1 + len(set(keys) & reference)) * overlap_weight
    return {key: count_weight + overlap_weight * (key in reference) + (1 << rank)
            for rank, key in enumerate(reversed(ordered))}, count_weight


def _integer_certificate(dual, incumbent):
    """Bounds on the maximization score, using the native minimization dual bound."""
    upper = math.floor(-dual + EPS) if dual is not None and math.isfinite(dual) else None
    if incumbent is not None and upper is not None and upper < incumbent:
        raise ValueError(("Integer score exceeds native dual bound", incumbent, dual))
    return [incumbent, upper]


def _service_proof(period, day, locked, reference, result):
    """Reconstruct the scalar proof from the saved schedule states and native bounds."""
    stats = result["stats"]
    today = {key for key in period.keys if key[0] == day}
    weights, count_weight = _day_weights(today, set(reference))
    incumbent = completed = None
    states = result["states"]
    if result["audit"] is not None:
        if (len(states) != len(period.keys) or {(s["date"], s["vehicle_id"]) for s in states} != period.keys
                or any(type(s["served"]) is not bool for s in states)):
            raise ValueError("Incomplete weekly service states")
        selected = eb.selected(result)
        if any((key in selected) != value for key, value in locked.items()):
            raise ValueError("Earlier service choices changed during replay")
        selected_today = today & selected
        completed = len(selected_today)
        incumbent = sum(weights[key] for key in selected_today)
        close(incumbent, -stats["objective_upper"], "daily integer service score")
    bounds = _integer_certificate(stats["native_mip_dual_bound"], incumbent)
    certified = stats["status_code"] in (0, 1) and incumbent is not None and bounds[0] == bounds[1]
    return dict(integer_score_bounds=bounds,
                score_bounds=[stats["native_mip_dual_bound"], stats["objective_upper"]],
                completed_bounds=[completed, min(len(today), bounds[1] // count_weight)
                                  if bounds[1] is not None else None],
                status="certified" if certified else "infeasible" if stats["status_code"] == 2 else "unresolved")


def audit_service_certificate(period, day, locked, reference, result):
    proof = _service_proof(period, day, locked, reference, result)
    if any(result["stats"][field] != value for field, value in proof.items()):
        raise ValueError("Stored daily service certificate differs from its native bounds and states")
    return proof


def solve_service_day(period, design, day, locked, reference, deadline):
    """Maximize today's count, overlap and numeric-ID order with earlier choices fixed."""
    began = perf_counter()
    today = {key for key in period.keys if key[0] == day}
    if not today or set(locked) != {key for key in period.keys if key[0] < day}:
        raise ValueError("An active date and all earlier service choices are required")
    if any(type(value) is not bool for value in locked.values()):
        raise ValueError("Earlier service choices must be Boolean")
    weights, _ = _day_weights(today, set(reference))
    spec, caps, hardware = eb.DEFAULT_SPEC, design.caps, design.hardware()
    model, levels, decisions, _ = ss._grouped_zero_delay_matrix(
        period, hardware, spec, dict(zip(SITES, caps, strict=True)), None, set())
    for key, (serve, _, _) in levels.items():
        model.cost[serve] = -weights.get(key, 0)
        if key in locked:
            model.lower[serve] = model.upper[serve] = int(locked[key])
    matrix = coo_matrix((model.data, (model.row, model.col)),
                        shape=(len(model.lb), len(model.cost))).tocsr()
    remaining = min(deadline, began + fc.SOLVE_SECONDS) - perf_counter()
    if remaining <= 0:
        native = OptimizeResult(status=1, message="wall-clock budget before solver", fun=None, x=None)
    else:
        # Match the grouped M8 physical solver tolerances and cap its wall-clock allocation.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Unrecognized options detected.*", category=RuntimeWarning)
            native = milp(model.cost, integrality=model.integer, bounds=Bounds(model.lower, model.upper),
                          constraints=LinearConstraint(matrix, model.lb, model.ub),
                          options={"time_limit": remaining, "mip_rel_gap": 0., "mip_abs_gap": 0.,
                                   "mip_feasibility_tolerance": 1e-9, "primal_feasibility_tolerance": 1e-9})
    stats = fc._solve_stats(native, False, len(today), perf_counter() - began, 0., 0.)
    result = dict(stats=stats, schedule=[], states=[], audit=None)
    if native.x is not None:
        for (d, v), (serve, x, y) in levels.items():
            chosen = bool(native.x[serve] > .5)
            close(native.x[serve], int(chosen), "binary service choice")
            result["states"].append(dict(date=d, vehicle_id=v, served=chosen,
                                         x=float(native.x[x]), y=float(native.x[y])))
        stats["objective"] = -len(eb.selected(result))  # physical replay checks the complete week's states
        assigned = defaultdict(dict)
        for d, v, site, q, left, right, energy in ss._expand_grouped(period, decisions, native.x):
            if energy <= fc.ENERGY_ROUNDOFF_KWH:
                continue
            plugs = assigned[site, q]
            plug = plugs.setdefault(v, len(plugs) + 1)
            result["schedule"].append(dict(date=d, vehicle_id=v, site=site, plug=plug,
                reservation_slot=q, start_min=period.offset[d] + left, end_min=period.offset[d] + right,
                power_kw=float(energy * 60 / (right - left))))
        result["audit"] = ss.meter_replay(period, hardware, spec, caps, result, physical=True)
    stats.update(_service_proof(period, day, locked, reference, result))
    stats["seconds"] = perf_counter() - began
    return result
