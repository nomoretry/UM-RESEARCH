"""Fixed-build feasibility with named plugs and downtime between different trucks."""
import math

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .model import validate_input


def solve_changeover(case, hardware, delay):
    """Keep one truck and one live charging setpoint per physical plug per original slot.

    The previous assignment releases at its right boundary. Idle time counts
    toward the required turnaround. Only a delayed start can truncate a slot.
    """
    validate_input(case)
    if not math.isfinite(delay) or delay < 0:
        raise ValueError("Changeover minutes must be finite and nonnegative")
    if case["connector_policy"] != "slot_boundary_switching":
        raise ValueError("This experiment requires boundary reassignment")
    sites = {s["id"]: s for s in case["sites"]}
    if set(hardware) != set(sites):
        raise ValueError("Hardware must specify the installed plugs and kW at every site")
    vehicles = {v["id"]: v for v in case["vehicles"]}
    n = case["slot_count"]
    width = case["slot_hours"] * 60
    remainder = delay % width
    cuts = [0, remainder, width] if 0 < remainder < width else [0, width]
    parts = list(zip(cuts, cuts[1:]))
    lo, hi, integer = [], [], []
    ri, ci, val, lower, upper = [], [], [], [], []

    def variable(low, high, binary=False):
        idx = len(lo)
        lo.append(low)
        hi.append(high)
        integer.append(int(binary))
        return idx

    def row(terms, low=-np.inf, high=np.inf):
        idx = len(lower)
        for col, value in terms:
            ri.append(idx)
            ci.append(col)
            val.append(value)
        lower.append(low)
        upper.append(high)

    assigned, power = {}, {}
    by_vehicle = {(v, t): [] for v in vehicles for t in range(n)}
    for site, build in hardware.items():
        plugs, capacity = build["interfaces"], build["power_kw"]
        if type(plugs) is not int or plugs < 0 or not math.isfinite(capacity) or capacity < 0:
            raise ValueError("Invalid fixed site hardware")
        for t in range(n):
            eligible = [v for v, truck in vehicles.items() if sites[site]["active"] and truck["charging_site"][t] == site]
            for k in range(1, plugs + 1):
                for v in eligible:
                    key = v, site, k, t
                    assigned[key] = variable(0, 1, binary=True)
                    by_vehicle[v, t].append(key)
                    limit = vehicles[v]["power_limit_kw"][site]
                    levels = [variable(0, limit) for _ in parts]
                    power[key] = levels
                    # An earlier, different truck on this same plug can block
                    # only prefixes of the current slot. Check all earlier slots
                    # so an idle slot consumes (rather than resets) setup time.
                    blockers_at_start = []
                    for i, (start, _) in enumerate(parts):
                        row([(levels[i], 1), (assigned[key], -limit)], high=0)
                        for prior in range(t - 1, -1, -1):
                            if (t - prior - 1) * width + start >= delay - 1e-10:
                                break
                            blockers = [assigned[u, site, k, prior] for u in vehicles
                                        if u != v and (u, site, k, prior) in assigned]
                            if blockers:
                                row([(levels[i], 1)] + [(x, limit) for x in blockers], high=limit)
                                if i == 0:
                                    blockers_at_start.extend(blockers)
                    if len(parts) == 2:
                        # Without a blocking predecessor, the setpoint must
                        # be identical on both sides of the accounting split.
                        row([(levels[0], 1), (levels[1], -1)], high=0)
                        row([(levels[1], 1), (levels[0], -1)]
                            + [(x, -limit) for x in blockers_at_start], high=0)
                if eligible:
                    row([(assigned[v, site, k, t], 1) for v in eligible], high=1)
            for i in range(len(parts)):
                if eligible and plugs:
                    row([(power[v, site, k, t][i], 1) for v in eligible for k in range(1, plugs + 1)],
                        high=capacity)

    energy = {}
    for v, truck in vehicles.items():
        initial = truck["initial_energy_kwh"]
        trace = [variable(initial, initial)]
        for t in range(n):
            keys = by_vehicle[v, t]
            if keys:
                row([(assigned[key], 1) for key in keys], high=1)
            minimum = initial if t == n - 1 else truck["energy_min_kwh"]
            trace.append(variable(minimum, truck["energy_max_kwh"]))
            terms = [(trace[-1], 1), (trace[-2], -1)]
            for key in keys:
                for level, (start, end) in zip(power[key], parts):
                    terms.append((level, -(end-start) / 60 * truck["efficiency"]))
            draw = truck["drive_energy_kwh"][t]
            row(terms, -draw, -draw)
        energy[v] = trace

    matrix = coo_matrix((val, (ri, ci)), shape=(len(lower), len(lo))).tocsr()
    result = milp(np.zeros(len(lo)), integrality=integer, bounds=Bounds(lo, hi),
                  constraints=LinearConstraint(matrix, lower, upper), options={"mip_rel_gap": 0, "time_limit": 60})
    if result.status not in (0, 2):
        raise RuntimeError(f"Feasibility unresolved: {result.message}")
    feasible = result.status == 0
    schedule = []
    if feasible:
        for (v, site, k, t), levels in power.items():
            segments = [[t * width + start, t * width + end, float(result.x[level])]
                        for level, (start, end) in zip(levels, parts) if result.x[level] > 1e-8]
            if segments:
                schedule.append({"site": site, "connector": k, "slot": t, "vehicle": v, "segments": segments})
    return {"status": "optimal" if feasible else "infeasible", "schedule": schedule,
            "objective": float(result.fun) if feasible else None,
            "dual_bound": float(result.mip_dual_bound) if feasible else None,
            "mip_gap": float(result.mip_gap) if feasible else None,
            "energy_kwh": {v: result.x[trace].tolist() for v, trace in energy.items()} if feasible else None}
