"""Shared equipment investment with independent fixed-trip dispatch in each service."""

import argparse
import copy
import gzip
import json
from itertools import product
from pathlib import Path

from .__main__ import checked_output, digest, write_json
from .changeover import solve_changeover
from .changeover_check import replay
from .changeover_study import facility_menu, hardware_key
from .day_ahead import ROOT, read_json
from .eligibility_stress import build_case, make_reference
from .facility_month import DELAY, ENERGY


RELEASES = (0, 15, 30, 45, 60)
TURNAROUNDS = (0, 2, 5, 10)
PRIOR = ROOT / "results/changeover_20261112/metrics.json"
ZERO = ROOT / "results/known_delay_investment_20261111/metrics.json"


def physical_cases():
    settings = read_json(DELAY)
    base = read_json(ROOT / settings["base_config"])
    cases = {}
    for row in read_json(ENERGY)["cases"]:
        if row["payload_t"] != 19.3 or row["aux_kw"] not in (5, 7):
            continue
        data = copy.deepcopy(base)
        for truck in data["vehicles"]:
            truck["drive_energy_kwh"] = [e * row["energy_ratio"] for e in truck["drive_energy_kwh"]]
        reference = make_reference(data)
        for release in RELEASES:
            # Only windows and the trip ledger are taken from this template.
            # Every solve and replay receives the actual enumerated hardware.
            cases[row["leg_kwh"], release] = build_case(
                reference, {"PORT": 2, "WAREHOUSE": 2}, release, settings["delayed_vehicle_ids"]
            )
    return cases


def equipment(build):
    return {site: {"interfaces": n, "power_kw": p} for site, n, p in build}


def relax_schedule(schedule, old_energy, new_energy, turnaround):
    """Keep each positive plug-slot, delivering scaled energy at one constant suffix setpoint."""
    ratio = new_energy / old_energy
    history = {}
    transferred = []
    for row in sorted(schedule, key=lambda item: item["slot"]):
        plug = row["site"], row["connector"]
        vehicle = row["vehicle"]
        start = 15 * row["slot"]
        end = start + 15
        if plug in history:
            last_vehicle, occupied_until = history[plug]
            if vehicle != last_vehicle:
                start = max(start, occupied_until + turnaround)
        if start >= end:
            raise ValueError("Dominating service witness lost a complete plug-slot")
        # All occupied plugs reach their highest setpoint at the right boundary.
        # The longer new suffix delivers no more energy than the old suffix.
        energy_minutes = sum((b - a) * kw for a, b, kw in row["segments"])
        level = energy_minutes * ratio / (end - start)
        transferred.append({**row, "segments": [[start, end, level]]})
        history[plug] = vehicle, end
    return transferred


def le_service(a, b):
    """Less travel energy, an earlier release and a shorter changeover are easier."""
    return all(x <= y for x, y in zip(a, b, strict=True))


def le_build(a, b):
    return all(site == other and n <= m and p <= q
               for (site, n, p), (other, m, q) in zip(a, b, strict=True))


def shared_minimum(menu, service_set, feasible):
    """Enumerate the common hardware choice; dispatch can respond to the realized service."""
    optimum = None
    winners = []
    for cost, hardware in menu:
        if optimum is not None and cost > optimum:
            break
        build = hardware_key(hardware)
        if all(feasible[s, build] for s in service_set):
            optimum = cost
            winners.append(build)
    return optimum, winners


