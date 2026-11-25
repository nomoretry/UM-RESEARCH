import csv
import json
from pathlib import Path
import subprocess

import pytest

from um_charging import m11_external_inputs as inputs, m11_external_seal as seals


prep = inputs.preparation()
HEADER = ("vehicle_id", "track_id", "freight_forwarder", "start_time", "stop_time",
          "home_base", "industrial_area", "energy_consumption_kwh")


def write_fixture(path):
    def row(vehicle, track, day, energy):
        return [vehicle, track, "1", day+"T10:00:00+01:00", day+"T10:20:00+01:00",
                "True", "False", energy]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADER)
        writer.writerows([row("101", i, day, energy) for i, (day,energy) in enumerate((
            ("2021-09-25","private-pre"),("2021-09-28","1.75"),("2021-12-17","2.25"),
            ("2021-12-21","private-later"),("2022-01-19","7"),("2022-02-08","private-after")),1)])
        writer.writerow(["999", "99", "2"] + ["INVALID"]*5)


def test_sealed_before_source_access(tmp_path):
    with pytest.raises(PermissionError):
        prep.index_source(tmp_path/"absent.csv", "6-10")
    assert prep.rank_slice([str(i) for i in reversed(range(22,44))], "6-10") == set(map(str,range(27,32)))
    assert prep.rank_slice(map(str,range(100,118)), "16+") == {"115","116","117"}


def test_projection_and_boundary_invariance(tmp_path, monkeypatch):
    path = tmp_path/"synthetic.csv"
    write_fixture(path)
    counts, bounds, sections = prep.project(path,"1",{"101"})
    assert len(counts) == 19 and sum(w["complete"] for w in counts) == 4
    pre = bounds["before_selection"]["101"]
    assert set(pre) == {"track_id","arrival","home_base","industrial_area"}
    assert all(set(bounds[key]["101"]) == {"track_id","departure"}
               for key in ("after_selection", "after_evaluation"))
    assert not any(token in json.dumps([bounds, counts, sections]) for token in ("private-", "1.75", "2.25"))
    section = sections["selection"]
    reads = []
    original = Path.open
    class Ranges:
        def __init__(self): self.stream = original(path, "rb")
        def __enter__(self): return self
        def __exit__(self, *exc): self.stream.close()
        def seek(self, offset): self.stream.seek(offset)
        def read(self, length):
            reads.append((self.stream.tell(), length))
            return self.stream.read(length)
    monkeypatch.setattr(Path, "open", lambda self,*args,**kw: Ranges())
    records = prep.read_period(path, section, {"101"}, *prep.BOUNDS["selection"])
    assert reads == [(a,b) for a,b,_ in section["records"]]
    result = prep.period_days(records, "selection", section, bounds)
    clipped = prep.period_days(records, "selection", section, bounds, truncate=True)
    strict = prep.period_days(records, "selection", section, bounds, strict=True)
    assert prep.effective_windows(result) == prep.effective_windows(clipped)
    assert len(prep.effective_windows(result)) == len(prep.effective_windows(strict)) + 2
    assert [t.energy for t in records["101"]] == [1.75,2.25]
    assert prep.period_days(records, "selection", section, {}) == strict


def test_tamper_rejected_by_stage_seal(tmp_path):
    subprocess.run(["git","init","-q",str(tmp_path)],check=True)
    seals.put(tmp_path,"counts.json",{"complete":3})
    seals.seal(tmp_path,"1-5",1,["counts.json"],None)
    def commit(*args):
        subprocess.run(["git","-C",str(tmp_path),"-c","user.name=Test","-c","user.email=test@example.invalid",
                        *args],check=True)
    commit("add",".")
    commit("commit","-qm","synthetic seal")
    assert seals.check(tmp_path,"1-5",1)
    (tmp_path/"counts.json").write_text("{}",encoding="utf-8")
    with pytest.raises(ValueError,match="differs"):
        seals.check(tmp_path,"1-5",1)


