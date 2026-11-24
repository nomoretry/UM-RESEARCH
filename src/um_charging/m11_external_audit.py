"""Audit the request inventory and repeat a seeded sample in independent processes."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import json
import os
from pathlib import Path
import random

from . import m10_evidence as e, m11_external_inputs as api, m11_external_secondary as secondary
from . import m11_rule_tables as tables, m11_rules as rules, m11_verify
from .m11_external_evidence import proof, replay, work
from .m11_external_seal import put
from .m11_rule_evidence import period_digest


def inventory(folder):
    starts={p.stem for p in (folder/"starts").glob("*.json")}
    ids={p.name.removesuffix(".json.gz") for p in (folder/"certificates").glob("*.json.gz")}
    if starts!=ids:
        raise ValueError("Incomplete started request inventory")
    rows=[]
    for label in sorted(ids):
        body=proof(folder,label)
        spec,raw=body["job"],body["result"]
        req=spec["request"]
        marker=api.read(folder/"starts"/(label+".json"))
        if marker["job"]!=spec:
            raise ValueError("Start record differs from completion")
        stat=raw["stats"]
        rows.append(dict(id=label,week=req["week"],design=req["design"],phase=req["phase"],input=spec["input"],
                         budget_s=spec["seconds"],status=stat["status"],code=stat["status_code"],
                         started=marker["started"],seconds=stat["seconds"],cpu_seconds=stat["cpu_seconds"],
                         pid=stat["worker_pid"],lower=stat["objective_lower"],upper=stat["objective_upper"]))
    return rows


def execute(archive,deadline,verify=False):
    root=archive/"1-5"
    train=api.read(root/"stage2"/"tasks.json")
    test=api.read(root/"stage3"/"tasks.json")
    normal=api.periods(train)
    strict=api.periods(secondary.strict_days(train,api.read(root/"stage1"/"boundary.json")))
    periods={period_digest(p):p for p in normal+api.periods(test)+strict+[rules.scaled(p,1.2) for p in normal]}
    folder=root/"evidence"
    rows=inventory(folder)
    sample=random.Random(20261122).sample([r["id"] for r in rows],20)
    target=root/"repeat"
    if not verify:
        for name in ("starts","certificates"):
            (target/name).mkdir(parents=True,exist_ok=True)
        os.environ.update(e.WORKER_ENV)
        for i in range(0,len(sample),e.WORKERS):
            with ProcessPoolExecutor(max_workers=e.WORKERS,max_tasks_per_child=1) as pool:
                futures=[]
                for label in sample[i:i+e.WORKERS]:
                    spec=proof(folder,label)["job"]
                    if not (target/"certificates"/(label+".json.gz")).is_file():
                        futures.append(pool.submit(work,target,periods[spec["input"]],spec,deadline))
                for f in futures:
                    f.result()
    checks=[]
    for label in sample:
        a,b=proof(folder,label),proof(target,label)
        if a["job"]!=b["job"]:
            raise ValueError("Repeated request changed")
        replay(periods[b["job"]["input"]],b["job"],b["result"])
        m11_verify.compare(a["result"],b["result"])
        checks.append(dict(id=label,pid=b["result"]["stats"]["worker_pid"]))
    if len({r["pid"] for r in checks})!=20 or len(inventory(target))!=20:
        raise ValueError("Expected twenty distinct repeat workers")
    report=dict(seed=20261122,new_requests=len(rows),checks=checks)
    if verify:
        if api.read(root/"determinism.json")!=report or (root/"requests.csv").read_bytes()!=tables.table(rows):
            raise ValueError("Request inventory or repeat summary differs")
    else:
        put(root,"determinism.json",report)
        raw=tables.table(rows)
        if (root/"requests.csv").is_file():
            if (root/"requests.csv").read_bytes()!=raw:
                raise ValueError("Existing request inventory differs")
        else:
            e._publish(root/"requests.csv",raw)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive",required=True,type=Path)
    parser.add_argument("--deadline",required=True,type=datetime.fromisoformat)
    args=parser.parse_args()
    execute(args.archive,args.deadline)
