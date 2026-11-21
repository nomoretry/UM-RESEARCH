from types import SimpleNamespace

from um_charging.holdout_bills import FIXED
from um_charging.holdout_repairs import repairs


def two_weeks():
    weeks = ("2021-01-04", "2021-01-11")
    periods = [SimpleNamespace(days=[{"week_start": w}], keys={(w, "2")}, chains=[[(w, "2")]]) for w in weeks]
    return weeks, periods, set.union(*(p.keys for p in periods))


def test_two_minimal_single_site_repairs_and_gap_week_first():
    (first, failed), periods, ref = two_weeks()
    low, high, baseline = FIXED
    checks = {low.label: {first: "feasible", failed: "infeasible"},
              high.label: {first: "feasible", failed: "feasible"},
              baseline.label: {first: "feasible", failed: "feasible"}}
    calls = []

    def verify(build, period):
        week = period.days[0]["week_start"]
        calls.append((build.label, week))
        return "feasible" if build.port_kw >= 30 or build.warehouse_kw >= 10 else "infeasible"

    result = repairs(periods, ref, checks, verify)
    row = result["starts"][low.label]
    assert row["minimum_added_kw"] == 10
    assert row["ways_at_verified_kw"] == ["p1-30-w0", "p1-20-w10"]
    assert set(result["starts"]) == {low.label}
    assert calls == [(label, failed) for label in ["p1-25-w0", "p1-30-w0", "p1-20-w10"]]
    options = {r["design"]: r for r in row["options"]}
    assert options["p1-25-w0"]["weeks"][first]["source"] == "monotonic:p1-20-w0"
    assert options["p1-30-w0"]["daily_policy_status"] == "unchecked"


def test_unresolved_smaller_increment_leaves_minimality_open():
    (w1, w2), periods, ref = two_weeks()
    low, high, _ = FIXED
    checks = {low.label: {w1: "infeasible", w2: "feasible"},
              high.label: {w1: "feasible", w2: "feasible"}}
    result = repairs(periods, ref, checks,
                     lambda d, p: "unresolved" if d.label == "p1-25-w0" else "feasible")
    row = result["starts"][low.label]
    assert (row["minimum_possible_added_kw"], row["verified_added_kw"], row["minimum_added_kw"]) == (5, 10, None)


def test_unique_design_budget_and_existing_rated_checks_are_reused():
    (w1, w2), periods, ref = two_weeks()
    checks = {d.label: {w1: "infeasible", w2: "feasible"} for d in FIXED[:2]}
    calls = []

    def verify(build, period):
        calls.append((build.label, period.days[0]["week_start"]))
        return "infeasible"

    result = repairs(periods, ref, checks, verify)
    assert len(result["extra_designs"]) == len(set(result["extra_designs"])) == 6
    assert calls[0] == ("p1-45-w0", w1)  # 40 kW already excludes the 20-to-25 kW change
    assert len(calls) == len(set(calls))
    assert set(label for label, _ in calls).isdisjoint(d.label for d in FIXED)
    assert all(r["verified_added_kw"] is None for r in result["starts"].values())


def test_policy_omission_can_coexist_with_exact_physical_feasibility():
    (w1, w2), periods, ref = two_weeks()
    low, _, _ = FIXED
    checks = {low.label: {w1: "feasible", w2: "feasible"}}

    def no_extra_physical_check(build, period):
        raise AssertionError("A smaller build already gives a physical witness")

    result = repairs(periods, ref, checks, no_extra_physical_check, missing_weeks={low.label: [w2]},
                     verify_daily=lambda d, p: "feasible")
    row = result["starts"][low.label]
    assert row["minimum_added_kw"] == 0 and row["policy_omission_with_feasible_R"] == [w2]
    assert row["options"][0]["daily_policy_status"] == "retained"
    assert set(row["options"][0]["daily_policy_weeks"]) == {w1, w2}
    assert row["daily_policy"]["minimum_added_kw"] == row["joint"]["minimum_added_kw"] == 5


def test_policy_cache_and_mixed_chain_limit_on_infeasibility_inference():
    (w1, w2), periods, ref = two_weeks()
    low, high, _ = FIXED
    periods[0].keys.add(("2021-01-05", "2"))
    periods[0].chains[0].append(("2021-01-05", "2"))
    checks = {low.label: {w1: "infeasible", w2: "feasible"},
              high.label: {w1: "feasible", w2: "feasible"}}
    calls = []

    def daily(build, period):
        calls.append((build.label, period.days[0]["week_start"]))
        return "feasible"

    result = repairs(periods, ref, checks, lambda d, p: "infeasible", verify_daily=daily,
                     missing_weeks={low.label: [w1]},
                     daily_checks={high.label: {w1: "feasible", w2: "feasible"}})
    entries = {row["design"]: row for row in result["starts"][low.label]["options"]}
    assert entries["p1-25-w0"]["fixed_R_status"] == "infeasible"
    assert entries["p1-25-w0"]["daily_policy_status"] == "unchecked"
    assert entries[high.label]["daily_policy_status"] == "retained"
    assert all(label != high.label for label, _ in calls)
