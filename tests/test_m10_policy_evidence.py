from time import monotonic
import hashlib
import gzip
import json

import pytest

from test_m10_evidence import toy_run
from um_charging import m10_evidence as m10
from um_charging import m10_rolling as rolling
from um_charging.m10_policy_evidence import PolicyEvidence


def test_mixed_daily_weekly_resume_and_fresh_processes(tmp_path, monkeypatch):
    inputs, weekly = toy_run()
    p = inputs.periods[0]
    req = weekly[0]
    daily, = rolling.rolling_requests(p,req.design,req.caps,inputs.registered)
    requests = [req,daily,weekly[1],daily]
    with PolicyEvidence(tmp_path,inputs,None,workers=2) as ledger:
        pairs = ledger.batch(requests)
        assert pairs[1] == pairs[-1] and pairs[1][0] != pairs[0][0]
        assert all(ledger.request_for(i)==r for r,(i,s) in zip(requests,pairs,strict=True))
        assert ledger.verify_all()["new_status_counts"] == {"certified":2,"infeasible":1}
        assert len(ledger.records)==len(ledger.new_records)==3
        det=ledger.determinism()
        assert det["all_match"] and det["requested"]==20 and det["sampled"]==3
        assert len({r["repeated"]["worker_pid"] for r in det["comparisons"]}) == 3
    with PolicyEvidence(tmp_path,inputs,None,verify=True) as ledger:
        monkeypatch.setattr(m10,"_solve",lambda *a,**kw:pytest.fail("verification started HiGHS"))
        assert ledger.batch(requests) == pairs
        assert ledger.determinism()==det
        assert ledger.verify_all()["certificates"]==3
        bad = m10.Request(req.week,req.design,"rolling_energy",req.caps,req.fixed,())
        with pytest.raises(ValueError,match="calendar"):
            ledger.batch([bad])


def test_weekly_unresolved_count_and_deadline(tmp_path):
    inputs,reqs=toy_run()
    with PolicyEvidence(tmp_path,inputs,None,deadline=monotonic()+2,workers=1) as ledger:
        with pytest.raises(m10.ss.fc.StudyLimit,match="300-second"):
            ledger.batch(reqs[:1])
        item=dict(week="2021-01-04",caps_kw=[50,20],design="p1-50-w20",status="unresolved")
        for _ in range(5):
            ledger.record_rolling_week(item)
        assert len(ledger.unresolved)==1
        for week in ("A","B"):
            ledger.record_rolling_week({**item,"week":week})
        with pytest.raises(m10.ss.fc.StudyLimit,match="three unresolved"):
            ledger.record_rolling_week({**item,"week":"C"})


def test_read_only_two_layer_parent_ledger_and_separate_new_scope(tmp_path):
    from um_charging.m10_tables import csv_bytes, solve_columns
    inputs,reqs=toy_run()
    coarse, policies=tmp_path/"coarse",tmp_path/"policies"
    inherited=coarse/"inherited"
    with m10.M10Evidence(inherited,inputs,workers=1) as one:
        (old_id,_),=one.batch(reqs[:1])
        first=csv_bytes(solve_columns(False),one.records)
    (inherited/"solves.csv").write_bytes(first)
    def sha(content):
        return hashlib.sha256(content).hexdigest()
    (inherited/"checkpoint.json").write_text(json.dumps({
        "files":{"solves.csv":sha(first)}, "audit":{"certificates":1}}))
    with m10.M10Evidence(coarse,inputs,workers=1,parent_archive=inherited) as second:
        second.batch(reqs[1:2])
        combined=csv_bytes(solve_columns(True),second.records)
    (coarse/"solves.csv").write_bytes(combined)
    (coarse/"seal.json").write_text(json.dumps({"products":{"solves.csv":sha(combined)}}))
    contents={p.relative_to(coarse):sha(p.read_bytes()) for p in coarse.rglob("*") if p.is_file()}
    with PolicyEvidence(policies,inputs,coarse,workers=1) as ledger:
        assert ledger.batch(reqs[:2])[0][0]==old_id and not ledger.new_records
        assert ledger._pool is None and not list(ledger.directory.iterdir())
        job,=rolling.rolling_requests(inputs.periods[0],reqs[0].design,reqs[0].caps,inputs.registered)
        (daily,_),=ledger.batch([job])
        assert daily!=old_id and ledger.verify_all()["certificates"]==3
        assert {r["source_round"] for r in ledger.records}=={"R012","R014"}
        sample=ledger.determinism()
        assert [r["id"] for r in sample["comparisons"]]==[daily]
    assert contents=={p.relative_to(coarse):sha(p.read_bytes()) for p in coarse.rglob("*") if p.is_file()}
    relative=next(p for p in contents if str(p).endswith(".json.gz"))
    corrupt=coarse/relative
    corrupt.write_bytes(corrupt.read_bytes()+b"\x00")
    with pytest.raises(ValueError,match="differs from parent|differ from the sealed"):
        with PolicyEvidence(policies,inputs,coarse,verify=True):
            pass


def test_restored_day_certificates_apply_week_width_only_to_timeout(tmp_path):
    from test_m10_rolling import _week
    from um_charging.m10_inputs import PlanningInputs
    from um_charging.site_sizing import Design
    week=_week()
    for day in week.cases:
        # A six-cent native bound on this synthetic bill meets the relative
        # optimality tolerance but exceeds the older time-limit tolerance.
        week.prices[day]=[10_000_000.] * 24
    inputs=PlanningInputs([week],frozenset(week.keys),[],{"synthetic":"rolling-width"})
    design=Design(1,50,0)
    jobs=rolling.rolling_requests(week,design,design.caps,inputs.registered)
    with PolicyEvidence(tmp_path,inputs,None,workers=2) as ledger:
        ids=[label for label,_ in ledger.batch(jobs)]
    def set_native(label,gap,timed_out):
        path=tmp_path/"certificates"/(label+".json.gz")
        body=json.loads(gzip.decompress(path.read_bytes()))["body"]
        stats=body["result"]["stats"]
        upper=stats["objective_upper"]
        lower=upper-gap
        stats.update(status="unresolved" if timed_out else "certified",status_code=int(timed_out),
                     message="Time limit reached" if timed_out else "Optimal", objective_lower=lower,
                     absolute_gap=upper-lower,relative_gap=(upper-lower)/abs(upper),native_mip_dual_bound=lower)
        path.write_bytes(gzip.compress(m10._encoded(dict(body=body,sha256=m10._hash(body))),mtime=0))
    for label in ids:
        set_native(label,.06,False)
    def check_week(expected,status):
        with PolicyEvidence(tmp_path,inputs,None,verify=True) as ledger:
            assert ledger.verify_all()["unresolved_weekly_groups"]==expected
            row=rolling.rolling_week(week,design,design.caps,inputs.registered,ledger.batch(jobs))
            ledger.record_rolling_week(row)
            assert row["status"]==status and len(ledger.unresolved)==expected
    check_week(0,"certified")
    set_native(ids[0],.06,True)
    check_week(1,"unresolved")
    set_native(ids[1],.03,False)
    check_week(0,"bounded")
    set_native(ids[0],.11,True)
    remaining=tmp_path/"certificates"/(ids[1]+".json.gz")
    saved=remaining.read_bytes()
    remaining.unlink()
    with PolicyEvidence(tmp_path,inputs,None,verify=True) as ledger:
        assert ledger.verify_all()["unresolved_weekly_groups"]==0
    remaining.write_bytes(saved)
    check_week(1,"unresolved")
