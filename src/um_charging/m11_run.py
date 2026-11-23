"""Run or resume the preregistered M11 boundary comparisons in a local archive."""
import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
from time import perf_counter, process_time

from . import m10_evidence as evidence, m10_final_run, m10_inputs, m11_boundary, site_sizing as ss


def encoded(data):
    return evidence._encoded(data)


def identity(req):
    return evidence._hash(req)


def request(kind, variant, period, design, caps=None, fixed=(), **extra):
    return dict(kind=kind, variant=variant, week=period.days[0]["week_start"],
                design=[design.port_plugs, design.port_kw, design.warehouse_kw],
                caps=list(caps or design.caps), fixed=sorted(map(list, fixed)), **extra)


def worker(period, req, folder):
    label = identity(req)
    stamp = datetime.now(timezone.utc).isoformat()
    (folder/"starts"/(label+".json")).write_bytes(encoded(dict(request=req, started_utc=stamp)))
    begin, cpu = perf_counter(), process_time()
    result = m11_boundary.solve(period, req)
    result["stats"].update(started_utc=stamp, seconds=perf_counter()-begin,
                           cpu_seconds=process_time()-cpu, worker_pid=os.getpid())
    body = dict(request=req, result=result)
    packed = dict(body=body, sha256=evidence._hash(body))
    target = folder/"certificates"/(label+".json.gz")
    pending = target.with_suffix(".tmp")
    pending.write_bytes(gzip.compress(encoded(packed), compresslevel=1, mtime=0))
    pending.replace(target)
    return result["stats"]["status"]


def certificate(folder, req):
    packed = json.loads(gzip.decompress((folder/"certificates"/(identity(req)+".json.gz")).read_bytes()))
    if packed["body"]["request"] != req or evidence._hash(packed["body"]) != packed["sha256"]:
        raise ValueError("Invalid M11 request or certificate")
    return packed["body"]["result"]


def inputs(outcome):
    train = m10_inputs.load_inputs()
    post, _, _, _ = m10_final_run._sealed_periods()
    prior = json.loads(outcome.read_bytes())
    post_ref = set(map(tuple, prior["reference"]))
    if len(post_ref) != 49 or not prior["reference_complete"]:
        raise ValueError("Frozen post hoc registration differs")
    special, = [p for p in post if p.days[0]["week_start"] == "2022-01-17"]
    return train, special, post_ref


