"""Adversarial summary checks, without using an optimizer as a test oracle."""
import copy
import itertools
import math
import random

import pytest

from um_charging.boundary_validation import check_boundary_properties


def allocation(port=1, warehouse=0, upgrade=None):
    return [{"site_id": "PORT", "new_interfaces": port, "upgrade_id": upgrade},
            {"site_id": "WAREHOUSE", "new_interfaces": warehouse, "upgrade_id": None}]


@pytest.fixture
def matrix():
    # A synthetic property fixture, not a result of the charging experiment.
    # One low-power zero-window corner is impossible; extra resources can
    # resolve it. Port-only results deliberately never depend on the window.
    rows = []
    for power, window, scope, policy in itertools.product(
            [50, 75, 100, 125, 150], [0, 15, 30, 45, 60],
            ["port_only", "two_sites"], ["slot_boundary_switching", "fixed_dwell_connection"]):
        feasible = power > 50 or (scope == "two_sites" and window > 0)
        value = 400 - power
        if scope == "two_sites":
            value -= window * (2 if policy == "slot_boundary_switching" else 1)
        rows.append({"port_available_power_kw": power, "warehouse_window_minutes": window,
                     "charging_scope": scope, "connector_policy": policy,
                     "status": "optimal" if feasible else "infeasible",
                     "objective": value if feasible else None, "dual_bound": value if feasible else None,
                     "mip_gap": 0.0 if feasible else None, "validation_passed": True if feasible else None,
                     "enumeration_comparison": {"passed": True},
                     "enumeration_best_hardware": [allocation()] if feasible else []})
    return rows


def find(rows, *, power=100, window=30, scope="two_sites", policy="slot_boundary_switching"):
    return next(row for row in rows if (row["port_available_power_kw"], row["warehouse_window_minutes"],
                    row["charging_scope"], row["connector_policy"]) == (power, window, scope, policy))


def cost(row, value):
    row["objective"] = row["dual_bound"] = value


def failed_properties(result):
    return {error["property"] for error in result["errors"]}


def test_order_independent_complete_matrix_and_ties_preserved(matrix):
    row = find(matrix)
    row["enumeration_best_hardware"].append(allocation(port=0, warehouse=1, upgrade="port_plus_50"))
    random.Random(71).shuffle(matrix)
    before = copy.deepcopy(matrix)
    checked = check_boundary_properties(matrix)
    assert checked["passed"] and checked["matrix_complete"]
    assert checked["checks"] == 310
    assert checked["property_counts"] == {"port_window_invariance": 40, "zero_window_scope_equivalence": 10,
        "power_monotonicity": 80, "window_monotonicity": 80, "scope_dominance": 50, "switching_dominance": 50}
    assert any(item["before_status"] == "infeasible" and item["after_status"] == "optimal"
               and item["passed"] for item in checked["comparisons"])
    assert any(item["before_status"] == item["after_status"] == "infeasible"
               and item["objective_change"] is None for item in checked["comparisons"])
    assert matrix == before


@pytest.mark.parametrize("property_name,mutation", [
    ("port_window_invariance", "port_window"),
    ("zero_window_scope_equivalence", "zero_window"),
    ("power_monotonicity", "power"),
    ("window_monotonicity", "window"),
    ("scope_dominance", "scope"),
    ("switching_dominance", "switching"),
])
def test_resource_or_scope_regression_is_exposed(matrix, property_name, mutation):
    if mutation == "port_window": cost(find(matrix, scope="port_only"), 299)
    elif mutation == "zero_window": cost(find(matrix, window=0), 299)
    elif mutation == "power": cost(find(matrix, power=125), 1000)
    elif mutation == "window": cost(find(matrix, window=45), 1000)
    elif mutation == "scope": cost(find(matrix), 301)
    elif mutation == "switching": cost(find(matrix), 271)
    checked = check_boundary_properties(matrix)
    assert not checked["passed"]
    assert property_name in failed_properties(checked)
    assert checked["checks"] == 310


