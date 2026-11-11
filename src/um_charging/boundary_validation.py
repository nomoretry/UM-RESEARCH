"""Cross-scenario checks for the declared power-by-window experiment.

This module does not optimize, alter results, or infer missing coordinates.
Original-solution and enumeration validation must already have passed. These
checks diagnose consistency across the complete 100-row experiment; they are
not a substitute for checking task inputs or the underlying primal solutions.
"""
from __future__ import annotations

import itertools
import math

from .timegrid import POLICIES

POWERS = (50, 75, 100, 125, 150)
WINDOWS = (0, 15, 30, 45, 60)
SCOPES = ("port_only", "two_sites")
COORDINATES = ("port_available_power_kw", "warehouse_window_minutes", "charging_scope", "connector_policy")
REQUIRED = set(COORDINATES) | {
    "status", "objective", "dual_bound", "mip_gap", "validation_passed",
    "enumeration_comparison", "enumeration_best_hardware",
}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _hardware_shape(hardware):
    """Keep all ties, checking only the exact allocation representation."""
    if not isinstance(hardware, list) or not hardware:
        return False
    for allocation in hardware:
        if not isinstance(allocation, list) or len(allocation) != 2:
            return False
        for item, site_id in zip(allocation, ("PORT", "WAREHOUSE")):
            if (not isinstance(item, dict) or set(item) != {"site_id", "new_interfaces", "upgrade_id"}
                    or item["site_id"] != site_id or type(item["new_interfaces"]) is not int
                    or item["new_interfaces"] < 0
                    or (item["upgrade_id"] is not None
                        and (not isinstance(item["upgrade_id"], str) or not item["upgrade_id"].strip()))):
                return False
    return True


def check_boundary_properties(rows, tolerance=1e-7):
    """Check the fixed 5 x 5 x 2 x 2 matrix and retain every pair's evidence.

    ``checks`` and ``property_counts`` count pairwise comparisons, not solver
    runs or physical-constraint checks. Invalid/missing rows stop pairwise
    comparisons and produce explicit INPUT errors. Costs use an absolute
    tolerance; infeasibility is ordered above finite cost without serializing
    infinity. Hardware ties are neither selected nor rounded nor modified.

    Window monotonicity under fixed_dwell_connection is appropriate to this
    fixture's common warehouse arrival and common extension of the plug window.
    It is not asserted as a theorem for arbitrary staggered parking intervals.
    """
    if not _finite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance must be finite and positive")
    errors, comparisons, index = [], [], {}
    property_counts = {name: 0 for name in (
        "port_window_invariance", "zero_window_scope_equivalence", "power_monotonicity",
        "window_monotonicity", "scope_dominance", "switching_dominance",
    )}

    def invalid(detail, row=None):
        error = {"property": "INPUT", "detail": detail}
        if row is not None:
            error["row"] = row
        errors.append(error)

    if not isinstance(rows, list):
        invalid("rows must be the complete explicit list of scenario summaries")
        rows = []
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or not REQUIRED.issubset(row):
            invalid("Missing required summary fields", position)
            continue
        power, window, scope, policy = (row[field] for field in COORDINATES)
        if (type(power) is not int or power not in POWERS or type(window) is not int or window not in WINDOWS
                or not isinstance(scope, str) or scope not in SCOPES
                or not isinstance(policy, str) or policy not in POLICIES):
            invalid("Coordinates must exactly match the declared power/window/scope/policy grid", position)
            continue
        key = (power, window, scope, policy)
        if key in index:
            invalid("Duplicate scenario coordinates", position)
            continue
        index[key] = row
        enumeration = row["enumeration_comparison"]
        if not isinstance(enumeration, dict) or enumeration.get("passed") is not True:
            invalid("Exhaustive facility comparison has not passed", position)
        if row["status"] == "optimal":
            if not all(_finite(row[field]) for field in ("objective", "dual_bound", "mip_gap")):
                invalid("Optimal result requires finite objective, dual bound and gap", position)
            elif row["mip_gap"] < 0 or abs(row["objective"] - row["dual_bound"]) > tolerance:
                invalid("Optimal objective and dual bound must agree within tolerance and gap must be nonnegative", position)
            if row["validation_passed"] is not True:
                invalid("Optimal result has not passed independent primal checks", position)
            if not _hardware_shape(row["enumeration_best_hardware"]):
                invalid("Optimal result needs all best hardware allocations in the exact enumeration format", position)
        elif row["status"] == "infeasible":
            if any(row[field] is not None for field in ("objective", "dual_bound", "mip_gap", "validation_passed")):
                invalid("Infeasible result requires null objective/bound/gap and nonapplicable primal check", position)
            if row["enumeration_best_hardware"] != []:
                invalid("Infeasible result cannot report optimal hardware", position)
        else:
            invalid("Unresolved or unsupported solver status; do not treat as proven optimal/infeasible", position)
    expected = set(itertools.product(POWERS, WINDOWS, SCOPES, POLICIES))
    missing = expected - set(index)
    if missing:
        invalid("Missing scenario coordinates: " + repr(sorted(missing)))
    if len(rows) != len(expected):
        invalid(f"Expected exactly {len(expected)} rows, received {len(rows)}")

    def coordinate(key):
        return dict(zip(COORDINATES, key))

    def compare(name, before_key, after_key, relation):
        before, after = index[before_key], index[after_key]
        before_feasible, after_feasible = before["status"] == "optimal", after["status"] == "optimal"
        delta = after["objective"] - before["objective"] if before_feasible and after_feasible else None
        if relation == "equal":
            passed = before_feasible == after_feasible and (delta is None or abs(delta) <= tolerance)
        else:
            passed = not before_feasible or (after_feasible and delta <= tolerance)
        record = {"property": name, "before": coordinate(before_key), "after": coordinate(after_key),
                  "relation": relation, "before_status": before["status"], "after_status": after["status"],
                  "before_objective": before["objective"], "after_objective": after["objective"],
                  "objective_change": delta, "passed": passed}
        property_counts[name] += 1
        comparisons.append(record)
        if not passed:
            errors.append(record.copy())

    if not errors:
        for policy in POLICIES:
            for power in POWERS:
                for window in WINDOWS[1:]:
                    compare("port_window_invariance", (power, 0, "port_only", policy),
                            (power, window, "port_only", policy), "equal")
                compare("zero_window_scope_equivalence", (power, 0, "port_only", policy),
                        (power, 0, "two_sites", policy), "equal")
                for scope in SCOPES:
                    for earlier, later in zip(WINDOWS, WINDOWS[1:]):
                        compare("window_monotonicity", (power, earlier, scope, policy),
                                (power, later, scope, policy), "not_worse")
            for window in WINDOWS:
                for scope in SCOPES:
                    for lower, higher in zip(POWERS, POWERS[1:]):
                        compare("power_monotonicity", (lower, window, scope, policy),
                                (higher, window, scope, policy), "not_worse")
                for power in POWERS:
                    compare("scope_dominance", (power, window, "port_only", policy),
                            (power, window, "two_sites", policy), "not_worse")
        for power, window, scope in itertools.product(POWERS, WINDOWS, SCOPES):
            compare("switching_dominance", (power, window, scope, "fixed_dwell_connection"),
                    (power, window, scope, "slot_boundary_switching"), "not_worse")
    return {"passed": not errors, "errors": errors, "checks": len(comparisons),
            "property_counts": property_counts, "comparisons": comparisons, "tolerance": tolerance,
            "matrix_complete": len(rows) == len(expected) and set(index) == expected,
            "scope_note": "Declared common-arrival window experiment; not a general monotonicity claim for heterogeneous fixed-dwell windows."}