def test_service_endpoint_and_registration_gates():
    from um_charging import m11_external_study as study
    win={"week":{"physical":True,"status":"certified"}}
    fail={"week":{"physical":False,"status":"infeasible"}}
    unknown={"week":{"physical":False,"status":"unresolved"}}
    rows=dict(a=win,b=fail,c=unknown)
    assert study.verdict(["a"],rows)=="守住"
    assert study.verdict(["b"],rows)=="未守住"
    for members in (["a","b"],["a","c"],["c"],[]):
        assert study.verdict(members,rows)=="未定"
    assert study.gate({"week":[["day","v"]]},1)=="passed"
    assert study.gate({"week":[]},1)=="not_evaluable"
    assert study.gate({"week":None},1)=="unresolved"


def test_evaluation_projection_never_decodes_training_or_post_period_energy(tmp_path):
    source=tmp_path/"synthetic.csv"
    write_fixture(source)
    text=source.read_text(encoding="utf-8").replace("1.75","private-train").replace("2.25","private-train")
    source.write_text(text.replace("private-later","3.75"),encoding="utf-8",newline="")
    counts,boundaries,sections=prep.project(source,"1",{"101"})
    assert sum(w["complete"] for w in counts)==4
    records=prep.read_period(source,sections["evaluation"],{"101"},*prep.BOUNDS["evaluation"])
    assert [t.energy for t in records["101"]]==[3.75,7.]
    preceding={"101":{"track_id":"3","arrival":"2021-12-17T10:20:00+01:00",
                      "home_base":True,"industrial_area":False}}
    args=(records,"evaluation",sections["evaluation"],boundaries)
    days=prep.period_days(*args,preceding=preceding)
    clipped=prep.period_days(*args,preceding=preceding,truncate=True)
    assert prep.effective_windows(days)==prep.effective_windows(clipped)


def test_opening_requires_exact_committed_synthetic_registration(tmp_path,monkeypatch):
    reg=tmp_path/"PREREG_M11_EXTERNAL.md"
    reg.write_bytes(b"synthetic preregistration\n")
    with pytest.raises(PermissionError):
        seals.authorize("6-10",reg)
    monkeypatch.setattr(seals,"FROZEN_SHA256",seals.digest(reg.read_bytes()))
    subprocess.run(["git","init","-q",str(tmp_path)],check=True)
    with pytest.raises(subprocess.CalledProcessError):
        seals.authorize("6-10",reg)
    subprocess.run(["git","-C",str(tmp_path),"add","--",reg.name],check=True)
    subprocess.run(["git","-C",str(tmp_path),"-c","user.name=Test","-c","user.email=test@example.invalid",
                    "commit","-qm","synthetic registration"],check=True)
    with pytest.raises(PermissionError,match="authorization"):
        seals.authorize("6-10",reg)
    # Model the committed external authorization in memory; no authorization file is created.
    auth=tmp_path/"OPENING_AUTHORIZATION.md"
    committed=seals.committed
    read=Path.read_text
    monkeypatch.setattr(seals,"committed",lambda path: tmp_path.resolve() if path==auth else committed(path))
    monkeypatch.setattr(Path,"read_text",lambda path,**kw: seals.FROZEN_SHA256 if path==auth else read(path,**kw))
    seals.authorize("6-10",reg,auth)
    reg.write_bytes(b"changed")
    with pytest.raises(PermissionError):
        seals.authorize("6-10",reg)


def test_mechanism_compares_against_every_training_segment():
    from um_charging.m11_external_mechanism import compare
    rows = [dict(week="train",sites=["WAREHOUSE"],required={"PORT":0,"WAREHOUSE":10}),
            dict(week="train",sites=["PORT","WAREHOUSE"],required={"PORT":10,"WAREHOUSE":40}),
            dict(week="test",sites=["WAREHOUSE"],required={"PORT":None,"WAREHOUSE":30})]
    outcome=compare(rows,{"train"},{"test"})
    assert outcome["training_segments"]==2
    assert outcome["training_max_kw"]["WAREHOUSE"]==40
    assert outcome["new_proven"]==0 and outcome["unknown"]==0
    rows[1]["required"]["WAREHOUSE"]=None
    assert compare(rows,{"train"},{"test"})["unknown"]==1


