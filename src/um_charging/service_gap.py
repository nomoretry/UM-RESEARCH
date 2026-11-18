"""Attribute six weeks of service gaps using fixed duties and cyclic daily SOC."""
import argparse
from collections import Counter
from dataclasses import asdict, replace
import math
from pathlib import Path
import platform
import subprocess

import numpy
import scipy

from .__main__ import checked_output, digest, write_json
from .changeover_study import hardware_key
from .day_ahead import ROOT, read_json
from .fleet_design import failure_reasons
from .fleet_service import (
    DEFAULT_SPEC, SITES, VehicleSpec, build_case, dispatch, max_service, menu, subset_case,
)

WEEKS = ROOT / "studies/fleet-service/operating_weeks.json"
REFERENCE = ROOT / "studies/day-ahead/second_port.json"
MENU_INPUT = ROOT / "configs/port_warehouse_investment.json"
CAPACITIES = (300, 450, 600, 750, 900)
CATEGORIES = (
    "served_at_baseline", "truck_power_recoverable", "release_recoverable",
    "battery_recoverable", "battery_and_power_recoverable",
    "no_um_charging_window", "unrecoverable_other",
)


def scaled_spec(capacity, power):
    return VehicleSpec(capacity, 0.1 * capacity, 0.5 * capacity, power, DEFAULT_SPEC.efficiency)


def reachable(truck, spec):
    """Propagate the interval in kWh. Only roundoff at a closed endpoint is tolerated."""
    events = [(a, b, None, None) for a, b, _ in truck["windows"]]
    events.extend(truck["trips"])
    low = high = spec.boundary_kwh
    for a, b, energy, track in sorted(events, key=lambda event: event[:2]):
        if energy is None:
            if b > a:
                high = min(spec.capacity_kwh, high + (b-a)/60 * spec.truck_kw * spec.efficiency)
        else:
            low = max(spec.reserve_kwh, low - energy)
            high = min(spec.capacity_kwh, high - energy)
            if low > high + 1e-10:
                return False, {"cause": "single_truck_leg_boundary", "track_id": track,
                               "trip_end_min": b, "low_kwh": low, "high_kwh": high}
    if not low - 1e-10 <= spec.boundary_kwh <= high + 1e-10:
        return False, {"cause": "single_truck_terminal_energy", "low_kwh": low, "high_kwh": high}
    return True, None


def _bisect(feasible, low, high):
    """Caller supplies an infeasible low and feasible high."""
    while high - low > 1e-6:
        mid = (low + high) / 2
        if feasible(mid):
            high = mid
        else:
            low = mid
    return low, high


def min_truck_kw(truck, base_spec):
    def feasible(power):
        return reachable(truck, replace(base_spec, truck_kw=power))[0]

    if not feasible(math.inf):
        return None
    if feasible(0):
        return 0., 0.
    high = 1.
    while not feasible(high):
        high *= 2
    return _bisect(feasible, 0., high)


def min_capacity(truck, P):
    # Translating a schedule by 0.5*dC preserves both cyclic boundaries.
    # Reserve slack grows by 0.4*dC, headroom by 0.5*dC, including signed trips.
    # Probe across the entire domain before bisecting, including above the first pass.
    max_fail, min_pass = -math.inf, math.inf

    def feasible(capacity):
        nonlocal max_fail, min_pass
        result = reachable(truck, scaled_spec(capacity, P))[0]
        if result:
            min_pass = min(min_pass, capacity)
        else:
            max_fail = max(max_fail, capacity)
        if max_fail >= min_pass:
            raise ValueError(f"Nonmonotone capacity reachability at {min_pass}, {max_fail}")
        return result

    for capacity in range(0, 5001, 100):
        feasible(capacity)
    if min_pass == math.inf:
        return None
    if min_pass == 0:
        return 0., 0.
    return _bisect(feasible, max_fail, min_pass)


class SolveLog:
    def __init__(self, output):
        self.output = output
        self.counts = Counter()
        self.seconds = 0.
        self.max_gap = 0.

    def solve(self, case, hardware, spec, label, *, partial=False):
        solve = max_service if partial else dispatch
        result = solve(case, hardware, spec=spec)
        status = result["status"]
        if status == "optimal":
            if not result["audit"]["passed"]:
                raise ValueError(f"Audit failed for {case['date']} {label}")
            self.max_gap = max(self.max_gap, result["mip_gap"])
        self.counts[f"{label}.{status}"] += 1
        self.seconds += result["seconds"]
        if self.output:
            write_json(self.output / f"solve_{self.counts.total():05d}.json", {
                "date": case["date"], "warehouse_release_min": case["warehouse_release_min"],
                "vehicles": list(case["trucks"]), "hardware": hardware, "spec": asdict(spec),
                "label": label, "method": solve.__name__, "result": result,
            })
        return result

    def stats(self):
        return {"calls": self.counts.total(), "seconds": self.seconds,
                "max_reported_gap": self.max_gap, "counts": dict(self.counts)}


