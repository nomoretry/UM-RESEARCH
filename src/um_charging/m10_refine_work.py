"""Estimate screened twelve-week refinement requests using the sealed coarse timings."""

from collections import Counter, defaultdict
from dataclasses import dataclass
import math
from statistics import mean

from . import site_sizing as ss
from .m10_costs import _solve_windows


WORKERS = 8
ROUND_SECONDS = 4 * 3600
CLOSING_SECONDS = 15 * 60
REPEAT_COUNT = 20
FRESH_PROCESS_OVERHEAD_SECONDS = 60
# The coarse preflight reserved 301 s per wave for a 300 s native time
# limit, including measured process-side assembly and replay overhead.
REPEAT_WAVE_SECONDS = 301


@dataclass(frozen=True)
class WorkPoint:
    design: ss.Design
    caps: tuple
    priced: bool
    missing_weeks: tuple
    service_weeks: tuple = ()

    @classmethod
    def from_row(cls, row):
        return cls(ss.Design(row["port_plugs"], row["port_kw"], row["warehouse_kw"]),
                   tuple(row["caps_kw"]), row["priced"], tuple(row["missing_weeks"]), tuple(row["service_weeks"]))


def _retained(points):
    result = []
    seen = set()
    for row in points:
        if isinstance(row, WorkPoint):
            point = row
        else:
            if row["decision"] == "exclude":
                continue
            if row["decision"] != "retain":
                raise ValueError(f"Unknown point decision {row['decision']}")
            point = WorkPoint.from_row(row)
        key = point.design, point.caps
        if key in seen:
            raise ValueError(f"Duplicate retained operating point {key}")
        if type(point.priced) is not bool or any(not 0 <= k <= limit for k, limit in
                                                zip(point.caps, point.design.caps, strict=True)):
            raise ValueError(f"Invalid priced flag or quarter caps at {key}")
        seen.add(key)
        result.append(point)
    return result


def _request_plan(points):
    points = list(points)
    retained = _retained(points)
    witnesses = defaultdict(dict)
    for row in points:
        if isinstance(row, WorkPoint):
            continue
        hardware = ss.Design(row["port_plugs"], row["port_kw"], row["warehouse_kw"])
        available = dict(row.get("rated_service_proofs", {}))
        available.update({w["week"]: w["proof"] for w in row.get("weekly", ()) if w["proof"]})
        for week, proof in available.items():
            earlier = witnesses[week].get(hardware)
            witnesses[week][hardware] = min(proof, earlier) if earlier is not None else proof
    jobs = {"priced": set(), "unquoted": set()}
    transfers = {}
    for point in retained:
        group = jobs["priced" if point.priced else "unquoted"]
        build = ss._active_build(point.design, point.caps)
        for week in point.missing_weeks:
            group.add(("energy", week, build, point.caps))
        # Service maximum with R-overlap tie breaking, then (if needed) one
        # fixed-R test. The rated fixed-R test is also a procurement request.
        for week in point.service_weeks:
            donor = next(((hardware, proof) for hardware, proof in sorted(witnesses[week].items())
                          if ss._dominates(point.design, hardware)), None)
            if donor is not None:
                transfers[(point.design, week)] = dict(design=point.design.label, week=week,
                                                       donor_design=donor[0].label, evidence_id=donor[1])
                continue
            group.add(("service", week, point.design, point.design.caps))
            group.add(("energy", week, point.design, point.design.caps))
    shared = jobs["priced"] & jobs["unquoted"]
    split = {"priced": sorted(jobs["priced"]), "unquoted": sorted(jobs["unquoted"] - shared),
             "shared": sorted(shared)}
    return retained, split, [transfers[key] for key in sorted(transfers)]


def work_requests(points):
    """Return unique prospective requests; shared requests belong to the priced phase first."""
    return _request_plan(points)[1]


