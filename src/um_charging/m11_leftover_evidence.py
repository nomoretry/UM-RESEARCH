"""Content-addressed energy and registration requests for the remaining M11 analyses."""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import json
import os
from time import monotonic

from . import m10_breakpoint as bp, m10_evidence as e, site_sizing as ss
from .m11_rule_evidence import compact, period_digest, read_envelope, work


def now():
    return datetime.now(timezone.utc)


def energy_job(p,design,caps,fixed):
    req=e.Request.make(p,design,"energy",caps,fixed=fixed)
    return json.loads(e._encoded(dict(input=period_digest(p),mode="energy",request=asdict(req))))


def registration_job(p,req):
    return dict(input=period_digest(p),mode="registration",request=req)


def replay(p,job,raw,label):
    if period_digest(p)!=job["input"]:
        raise ValueError("Certificate input does not match the weekly model")
    if job["mode"]=="energy":
        e.replay(p,e.Request.from_json(job["request"]),raw)
        return compact(p,job,raw,label)
    if job["mode"]!="registration":
        raise ValueError("Unexpected M11 request mode")
    bp._audit(p,job["request"],raw)
    return dict(id=label,status=raw["stats"]["status"],selected=sorted(map(list,ss.eb.selected(raw))))


def run_one(folder,p,job,deadline):
    if (deadline-now()).total_seconds()<305:
        raise ss.fc.StudyLimit("Another 300-second request no longer fits")
    if job["mode"]=="energy":
        return work(folder,p,job,deadline)
    label=e._hash(job)
    e._publish(folder/"starts"/(label+".json"),e._encoded(dict(started_utc=now().isoformat(),job=job)))
    raw=bp._solve(p,job["request"],monotonic()+(deadline-now()).total_seconds())
    row=replay(p,job,raw,label)
    body=dict(job=job,result=raw)
    e._publish(folder/"certificates"/(label+".json.gz"),
               gzip.compress(e._encoded(dict(body=body,sha256=e._hash(body))),compresslevel=1,mtime=0))
    return row


class Evidence:
    def __init__(self,archive,deadline,verify):
        self.folder=archive/"formal"
        self.deadline=deadline
        self.verify=verify
        self.periods={}
        self.rows={}
        self.used=set()
        self.pool=None
        past=archive.parent/"20261123_m11_rules"
        self.past=(past/"formal",past/"continuation"/"fine")
        if not verify:
            for sub in ("certificates","starts"):
                (self.folder/sub).mkdir(parents=True,exist_ok=True)
            os.environ.update(e.WORKER_ENV)
            self.pool=ProcessPoolExecutor(max_workers=e.WORKERS)

    def close(self):
        if self.pool is not None:
            self.pool.shutdown()

    def batch(self,pairs):
        pending={}
        labels=[]
        for p,job in pairs:
            label=e._hash(job)
            labels.append(label)
            self.periods[job["input"]]=p
            if label in self.rows or label in pending:
                continue
            for source in (self.folder,*self.past):
                if (source/"certificates"/(label+".json.gz")).is_file():
                    body=read_envelope(source,label)
                    if body["job"]!=job:
                        raise ValueError("Request scope differs")
                    row=replay(p,job,body["result"],label)
                    if source==self.folder:
                        self.used.add(label)
                    else:
                        row=dict(row,source="archived_M11")
                    self.rows[label]=row
                    break
            else:
                if self.verify or (self.folder/"starts"/(label+".json")).exists():
                    raise ValueError("Missing or unfinished weekly proof: "+label)
                pending[label]=(p,job)
        jobs=list(pending.items())
        for i in range(0,len(jobs),e.WORKERS):
            if (self.deadline-now()).total_seconds()<325:
                raise ss.fc.StudyLimit("Full weekly batch no longer fits")
            group=jobs[i:i+e.WORKERS]
            futures=[self.pool.submit(run_one,self.folder,p,job,self.deadline) for _,(p,job) in group]
            for (label,_),future in zip(group,futures,strict=True):
                self.rows[label]=future.result()
                self.used.add(label)
        return [self.rows[label] for label in labels]