def _prove(case, spec, label, expected, log):
    hardware = {site: {"interfaces": 1, "power_kw": max(spec.truck_kw, 1e6)} for site in SITES}
    result = log.solve(case, hardware, spec, label)
    if result["status"] != expected:
        raise ValueError(f"{case['date']} {list(case['trucks'])} {label}: expected {expected}, "
                         f"got {result['status']} with {spec}")


def vehicle_row(case, vehicle, zero_release_truck, log):
    truck = case["trucks"][vehicle]
    single = subset_case(case, [vehicle])
    baseline, failure = reachable(truck, DEFAULT_SPEC)
    power = min_truck_kw(truck, DEFAULT_SPEC)
    capacity = min_capacity(truck, DEFAULT_SPEC.truck_kw)
    unlimited = min_capacity(truck, math.inf)
    energies = [energy for _, _, energy, _ in truck["trips"]]
    if baseline:
        _prove(single, DEFAULT_SPEC, "baseline", "optimal", log)
    for label, bracket, make_spec in (
        ("power", power, lambda p: replace(DEFAULT_SPEC, truck_kw=p)),
        ("capacity", capacity, lambda c: scaled_spec(c, DEFAULT_SPEC.truck_kw)),
    ):
        if bracket is not None:
            _prove(single, make_spec(bracket[1] + .001), label + "_above", "optimal", log)
            _prove(single, make_spec(bracket[0] - .001), label + "_below", "infeasible", log)

    if baseline:
        category = "served_at_baseline"
    elif power is not None:
        category = "truck_power_recoverable"
    elif case["warehouse_release_min"] == 45 and reachable(zero_release_truck, DEFAULT_SPEC)[0]:
        category = "release_recoverable"
    elif capacity is not None:
        category = "battery_recoverable"
    elif unlimited is not None:
        category = "battery_and_power_recoverable"
    elif not truck["windows"] and sum(energies) > 0:
        category = "no_um_charging_window"
    else:
        category = "unrecoverable_other"
    return {"date": case["date"], "vehicle_id": vehicle, "category": category,
            "min_truck_kw": power, "min_capacity_kwh_50": capacity,
            "min_capacity_kwh_inf": unlimited, "first_failure": failure,
            "max_leg_kwh": max(energies), "day_kwh": sum(energies),
            "window_minutes": {s: sum(b-a for a, b, site in truck["windows"] if site == s)
                               for s in SITES}}


def fleet_result(cases, capacity, options, builds, log):
    spec = scaled_spec(capacity, DEFAULT_SPEC.truck_kw)
    largest = {s: {k: max(h[s][k] for _, h in options) for k in ("interfaces", "power_kw")}
               for s in SITES}
    cache = {}
    gaps = []
    start_seconds = log.seconds

    def solve(case, hardware, partial):
        key = (case["date"], hardware_key(hardware), partial)
        if key not in cache:
            result = log.solve(case, hardware, spec, "fleet", partial=partial)
            if result["mip_gap"] is not None:
                gaps.append(result["mip_gap"])
            cache[key] = result["status"], result["selected_ids"]
        return cache[key]

    goals, remaining = {}, []
    for case in cases:
        status, ids = solve(case, largest, False)
        if status == "infeasible":
            status, ids = solve(case, largest, True)
            if status != "optimal":
                raise RuntimeError("Maximum-service solve failed")
            reasons = failure_reasons(case, largest, spec=spec)
            for v in sorted(case["trucks"].keys() - set(ids)):
                own = [r for r in reasons if r.get("vehicle_id") == v]
                remaining.append({"date": case["date"], "vehicle_id": v, "failure_reasons":
                                  own or [{"cause": "shared_connectors_or_site_power"}]})
        goals[case["date"]] = len(ids)

    def coverage(case, hardware):
        goal = goals[case["date"]]
        if goal == 0:
            return 0
        status, ids = solve(case, hardware, goal < len(case["trucks"]))
        if status == "infeasible":
            _, ids = solve(case, hardware, True)
        return len(ids)

    investment, ties = None, []
    for cost, hardware in options:
        if investment is not None and cost > investment:
            break
        if all(coverage(case, hardware) == goals[case["date"]] for case in cases):
            investment = cost
            ties.append(hardware)
    if not ties:
        raise RuntimeError("No menu build attained maximal service")
    daily = {name: {c["date"]: coverage(c, h) for c in cases} for name, h in builds.items()}
    totals = {name: sum(counts.values()) for name, counts in daily.items()}
    return {"capacity_kwh": capacity, "goals": goals, "goal_total": sum(goals.values()),
            **totals, "investment": investment, "ties": ties, "largest": largest,
            "remaining": remaining, "daily_reference_service": daily,
            "solves": {"calls": len(cache), "seconds": log.seconds - start_seconds,
                      "max_reported_gap": max(gaps)}}


