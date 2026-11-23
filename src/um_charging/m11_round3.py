"""Execute or replay the preregistered M11 supplemental analyses."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess

from . import m10_evidence as e, m11_leftovers as study, m11_rule_tables as tables
from . import m11_verify, site_sizing as ss
from .m11_leftover_evidence import Evidence, now, replay, run_one
from .m11_rule_evidence import json_file, read_envelope


def publish(path,data,verify=False):
    if path.exists() or verify:
        if path.read_bytes()!=data:
            raise ValueError("Archived output differs: "+path.name)
    else:
        e._publish(path,data)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bindings(archive,s):
    files=[s.old/"service_summary.json",s.old/"annual_costs.csv",s.old/"selection.json",
           *sorted((s.old/"operating_batches").glob("*.csv")),
           s.bp/"summary.json",s.bp/"weekly_points.csv",s.bp/"annual_bills.csv"]
    return dict(training=s.main.source_sha256,prereg_sha256=digest(archive/"PREREG_M11_R3.md"),
                archives={p.relative_to(archive.parent).as_posix():digest(p) for p in files},
                price_factor_file=digest(ss.eb.WEEKS.with_name("site_sizing.json")),
                network=digest(ss.NETWORK_INPUT),connection=digest(ss.CONNECTION_INPUT),equipment=digest(ss.COST_INPUT))


def exports(name,result):
    outputs={name+".json":e._encoded(result)}
    for key in ("fees","ranks","upgrade","other_gaps","thresholds"):
        if result.get(key):
            outputs[name+"_"+key+".csv"]=tables.table(result[key])
    weeks=[]
    components=[]
    for p in result["points"]:
        base=dict(design=p["design"],caps=p["caps"],point_status=p["status"],period_weeks=len(p["weeks"]))
        weeks.extend({**base,**r} for r in p["weeks"])
        components.extend({**base,**r} for r in p["bills"])
    if weeks:
        outputs[name+"_weeks.csv"]=tables.table(weeks)
    if components:
        outputs[name+"_bills.csv"]=tables.table(components)
    if "registered" in result and isinstance(result["registered"],list):
        diff=[dict(date=d,vehicle=v,change=k) for k in ("added","removed") for d,v in result[k]]
        outputs[name+"_registration_changes.csv"]=tables.table(diff,["date","vehicle","change"])
    return outputs


def inventory(folder,used):
    starts={p.stem for p in (folder/"starts").glob("*.json")}
    certs={p.name.removesuffix(".json.gz") for p in (folder/"certificates").glob("*.json.gz")}
    if starts!=certs or used!=starts:
        raise ValueError("Weekly starts, certificates and reconstructed requests differ")
    journal=[]
    for label in sorted(starts):
        body=read_envelope(folder,label)
        job=body["job"]
        req=job["request"]
        start=json_file(folder/"starts"/(label+".json"))
        raw=body["result"]
        stat=raw["stats"]
        if start["job"]!=job:
            raise ValueError("Archived start differs from its certificate")
        status=stat["status"]
        if (job["mode"]=="energy" and status=="unresolved" and stat["status_code"]==1 and raw["audit"] is not None
                and "time limit" in stat["message"].lower() and stat["absolute_gap"] is not None
                and 0<=stat["absolute_gap"]<=e.CONTINUATION_TIMEOUT_GAP_EUR):
            status="bounded"
        journal.append(dict(id=label,mode=job["mode"],input_sha256=job["input"],request=req,
                            week=req["week"],status=status,worker_pid=stat["worker_pid"],native_status=stat["status"],
                            code=stat["status_code"],lower=stat["objective_lower"],upper=stat["objective_upper"],
                            gap=stat["absolute_gap"],started_utc=start["started_utc"],native_utc=stat["started_utc"],
                            seconds=stat["seconds"],cpu_seconds=stat["cpu_seconds"]))
    return journal


def repeats(folder,journal,ledger,deadline,verify):
    eligible=sorted(r["id"] for r in journal if r["status"]!="unresolved")
    ids=random.Random(20261122).sample(eligible,20)
    target=folder/"repeat"
    if not verify:
        for sub in ("certificates","starts"):
            (target/sub).mkdir(parents=True,exist_ok=True)
        # A separate pool for each batch guarantees one task per child.
        for i in range(0,len(ids),4):
            with ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1) as pool:
                work=[]
                for label in ids[i:i+4]:
                    if (target/"certificates"/(label+".json.gz")).is_file():
                        continue
                    if (target/"starts"/(label+".json")).exists():
                        raise ValueError("Incomplete deterministic replay")
                    job=read_envelope(folder,label)["job"]
                    work.append(pool.submit(run_one,target,ledger.periods[job["input"]],job,deadline))
                for future in work:
                    future.result()
    checked=[]
    for label in ids:
        a,b=[read_envelope(f,label) for f in (folder,target)]
        if a["job"]!=b["job"]:
            raise ValueError("Repeated request changed")
        replay(ledger.periods[b["job"]["input"]],b["job"],b["result"],label)
        m11_verify.compare(a["result"],b["result"])
        checked.append(dict(id=label,pid=b["result"]["stats"]["worker_pid"],match=True))
    repeated=inventory(target,set(ids))
    if len({r["pid"] for r in checked})!=len(ids):
        raise ValueError("Not all repeated requests used independent processes")
    publish(target/"solves.csv",tables.table(repeated),verify)
    report=dict(seed=20261122,eligible=len(eligible),matches=len(checked),checks=checked)
    publish(folder/"determinism.json",e._encoded(report),verify)
    return report


def execute(archive,deadline=None,verify=False):
    folder=archive/"formal"
    ledger=Evidence(archive,None if verify else deadline-timedelta(minutes=30),verify)
    total_points=0
    try:
        s=study.Study(archive,ledger)
        publish(folder/"binding.json",e._encoded(bindings(archive,s)),verify)
        prices=None
        skipped=[]
        optional=folder/"optional.json"
        plan=json_file(optional)["skipped"] if optional.is_file() else []
        for name in ("penalty","breakpoint","scale_1.1","scale_1.2","scale_0.9","scale_0.8","prices","posthoc"):
            if name in ("scale_0.9","scale_0.8"):
                if name in plan or (not verify and not optional.exists() and
                   not (folder/(name+".json")).exists() and (deadline-now()).total_seconds()<65*60):
                    skipped.append(name)
                    continue
            if name=="penalty":
                result=study.penalty(s)
            elif name=="breakpoint":
                result=study.breakpoint(s)
            elif name.startswith("scale_"):
                result=study.scaled(s,float(name.split("_")[1]))
            elif name=="prices":
                publish(optional,e._encoded(dict(skipped=skipped)),verify)
                result=prices=study.prices(s)
            else:
                result=study.posthoc(s,prices)
            for fn,data in exports(name,result).items():
                publish(folder/fn,data,verify)
            total_points+=len(result["points"])
            print(name,len(result["points"]),"points",len(ledger.used),"native requests",flush=True)
            if not verify:
                with (archive/"PROGRESS.md").open("a",encoding="utf-8") as stream:
                    stream.write(f"- {now().astimezone().isoformat()} {name} 完成，{len(result['points'])} 个点，累计 {len(ledger.used)} 个新增原生请求。\n")
    finally:
        ledger.close()
    journal=inventory(folder,ledger.used)
    unknown=[r for r in journal if r["status"]=="unresolved"]
    stats=dict(requests=len(journal),status=dict(Counter(r["status"] for r in journal)),
               seconds=math.fsum(r["seconds"] for r in journal),cpu_seconds=math.fsum(r["cpu_seconds"] for r in journal),
               first_start=min(r["started_utc"] for r in journal),points=total_points,skipped=skipped)
    publish(folder/"solves.csv",tables.table(journal),verify)
    publish(folder/"unresolved.csv",tables.table(unknown,list(journal[0])),verify)
    publish(folder/"compute_statistics.json",e._encoded(stats),verify)
    checks=repeats(folder,journal,ledger,deadline,verify)
    return dict(status="verified" if verify else "complete",round=3,**stats,repeats=checks["matches"],
                new_solves=0 if verify else len(journal)+checks["matches"])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",required=True,type=Path)
    p.add_argument("--deadline",required=True,type=datetime.fromisoformat)
    p.add_argument("--source",required=True)
    args=p.parse_args()
    def git(*args):
        return subprocess.check_output(["git","-C",str(ss.eb.ROOT),*args],text=True).strip()
    if git("rev-parse","HEAD")!=args.source or git("status","--porcelain"):
        raise ValueError("New calculations require the recorded clean execution commit")
    if args.deadline.tzinfo is None:
        raise ValueError("A timezone-aware round deadline is required")
    print(json.dumps(execute(args.archive,args.deadline),sort_keys=True))


if __name__=="__main__":
    main()
