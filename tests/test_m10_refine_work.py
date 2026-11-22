from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math

import pytest

from um_charging import m10_refine_work as work
from um_charging.site_sizing import Design


WEEK = "2021-11-15"
OTHER_WEEK = "2021-11-22"


def observations():
    first = datetime(2026, 11, 20, tzinfo=timezone.utc)
    rows = []
    for i, (origin, offset, seconds, week) in enumerate((
        ("parent", 0, 100, WEEK), ("parent", 0, 100, WEEK), ("current", 86400, 50, OTHER_WEEK)
    )):
        rows.append(dict(id=str(i), phase="energy", week=week, design="p1-20-w20", port_cap_kw="20",
                         warehouse_cap_kw="20", seconds=str(seconds), certificate_origin=origin,
                         started_utc=(first + timedelta(seconds=offset)).isoformat()))
    return rows


def test_deduplicate_shared_requests_and_separate_inactive_time():
    # A zero washer limit makes different installed warehouse capacities
    # equivalent for this particular grid request.
    priced = work.WorkPoint(Design(1, 20, 20), (20, 0), True, (WEEK,))
    free_price = work.WorkPoint(Design(1, 20, 15), (20, 0), False, (WEEK,))
    rated = work.WorkPoint(Design(1, 20, 15), (20, 15), False, (WEEK,), (WEEK,))
    pending = work.work_requests([priced, free_price, rated])
    assert len(pending["priced"]) == len(pending["shared"]) == 1
    assert set(pending["unquoted"]) == {("energy", WEEK, rated.design, rated.caps),
                                        ("service", WEEK, rated.design, rated.caps)}
    est = work.estimate_work([priced, free_price, rated], observations(), elapsed_seconds=100)
    assert est["history"]["solve_windows_seconds"] == {"parent": 100, "current": 50}
    assert est["history"]["wall_per_solver_second"] == pytest.approx(150/250)
    assert est["priced"]["estimated_solver_seconds"] == pytest.approx(250/3)
    assert est["priced"]["strata"][0]["timing_source"] == "phase_mean"
    assert est["unquoted"]["estimated_solver_seconds"] == 400
    assert {r["timing_source"] for r in est["unquoted"]["strata"]} == {"matched_stratum", "time_limit"}
    assert est["combined"]["unique_weekly_requests"] == 3
    assert est["budget"]["fresh_process_allowance_seconds"] == 963
    assert est["budget"]["priced_required_seconds"] == 50 + 100 + 963
    assert est["budget"]["all_required_seconds"] == est["budget"]["priced_required_seconds"] + 240


def test_unrounded_gate_uses_priced_work_and_reserves_closure_once():
    r = dict(design="p1-20-w20", port_plugs=1, port_kw=20, warehouse_kw=20,
             caps_kw=[20, 20], decision="retain", priced=True, missing_weeks=[WEEK], service_weeks=[])
    unquoted = dict(r, design="p2-50-w15", port_plugs=2, port_kw=50, warehouse_kw=15,
                    caps_kw=[50, 15], priced=False, service_weeks=[WEEK])
    rows = [r, unquoted, dict(r, decision="exclude")]
    history = observations()
    before = deepcopy(history)
    cost = work.estimate_work(rows, history, elapsed_seconds=0)["budget"]["priced_required_seconds"]
    edge = 14400 - 900 - cost
    yes = work.estimate_work(rows, history, elapsed_seconds=edge)["budget"]
    no = work.estimate_work(rows, history, elapsed_seconds=math.nextafter(edge, math.inf))["budget"]
    assert yes["branch"] == "A" and yes["all_required_seconds"] > yes["available_seconds"]
    assert no["branch"] == "B" and no["priced_margin_seconds"] < 0
    assert history == before
    with pytest.raises(ValueError, match="Duplicate retained"):
        work.estimate_work([r, r], history, elapsed_seconds=0)


def test_fully_covered_priced_points_require_no_new_solver_or_repeat_time():
    row = work.WorkPoint(Design(1, 20, 20), (20, 20), True, ())
    result = work.estimate_work([row], observations(), elapsed_seconds=13500)
    assert result["priced"]["retained_points"] == 1
    assert result["budget"]["priced_required_seconds"] == result["combined"]["projected_wall_seconds"] == 0
    assert result["budget"]["branch"] == "A"


def test_archived_fixed_service_on_smaller_hardware_certifies_only_rated_service():
    donor = dict(port_plugs=1, port_kw=15, warehouse_kw=15, caps_kw=[10, 10], priced=False,
                 decision="exclude", weekly=[dict(week=WEEK, proof="fixed-witness")])
    target = dict(port_plugs=1, port_kw=20, warehouse_kw=15, caps_kw=[10, 15], priced=False,
                  decision="retain", weekly=[], missing_weeks=[WEEK], service_weeks=[WEEK])
    result = work.estimate_work([target, donor], observations(), elapsed_seconds=0)
    assert result["unquoted"]["request_counts"] == {"energy": 1}
    assert result["service_qualification_transfers"] == [
        dict(design="p1-20-w15", donor_design="p1-15-w15", week=WEEK, evidence_id="fixed-witness")]
