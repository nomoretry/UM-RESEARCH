"""Replay M11 certificates, tabulate registered comparisons and repeat a seeded sample."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import random

from . import m10_costs, m10_evidence as evidence, m10_policy_costs, m11_boundary, m11_run, site_sizing as ss
from . import holdout_service, m10_breakpoint


def load(folder, name):
    return json.loads((folder/name).read_bytes())


def write_table(folder, name, rows):
    if not rows:
        raise ValueError(f"Empty result table: {name}")
    with (folder/name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader()
        writer.writerows(rows)


def repeat(p, req, folder, repeats):
    if not (repeats/"certificates"/(m11_run.identity(req)+".json.gz")).exists():
        m11_run.worker(p, req, repeats)
    a, b = [m11_run.certificate(d,req) for d in (folder,repeats)]
    numeric = ("objective","objective_upper","objective_lower")
    bounds = all(a["stats"][k] == b["stats"][k] or (
        a["stats"][k] is not None and b["stats"][k] is not None and
        math.isclose(a["stats"][k],b["stats"][k],rel_tol=0,abs_tol=ss.EPS)) for k in numeric)
    audit = True
    try:
        evidence._assert_close(a["audit"],b["audit"])
    except (ValueError,TypeError):
        audit = False
    return dict(id=m11_run.identity(req), status=a["stats"]["status"]==b["stats"]["status"],
                status_code=a["stats"]["status_code"]==b["stats"]["status_code"],
                bounds=bounds, schedule=evidence._schedule_digest(a)==evidence._schedule_digest(b), replay=audit,
                seconds=b["stats"]["seconds"], cpu_seconds=b["stats"]["cpu_seconds"])


def classify(statuses):
    if "infeasible" in statuses:
        return "infeasible"
    return "feasible" if statuses and all(s in ss.ENERGY_ACCEPTED for s in statuses) else "unresolved"


def report(folder, outcome, deadline, determinism):
    train,special,_ = m11_run.inputs(outcome)
    periods = {p.days[0]["week_start"]:p for p in [*train.periods,special]}
    index = load(folder,"request_index.json")
    if {s.stem for s in (folder/"starts").glob("*.json")} != set(index):
        raise ValueError("Started requests differ from index")
    statuses, summary, meters, segments = {}, [], {}, []
    for label, req in index.items():
        if label != m11_run.identity(req):
            raise ValueError("Changed request identity")
        res = m11_run.certificate(folder,req)
        p, stat = periods[req["week"]],res["stats"]
        statuses[label] = stat["status"]
        if res["audit"] is not None:
            audit = m11_boundary.replay(p,req,res)
            evidence._assert_close(audit,res["audit"])
            if req["kind"] in ("m8", "m9"):
                if req["kind"] == "m8":
                    weights = m10_breakpoint._weights(p, set(map(tuple, req["preferred"])))
                else:
                    today = {k for k in p.keys if k[0] == req["date"]}
                    weights, _ = holdout_service._day_weights(today, set())
                chosen = ss.eb.selected(res)
                score = sum(weights.get(k, 0) for k in chosen)
                ss.close(score, -stat["objective_upper"], "replayed service score")
                proof = holdout_service._integer_certificate(stat["objective_lower"], score)
                if proof != stat["integer_score_bounds"] or (stat["status"] == "certified" and proof != [score, score]):
                    raise ValueError("Archived registration score differs")
            elif req["kind"] == "energy":
                ss.close(audit["purchase_eur"], stat["objective_upper"], "replayed purchase")
                if stat["status"] == "bounded" and not (
                        stat["status_code"] == 1 and 0 <= stat["absolute_gap"] <= .10):
                    raise ValueError("Bounded bill lacks an admissible timeout interval")
            meters[label] = dict(purchase_lower=stat["objective_lower"], audit=audit)
            segments.extend(dict(id=label,kind=req["kind"],variant=req["variant"],week=req["week"],
                design=ss.Design(*req["design"]).label, **row) for row in audit["segments"])
        elif stat["status"] in ss.ENERGY_ACCEPTED:
            raise ValueError("Accepted solution lacks a replay")
        if stat["status"] == "infeasible" and stat["status_code"] != 2:
            raise ValueError("Missing infeasibility status")
        _, caps = m11_boundary._hardware(req)
        design_label = "M8_one" if req["kind"]=="m8" else ss.Design(*req["design"]).label
        summary.append(dict(id=label,week=req["week"],variant=req["variant"],kind=req["kind"],
            design=design_label,port_cap_kw=caps[0],warehouse_cap_kw=caps[1],
            registered_count=len(req["fixed"]) if req["kind"] in ("energy","service") else None,
            **{k:stat[k] for k in ("status","status_code","started_utc","seconds","cpu_seconds",
                                   "objective_lower","objective_upper","worker_pid")}))
    write_table(folder,"solves.csv",summary)
    write_table(folder,"segments.csv",segments)
    registered = load(folder,"registration.json")
    reg_diff = {}
    reg_service = {}
    for v in ("weekly","open"):
        groups = [g for g in registered if g["variant"]==v]
        if len(groups) != 12 or any(g["selected"] is None for g in groups):
            reg_diff[v] = None
        else:
            keys = {tuple(k) for g in groups for k in g["selected"]}
            reg_diff[v] = dict(registered=len(keys),added=sorted(keys-train.main_reference),
                               removed=sorted(train.main_reference-keys))
        for design in (ss.Design(1,40,20), ss.Design(1,20,20)):
            ids = [i for i in load(folder,"registered_service.json") if index[i]["variant"]==v and
                   ss.Design(*index[i]["design"])==design]
            reg_service[v,design.label] = dict(status=classify([statuses[i] for i in ids]) if len(ids)==12
                else "unresolved", failed_weeks=[index[i]["week"] for i in ids if statuses[i]=="infeasible"])
    grid, bills = [], []
    designs = {d.label:d for d in ss.design_grid(ss.COARSE_KW)}
    params = m10_costs._parameters(train.periods)
    for point in load(folder,"grid.json"):
        design = designs[point["design"]]
        for v, ids in point["service"].items():
            grid.append(dict(design=design.label,variant=v,registered=106,status=classify([statuses[i] for i in ids]),
                             failed_weeks=" ".join(index[i]["week"] for i in ids if statuses[i]=="infeasible"),
                             unknown_weeks=" ".join(index[i]["week"] for i in ids if statuses[i]=="unresolved")))
        for op in point["operation"]:
            ids = op["ids"]
            status = classify([statuses[i] for i in ids])
            rows = {}
            if status=="feasible":
                rows = {b["connection_basis"]:b for b in m10_policy_costs.invoices(
                    train.periods,design,[meters[i] for i in ids],parameters=params) if b["scenario"]=="official"}
            for basis in op["bases"]:
                bill = rows.get(basis,{})
                bills.append(dict(design=design.label,scenario="official",connection_basis=basis,
                    port_cap_kw=op["caps"][0],warehouse_cap_kw=op["caps"][1],status=status,
                    missing_ratings_kw=bill.get("missing_ratings_kw",[]),
                    **{k:bill.get(k) for k in ("total_lower","total_upper","purchase","network_energy","demand",
                                               "equipment","connection")}))
    write_table(folder,"service_grid.csv",grid)
    ranks,winners = m10_costs._rank_designs(bills)
    write_table(folder,"official_bills.csv",bills)
    unknowns = load(folder,"unresolved.json")
    result = dict(registration=reg_diff, registered_service={v:{d:s for (u,d),s in reg_service.items() if u==v}
                  for v in reg_diff}, service={v:dict(Counter(g["status"] for g in grid if g["variant"]==v))
                  for v in reg_diff}, posthoc={v:statuses[i] for v,i in load(folder,"posthoc.json").items()},
                  billed_ranks=ranks, billed_minima=winners, unresolved_groups=unknowns,
                  native_requests=len(index), native_status=dict(Counter(statuses.values())),
                  cpu_seconds=sum(s["cpu_seconds"] for s in summary), solver_seconds=sum(s["seconds"] for s in summary),
                  first_native_utc=min(s["started_utc"] for s in summary), feasible_replayed=len(meters),
                  minimum_coverage_complete=len(grid)==70 and not unknowns)
    (folder/"results.json").write_bytes(evidence._encoded(result))
    if determinism:
        os.environ.update(evidence.WORKER_ENV)
        ids = random.Random(20261122).sample(sorted(index),20)
        repeats = folder/"repeat"
        for sub in ("certificates","starts"):
            (repeats/sub).mkdir(exist_ok=True,parents=True)
        checks = []
        with ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1) as pool:
            for start in range(0,len(ids),4):
                if (deadline-datetime.now(timezone.utc)).total_seconds() <= 310:
                    raise ss.fc.StudyLimit("Insufficient time for another verification batch")
                jobs = [pool.submit(repeat,periods[index[i]["week"]],index[i],folder,repeats) for i in ids[start:start+4]]
                checks.extend(job.result() for job in jobs)
        (folder/"determinism.json").write_bytes(evidence._encoded(dict(seed=20261122,checks=checks)))
        if not all(all(c[k] for k in ("status","status_code","bounds","schedule","replay")) for c in checks):
            raise ValueError("A fresh-process repeat differs from its original")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("folder","outcome"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--deadline",type=datetime.fromisoformat,required=True)
    parser.add_argument("--determinism",action="store_true")
    report(**vars(parser.parse_args()))
