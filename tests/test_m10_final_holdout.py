from copy import deepcopy

import pytest

from test_site_sizing import two_sites
from um_charging import energy_boundary as eb
from um_charging import m10_final_holdout as holdout
from um_charging.m10_final_evidence import FinalEvidence


def _frozen_toy_matrix():
    return {
        "full": [["p1-20-w20", [20, 20]], ["p1-40-w20", [20, 20]], ["p1-40-w20", [40, 20]],
                 ["p1-50-w50", [20, 20]], ["p1-50-w50", [50, 20]], ["p1-50-w50", [50, 50]]],
        "rolling": [["p1-20-w20", [20, 20]], ["p1-30-w20", [30, 20]], ["p1-40-w20", [40, 20]]],
        "immediate": [["p1-20-w20", [20, 20]], ["p1-40-w20", [40, 20]], ["p2-100-w20", [100, 20]]],
        "union": {"design": "p1-40-w20", "caps_kw": "[40,20]", "all_weekly_minima_classified": "True"},
        "frozen_full_information": [
            dict(scenario=t, connection_basis=b, design=d.label, port_cap_kw=d.port_kw,
                 warehouse_cap_kw=d.warehouse_kw)
            for t in holdout.TARIFFS for b in holdout.BASES
            for d in (holdout.F40 if t in ("N0", "official") or (t, b) == ("frank", "existing") else holdout.F20,)
        ],
        "policies": {
            mode: [dict(scenario=t, connection_basis=b, design=d.label, caps=d.caps)
                   for t in holdout.TARIFFS for b in holdout.BASES
                   for d in (holdout.I if mode == holdout.IMMEDIATE else
                             holdout.D30 if t == "capacity_208_38" else holdout.F40,)]
            for mode in (holdout.IMMEDIATE, holdout.ROLLING)
        },
    }


def _periods():
    toy = two_sites(8.5)
    day = deepcopy(toy.days[0])
    day["vehicles"][0]["vehicle_id"] = "1"
    day["week_start"] = day["date"]
    period = eb.Period([day], toy.prices)
    return holdout.scenario_periods([period], [period])


def test_frozen_matrix_rejects_changed_caps():
    matrix = _frozen_toy_matrix()
    assert len(holdout.build_plan(matrix)["full"]) == 6
    matrix["rolling"][1][1] = [20, 20]
    with pytest.raises(ValueError, match="Archived holdout matrix changed"):
        holdout.build_plan(matrix)


def test_synthetic_full_matrix_settlement_inputs_and_margin(tmp_path):
    scenarios = _periods()
    matrix = _frozen_toy_matrix()
    with FinalEvidence(tmp_path, scenarios, workers=1) as ledger:
        out = holdout.execute(scenarios, matrix, ledger)
    assert out["status"] == "complete"
    assert out["reference"] == [("2021-01-04", "1")]
    assert out["primary"]["classification"] == "passed"
    assert [s["endpoint"] for s in out["secondary"]] == ["S1", "S2", "S3"]
    assert len(out["points"]) == 12
    assert len(out["billing_roles"]) == 120
    assert all(r["service"] == "passed" and r["bill_admitted"] for r in out["points"])
    row = out["points"][0]["weeks"][0]
    assert row["proof_id"] != row["purchase_proof_id"]
    assert row["purchase_upper"] == pytest.approx(row["audit"]["purchase_eur"])
    margin = out["sensitivities"]["energy_plus_20"]
    assert margin["points"][1]["service"] == "passed"
    assert margin["points"][2]["service"] == "failure_independent"
    assert not margin["baseline_also_lost"]
    assert out["sensitivities"]["parking_gap"]["added"] == []
    assert scenarios["main"][0].days[0]["vehicles"][0]["trips"][0]["energy_kwh"] == 8.5
    assert scenarios["energy_plus_20"][0].days[0]["vehicles"][0]["trips"][0]["energy_kwh"] == pytest.approx(10.2)


def test_primary_native_timeout_preserves_issued_request_and_stops():
    class SyntheticLedger:
        def __init__(self):
            self.requests = []
            self.unresolved = []
        def is_new(self, request):
            return True
        def check(self, limit_unresolved=True):
            pass
        def record_unresolved(self, request):
            self.unresolved.append(request)
        def batch(self, requests):
            result = []
            for r in requests:
                self.requests.append(r)
                if r.phase == "fixed_service":
                    result.append(("fixed-timeout", dict(stats=dict(status="unresolved", status_code=1),
                                                         audit=None, schedule=[], states=[])))
                elif r.phase == "registration":
                    result.append(("registration", dict(stats=dict(status="certified", status_code=0,
                        integer_score_bounds=[2, 2]), audit={"passed": True},
                        states=[dict(date=r.date, vehicle_id="1", served=True)])))
                else:
                    pytest.fail(f"request dispatched after primary timeout: {r}")
            return result

    ledger = SyntheticLedger()
    saved = {}
    out = holdout.execute(_periods(), _frozen_toy_matrix(), ledger, save=saved.__setitem__)
    assert out["status"] == "stopped"
    assert out["primary"]["classification"] == "unresolved"
    assert out["pause"]["request"] == "fixed-timeout"
    assert out["points"][0]["weeks"][0]["proof_id"] == "fixed-timeout"
    assert saved["outcome"] == out
    assert ledger.requests[-1].phase == "fixed_service"
    assert ledger.unresolved == [ledger.requests[-1]]
