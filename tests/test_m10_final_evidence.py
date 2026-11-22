from dataclasses import asdict
from datetime import datetime, timezone
import json

import pytest

from test_site_sizing import two_sites
from um_charging import m10_evidence as standard
from um_charging import m10_final_evidence as final
from um_charging import site_sizing as ss


def _period():
    base = two_sites(9)
    day, = base.days
    day["vehicles"][0]["vehicle_id"] = "1"
    day["week_start"] = day["date"]
    return ss.eb.Period([day], base.prices)


def test_certifies_registration_feasibility_and_native_purchase_separately(tmp_path, monkeypatch):
    p = _period()
    week = p.days[0]["week_start"]
    d = ss.Design(1, 50, 20)
    scenario = {"main": [p]}
    grouped = [
        final.FinalRequest("main", week, d, "registration", d.caps, date=week),
        final.FinalRequest("main", week, d, "fixed_service", d.caps, p.keys),
        final.FinalRequest("main", week, d, "energy", d.caps, p.keys),
        final.FinalRequest("main", week, d, "rolling_energy", d.caps, p.keys, date=week),
    ]
    with final.FinalEvidence(tmp_path, scenario, workers=2) as ledger:
        pairs = ledger.batch(grouped)
        assert [r["stats"]["status"] for _, r in pairs] == ["certified"] * 4
        assert pairs[0][1]["stats"]["integer_score_bounds"] == [3, 3]
        assert pairs[1][1]["stats"]["objective_upper"] == 0.
        assert pairs[1][1]["audit"]["purchase_eur"] == 0.
        assert pairs[2][1]["stats"]["objective_upper"] > 0.
        assert pairs[2][1]["stats"]["objective_upper"] == pytest.approx(pairs[3][1]["stats"]["objective_upper"])
        assert p.prices[week][1] == 100.
        assert ledger.verify_all()["certificates"] == 4
        assert all(not ledger.is_new(req) for req in grouped)
        det = ledger.determinism()
        assert det["sampled"] == 4 and det["all_match"]
        assert len({r["repeated"]["worker_pid"] for r in det["comparisons"]}) == 4
    with final.FinalEvidence(tmp_path, scenario, verify=True) as ledger:
        monkeypatch.setattr(final, "_solve", lambda *a, **kw: pytest.fail("Replay invoked native solver"))
        assert ledger.batch(grouped) == pairs
        assert ledger.determinism() == det
        assert ledger.verify_all()["feasible_replayed"] == 4


def test_started_only_request_remains_unresolved_across_resume(tmp_path, monkeypatch):
    p = _period()
    week = p.days[0]["week_start"]
    d = ss.Design(1, 50, 20)
    req = final.FinalRequest("main", week, d, "fixed_service", d.caps, p.keys)
    with final.FinalEvidence(tmp_path, {"main": [p]}, workers=1) as first:
        label = req.identifier(first.scope)
        body = dict(scope=first.scope, request=asdict(req),
                    started_utc=datetime.now(timezone.utc).isoformat(), worker_pid=123)
        (first.starts / (label + ".json")).write_text(json.dumps(dict(body=body, sha256=standard._hash(body))))
    with final.FinalEvidence(tmp_path, {"main": [p]}, workers=1) as resumed:
        monkeypatch.setattr(resumed, "_run", lambda *a: pytest.fail("Resume retried a begun request"))
        assert not resumed.is_new(req)
        (certificate, result), = resumed.batch([req])
        assert certificate == label
        assert result["stats"]["status"] == "unresolved"
        assert result["stats"]["status_code"] is None
        assert resumed.verify_all()["final_interrupted"] == 1
        resumed.record_unresolved(req)
        resumed.record_unresolved(final.FinalRequest("main", week, d, "energy", d.caps, p.keys))
        assert len(resumed.unresolved) == 1


def test_request_scope_rejects_wrong_date_and_duplicate_fixed_keys(tmp_path):
    p = _period()
    week = p.days[0]["week_start"]
    d = ss.Design(1, 50, 20)
    with final.FinalEvidence(tmp_path, {"main": [p]}) as ledger:
        job = final.FinalRequest("main", week, d, "rolling_energy", d.caps, p.keys, date="2021-01-06")
        with pytest.raises(ValueError, match="calendar day"):
            ledger.batch([job])
        job = final.FinalRequest("main", week, d, "energy", d.caps, list(p.keys) * 2)
        with pytest.raises(ValueError, match="repeated"):
            ledger.batch([job])
