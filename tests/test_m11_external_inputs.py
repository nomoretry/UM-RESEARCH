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
