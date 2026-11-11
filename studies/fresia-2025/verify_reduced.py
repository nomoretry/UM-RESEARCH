"""Direct SOC replay and exhaustive hardware/connection search, independent of the MILP."""
from bisect import bisect_right
from itertools import product
from math import isclose, isfinite

from check_milan import CAPITAL_RECOVERY_FACTOR, CHARGERS


TOL = 1e-6


def require(condition, message):
    if not condition:
        raise ValueError(message)


def curve_power(curve, soc):
    """Direct interpolation of neighbouring plot points, without MILP segment inequalities."""
    xs = [s for s, _ in curve]
    i = min(max(0, bisect_right(xs, soc) - 1), len(curve) - 2)
    (s0, p0), (s1, p1) = curve[i:i + 2]
    return p0 + (p1 - p0) * (soc - s0) / (s1 - s0)


def reachable_energy(data, events, chosen, curves=None):
    """Exact terminal energy interval for a single vehicle with a specified plug sequence."""
    retention = 1 - data["self_discharge_fraction_per_slot"]
    low = high = data["initial_kwh"]
    for t, (activity, _) in enumerate(events):
        demand = data["use_kwh_per_slot"][activity]
        kind = chosen.get(t)
        highest = high * retention - demand
        if kind is not None:
            hours = data["efficiency"][kind] * data["slot_hours"]
            if curves is None:
                highest += data["equipment_grid_kw"][kind] * hours
            else:
                # The maximum can occur at an interior SOC kink during taper.
                capacity = data["max_kwh"]
                energies = [low, high] + [s * capacity for s, _ in curves[kind] if low < s * capacity < high]
                highest = max(e * retention + hours * curve_power(curves[kind], e / capacity)
                              for e in energies) - demand
        low = max(data["min_kwh"], low * retention - demand)
        high = min(data["max_kwh"], highest)
        if low > high + TOL:
            return None
    return low, high


def enumerate_facilities(data, slots, routes, curves=None):
    """Enumerate individual plug assignments and check joint use of installed devices."""
    vehicles = data["vehicles"]
    kinds = tuple(data["equipment_grid_kw"])
    permitted = {}
    for v in vehicles:
        for t in slots:
            require(routes[v][t] == ("idle", data["depot"]), "enumeration requires depot dwell")
        permitted[v] = []
        for sequence in product((None, *kinds), repeat=len(slots)):
            band = reachable_energy(data, routes[v], dict(zip(slots, sequence)), curves)
            if band is not None and band[0] - TOL <= data["terminal_kwh"] <= band[1] + TOL:
                permitted[v].append(sequence)
    results = []
    for counts in product(range(len(vehicles) + 1), repeat=len(kinds)):
        units = dict(zip(kinds, counts))
        feasible = any(
            all(assignments.count(k) <= units[k] for assignments in zip(*plan) for k in kinds)
            for plan in product(*(permitted[v] for v in vehicles))
        )
        annual = sum(n * (CAPITAL_RECOVERY_FACTOR * CHARGERS[k][0] + CHARGERS[k][1])
                     for k, n in units.items())
        results.append({"units": units, "feasible": feasible, "annual_eur": annual})
    return results


def check_solution(data, slots, routes, solution, options, curves=None):
    feasible = [row for row in options if row["feasible"]]
    if solution["status"] == "infeasible":
        require(not feasible, "MILP infeasibility disagrees with independent enumeration")
        return
    require(solution["status"] == "optimal" and feasible, "no independently feasible facility")
    units = solution["units"]
    for k in data["equipment_grid_kw"]:
        require(type(units[k]) is int and 0 <= units[k] <= len(routes), "invalid device count")
    selected = [row for row in feasible if row["units"] == units]
    require(len(selected) == 1, "MILP hardware has no independent feasible assignment")
    optimum = min(row["annual_eur"] for row in feasible)
    for value in (solution["annual_eur"], solution["bound_eur_per_year"], selected[0]["annual_eur"]):
        require(isclose(value, optimum, rel_tol=0, abs_tol=TOL), "annual cost or bound disagrees")
    require(abs(solution["relative_gap"]) <= TOL, "nonzero gap")
    vehicles, occupied, grid = set(), {}, {}
    for row in solution["connections"]:
        v, t, k, kw = row["vehicle"], row["slot"], row["kind"], row["grid_kw"]
        require(v in routes and t in slots and routes[v][t] == ("idle", data["depot"]),
                "connection conflicts with service, travel, location or plug window")
        require((v, t) not in vehicles, "multiple devices on one vehicle")
        vehicles.add((v, t))
        occupied[k, t] = occupied.get((k, t), 0) + 1
        require(occupied[k, t] <= units[k], "installed device count exceeded")
        require(isfinite(kw) and -TOL <= kw <= data["equipment_grid_kw"][k] + TOL,
                "device power out of range")
        grid[v, t] = (k, kw)
    for v, events in routes.items():
        energy = data["initial_kwh"]
        reported = solution["energy_kwh"][v]
        require(len(reported) == len(events) + 1 and abs(energy - reported[0]) <= TOL, "initial energy")
        for t, (activity, _) in enumerate(events):
            gain = 0.0
            if (v, t) in grid:
                kind, kw = grid[v, t]
                if curves is not None:
                    limit = curve_power(curves[kind], energy / data["max_kwh"])
                    require(kw <= limit + TOL, "SOC-dependent charging limit exceeded")
                gain = data["slot_hours"] * data["efficiency"][kind] * kw
            energy = (1 - data["self_discharge_fraction_per_slot"]) * energy + gain - data["use_kwh_per_slot"][activity]
            require(data["min_kwh"] - TOL <= energy <= data["max_kwh"] + TOL, "SOC bound")
            require(abs(energy - reported[t + 1]) <= TOL, "SOC trajectory disagrees")
        require(abs(energy - data["terminal_kwh"]) <= TOL, "terminal energy")