def seed_evidence(archive, cases, costs):
    low_energy = min(e for e, _ in cases)
    infeasible = []
    # All feasible builds in the old low-energy run incurred the same energy cost.
    for row in read_json(ZERO)["cases"]:
        for build, cost in costs.items():
            if cost < row["investment_cost"]:
                service = low_energy, row["delay_minutes"], 0
                infeasible.append((service, build, "published zero-changeover investment bound"))
    verified = []
    prior = read_json(PRIOR)
    for row in prior["baseline_and_sensitivity"]:
        build = hardware_key(row["hardware"])
        if row["critical_schedule"]:
            service = row["leg_kwh"], 45, row["critical_minutes"]
            replay(cases[service[:2]], row["hardware"], service[2], row["critical_schedule"])
            verified.append((service, build, row["critical_schedule"], "published threshold witness"))
        for result in row["runs"]:
            if result["status"] == "infeasible":
                service = row["leg_kwh"], 45, result["delay_minutes"]
                infeasible.append((service, build, "published changeover infeasibility"))

    loaded = 0
    if archive is not None:
        if read_json(archive / "selected.json") != prior:
            raise ValueError("Previous run differs from the published changeover study")
        for rel, expected in prior["inputs_sha256"].items():
            if digest(ROOT / rel) != expected:
                raise ValueError(f"Prior run input differs: {rel}")
        for file in sorted(archive.glob("e*-d*.json")):
            row = read_json(file)
            service = row["leg_kwh"], 45, row["delay_minutes"]
            build = hardware_key(row["hardware"])
            result = row["solver"]
            if result["status"] == "optimal":
                replay(cases[service[:2]], row["hardware"], service[2], result["schedule"])
                verified.append((service, build, result["schedule"], file.name))
            elif result["status"] == "infeasible":
                infeasible.append((service, build, file.name))
            else:
                raise ValueError(f"Unresolved previous result: {file}")
            loaded += 1
        if loaded != prior["distinct_changeover_solves"]:
            raise ValueError("Incomplete previous run")
    return infeasible, verified, loaded


def check_service(service, case, hardware, negatives, positives, stats):
    build = hardware_key(hardware)
    energy, _, turnaround = service
    for other, previous, origin in negatives:
        if le_service(other, service) and le_build(build, previous):
            stats["negative_deductions"] += 1
            return None, {"infeasible_from": [other, previous, origin]}
    for other, previous, original, origin in positives:
        if le_service(service, other) and le_build(previous, build):
            schedule = relax_schedule(original, other[0], energy, turnaround)
            return schedule, {"witness_from": [other, previous, origin]}

    result = solve_changeover(case, hardware, turnaround)
    stats["new_solves"] += 1
    status = result["status"]
    source = {"new_status": status, "gap": result["mip_gap"], "bound": result["dual_bound"]}
    if status == "optimal":
        schedule = result["schedule"]
        positives.append((service, build, schedule, "fresh MILP"))
        return schedule, source
    if status == "infeasible":
        negatives.append((service, build, "fresh MILP"))
        return None, source
    raise RuntimeError(f"Unconfirmed physical status: {status}")


