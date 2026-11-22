import gzip
import hashlib
import json
import math
from time import monotonic

import pytest

from test_site_sizing import two_sites
from um_charging import m10_evidence as engine
from um_charging.m10_inputs import PlanningInputs
from um_charging.site_sizing import Design, fc


def toy_run():
    period = two_sites(9)
    period.days[0]["week_start"] = period.days[0]["date"]
    inputs = PlanningInputs([period], frozenset(period.keys), [], {"synthetic": "test"})
    requests = [engine.Request.make(period, Design(1, 50, 20), "energy", (50, 0), fixed=period.keys),
                engine.Request.make(period, Design(0, 0, 0), "energy", (0, 0), fixed=period.keys),
                engine.Request.make(period, Design(1, 50, 20), "service", (50, 20), prefer=period.keys)]
    return inputs, requests


def test_archived_solves_resume_verify_and_seeded_repetition(tmp_path, monkeypatch):
    inputs, requests = toy_run()
    with engine.M10Evidence(tmp_path, inputs, workers=2) as evidence:
        rows = evidence.batch([*requests, requests[0]])
        assert rows[0] == rows[-1]
        assert len(evidence.records) == 3
        assert [r["stats"]["status"] for _, r in rows[:3]] == ["certified", "infeasible", "certified"]
        repeats = evidence.determinism(count=2)
        assert repeats["all_match"]
        assert len({r["repeated"]["worker_pid"] for r in repeats["comparisons"]}) == 2
        assert all(r["seconds"] > 0 and r["cpu_seconds"] >= 0 for r in evidence.records)
        before = evidence.records
    with engine.M10Evidence(tmp_path, inputs) as resumed:
        assert resumed.batch(requests) == rows[:3]
        assert resumed.records == before
        assert resumed._pool is None
    with engine.M10Evidence(tmp_path, inputs, verify=True) as verification:
        def forbidden(*args, **kwargs):
            pytest.fail("Verification started the optimizer")
        monkeypatch.setattr(engine, "_solve", forbidden)
        assert verification.batch(requests) == rows[:3]
        assert verification.determinism(count=2) == repeats
        assert verification.verify_all() == {
            "certificates": 3, "feasible_replayed": 2, "unresolved_weekly_groups": 0,
            "status_counts": {"certified": 2, "infeasible": 1}}
        missing = engine.Request.make(inputs.periods[0], Design(1, 20, 20), "energy", (20, 20),
                                      fixed=inputs.main_reference)
        with pytest.raises(ValueError, match="Missing sealed"):
            verification.batch([missing])
    certificate = next((tmp_path / "certificates").glob("*.json.gz"))
    changed = json.loads(gzip.decompress(certificate.read_bytes()))
    changed["body"]["result"]["stats"]["status_code"] = 99
    certificate.write_bytes(gzip.compress(json.dumps(changed).encode("utf-8")))
    with pytest.raises(ValueError, match="hash or input scope"):
        with engine.M10Evidence(tmp_path, inputs, verify=True):
            pass


def test_admission_preserves_closing_reserve(tmp_path):
    inputs, requests = toy_run()
    with engine.M10Evidence(tmp_path, inputs, deadline=monotonic() + 299) as evidence:
        with pytest.raises(fc.StudyLimit, match="closing reserve"):
            evidence.batch(requests)
        assert not evidence.records


