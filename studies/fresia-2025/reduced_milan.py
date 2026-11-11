"""Joint AC/DC investment and individual-vehicle charging for the reduced Milan shift."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from check_milan import CAPITAL_RECOVERY_FACTOR, CHARGERS
from route_time import SHIFT_SLOTS, shortest_tour, travel_slots


HERE = Path(__file__).resolve().parent
TYPES = ("ac_units", "dc_units")


def annual_cost(kind):
    purchase, maintenance = CHARGERS[kind]
    return purchase * CAPITAL_RECOVERY_FACTOR + maintenance


def timelines(data):
    """Fix each selected Table 6 route and the order of all service and travel slots."""
    result = {}
    with (HERE / "service_slots.csv").open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            vehicle = row["vehicle"]
            if vehicle not in data["vehicles"]:
                continue
            home = int(row["home_depot"])
            if home != data["depot"]:
                raise ValueError("All vehicles must start and end at the selected depot")
            demand = {zone: int(row[f"zone_{zone}"]) for zone in range(1, 7)}
            _, route = shortest_tour(home, demand)
            slots = []
            for start, end in zip(route, route[1:]):
                slots.extend([("service", start)] * demand[start])
                slots.extend([("travel", (start, end))] * travel_slots(start, end))
            if len(slots) > SHIFT_SLOTS:
                raise ValueError("Tasks do not fit in the shift")
            slots.extend([("idle", home)] * (SHIFT_SLOTS - len(slots)))
            result[vehicle] = slots
    if set(result) != set(data["vehicles"]):
        raise ValueError("Selected vehicle missing from Table 6")
    return result


def solve(data, eligible_slots, routes, curves=None):
    """Keep SOC at every slot boundary; generate connection variables only for idle depot slots."""
    if (len(set(eligible_slots)) != len(eligible_slots)
            or any(type(t) is not int or not 0 <= t < SHIFT_SLOTS for t in eligible_slots)):
        raise ValueError("Plug slots must be distinct integers within the shift")
    if not all(data["min_kwh"] <= data[key] <= data["max_kwh"]
               for key in ("initial_kwh", "terminal_kwh")):
        raise ValueError("Initial and terminal energy must lie within SOC bounds")
    if curves is not None:
        for kind in TYPES:
            soc, kw = np.array(curves[kind], dtype=float).T
            if (soc[0] != 0 or soc[-1] != 1 or np.any(np.diff(soc) <= 0)
                    or np.any(kw < 0) or np.any(kw > data["equipment_grid_kw"][kind])
                    or np.any(np.diff(np.diff(kw) / np.diff(soc)) > 1e-8)):
                raise ValueError("Expected concave charging limits over SOC 0 to 1, within the device rating")
    lower, upper, integer, cost = [], [], [], []

    def variable(lo, hi, is_integer=False, price=0):
        index = len(cost)
        lower.append(lo)
        upper.append(hi)
        integer.append(int(is_integer))
        cost.append(price)
        return index

    vehicles = data["vehicles"]
    equipment = data["equipment_grid_kw"]
    units = {k: variable(0, len(vehicles), True, annual_cost(k)) for k in TYPES}
    energy, connects, power = {}, {}, {}
    initial_or_end = {0: data["initial_kwh"], SHIFT_SLOTS: data["terminal_kwh"]}
    for v in vehicles:
        for t in range(SHIFT_SLOTS + 1):
            value = initial_or_end.get(t)
            energy[v, t] = variable(value if value is not None else data["min_kwh"],
                                    value if value is not None else data["max_kwh"])
        for t in eligible_slots:
            if routes[v][t] != ("idle", data["depot"]):
                raise ValueError("Plug window intersects service, travel or another depot")
            for k in TYPES:
                connects[v, t, k] = variable(0, 1, True)
                power[v, t, k] = variable(0, equipment[k])

    rows, lows, highs = [], [], []

    def constraint(terms, lo, hi):
        row = np.zeros(len(cost))
        for index, coefficient in terms:
            row[index] += coefficient
        rows.append(row)
        lows.append(lo)
        highs.append(hi)

    for v in vehicles:
        for t, (activity, _) in enumerate(routes[v]):
            retention = 1 - data["self_discharge_fraction_per_slot"]
            balance = [(energy[v, t + 1], 1), (energy[v, t], -retention)]
            if t in eligible_slots:
                constraint([(connects[v, t, k], 1) for k in TYPES], 0, 1)
                for k in TYPES:
                    ix = (v, t, k)
                    constraint([(power[ix], 1), (connects[ix], -equipment[k])], -np.inf, 0)
                    if curves is not None:
                        # The minimum of these affine segments is the concave Fig. 4 envelope.
                        for (s0, p0), (s1, p1) in zip(curves[k], curves[k][1:]):
                            slope = (p1 - p0) / (s1 - s0)
                            constraint([(power[ix], 1), (energy[v, t], -slope / data["max_kwh"])],
                                       -np.inf, p0 - slope * s0)
                    balance.append((power[ix], -data["slot_hours"] * data["efficiency"][k]))
            demand = data["use_kwh_per_slot"][activity]
            constraint(balance, -demand, -demand)
    for t in eligible_slots:
        for k in TYPES:
            constraint([(connects[v, t, k], 1) for v in vehicles] + [(units[k], -1)], -np.inf, 0)

    result = milp(cost, integrality=integer, bounds=Bounds(lower, upper),
                  constraints=LinearConstraint(rows, lows, highs), options={"mip_rel_gap": 0})
    if result.status == 2:
        return {"status": "infeasible"}
    if result.status != 0:
        raise RuntimeError(f"Solver did not prove optimality: {result.message}")
    x = result.x
    return {
        "status": "optimal",
        "units": {k: int(round(x[units[k]])) for k in TYPES},
        "annual_eur": float(result.fun),
        "bound_eur_per_year": float(result.mip_dual_bound),
        "relative_gap": float(result.mip_gap),
        "energy_kwh": {v: [float(x[energy[v, t]]) for t in range(SHIFT_SLOTS + 1)] for v in vehicles},
        "connections": [
            {"vehicle": v, "slot": t, "kind": k, "grid_kw": float(x[power[v, t, k]])}
            for (v, t, k), index in connects.items() if x[index] > 0.5
        ],
    }


def main():
    from verify_reduced import check_solution, enumerate_facilities, reachable_energy

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dispatch", type=Path, help="Write complete schedules and SOC to this local JSON file")
    parser.add_argument("--power-limit", choices=("nameplate", "figure4"), default="nameplate")
    args = parser.parse_args()
    config = HERE / "reduced_milan.json"
    data = json.loads(config.read_text(encoding="utf-8"))
    routes = timelines(data)
    inputs = [config.name, "service_slots.csv"]
    curves = None
    if args.power_limit == "figure4":
        inputs.append("figure4_power.json")
        curves = json.loads((HERE / inputs[-1]).read_text(encoding="utf-8"))["soc_fraction_and_grid_kw"]
    selected, schedules = {}, {}
    for name, slots in data["plug_slots"].items():
        solution = solve(data, slots, routes, curves)
        options = enumerate_facilities(data, slots, routes, curves)
        check_solution(data, slots, routes, solution, options, curves)
        schedules[name] = solution
        feasible = [r for r in options if r["feasible"]]
        selected[name] = {
            key: solution[key] for key in ("status", "units", "annual_eur", "bound_eur_per_year", "relative_gap")
            if key in solution
        }
        selected[name].update({
            "feasible_facilities": len(feasible), "enumerated_facilities": len(options),
            "annual_cost_minimizers": [r["units"] for r in feasible if abs(r["annual_eur"] - solution["annual_eur"]) < 1e-6],
            "independent_check": "passed",
        })
        if solution["status"] == "optimal":
            selected[name]["initial_investment_eur"] = sum(
                solution["units"][k] * CHARGERS[k][0] for k in TYPES
            )
        if curves is not None:
            selected[name]["vehicle_1_max_terminal_kwh_dedicated_charger"] = {
                k: round(reachable_energy(data, routes["1"], dict.fromkeys(slots, k), curves)[1], 6)
                for k in TYPES
            }
    if args.dispatch:
        args.dispatch.write_text(json.dumps(schedules, indent=2) + "\n", encoding="utf-8")
    hashes = {name: hashlib.sha256((HERE / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
              for name in inputs}
    print(json.dumps({"input_sha256_lf": hashes, "scenarios": selected}, indent=2))


if __name__ == "__main__":
    main()