def test_constructed_members_never_substitute_registration_for_service():
    from um_charging import m11_external_study as study
    base="p1-50-w50"
    weekly={i:dict(status="certified",physical=True) for i in range(7)}
    result=dict(verdict="守住",choices=[base],service={base:weekly})
    assert study.annotate(dict(result))["标注"]=="按构造，无信息"
    weekly[6]=dict(status="unresolved",physical=False)
    result["verdict"]=study.verdict([base],result["service"])
    marked=study.annotate(result)
    assert marked["verdict"]=="未定" and marked["未定原因"]=="计算未判出"
    assert marked["按构造"]==[base] and "标注" not in marked


def test_revised_mechanism_and_joint_only_week(monkeypatch):
    from um_charging import m11_external_mechanism as mechanism
    from um_charging import site_sizing as ss
    seen=[]
    def reachable(truck,spec,*,site_power_kw):
        seen.append(site_power_kw.copy())
        return site_power_kw["WAREHOUSE"]>=20 and site_power_kw["PORT"]>=10,{}
    monkeypatch.setattr(mechanism.service_gap,"reachable",reachable)
    result=mechanism.thresholds({},ss.LARGEST)
    assert result=={"PORT":20,"WAREHOUSE":20}
    assert all(r["PORT"]==100 or r["WAREHOUSE"]==50 for r in seen)
    failed=[dict(days=[i],required=result,higher_by_station={},new_requirement=v)
            for i,v in enumerate((True,False,None))]
    assert [r["prediction_two"] for r in mechanism.per_segment("design","week",failed)]==["命中","未命中","未识别"]
    assert mechanism.per_segment("design","week",[])[0]["prediction_two"]=="不适用"


