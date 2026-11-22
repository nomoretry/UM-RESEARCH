from concurrent.futures import ProcessPoolExecutor
import math
import multiprocessing

from test_holdout_service import overnight
from um_charging import m10_breakpoint as breakpoint


def test_legacy_m8_registration_prioritizes_count_then_overlap_then_numeric_id():
    period = overnight({"10": 22.5, "2": 22.5})
    first, second = sorted(period.cases)
    prior = {(first, "10")}
    # HiGHS retains its native thread scheduler for the life of an interpreter.
    # Use a fresh worker, as the formal phase does, when locking it to one thread.
    with ProcessPoolExecutor(1, mp_context=multiprocessing.get_context("spawn")) as pool:
        with_overlap = pool.submit(breakpoint._m8_week, period, prior, math.inf).result()
        no_prior = pool.submit(breakpoint._m8_week, period, set(), math.inf).result()
    chosen = breakpoint.ss.eb.selected(with_overlap)
    assert chosen == {(first, "10"), (second, "10"), (second, "2")}
    assert with_overlap["stats"]["status"] == "certified"
    lo, hi = with_overlap["stats"]["integer_score_bounds"]
    assert lo == hi
    assert breakpoint.ss.eb.selected(no_prior) == {(first, "2"), (second, "10"), (second, "2")}


def test_breakpoint_saved_certificate_replays_with_optimizer_disabled(tmp_path, monkeypatch):
    period = overnight({"1": 22.5})
    for day in period.days:
        day["week_start"] = "2021-01-04"
    request = breakpoint._request("breakpoint_m8_registration", period)
    with ProcessPoolExecutor(1, mp_context=multiprocessing.get_context("spawn")) as pool:
        pair = pool.submit(breakpoint._call, period, request, tmp_path, "synthetic", math.inf, False).result()
    assert pair[1]["stats"]["status"] == "certified"

    def forbidden(*args, **kwargs):
        raise AssertionError("Archived replay invoked optimization")

    monkeypatch.setattr(breakpoint, "_solve", forbidden)
    archived = breakpoint._call(period, request, tmp_path, "synthetic", math.inf, True)
    assert breakpoint.evidence._encoded(archived) == breakpoint.evidence._encoded(pair)