def test_exact_continuation_threshold_and_required_evidence(monkeypatch):
    inputs, requests = toy_run()
    period = inputs.periods[0]
    verified = []
    monkeypatch.setattr(engine, "replay", lambda *args: verified.append(args))
    for gap in (0.10, math.nextafter(0.10, math.inf)):
        stats = {"status": "unresolved", "status_code": 1, "message": "Time limit reached",
                 "objective_lower": 0.0, "objective_upper": gap}
        native = {"audit": {"passed": True}, "stats": stats}
        result = engine._admitted_result(period, requests[0], native)
        assert result["stats"]["widened_interval"] == (gap == 0.10)
        assert stats["status"] == result["stats"]["original_status"] == "unresolved"
        assert result["stats"]["status"] == ("bounded" if gap == 0.10 else "unresolved")
    for request, audit, edits in (
        (requests[2], {}, {}), (requests[0], None, {}), (requests[0], {}, {"status_code": 4}),
        (requests[0], {}, {"objective_lower": None}), (requests[0], {}, {"objective_upper": math.inf}),
        (requests[0], {}, {"message": "Interrupted"}), (requests[0], {}, {"objective_lower": 0.2})
    ):
        data = {"stats": {**stats, "objective_upper": 0.09, **edits}, "audit": audit}
        assert engine._admitted_result(period, request, data)["stats"]["status"] == "unresolved"
    assert len(verified) == 1


def test_cross_directory_reuse_keeps_parent_bytes_and_old_policy(tmp_path):
    from um_charging.m10_tables import SOLVE_COLUMNS, csv_bytes
    inputs, requests = toy_run()
    parent, current = tmp_path / "earlier", tmp_path / "continuation"
    with engine.M10Evidence(parent, inputs, workers=1) as first:
        (label, _), = first.batch(requests[:1])
    path = parent / "certificates" / (label + ".json.gz")
    body = json.loads(gzip.decompress(path.read_bytes()))["body"]
    # A toy incumbent with its real replayed schedule, plus a simulated
    # time-limit termination with a finite seven-cent evidence interval.
    stats = body["result"]["stats"]
    upper = stats["objective_upper"]
    lower = upper - 0.07
    stats.update(status="unresolved", status_code=1, message="Time limit reached", objective_lower=lower,
                 absolute_gap=upper-lower, relative_gap=(upper-lower)/abs(upper), native_mip_dual_bound=lower)
    original = gzip.compress(engine._encoded({"body": body, "sha256": engine._hash(body)}))
    path.write_bytes(original)
    with engine.M10Evidence(parent, inputs, verify=True) as old:
        assert old.verify_all()["unresolved_weekly_groups"] == 1
        ledger = csv_bytes(SOLVE_COLUMNS, old.records)
    (parent / "solves.csv").write_bytes(ledger)
    checkpoint = {"files": {"solves.csv": hashlib.sha256(ledger).hexdigest()}, "audit": {"certificates": 1}}
    (parent / "checkpoint.json").write_text(json.dumps(checkpoint))

    with engine.M10Evidence(current, inputs, parent_archive=parent, workers=1) as continuation:
        (same_id, admitted), = continuation.batch(requests[:1])
        assert same_id == label and continuation.request_for(label) == requests[0]
        assert admitted["stats"]["status"] == "bounded" and admitted["stats"]["original_status"] == "unresolved"
        assert continuation._pool is None and not list(continuation.directory.iterdir())
        continuation.batch(requests[1:2])
        assert len(list(continuation.directory.glob("*.json.gz"))) == 1
        repeats = continuation.determinism(count=1)
        record = repeats["comparisons"][0]
        assert record["original_status_equal"] == (record["original"]["original_status"]
                                                    == record["repeated"]["original_status"])
    with engine.M10Evidence(current, inputs, parent_archive=parent, verify=True) as sealed:
        audit = sealed.verify_all()
        assert audit["status_counts"] == {"bounded": 1, "infeasible": 1}
        assert audit["original_status_counts"] == {"unresolved": 1, "infeasible": 1}
        assert audit["certificate_origins"] == {"parent": 1, "current": 1}
        assert audit["widened_intervals"] == 1 and audit["unresolved_weekly_groups"] == 0
        assert sealed.determinism(count=1) == repeats
        inherited, = [r for r in sealed.records if r["certificate_origin"] == "parent"]
        assert inherited["certificate_sha256"] == hashlib.sha256(original).hexdigest()
    assert path.read_bytes() == original
    path.write_bytes(original + b"\0")
    with pytest.raises(ValueError, match="differs from parent solve ledger"):
        with engine.M10Evidence(current, inputs, parent_archive=parent, verify=True):
            pass
