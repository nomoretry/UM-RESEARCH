"""Persist and replay M11 boundary-B requests with an absolute clock and uncertainty limit."""
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from copy import copy
from dataclasses import asdict
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import json
import os
from time import monotonic

from . import m10_evidence as e, m11_rules as rules, site_sizing as ss


def clock():
    return datetime.now(timezone.utc)


def json_file(path):
    return json.loads(path.read_bytes())


def priced_period(period, mode):
    if mode == "energy":
        return period
    if mode != "service":
        raise ValueError(mode)
    result = copy(period)
    result.prices = {d:[0.]*len(prices) for d,prices in period.prices.items()}
    return result


@lru_cache(maxsize=256)
def period_digest(period):
    return e._hash([period.days,period.prices])


def read_envelope(folder, label):
    content = json.loads(gzip.decompress((folder/"certificates"/(label+".json.gz")).read_bytes()))
    body = content["body"]
    if e._hash(body)!=content["sha256"] or e._hash(body["job"])!=label:
        raise ValueError("Invalid weekly certificate")
    return body


def calculate(period, job, deadline):
    if period_digest(period)!=job["input"]:
        raise ValueError("Weekly inputs have changed")
    p = priced_period(period, job["mode"])
    req = e.Request.from_json(job["request"])
    raw = e._solve(p,req,monotonic()+(deadline-clock()).total_seconds())
    e.replay(p,req,raw)
    return raw


def compact(p,job,raw,label):
    req = e.Request.from_json(job["request"])
    res = e._admitted_result(priced_period(p,job["mode"]),req,raw)
    stat,audit = res["stats"], res["audit"]
    row = dict(id=label,status=stat["status"],week=req.week,mode=job["mode"],source="native",
               physical=audit is not None,lower=stat["objective_lower"],upper=stat["objective_upper"])
    if audit:
        row.update(grid=audit["site_grid_kwh"],peak=audit["site_quarter_peak_kw"])
    return row


def work(folder,p,job,deadline):
    label=e._hash(job)
    e._publish(folder/"starts"/(label+".json"),e._encoded(dict(started_utc=clock().isoformat(),job=job)))
    raw=calculate(p,job,deadline)
    body=dict(job=job,result=raw)
    e._publish(folder/"certificates"/(label+".json.gz"),
               gzip.compress(e._encoded(dict(body=body,sha256=e._hash(body))),compresslevel=1,mtime=0))
    return compact(p,job,raw,label)


class Ledger:
    def __init__(self,folder,deadline,verify=False,workers=4):
        self.folder,self.deadline,self.verify=folder,deadline,verify
        self.unknown=set()
        self.rows={}
        self.workers=workers
        self.pool=None
        if not verify:
            for name in ("starts","certificates","unresolved"):
                (folder/name).mkdir(parents=True,exist_ok=True)
            self.unknown={p.stem for p in (folder/"unresolved").glob("*.json")}
            if len(self.unknown)>=4:
                raise ss.fc.StudyLimit("Fourth unresolved weekly group already recorded")
            os.environ.update(e.WORKER_ENV)
            self.pool=ProcessPoolExecutor(max_workers=workers)

    def close(self):
        if self.pool:
            self.pool.shutdown()

    def batch(self,pairs):
        pending={}
        items=[]
        for p,mode,design,caps,fixed in pairs:
            req=e.Request.make(p,design,mode,caps,fixed=fixed)
            job=json.loads(e._encoded(dict(input=period_digest(p),mode=mode,request=asdict(req))))
            label=e._hash(job)
            items.append(label)
            if label not in self.rows:
                pending[label]=(p,job)
        def record(label,row):
            self.rows[label]=row
            if row["status"]=="unresolved":
                job=pending[label][1]
                req=job["request"]
                group=e._hash([job["input"],req["week"],req["design"],req["caps"],req["fixed"]])
                self.unknown.add(group)
                path=self.folder/"unresolved"/(group+".json")
                if not self.verify and not path.exists():
                    e._publish(path,e._encoded(dict(group=group,request=label)))
                if len(self.unknown)>=4:
                    raise ss.fc.StudyLimit("Fourth unresolved weekly group")
        jobs=iter(pending.items())
        active={}
        while True:
            while len(active)<min(self.workers,4-len(self.unknown)):
                entry=next(jobs,None)
                if entry is None:
                    break
                label,(p,job)=entry
                path=self.folder/"certificates"/(label+".json.gz")
                if path.exists() or self.verify:
                    body=read_envelope(self.folder,label)
                    if body["job"]!=job:
                        raise ValueError("Requested replay differs")
                    raw=body["result"]
                    e.replay(priced_period(p,job["mode"]),e.Request.from_json(job["request"]),raw)
                    record(label,compact(p,job,raw,label))
                else:
                    if (self.deadline-clock()).total_seconds()<=320:
                        raise ss.fc.StudyLimit("Full weekly request no longer fits before deadline")
                    if (self.folder/"starts"/(label+".json")).exists():
                        raise ValueError("Unfinished native request requires explicit checkpoint review")
                    active[self.pool.submit(work,self.folder,p,job,self.deadline)]=label
            if not active:
                break
            done,_=wait(active,return_when=FIRST_COMPLETED)
            for future in done:
                record(active.pop(future),future.result())
        return [self.rows[i] for i in items]