def test_a_previously_feasible_problem_cannot_become_infeasible(matrix):
    row = find(matrix, power=125)
    row.update(status="infeasible", objective=None, dual_bound=None, mip_gap=None,
               validation_passed=None, enumeration_best_hardware=[])
    result = check_boundary_properties(matrix)
    assert not result["passed"]
    assert {"power_monotonicity", "window_monotonicity", "scope_dominance"} <= failed_properties(result)


def test_absolute_tolerance_not_rounded_currency(matrix):
    for row in matrix:
        if row["status"] == "optimal": cost(row, 100.0)
    cost(find(matrix, scope="port_only"), 100.0 + 5e-8)
    assert check_boundary_properties(matrix)["passed"]
    cost(find(matrix, scope="port_only"), 100.0 + 2e-7)
    assert not check_boundary_properties(matrix)["passed"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "illegal_power", "float_power", "bool_window",
                                      "unknown_scope", "unknown_policy", "missing_field", "not_dict"])
def test_incomplete_or_unrecognized_grid_is_rejected(matrix, mutation):
    if mutation == "missing": matrix.pop()
    elif mutation == "duplicate": matrix[-1] = copy.deepcopy(matrix[0])
    elif mutation == "illegal_power": matrix[0]["port_available_power_kw"] = 51
    elif mutation == "float_power": matrix[0]["port_available_power_kw"] = 50.0
    elif mutation == "bool_window": matrix[0]["warehouse_window_minutes"] = False
    elif mutation == "unknown_scope": matrix[0]["charging_scope"] = "PORT_ONLY"
    elif mutation == "unknown_policy": matrix[0]["connector_policy"] = "switching"
    elif mutation == "missing_field": del matrix[0]["status"]
    elif mutation == "not_dict": matrix[0] = []
    checked = check_boundary_properties(matrix)
    assert not checked["passed"]
    assert checked["checks"] == 0
    assert failed_properties(checked) == {"INPUT"}


@pytest.mark.parametrize("field,value", [("objective", math.nan), ("objective", math.inf),
    ("dual_bound", -math.inf), ("mip_gap", math.nan), ("mip_gap", -1),
    ("objective", True), ("dual_bound", None), ("status", "limit"), ("status", "timeout"),
    ("validation_passed", False), ("validation_passed", 1),
    ("enumeration_comparison", {"passed": False}), ("enumeration_comparison", {"passed": 1}),
    ("enumeration_best_hardware", []), ("enumeration_best_hardware", [[{}]])])
def test_unresolved_unverified_or_malformed_optimum_cannot_pass(matrix, field, value):
    find(matrix)[field] = value
    result = check_boundary_properties(matrix)
    assert not result["passed"]
    assert result["checks"] == 0
    assert "INPUT" in failed_properties(result)


def test_nonmatching_bound_is_not_proof_of_optimality(matrix):
    find(matrix)["dual_bound"] -= 1
    assert not check_boundary_properties(matrix)["passed"]


@pytest.mark.parametrize("field,value", [("objective", 0), ("dual_bound", 0), ("mip_gap", 0),
                                       ("validation_passed", True), ("enumeration_best_hardware", [allocation()])])
def test_infeasible_has_no_primal_cost_or_best_hardware(matrix, field, value):
    find(matrix, power=50, window=0)[field] = value
    assert not check_boundary_properties(matrix)["passed"]


@pytest.mark.parametrize("tolerance", [0, -1, math.nan, math.inf, True, "0.1"])
def test_invalid_tolerance_is_explicit_error(matrix, tolerance):
    with pytest.raises(ValueError, match="tolerance"):
        check_boundary_properties(matrix, tolerance)


def test_nonlist_input_is_explicit_failed_report():
    checked = check_boundary_properties({})
    assert not checked["passed"] and checked["checks"] == 0