def run(previous=None, output=None):
    cases = physical_cases()
    base = ROOT / read_json(DELAY)["base_config"]
    menu = facility_menu(make_reference(read_json(base)))
    energies = sorted({e for e, _ in cases})
    main_grid = list(product(energies, RELEASES, TURNAROUNDS))
    anchors = sorted(row["delay_minutes"] for row in read_json(PRIOR)["high_energy_recovery"]
                     if 2 < row["delay_minutes"] < 5)
    grid = sorted(set(main_grid) | {(energies[-1], 45, t) for t in anchors})
    costs = {hardware_key(hardware): cost for cost, hardware in menu}
    ids = {b: f"P{b[0][1]}-{b[0][2]}_W{b[1][1]}-{b[1][2]}" for b in costs}
    negatives, positives, loaded = seed_evidence(previous, cases, costs)
    stats = {"archived_inputs_loaded": loaded, "new_solves": 0, "positive_replays": 0, "negative_deductions": 0}
    feasible, schedules = {}, {}
    log = None
    if output is not None:
        output = checked_output(Path(output), ROOT)
        output.mkdir(parents=True)
        log = gzip.open(output / "evidence.jsonl.gz", "wt", encoding="utf-8")
    try:
        for _, hardware in menu:
            build = hardware_key(hardware)
            for service in reversed(grid):
                case = cases[service[:2]]
                schedule, source = check_service(service, case, hardware, negatives, positives, stats)
                feasible[service, build] = schedule is not None
                if schedule is not None:
                    checked = replay(case, hardware, service[2], schedule)
                    if not checked["passed"] or checked["trip_count"] != 6:
                        raise ValueError("Incomplete service")
                    schedules[service, build] = schedule
                    stats["positive_replays"] += 1
                if log:
                    record = {"service": service, "build": build, "source": source, "schedule": schedule}
                    log.write(json.dumps(record, allow_nan=False) + "\n")
    finally:
        if log:
            log.close()

    table = []
    for service in grid:
        scope = [s for s in grid if le_service(s, service)]
        cost, winners = shared_minimum(menu, scope, feasible)
        if (cost, winners) != shared_minimum(menu, [service], feasible):
            raise RuntimeError("Corner and full service envelope disagree")
        table.append({"max_leg_kwh": service[0], "max_release_min": service[1], "max_turnaround_min": service[2],
                      "grid": "primary" if service in main_grid else "prior_threshold_anchor",
                      "services": len(scope), "investment": cost, "optimal_builds": [ids[b] for b in winners]})

    mixed = [(energies[0], 45, 10), (energies[1], 45, 2)]
    cost, winners = shared_minimum(menu, mixed, feasible)
    mixed_result = {"services": mixed, "individual_minima": [shared_minimum(menu, [s], feasible)[0] for s in mixed],
                    "shared_investment": cost, "optimal_builds": [ids[b] for b in winners]}
    named = {"warehouse_upgrade": (energies[-1], 45, anchors[0]), "port_capacity": (energies[-1], 60, 10)}
    certificates = {}
    for name, service in named.items():
        cost, winners = shared_minimum(menu, [s for s in grid if le_service(s, service)], feasible)
        certificates[name] = {"service": service, "investment": cost,
                              "witnesses": {ids[b]: schedules[service, b] for b in winners},
                              "cheaper_builds_infeasible_at_corner": [ids[b] for b, c in costs.items()
                                                                      if c < cost and not feasible[service, b]]}
    optimal_ids = {b for row in table for b in row["optimal_builds"]} | set(mixed_result["optimal_builds"])
    coverage = []
    for build, cost in costs.items():
        if ids[build] in optimal_ids:
            accepted = [s for s in grid if feasible[s, build]]
            maximal = [s for s in accepted if not any(s != r and le_service(s, r) for r in accepted)]
            coverage.append({"build": ids[build], "cost": cost, "feasible_primary_cells": sum(
                s in main_grid for s in accepted), "feasible_cells_with_anchors": len(accepted),
                             "maximal_feasible_services": maximal})
    selected = {"units": "synthetic investment per cycle; power in kW", "menu_size": len(menu),
                "primary_service_cells": len(main_grid), "threshold_anchors": anchors,
                "table": table, "nonrectangular_shared_plan": mixed_result, "coverage": coverage,
                "certificates": certificates, "input_sha256": {p.relative_to(ROOT).as_posix(): digest(p)
                                                              for p in [DELAY, ENERGY, base, ZERO, PRIOR]}}
    if output:
        write_json(output / "selected.json", selected)
        write_json(output / "work.json", stats)
    return selected, stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, help="Optional complete offline changeover dispatch directory")
    parser.add_argument("--output", type=Path, help="Fresh directory in the existing offline Git archive")
    args = parser.parse_args()
    selected, stats = run(args.previous, args.output)
    for row in selected["table"]:
        print(row["max_leg_kwh"], row["max_release_min"], row["max_turnaround_min"],
              row["investment"], *row["optimal_builds"])
    print("Nonrectangular service set:", selected["nonrectangular_shared_plan"])
    print("Verification:", stats)
