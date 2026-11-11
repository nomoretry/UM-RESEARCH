"""Direct SOC replay and exhaustive hardware/connection search, independent of the MILP."""
from itertools import product
from math import isclose, isfinite

from check_milan import CAPITAL_RECOVERY_FACTOR, CHARGERS


TOL = 1e-6


def require(condition, message):
    if not condition:
        raise ValueError(message)


def enumerate_facilities(data, slots, routes):
    """Enumerate individual plug assignments and propagate continuous reachable energy intervals."""
    vehicles = data["vehicles"]
    kinds = tuple(data["equipment_grid_kw"])
    retention = 1 - data["self_discharge_fraction_per_slot"]
    permitted = {}
    for v in vehicles:
        for t in slots:
            require(routes[v][t] == ("idle", data["depot"]), "enumeration requires depot dwell")
        permitted[v] = []
        for sequence in product((None, *kinds), repeat=len(slots)):
            chosen = dict(zip(slots, sequence))
            low = high = data["initial_kwh"]
            for t, (activity, _) in enumerate(routes[v]):
                demand = data["use_kwh_per_slot"][activity]
                kind = chosen.get(t)
                gain = (data["equipment_grid_kw"][kind] * data["efficiency"][kind] * data["slot_hours"]
                        if kind is not None else 0)
                low = max(data["min_kwh"], low * retention - demand)
                high = min(data["max_kwh"], high * retention - demand + gain)
                if low > high + TOL:
                    break
            else:
                if low - TOL <= data["terminal_kwh"] <= high + TOL:
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


def check_solution(data, slots, routes, solution, options):
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
        grid[v, t] = kw * data["efficiency"][k]
    for v, events in routes.items():
        energy = data["initial_kwh"]
        reported = solution["energy_kwh"][v]
        require(len(reported) == len(events) + 1 and abs(energy - reported[0]) <= TOL, "initial energy")
        for t, (activity, _) in enumerate(events):
            energy *= 1 - data["self_discharge_fraction_per_slot"]
            energy += data["slot_hours"] * grid.get((v, t), 0) - data["use_kwh_per_slot"][activity]
            require(data["min_kwh"] - TOL <= energy <= data["max_kwh"] + TOL, "SOC bound")
            require(abs(energy - reported[t + 1]) <= TOL, "SOC trajectory disagrees")
        require(abs(energy - data["terminal_kwh"]) <= TOL, "terminal energy")