def _timings(records):
    builds = {d.label: d for d in ss.design_grid(ss.COARSE_KW)}
    by_stratum, by_phase = defaultdict(list), defaultdict(list)
    source = []
    ids = set()
    for r in records:
        seconds = float(r["seconds"])
        if not math.isfinite(seconds) or seconds < 0 or r["id"] in ids:
            raise ValueError("Invalid elapsed time or duplicate historical request")
        ids.add(r["id"])
        dual = builds[r["design"]].port_plugs == 2
        both = bool(int(r["port_cap_kw"]) and int(r["warehouse_cap_kw"]))
        by_stratum[r["phase"], r["week"], dual, both].append(seconds)
        by_phase[r["phase"]].append(seconds)
        source.append({**r, "seconds": seconds})
    seconds = math.fsum(r["seconds"] for r in source)
    if seconds <= 0:
        raise ValueError("Sealed nonzero timing observations are required")
    windows = _solve_windows(source)
    history = dict(unique_observations=len(source), observed_solver_seconds=seconds,
                   solve_windows_seconds=windows, observed_active_wall_seconds=math.fsum(windows.values()),
                   longest_solve_seconds=max(r["seconds"] for r in source))
    return by_stratum, by_phase, history


def _workload(jobs, by_stratum, by_phase, factor):
    counts = Counter((phase, week, design.port_plugs == 2, all(caps)) for phase, week, design, caps in jobs)
    strata = []
    for (phase, week, dual, both), count in sorted(counts.items()):
        group = by_stratum.get((phase, week, dual, both))
        if group:
            origin = "matched_stratum"
        else:
            group = by_phase.get(phase)
            origin = "phase_mean" if group else "time_limit"
        average = mean(group) if group else ss.fc.SOLVE_SECONDS
        strata.append(dict(phase=phase, week=week, two_port_plugs=dual, both_sites_active=both,
                           requests=count, timing_source=origin, observed_samples=len(group) if group else 0,
                           mean_seconds=average, estimated_solver_seconds=average * count))
    seconds = math.fsum(r["estimated_solver_seconds"] for r in strata)
    return dict(unique_weekly_requests=len(jobs), request_counts=dict(Counter(job[0] for job in jobs)),
                estimated_solver_seconds=seconds, processing_wall_seconds=seconds * factor, strata=strata)


def estimate_work(points, records, *, elapsed_seconds, workers=WORKERS):
    """Split processing time, count the tail and fresh-process check once, and apply the remaining clock."""
    if not math.isfinite(elapsed_seconds) or elapsed_seconds < 0 or type(workers) is not int or workers < 1:
        raise ValueError("Invalid elapsed time or worker count")
    retained, jobs, transfers = _request_plan(points)
    strata, phases, historical = _timings(records)
    factor = max(historical["observed_active_wall_seconds"] / historical["observed_solver_seconds"], 1 / workers)
    historical.update(wall_per_solver_second=factor, workers=workers)
    reports = {}
    for label, priced in (("priced", True), ("unquoted", False)):
        group = _workload(jobs[label], strata, phases, factor)
        group["retained_points"] = sum(point.priced == priced for point in retained)
        reports[label] = group
    reports["unquoted"]["requests_also_needed_by_priced_points"] = len(jobs["shared"])
    combined_work = reports["priced"]["processing_wall_seconds"] + reports["unquoted"]["processing_wall_seconds"]
    total_requests = len(jobs["priced"]) + len(jobs["unquoted"])
    repeat_allowance = math.ceil(REPEAT_COUNT / workers) * REPEAT_WAVE_SECONDS + FRESH_PROCESS_OVERHEAD_SECONDS
    overhead = historical["longest_solve_seconds"] + repeat_allowance
    priced_wall = reports["priced"]["processing_wall_seconds"] + (overhead if jobs["priced"] else 0)
    combined_wall = combined_work + (overhead if total_requests else 0)
    available = ROUND_SECONDS - elapsed_seconds - CLOSING_SECONDS
    return {**reports, "combined": dict(unique_weekly_requests=total_requests, processing_wall_seconds=combined_work,
                                        projected_wall_seconds=combined_wall),
            "history": historical, "service_qualification_transfers": transfers,
            "budget": dict(round_seconds=ROUND_SECONDS, elapsed_seconds=elapsed_seconds,
                closing_seconds=CLOSING_SECONDS, available_seconds=available,
                fresh_process_checks=REPEAT_COUNT, fresh_process_allowance_seconds=repeat_allowance,
                long_tail_seconds=historical["longest_solve_seconds"], priced_required_seconds=priced_wall,
                priced_margin_seconds=available-priced_wall, all_required_seconds=combined_wall,
                branch="A" if priced_wall <= available else "B")}
