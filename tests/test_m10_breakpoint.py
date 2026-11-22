import math

from test_holdout_service import overnight
from um_charging import m10_breakpoint as breakpoint


def test_legacy_m8_registration_prioritizes_count_then_overlap_then_numeric_id():
    period = overnight({"10": 22.5, "2": 22.5})
    first, second = sorted(period.cases)
    prior = {(first, "10")}
    with_overlap = breakpoint._m8_week(period, prior, math.inf)
    chosen = breakpoint.ss.eb.selected(with_overlap)
    assert chosen == {(first, "10"), (second, "10"), (second, "2")}
    assert with_overlap["stats"]["status"] == "certified"
    lo, hi = with_overlap["stats"]["integer_score_bounds"]
    assert lo == hi
    no_prior = breakpoint._m8_week(period, set(), math.inf)
    assert breakpoint.ss.eb.selected(no_prior) == {(first, "2"), (second, "10"), (second, "2")}


def test_breakpoint_saved_certificate_replays_with_optimizer_disabled(tmp_path, monkeypatch):
    period = overnight({"1": 22.5})
    for day in period.days:
        day["week_start"] = "2021-01-04"
    request = breakpoint._request("breakpoint_m8_registration", period)
    pair = breakpoint._call(period, request, tmp_path, "synthetic", math.inf, False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Archived replay invoked optimization")

    monkeypatch.setattr(breakpoint, "_solve", forbidden)
    archived = breakpoint._call(period, request, tmp_path, "synthetic", math.inf, True)
    assert breakpoint.evidence._encoded(archived) == breakpoint.evidence._encoded(pair)