def run(output=None):
    days = [d for d in read_json(WEEKS)["days"] if d["availability"] == "complete_tasks" and d["vehicles"]]
    reference = read_json(REFERENCE)
    options = menu()
    cases = {r: [build_case(d, r) for d in days] for r in (45, 0)}
    log = SolveLog(output)
    releases = {}
    served = {}
    widths = []
    for release, group in cases.items():
        rows = [vehicle_row(case, v, zero["trucks"][v], log)
                for case, zero in zip(group, cases[0]) for v in case["trucks"]]
        counts = Counter(row["category"] for row in rows)
        served[release] = {(row["date"], row["vehicle_id"]) for row in rows
                           if row["category"] == "served_at_baseline"}
        releases[str(release)] = {"counts": {k: counts[k] for k in CATEGORIES}, "rows": rows}
        for row in rows:
            for key in ("min_truck_kw", "min_capacity_kwh_50", "min_capacity_kwh_inf"):
                if row[key] is not None:
                    low, high = row[key]
                    widths.append(high - low)
    cases45 = sorted(cases[45], key=lambda c: (-len(c["trucks"]), c["date"]))
    fleet = [fleet_result(cases45, c, options, reference["hardware"], log) for c in CAPACITIES]
    expected = reference["extension"]["concurrent"]
    checks = {
        "scope": len(days) == len({d["date"] for d in days}) == 30 and len(options) == 54,
        "category_totals": all(sum(r["counts"].values()) == 73 for r in releases.values()),
        "baseline": all(len(served[45]) == expected[k]["max_vehicle_days"] == fleet[0][k] == 54
                        for k in ("one", "two")),
        "release_monotone": served[0] >= served[45],
        "capacity_monotone": all(a[k] <= b[k] for a, b in zip(fleet, fleet[1:])
                                 for k in ("goal_total", "one", "two")),
        "bracket_width": max(widths) <= 2e-6,
    }
    if not all(checks.values()):
        raise ValueError(f"Study checks failed: {checks}")
    source = {"commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
              "dirty": bool(subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"]).strip())}
    return {"source": source,
            "inputs_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in (WEEKS, REFERENCE, MENU_INPUT)},
            "default_spec": asdict(DEFAULT_SPEC), "capacity_rule": "reserve=0.1*C, boundary=0.5*C; "
            "efficiency=0.9, search through 5000 kWh", "thresholds": "Brackets [lower, upper]; "
            "null means unreachable within the search domain. Power search has no finite cap.",
            "investment_unit": "synthetic cycle-equivalent incremental capital allocation",
            "fleet_scope": "Minimum synthetic period investment evaluated against daily service "
            "maxima on the six later weeks (warehouse release 45 min); retrospective.",
            "reference_hardware": reference["hardware"], "releases": releases, "fleet": fleet,
            "checks": checks, "max_bracket_width": max(widths), "solves": log.stats(),
            "python": platform.python_version(), "numpy_version": numpy.__version__,
            "scipy_version": scipy.__version__, "solver": "scipy.optimize.milp / HiGHS, mip_rel_gap=0, 60 s limit"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    output = checked_output(args.output, ROOT) if args.output else None
    if output:
        # Formal evidence requires committed, unmodified source.
        if subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"]).strip():
            raise ValueError("--output requires a clean committed source tree")
        output.mkdir(parents=True)
    result = run(output)
    if output:
        write_json(output / "vehicle_days.json", result["releases"])
        write_json(output / "summary.json", result)
    if args.summary:
        write_json(args.summary, result)
    for release, data in result["releases"].items():
        print(f"release={release} min", " ".join(f"{k}={v}" for k, v in data["counts"].items()))
    for row in result["fleet"]:
        print(f"C={row['capacity_kwh']} kWh goals={row['goal_total']} one={row['one']} two={row['two']} "
              f"six_week_min_period_investment={row['investment']} ties={row['ties']}")


if __name__ == "__main__":
    main()
