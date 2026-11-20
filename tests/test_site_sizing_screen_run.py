from collections import defaultdict
from types import SimpleNamespace

from um_charging.site_sizing import Design
from um_charging.site_sizing_screen_evidence import ArchiveWeek, PointPlan
from um_charging.site_sizing_screen_run import FormalGrid, OperatingPoint, _all_above


DESIGN = Design(1, 50, 0)
CAPS = (25, 0)
FIRST_WEEK = "2021-09-27"
SECOND_WEEK = "2021-10-04"


def _proof(status):
    return ArchiveWeek(FIRST_WEEK, DESIGN, CAPS, status, 5., None, None,
                       "formal/worker-01/00001", "checksum", "source")


def _classification_grid(dual):
    first = (FIRST_WEEK, DESIGN, CAPS)
    second = (SECOND_WEEK, DESIGN, CAPS)
    grid = FormalGrid.__new__(FormalGrid)
    grid.points = [OperatingPoint(DESIGN, CAPS, kind) for kind in ("ranking", "threshold")]
    grid.incumbent = {("official", "new"): 10.}
    grid.attempts = {first: _proof("unresolved")}
    grid.evidence = SimpleNamespace(point_plan=lambda *_: PointPlan("needs_solves", missing=(first, second)))
    grid.quote_evidence = grid.evidence
    grid.archive_records = {}
    grid.quote_records = {}
    grid.bounds = SimpleNamespace(annual_lower_bounds=lambda *_: {
        "total_eur": {"official": {"new": dual}}, "weekly": {}})
    return grid, first, second


def test_one_failed_week_does_not_mark_an_unfinished_ranking_point_unresolved():
    grid, first, second = _classification_grid(9.)
    grid.refresh()
    assert [point.status for point in grid.points] == ["pending", "pending"]
    assert grid.unresolved_count() == 0
    grid.attempts[second] = grid.attempts[first]
    grid.refresh()
    assert [point.status for point in grid.points] == ["unresolved", "threshold_interval"]
    assert grid.unresolved_count() == 1


def test_ranking_interval_exclusion_does_not_skip_quote_only_week():
    grid, _, second = _classification_grid(11.)
    grid.refresh()
    assert [point.status for point in grid.points] == ["excluded_by_interval", "pending"]
    assert grid.next_scope(()) == second


def test_quote_only_proof_does_not_enter_ranking_indexes_or_lower_bounds():
    grid = FormalGrid.__new__(FormalGrid)
    grid.evidence = SimpleNamespace(combined_index=({}, ()))
    grid.quote_evidence = SimpleNamespace(combined_index=({}, ()))
    grid.archive_records = {FIRST_WEEK: []}
    grid.quote_records = {FIRST_WEEK: []}
    grid.attempts = {}
    grid.results = []
    grid.ranking_scopes = set()
    grid.by_hardware = defaultdict(list)

    proof = _proof("infeasible")
    grid.add_proof(proof, 9.)
    assert grid.evidence.combined_index == ({}, ())
    assert grid.quote_evidence.combined_index == ({}, (proof,))
    assert not grid.archive_records[FIRST_WEEK]
    assert grid.quote_records[FIRST_WEEK] == [proof]
    assert grid.results[0]["kind"] == "threshold"


def test_interval_lower_bound_must_clear_every_published_incumbent():
    incumbent = {("official", "new"): 5., ("official", "existing"): 7.}
    assert not _all_above({"official": {"new": 5. + 1e-6, "existing": 8.}}, incumbent)
    assert not _all_above({"official": {"new": 6., "existing": 7.}}, incumbent)
    assert _all_above({"official": {"new": 6., "existing": 8.}}, incumbent)