def test_interrupted_request_single_extension_and_replay(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from um_charging import m11_external_evidence as ev, m11_external_study as study
    from um_charging import m11_external_audit as audit
    period=SimpleNamespace(days=[{"week_start":"week"}])
    monkeypatch.setattr(study.rules,"week",lambda period:"week")
    def job(period,design,phase,seconds=300,**kw):
        return dict(input="test",seconds=seconds,request=dict(week="week",phase=phase,design={}))
    monkeypatch.setattr(study,"job",job)
    ledger=ev.Ledger(tmp_path,None,verify=True)
    (tmp_path/"starts").mkdir()
    label="p1-50-w50"
    for seconds in (300,1800):
        spec=job(period,None,"fixed_service",seconds)
        seals.put(tmp_path/"starts",ev.e._hash(spec)+".json",dict(job=spec,started="synthetic"))
    rows=study.matrix([period],{"week":[["day","v"]]},[label],ledger,"fixed_service")
    for _ in range(2):
        study.retry([period],{"week":[["day","v"]]},rows,[label],"fixed_service",ledger)
    assert len(ledger.used)==2 and len(audit.inventory(tmp_path))==2
    assert rows[label]["week"]["reason"]=="interrupted"
    assert study.verdict([label],rows)=="未定"


@pytest.mark.parametrize("selection_gate,complete,expected",[
    ("passed",False,"不可评"),("not_evaluable",True,"不可评"),("unresolved",True,"未定")])
def test_synthetic_stage_gates(tmp_path,monkeypatch,selection_gate,complete,expected):
    from um_charging import m11_external_run as run
    from um_charging import m11_external_study as study
    root=tmp_path/"mock"
    (root/"stage2").mkdir(parents=True)
    if complete:
        ref={"w":None if selection_gate=="unresolved" else []}
        monkeypatch.setattr(study,"register",lambda *a,**kw:(ref,[]))
    selection=run.main_results(root,2,[] if complete else None,None,revised=True)
    seals.put(root/"stage2","selection.json",selection)
    primary=run.main_results(root,3,None,None,revised=True)
    assert primary["verdict"]==expected
    (root/"stage3").mkdir()
    seals.put(root/"stage3","primary.json",primary)
    assert run.main_results(root,4,None,None,revised=True)["verdict"]==expected


def test_synthetic_ranks_and_sealed_membership(tmp_path,monkeypatch):
    source=tmp_path/"synthetic.csv"
    write_fixture(source)
    raw=source.read_text(encoding="utf-8")
    originals=["20","21","22","23","24"]
    # Extra synthetic carrier rows put the fixture's vehicle in the second rank interval.
    line=raw.splitlines()[1]
    with source.open("a",encoding="utf-8",newline="") as stream:
        for v in reversed(originals):
            stream.write(line.replace("101,",v+",",1)+"\n")
    seals.put(tmp_path,"duties.json",dict(coverage=dict(freight_forwarder=1,cohort_vehicle_ids=originals)))
    monkeypatch.setattr(prep,"HERE",tmp_path)
    assert prep.identities(source,"6-10")[1]=={"101"}
    assert prep.identities(source,"1-5")[1]==set(originals)
    _,_,sections=prep.project(source,"1",{"101"})
    with pytest.raises(ValueError,match="outside"):
        prep.read_period(source,sections["selection"],set(originals),*prep.BOUNDS["selection"])
    (tmp_path/"duties.json").write_text('{"coverage":{"freight_forwarder":1,"cohort_vehicle_ids":[]}}')
    with pytest.raises(ValueError,match="self-check failed"):
        prep.identities(source,"1-5")


def test_margin_ambiguity_continues(monkeypatch):
    from um_charging import m11_external_secondary as sec
    monkeypatch.setattr(sec.rules,"scaled",lambda p,f:p)
    monkeypatch.setattr(sec.rules,"week",lambda p:"w")
    monkeypatch.setattr(sec.rules,"feasible_subsets",lambda *a:{"v":[[("a","v")],[("b","v")]]})
    monkeypatch.setattr(sec,"matrix",lambda *a,**kw:{sec.ss.LARGEST.label:{"w":{"physical":True}}})
    design,reason=sec.margin_rule([object()],{"w":[["a","v"],["b","v"]]},None)
    assert design is None and reason["status"]=="不适用（歧义）" and reason["reason"]=="nonunique"


def test_external_stages_on_synthetic_insufficient_cohort(tmp_path,monkeypatch):
    from datetime import datetime, timedelta, timezone
    from um_charging import m11_external_run as run
    source=tmp_path/"synthetic.csv"
    write_fixture(source)
    raw=source.read_text(encoding="utf-8").splitlines()
    originals=["20","21","22","23","24"]
    with source.open("a",encoding="utf-8",newline="") as stream:
        for vehicle in reversed(originals):
            stream.write(raw[1].replace("101,",vehicle+",",1)+"\n")
    seals.put(tmp_path,"duties.json",dict(coverage=dict(freight_forwarder=1,cohort_vehicle_ids=originals)))
    monkeypatch.setattr(prep,"HERE",tmp_path)
    monkeypatch.setattr(prep,"SHA256",seals.digest(source.read_bytes()))
    # Gates are tested independently. This fixture has no external data or opening authorization.
    for module in (prep,inputs,run):
        monkeypatch.setattr(module,"authorize",lambda *a:None)
    monkeypatch.setattr(run,"prerequisite",lambda *a:None)
    monkeypatch.setattr(run,"git",lambda path,*args:b"" if args[0]=="status" else b"synthetic")
    archive=tmp_path/"stages"
    subprocess.run(["git","init","-q",str(archive)],check=True)
    cohort="6-10"
    for stage in range(1,5):
        run.execute(archive,cohort,stage,source,None,datetime.now(timezone.utc)+timedelta(hours=1))
        subprocess.run(["git","-C",str(archive),"add","."],check=True)
        subprocess.run(["git","-C",str(archive),"-c","user.name=Test","-c","user.email=test@example.invalid",
                        "commit","-qm","synthetic stage"],check=True)
    root=archive/cohort
    assert inputs.read(root/"stage1"/"roster.json")==["101"]
    assert inputs.read(root/"stage3"/"primary.json")["verdict"]=="不可评"
    assert run.verify(archive,cohort)["replayed"]==[0,0,0]


def test_evaluation_registration_gate(monkeypatch):
    from um_charging import m11_external_study as study
    for reference,expected in (({"w":[],"v":[]}, "不可评"),({"w":[],"v":None},"未定")):
        monkeypatch.setattr(study,"register",lambda *a,**kw:(reference,[]))
        assert study.evaluate([],{},None)["verdict"]==expected
