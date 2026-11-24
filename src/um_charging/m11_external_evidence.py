"""Content-addressed requests, replay and fixed-length retries for external cohorts."""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import json
import os
from time import monotonic
from unittest.mock import patch

from . import m10_evidence as e, m10_final_evidence as final, site_sizing as ss
from .m11_rule_evidence import period_digest
from .m11_external_seal import put


def utc():
    return datetime.now(timezone.utc)


def job(period, design, phase, seconds=300, **kw):
    req = final.FinalRequest("external", period.days[0]["week_start"], design, phase, design.caps, **kw)
    return json.loads(e._encoded(dict(input=period_digest(period), seconds=seconds, request=asdict(req))))


def unpack(spec):
    fields = dict(spec["request"])
    fields["design"] = ss.Design(**fields["design"])
    return final.FinalRequest(**fields)


def proof(folder, label):
    path = folder / "certificates" / (label+".json.gz")
    body = json.loads(gzip.decompress(path.read_bytes()))
    if body["sha256"] != e._hash(body["body"]) or e._hash(body["body"]["job"]) != label:
        raise ValueError("Invalid external request envelope")
    return body["body"]


def replay(period, spec, raw):
    if spec["input"] != period_digest(period):
        raise ValueError("Weekly certificate input changed")
    req = unpack(spec)
    final._replay(period, req, raw)
    result = final._effective(period, req, raw)
    stat = result["stats"]
    row = dict(id=e._hash(spec), week=req.week, status=stat["status"], physical=result["audit"] is not None,
               lower=stat["objective_lower"], upper=stat["objective_upper"])
    if req.phase == "registration":
        row["selected"] = sorted(ss.eb.selected(raw)) if row["physical"] else None
    if row["physical"] and req.phase == "energy":
        audit = result["audit"]
        row.update(grid=audit["site_grid_kwh"], peak=audit["site_quarter_peak_kw"], daily=audit["daily_eur"])
    return row


def work(folder, period, spec, deadline):
    seconds = spec["seconds"]
    if seconds not in (300,1800) or (deadline-utc()).total_seconds() < seconds+2:
        raise ss.fc.StudyLimit("Another full request no longer fits")
    label = e._hash(spec)
    put(folder/"starts", label+".json", dict(job=spec, started=utc().isoformat()))
    with patch.object(ss.fc, "SOLVE_SECONDS", seconds):
        raw = final._solve(period, unpack(spec), monotonic()+(deadline-utc()).total_seconds())
    row = replay(period, spec, raw)
    body = dict(job=spec, result=raw)
    e._publish(folder/"certificates"/(label+".json.gz"),
               gzip.compress(e._encoded(dict(sha256=e._hash(body), body=body)), compresslevel=1, mtime=0))
    return row


class Ledger:
    def __init__(self, folder, deadline, verify=False):
        self.folder, self.deadline, self.verify = folder, deadline, verify
        self.rows = {}
        self.used = set()
        self.pool = None
        if not verify:
            for name in ("starts","certificates"):
                (folder/name).mkdir(parents=True, exist_ok=True)
            os.environ.update(e.WORKER_ENV)
            self.pool = ProcessPoolExecutor(max_workers=e.WORKERS)

    def close(self):
        if self.pool:
            self.pool.shutdown()

    def batch(self, pairs):
        labels = []
        pending = {}
        for p, spec in pairs:
            label = e._hash(spec)
            labels.append(label)
            self.used.add(label)
            if label in self.rows or label in pending:
                continue
            if (self.folder/"certificates"/(label+".json.gz")).is_file():
                body = proof(self.folder,label)
                self.rows[label] = replay(p,spec,body["result"])
            elif self.verify or (self.folder/"starts"/(label+".json")).is_file():
                raise ValueError("Missing or interrupted external request " + label)
            else:
                pending[label] = (p,spec)
        items = list(pending.items())
        for i in range(0,len(items),e.WORKERS):
            group = items[i:i+e.WORKERS]
            if (self.deadline-utc()).total_seconds() < max(s["seconds"] for _,(_,s) in group)+5:
                raise ss.fc.StudyLimit("Full batch would exceed the original clock")
            futures = [(label,self.pool.submit(work,self.folder,p,s,self.deadline)) for label,(p,s) in group]
            for label,future in futures:
                self.rows[label] = future.result()
        return [self.rows[label] for label in labels]
