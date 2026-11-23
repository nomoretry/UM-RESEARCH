"""Audit either registered M11 archive without solving; or finalize a new R021 archive."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
import csv
import gzip
import json
import math
import os
from pathlib import Path
import random
import shutil
import tempfile
from unittest.mock import patch

from . import m10_evidence as e, m10_final_run, m10_inputs, m11_boundary, m11_mechanism, m11_results
from . import m11_round2, m11_rule_tables as tables, m11_rules as rules, m11_run, site_sizing as ss
from .m11_rule_evidence import calculate, compact, json_file, period_digest, priced_period, read_envelope


def compare(a,b):
    if (a["stats"]["status"],a["stats"]["status_code"])!=(b["stats"]["status"],b["stats"]["status_code"]):
        raise ValueError("Repeated solver status differs")
    for k in ("objective","objective_lower","objective_upper"):
        x,y=a["stats"][k],b["stats"][k]
        if x!=y and (x is None or y is None or not math.isclose(x,y,abs_tol=ss.EPS,rel_tol=0.)):
            raise ValueError("Repeated objective bounds differ")
    e._assert_close(a["audit"],b["audit"])
    if e._schedule_digest(a)!=e._schedule_digest(b):
        raise ValueError("Repeated schedule differs")


def sample(folder):
    ids=sorted(p.name.removesuffix(".json.gz") for p in (folder/"certificates").glob("*.json.gz"))
    return random.Random(20261122).sample(ids,20)


def same_csv(path,rows):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))==[{k:"" if v is None else str(v) for k,v in r.items()} for r in rows]


def first_round(archive):
    folder=archive/"formal"
    outcome=archive.parent/"20261123_m10_second_holdout"/"formal"/"outcome.json"
    frozen=json_file(outcome)
    first=m10_inputs.load_inputs()
    extra=m10_final_run._sealed_periods()[0]
    ref=set(map(tuple,frozen["reference"]))
    for label,ps,keys in (("training",first.periods,first.main_reference),("posthoc",extra,ref)):
        if not same_csv(archive/(label+"_census.csv"),m11_mechanism.census(ps,keys)):
            raise ValueError("R020 census changed")
    if json_file(archive/"posthoc_s1_bound.json")!=m11_mechanism.rolling_terminal_bound(next(iter(m10_final_run.SEALED)),ref):
        raise ValueError("R020 S1 bound changed")
    with tempfile.TemporaryDirectory() as temp:
        dest=Path(temp)/"formal"
        shutil.copytree(folder,dest)
        result=m11_results.report(dest,outcome,None,False)
        for name in ("solves.csv","segments.csv","service_grid.csv","official_bills.csv","results.json"):
            if (dest/name).read_bytes()!=(folder/name).read_bytes():
                raise ValueError("R020 table differs: "+name)
    periods={rules.week(p):p for p in [*first.periods,*extra]}
    index=json_file(folder/"request_index.json")
    sampled=sample(folder)
    archived=json_file(folder/"determinism.json")
    if [r["id"] for r in archived["checks"]]!=sampled:
        raise ValueError("R020 deterministic sample differs")
    for label in sampled:
        req=index[label]
        old=m11_run.certificate(folder,req)
        repeated=m11_run.certificate(folder/"repeat",req)
        compare(old,repeated)
        if repeated["audit"] is not None:
            e._assert_close(m11_boundary.replay(periods[req["week"]],req,repeated),repeated["audit"])
    return dict(status="verified",round=1,requests=result["native_requests"],
                feasible_replayed=result["feasible_replayed"],repeats=len(sampled),new_solves=0)


def repeat_one(folder,label,p,deadline):
    job=read_envelope(folder,label)["job"]
    repeats=folder/"repeat"
    path=repeats/"certificates"/(label+".json.gz")
    if not path.exists():
        from .m11_rule_evidence import work
        work(repeats,p,job,deadline)
    return label


def audit_repeats(folder,ps,ids):
    results=[]
    for label in ids:
        a=read_envelope(folder,label)
        b=read_envelope(folder/"repeat",label)
        job=a["job"]
        if job!=b["job"]:
            raise ValueError("Repeat input differs")
        p=ps[job["input"]]
        e.replay(priced_period(p,job["mode"]),e.Request.from_json(job["request"]),b["result"])
        compare(a["result"],b["result"])
        results.append(dict(id=label,matched=True,seconds=b["result"]["stats"]["seconds"]))
    return dict(seed=20261122,matched=len(results),checks=results)


def second_round(archive,deadline,verify):
    folder=archive/"formal"
    used=set()
    if verify:
        for stage in ("rules","sensitivity","fine"):
            used.update(m11_round2.execute(archive.parent,folder,stage,deadline,True))
        if used!={p.stem for p in (folder/"starts").glob("*.json")}:
            raise ValueError("Replayed request set differs from archived starts")
    outputs={**tables.distributions(folder),**tables.inventory(folder)}
    periods,_=rules.cohorts(archive.parent/"20261123_m10_second_holdout"/"formal"/"outcome.json")
    ps={}
    for f in (1,.8,.9,1.1,1.2):
        for p in periods if f in (1,1.2) else periods[:12]:
            q=rules.scaled(p,f)
            ps[period_digest(q)]=q
    ids=sample(folder)
    if not verify:
        for sub in ("certificates","starts"):
            (folder/"repeat"/sub).mkdir(exist_ok=True,parents=True)
        os.environ.update(e.WORKER_ENV)
        with ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1) as pool:
            for start in range(0,len(ids),4):
                if (deadline-datetime.now(timezone.utc)).total_seconds()<=320:
                    raise ss.fc.StudyLimit("Another repeat batch no longer fits")
                jobs=[pool.submit(repeat_one,folder,i,ps[read_envelope(folder,i)["job"]["input"]],deadline)
                      for i in ids[start:start+4]]
                for j in jobs:
                    j.result()
    outputs["determinism.json"]=e._encoded(audit_repeats(folder,ps,ids))
    for name,value in outputs.items():
        path=folder/name
        if verify or path.exists():
            if path.read_bytes()!=value:
                raise ValueError("R021 table changed: "+name)
        else:
            e._publish(path,value)
    return dict(status="verified" if verify else "finalized",round=2,requests=len(used) if verify else
                json.loads(outputs["compute_statistics.json"])["unique_requests"],tables=len(outputs),
                repeats=len(ids),new_solves=0 if verify else "see repeat/starts")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--verify",type=Path)
    action.add_argument("--finalize",type=Path)
    parser.add_argument("--deadline",type=datetime.fromisoformat)
    args=parser.parse_args()
    if args.finalize:
        if args.deadline is None or args.deadline.tzinfo is None:
            parser.error("--finalize requires a timezone-aware original deadline")
        result=second_round(args.finalize,args.deadline,False)
    else:
        def deny(*a,**kw):
            raise RuntimeError("Optimization prohibited in M11 replay")
        with ExitStack() as stack:
            for module,name in ((e,"_solve"),(e,"milp"),(ss,"milp"),(ss,"solve"),(m11_boundary,"solve")):
                stack.enter_context(patch.object(module,name,deny))
            if (args.verify/"PREREG_M11_R2.md").is_file():
                result=second_round(args.verify,None,True)
            elif (args.verify/"PREREG_M11_R1.md").is_file():
                result=first_round(args.verify)
            else:
                raise ValueError("Missing M11 preregistration")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
