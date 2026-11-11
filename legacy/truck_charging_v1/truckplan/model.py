"""Finite-plan charging-facility MILP for the explicitly synthetic V1 model.

The optimiser selects exactly one already energy/time-feasible plan per job.
It does not manufacture routes, make unmet demand disappear, or certify that
the finite route set contains the global road-network optimum.  Call the data
validator before plan generation and the independent verifier after solving.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .data import validate_dataset


def _empty_result(status, message):
    """Absent incumbents must never look like zero-cost feasible solutions."""
    return {
        "status": status,
        "objective_cny_per_year": None,
        "station_decisions": [],
        "selected_plan_ids": [],
        "investment_cny_per_year": None,
        "operation_cny_per_year": None,
        "mip_gap": None,
        "message": message,
    }


def _finite_gap(value):
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def solve(data, plans, *, enforce_service_capacity=True):
    """Solve siting, integer bay sizing, and one-plan-per-job selection.

    ``enforce_service_capacity=False`` removes ONLY simultaneous bay occupancy
    constraints. Site electrical-power limits and build/use links remain. That
    variant is diagnostic, never a deployable charging schedule. Its optimum
    is a lower bound; a time-limited feasible incumbent need not be a bound.

    A HiGHS limit without a feasible incumbent is reported as ``solver_error``
    with an explicit message, because the V1 status contract has no separate
    limit-without-incumbent category. It is not evidence of infeasibility.
    """
    if not isinstance(enforce_service_capacity, bool):
        raise ValueError("enforce_service_capacity must be a boolean")
    validate_dataset(data)
    sites = data["sites"]
    jobs = data["jobs"]
    settings = data["settings"]
    plans = list(plans)
    site_index = {site["site_id"]: i for i, site in enumerate(sites)}
    job_ids = [job["job_id"] for job in jobs]
    if len(site_index) != len(sites) or len(set(job_ids)) != len(job_ids):
        raise ValueError("site_id and job_id must each be unique")
    plans_by_job = {job_id: [] for job_id in job_ids}
    occupancy = defaultdict(dict)
    plan_sites = []
    plan_ids = set()
    horizon = settings["horizon_slots"]

    # Validate the optimisation interface; physical plan reconstruction belongs
    # to verify.py, while data.py above checks the full dataset schema.
    for p, plan in enumerate(plans):
        plan_id = plan["plan_id"]
        if plan_id in plan_ids:
            raise ValueError(f"Duplicate plan_id: {plan_id!r}")
        plan_ids.add(plan_id)
        job_id = plan["job_id"]
        if job_id not in plans_by_job:
            raise ValueError(f"Unknown job_id in plan {plan_id!r}: {job_id!r}")
        plans_by_job[job_id].append(p)
        cost = plan["operating_cost_cny"]
        if isinstance(cost, bool) or not isinstance(cost, (int, float)):
            raise ValueError("operating_cost_cny must be a finite nonnegative number")
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("operating_cost_cny must be a finite nonnegative number")
        used = set()
        intervals = []
        for event in plan["events"]:
            site_id = event["site_id"]
            if site_id not in site_index:
                raise ValueError(f"Unknown site_id in plan {plan_id!r}: {site_id!r}")
            start, end = event["start_slot"], event["end_slot"]
            if type(start) is not int or type(end) is not int:
                raise ValueError("Charging event start_slot and end_slot must be integers")
            if not 0 <= start < end <= horizon:
                raise ValueError("Charging event must satisfy 0 <= start_slot < end_slot <= horizon_slots")
            site = sites[site_index[site_id]]
            if start < site["open_slot"] or end > site["close_slot"]:
                raise ValueError(f"Charging event outside station opening: {site_id!r}")
            intervals.append((start, end))
            used.add(site_index[site_id])
            for slot in range(start, end):
                occupancy[(site_index[site_id], slot)][p] = 1.0
        intervals.sort()
        if any(left[1] > right[0] for left, right in zip(intervals, intervals[1:])):
            raise ValueError(f"Overlapping charging events within plan {plan_id!r}")
        plan_sites.append(used)

    missing = [job_id for job_id, indices in plans_by_job.items() if not indices]
    if missing:
        return _empty_result(
            "infeasible",
            "No feasible plan supplied for job(s): " + ", ".join(map(str, missing))
            + ". All jobs must be served; no unmet-demand slack is permitted. "
            "This proves infeasibility only for the supplied finite plan set.",
        )

    # All variables are bounded integers: [build_s, bays_s, selected_plan_p].
    n_sites, n_plans = len(sites), len(plans)
    n_variables = 2 * n_sites + n_plans
    annualization = settings["annualization_factor"]
    days = settings["operating_days_per_year"]
    cost_vector = np.zeros(n_variables, dtype=float)
    upper_bounds = np.ones(n_variables, dtype=float)
    for s, site in enumerate(sites):
        cost_vector[s] = annualization * site["fixed_cost_cny"]
        cost_vector[n_sites + s] = annualization * site["bay_cost_cny"]
        upper_bounds[n_sites + s] = site["max_bays"]
    for p, plan in enumerate(plans):
        cost_vector[2 * n_sites + p] = days * plan["operating_cost_cny"]

    row_indices, column_indices, coefficients = [], [], []
    row_lower, row_upper = [], []

    def add_row(terms, lower=-np.inf, upper=np.inf):
        row = len(row_lower)
        for column, value in terms.items():
            if value != 0:
                row_indices.append(row)
                column_indices.append(column)
                coefficients.append(value)
        row_lower.append(lower)
        row_upper.append(upper)

    for indices in plans_by_job.values():
        add_row({2 * n_sites + p: 1.0 for p in indices}, lower=1.0, upper=1.0)
    for s, site in enumerate(sites):
        # build <= bays <= max_bays * build.
        add_row({s: 1.0, n_sites + s: -1.0}, upper=0.0)
        add_row({n_sites + s: 1.0, s: -site["max_bays"]}, upper=0.0)
    for p, used_sites in enumerate(plan_sites):
        for s in used_sites:
            add_row({2 * n_sites + p: 1.0, s: -1.0}, upper=0.0)
    for (s, _slot), occupied_plans in occupancy.items():
        if enforce_service_capacity:
            terms = {2 * n_sites + p: count for p, count in occupied_plans.items()}
            terms[n_sites + s] = -1.0
            add_row(terms, upper=0.0)
        terms = {
            2 * n_sites + p: count * sites[s]["charger_kw"]
            for p, count in occupied_plans.items()
        }
        terms[s] = -sites[s]["site_power_kw"]
        add_row(terms, upper=0.0)

    matrix = coo_matrix(
        (coefficients, (row_indices, column_indices)),
        shape=(len(row_lower), n_variables),
    ).tocsc()
    lower = np.asarray(row_lower, dtype=float)
    upper = np.asarray(row_upper, dtype=float)
    diagnostic_note = (
        " Service-capacity-relaxed diagnostic: bay occupancy was removed, "
        "but site power limits remain; this is not a deployable schedule. "
        "Only its optimum is a lower bound; a time-limited incumbent need not be a bound."
        if not enforce_service_capacity else ""
    )
    try:
        result = milp(
            c=cost_vector,
            integrality=np.ones(n_variables, dtype=np.int32),
            bounds=Bounds(np.zeros(n_variables), upper_bounds),
            constraints=LinearConstraint(matrix, lower, upper),
            options={"time_limit": settings["solver_time_limit_seconds"]},
        )
    except Exception as error:
        return _empty_result("solver_error", f"MILP solver failed: {type(error).__name__}: {error}" + diagnostic_note)

    message = str(result.message) + diagnostic_note
    if result.status == 2:
        return _empty_result(
            "infeasible", message + " Infeasible for the supplied finite plan set; no jobs were dropped."
        )
    if result.status == 3:
        return _empty_result("unbounded", message)
    if result.status not in (0, 1):
        return _empty_result("solver_error", message)
    if result.x is None:
        return _empty_result(
            "solver_error", message + " No feasible incumbent was returned; this is not an infeasibility proof."
        )

    vector = np.asarray(result.x, dtype=float)
    if vector.shape != (n_variables,) or not np.all(np.isfinite(vector)):
        return _empty_result("solver_error", message + " Invalid solution vector returned by solver.")
    rounded = np.rint(vector)
    tolerance = 1e-5
    activity = matrix @ rounded
    if (
        np.max(np.abs(vector - rounded), initial=0.0) > tolerance
        or np.any(rounded < -tolerance)
        or np.any(rounded > upper_bounds + tolerance)
        or np.any(activity < lower - tolerance)
        or np.any(activity > upper + tolerance)
    ):
        return _empty_result("solver_error", message + " Returned incumbent fails integer/bound/constraint checks.")

    investment = float(cost_vector[:2 * n_sites] @ rounded[:2 * n_sites])
    operation = float(cost_vector[2 * n_sites:] @ rounded[2 * n_sites:])
    return {
        "status": "optimal" if result.status == 0 else "feasible_limit",
        "objective_cny_per_year": investment + operation,
        "station_decisions": [
            {"site_id": site["site_id"], "build": int(rounded[s]), "bays": int(rounded[n_sites + s])}
            for s, site in enumerate(sites)
        ],
        "selected_plan_ids": [
            plan["plan_id"] for p, plan in enumerate(plans) if rounded[2 * n_sites + p] == 1
        ],
        "investment_cny_per_year": investment,
        "operation_cny_per_year": operation,
        "mip_gap": _finite_gap(getattr(result, "mip_gap", None)),
        "message": message,
    }
