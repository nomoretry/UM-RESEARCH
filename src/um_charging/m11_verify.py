"""Audit either registered M11 archive without solving; or finalize a new R021 archive."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
import csv
import gzip
import hashlib
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


def sample(folder, excluded=()):
    ids=sorted({p.name.removesuffix(".json.gz") for p in (folder/"certificates").glob("*.json.gz")}-set(excluded))
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


def repeat_one(folder,label,p,deadline,repeats):
    job=read_envelope(folder,label)["job"]
    path=repeats/"certificates"/(label+".json.gz")
    if not path.exists():
        from .m11_rule_evidence import work
        work(repeats,p,job,deadline)
    return label


def audit_repeats(folder,ps,ids,repeats):
    pids=set()
    results=[]
    for label in ids:
        a=read_envelope(folder,label)
        b=read_envelope(repeats,label)
        if json_file(repeats/"starts"/(label+".json"))["job"]!=b["job"]:
            raise ValueError("Repeated start differs")
        pids.add(b["result"]["stats"]["worker_pid"])
        job=a["job"]
        if job!=b["job"]:
            raise ValueError("Repeat input differs")
        p=ps[job["input"]]
        e.replay(priced_period(p,job["mode"]),e.Request.from_json(job["request"]),b["result"])
        compare(a["result"],b["result"])
        results.append(dict(id=label,matched=True,seconds=b["result"]["stats"]["seconds"]))
    if len(pids)!=len(ids):
        raise ValueError("Expected distinct fresh repeat workers")
    return dict(seed=20261122,matched=len(results),checks=results)


def stopped_fine(archive,stop):
    from . import m11_rule_study, m11_sensitivity
    from .m11_rule_evidence import Ledger
    folder=archive/"formal"
    ledger=Ledger(folder,None,verify=True)
    saved=json_file(folder/"fine_checkpoint.json")
    last=[]
    def observe(snapshot):
        last[:]=[snapshot["last_design"]]
        if last[0]==saved["last_design"] and e._encoded(snapshot)!=(folder/"fine_checkpoint.json").read_bytes():
            raise ValueError("Partial fine grid differs")
    try:
        m11_sensitivity.fine(m11_rule_study.Study(archive.parent,ledger),observe)
    except ss.fc.StudyLimit as exc:
        if str(exc)!="Fourth unresolved weekly group":
            raise
    else:
        raise ValueError("Expected the archived fourth-group stop")
    if (stop["stop"]!="fourth_unresolved_weekly_group" or last!=[saved["last_design"]]
        or stop["last_full_design"]!=last[0] or stop["last_full_point_count"]!=len(saved["points"])):
        raise ValueError("Stop boundary differs")
    entries={r["group"]:r for r in stop["unknown"]}
    if len(entries)!=4 or set(entries)!=ledger.unknown or set(entries)!={p.stem for p in (folder/"unresolved").glob("*.json")}:
        raise ValueError("Terminal weekly groups differ")
    for group,r in entries.items():
        label=r["id"]
        body=read_envelope(folder,label)
        job=body["job"]
        req=job["request"]
        s=body["result"]["stats"]
        expected=e._hash([job["input"],req["week"],req["design"],req["caps"],req["fixed"]])
        if (group!=expected or ledger.rows[label]["status"]!="unresolved" or
            json_file(folder/"unresolved"/(group+".json"))!={"group":group,"request":label} or
            any(req[k]!=r[k] for k in ("week","design","caps")) or
            any(s[k]!=r[a] for k,a in (("objective_lower","lower"),("objective_upper","upper"),
                ("absolute_gap","gap"),("status_code","status_code"),("seconds","seconds"),("started_utc","started_utc"))) or
            r["audited"]!=(body["result"]["audit"] is not None)):
            raise ValueError("Terminal week differs: "+label)
    return set(ledger.rows)


def second_round(archive,deadline,verify):
    folder=archive/"formal"
    binding=json_file(archive/"binding.json")
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if binding["method_sha256"]!=digest(archive/"PREREG_M11_R2.md"):
        raise ValueError("Rule or monthly-demand preregistration differs")
    root=archive.parent.resolve()
    for relative,expected in binding["archives"].items():
        path=(root/relative).resolve()
        if not path.is_relative_to(root) or digest(path)!=expected:
            raise ValueError("Historical sizing evidence differs")
    if m10_inputs.load_inputs().source_sha256!=binding["training_sha256"]:
        raise ValueError("Training input hashes differ")
    post={p.relative_to(ss.eb.ROOT).as_posix():digest(p) for p in m10_final_run.SEALED}
    if post!=binding["posthoc_sha256"]:
        raise ValueError("Post hoc input hashes differ")
    used=set()
    stopped=(folder/"stop.json").is_file()
    stop=json_file(folder/"stop.json") if stopped else {}
    if verify:
        for stage in (("rules","sensitivity") if stopped else ("rules","sensitivity","fine")):
            used.update(m11_round2.execute(archive.parent,folder,stage,deadline,True))
        if stopped:
            used.update(stopped_fine(archive,stop))
        if used!={p.stem for p in (folder/"starts").glob("*.json")}:
            raise ValueError("Replayed request set differs from archived starts")
    outputs={**tables.distributions(folder),**tables.inventory(folder)}
    periods,_=rules.cohorts(archive.parent/"20261123_m10_second_holdout"/"formal"/"outcome.json")
    ps={}
    for f in (1,.8,.9,1.1,1.2):
        for p in periods if f in (1,1.2) else periods[:12]:
            q=rules.scaled(p,f)
            ps[period_digest(q)]=q
    if stopped and stop["summary"]!=json.loads(outputs["compute_statistics.json"]):
        raise ValueError("Stop inventory differs")
    ids=sample(folder,[x["id"] for x in stop.get("unknown",[])])
    repeats=archive/"continuation"/"repeat" if stopped else folder/"repeat"
    if not verify:
        for sub in ("certificates","starts"):
            (repeats/sub).mkdir(exist_ok=True,parents=True)
        os.environ.update(e.WORKER_ENV)
        with ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1) as pool:
            for start in range(0,len(ids),4):
                if (deadline-datetime.now(timezone.utc)).total_seconds()<=320:
                    raise ss.fc.StudyLimit("Another repeat batch no longer fits")
                jobs=[pool.submit(repeat_one,folder,i,ps[read_envelope(folder,i)["job"]["input"]],deadline,repeats)
                      for i in ids[start:start+4]]
                for j in jobs:
                    j.result()
    repeat_count=0
    if not stopped or not verify or repeats.exists():
        replay=e._encoded(audit_repeats(folder,ps,ids,repeats))
        repeat_count=len(ids)
        if stopped:
            report=repeats/"determinism.json"
            if verify or report.exists():
                if report.read_bytes()!=replay:
                    raise ValueError("Stopped repeat table differs")
            else:
                e._publish(report,replay)
        else:
            outputs["determinism.json"]=replay
    for name,value in outputs.items():
        path=folder/name
        if verify or path.exists():
            if path.read_bytes()!=value:
                raise ValueError("R021 table changed: "+name)
        else:
            e._publish(path,value)
    robustness={}
    if verify and (archive/"continuation"/"fine").is_dir():
        from . import m11_robustness
        robustness["robustness"]=m11_robustness.verify(archive)
    if verify and stopped:
        audit_other_bounds(archive)
    return dict(**robustness,status="verified" if verify else "finalized",round=2,requests=len(used) if verify else
                json.loads(outputs["compute_statistics.json"])["unique_requests"],tables=len(outputs),
                terminal_groups=len(stop.get("unknown",[])),repeats=repeat_count,
                new_solves=0 if verify else "see repeat/starts")


def audit_other_bounds(archive):
    from . import m10_costs, m11_robustness, m11_rule_study as study
    from itertools import product
    coarse=archive.parent/"20261122_m10_selection_coarse2"/"formal"
    refine=archive.parent/"20261122_m10_refine"/"formal"
    def key(r):
        return r["design"],int(r["port_cap_kw"]),int(r["warehouse_cap_kw"])
    coarse_keys={key(r) for r in study.csv_rows(coarse/"annual_costs.csv")}
    screens={key(r):r["reason"] for r in study.csv_rows(refine/"screen_points.csv")}
    fees={(*key(r),r["scenario"],r["connection_basis"]):r for r in study.csv_rows(refine/"screen_tariffs.csv")}
    cases=[(r["scenario"],r["connection_basis"]) for r in json_file(coarse/"selection.json")["winners"]
           if r["scenario"]!="official"]
    designs=m11_robustness.hardware(m10_costs._parameters(m10_inputs.load_inputs().periods)[1])
    expected={(d.label,p,w,*c) for d in designs
              for p,w in product(range(0,d.port_kw+1,5),range(0,d.warehouse_kw+1,5))
              if (d.label,p,w) not in coarse_keys for c in cases}
    for row in study.csv_rows(archive/"formal"/"other_tariff_bounds.csv"):
        k=key(row)
        scope=(*k,row["scenario"],row["basis"])
        expected.remove(scope)
        fee=fees.get(scope,{})
        low=fee.get("annual_lower_eur_2025","")
        upper=fee.get("incumbent_upper_eur_2025","")
        if not fee:
            reason="no_R013_row"
        elif screens[k] in ("infeasible_superset","weekly_window_capacity","infeasible_network_relaxation"):
            reason="physical_bound"
        else:
            reason="annual_lower_bound" if low and float(low)>float(upper)+1e-6 else "not_excluded"
        if (row["annual_lower"],row["incumbent_upper"],row["reason"])!=(low,upper,reason):
            raise ValueError("Historical tariff bound differs: "+str(scope))
    if expected:
        raise ValueError("Incomplete other-tariff coverage")


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
            if (args.verify/"PREREG_M11_R5.md").is_file():
                from . import m11_external_run
                result=m11_external_run.verify(args.verify/"rehearsal")
            elif (args.verify/"PREREG_M11_R4.md").is_file():
                from . import m11_external_run
                result=m11_external_run.verify(args.verify)
            elif (args.verify/"PREREG_M11_R3.md").is_file():
                from . import m10_breakpoint, m11_round3
                stack.enter_context(patch.object(m10_breakpoint,"_solve",deny))
                result=m11_round3.execute(args.verify,verify=True)
            elif (args.verify/"PREREG_M11_R2.md").is_file():
                result=second_round(args.verify,None,True)
            elif (args.verify/"PREREG_M11_R1.md").is_file():
                result=first_round(args.verify)
            else:
                raise ValueError("Missing M11 preregistration")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