def run(folder, selection, outcome, deadline, workers):
    if deadline.tzinfo is None or not 1 <= workers <= 8:
        raise ValueError("An absolute zoned deadline and 1 to 8 workers are required")
    os.environ.update(evidence.WORKER_ENV)
    train, special, post_ref = inputs(outcome)
    by_week = {p.days[0]["week_start"]:p for p in [*train.periods,special]}
    selected = json.loads(selection.read_bytes())["design_ranks"]
    cap_table = {(r["design"],r["connection_basis"]):tuple(r["caps_kw"])
                 for r in selected if r["scenario"] == "official" and r["caps_kw"] is not None}
    folder.mkdir(exist_ok=True)
    for sub in ("certificates","starts"):
        (folder/sub).mkdir(exist_ok=True)
    variants = ("weekly","open")
    primary = (ss.Design(1,40,20),ss.Design(1,20,20))
    unknown = set()
    index = {}
    def batch(requests):
        iterator = iter({identity(r):r for r in requests}.values())
        pending = {}
        def finish(req, status):
            if status == "unresolved":
                unknown.add((req["variant"],req["week"],tuple(req["design"]),tuple(req["caps"])))
        while True:
            while len(pending) < min(workers, 4-len(unknown)) and len(unknown) < 4:
                req = next(iterator, None)
                if req is None:
                    break
                label = identity(req)
                index[label] = req
                if (folder/"certificates"/(label+".json.gz")).exists():
                    finish(req, certificate(folder,req)["stats"]["status"])
                else:
                    if (deadline-datetime.now(timezone.utc)).total_seconds() <= 310:
                        raise ss.fc.StudyLimit("A full solve no longer fits before the original deadline")
                    future = pool.submit(worker, by_week[req["week"]], req, folder)
                    pending[future] = req
            if len(unknown) >= 4:
                raise ss.fc.StudyLimit("Fourth unresolved weekly group")
            if not pending:
                break
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for f in done:
                finish(pending.pop(f), f.result())
        print("completed request batch", len(index), "unresolved groups", len(unknown), flush=True)

    def value(r):
        return certificate(folder,r)
    def record(name, data):
        (folder/name).write_bytes(encoded(data))
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            post = [request("service",v,special,primary[0],fixed=post_ref & special.keys) for v in variants]
            batch(post)
            record("posthoc.json", {r["variant"]:identity(r) for r in post})
            reference = {}
            reg_rows = []
            for v in variants:
                m8 = [request("m8",v,p,ss.BASELINE,preferred=sorted(map(list,train.main_reference&p.keys)))
                      for p in train.periods[:6] if p.keys]
                batch(m8)
                for r in m8:
                    res = value(r)
                    keys = ss.eb.selected(res) if res["stats"]["status"] == "certified" else None
                    reference[v,r["week"]] = keys
                    reg_rows.append(dict(variant=v, week=r["week"], ids=[identity(r)],
                                         selected=None if keys is None else sorted(keys)))
                locked = {p.days[0]["week_start"]:{} for p in train.periods[6:]}
                ids = {w:[] for w in locked}
                for i in range(7):
                    daily = []
                    for p in train.periods[6:]:
                        d = p.days[i]["date"]
                        w = p.days[0]["week_start"]
                        if locked[w] is not None and any(k[0]==d for k in p.keys):
                            daily.append(request("m9",v,p,ss.BASELINE,date=d,
                                locked=[[a,b,val] for (a,b),val in sorted(locked[w].items())]))
                    batch(daily)
                    for r in daily:
                        w, d = r["week"], r["date"]
                        res = value(r)
                        ids[w].append(identity(r))
                        if res["stats"]["status"] == "certified":
                            chosen = ss.eb.selected(res)
                            locked[w].update({k:k in chosen for k in by_week[w].keys if k[0]==d})
                        else:
                            locked[w] = None
                for w, choices in locked.items():
                    keys = None if choices is None else {k for k,take in choices.items() if take}
                    reference[v,w] = keys
                    reg_rows.append(dict(variant=v,week=w,ids=ids[w],selected=None if keys is None else sorted(keys)))
                for p in train.periods[:6]:
                    if not p.keys:
                        w = p.days[0]["week_start"]
                        reference[v,w] = set()
                        reg_rows.append(dict(variant=v,week=w,ids=[],selected=[]))
                record("registration.json", reg_rows)
            registry = []
            for v in variants:
                for d in primary:
                    for p in train.periods:
                        w = p.days[0]["week_start"]
                        keys = reference[v,w]
                        if keys is not None:
                            registry.append(request("service",v,p,d,fixed=keys))
            batch(registry)
            record("registered_service.json",[identity(r) for r in registry])
            rows = []
            for d in dict.fromkeys([*primary,*ss.design_grid(ss.COARSE_KW)]):
                requests = []
                for v in variants:
                    for p in train.periods:
                        requests.append(request("service",v,p,d,fixed=train.main_reference&p.keys))
                batch(requests)
                row = dict(design=d.label, service={v:[identity(r) for r in requests if r["variant"]==v]
                                                    for v in variants}, operation=[])
                feasible = all(value(r)["audit"] is not None for r in requests if r["variant"]=="weekly")
                if feasible:
                    caps = dict.fromkeys([d.caps]+[cap_table[d.label,b] for b in ("new","existing")
                                                  if (d.label,b) in cap_table])
                    for c in caps:
                        costs = [request("energy","weekly",p,d,c,train.main_reference&p.keys) for p in train.periods]
                        batch(costs)
                        bases = [b for b in ("new","existing") if c in {d.caps,cap_table.get((d.label,b))}]
                        row["operation"].append(dict(caps=c,bases=bases,ids=[identity(r) for r in costs]))
                rows.append(row)
                record("grid.json",rows)
    finally:
        record("request_index.json",index)
        record("unresolved.json",sorted(unknown))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("folder","selection","outcome"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--deadline", type=datetime.fromisoformat, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    run(**vars(args))


if __name__ == "__main__":
    main()
