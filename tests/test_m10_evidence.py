import gzip
import json
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
