"""Tidy exports shared by the R021 archive writer and the solver-free verifier."""
import csv
import io
import json
from collections import Counter

from . import m10_evidence as e
from .m11_rule_evidence import json_file, read_envelope


def table(rows,fields=None):
    columns=fields or list(dict.fromkeys(k for row in rows for k in row))
    stream=io.StringIO(newline="")
    writer=csv.DictWriter(stream,columns,lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({k:json.dumps(v,ensure_ascii=False,separators=(",",":")) if isinstance(v,(list,dict)) else v
                         for k,v in r.items()})
    return stream.getvalue().encode()


def distributions(folder):
    rules=json_file(folder/"rules.json")
    sensitivity=json_file(folder/"sensitivity.json")
    rule_rows=[]
    warehouse=[]
    benchmark=[]
    for n,g in rules["cohorts"].items():
        for r in g["rules"]:
            for basis in ("new","existing"):
                b=next((x for x in r["bills"] if x["connection_basis"]==basis),{})
                premium=b.get("premium") or (None,None)
                rule_rows.append(dict(input_weeks=int(n),posthoc=int(n)==19,registered=g["count"],rule=r["rule"],
                        design=r["design"],basis=basis,annual_lower=b.get("total_lower"),annual_upper=b.get("total_upper"),
                        premium_lower=premium[0],premium_upper=premium[1],posthoc_49=r["posthoc_49"]))
        for threshold in g["warehouse_segments"]:
            seg=threshold["segment"]
            warehouse.append(dict(weeks=n,vehicle_id=seg[0][1],start=seg[0][0],end=seg[-1][0],
                                  required_priced_kw=threshold["warehouse_kw"],unreachable_at_50=threshold["warehouse_kw"] is None))
        for w in g["benchmark"]:
            benchmark.append(dict(weeks=n,basis=w["connection_basis"],design=w["incumbent"]["design"],
                                  rated_only=int(n)==19,minimum_lower=w["minimum_lower"],minimum_upper=w["minimum_upper"],
                                  possible_minimum_designs=w["possible_minimum_designs"]))
    exclusions=[dict(week=r["week"],date=k[0],vehicle_id=k[1]) for r in rules["exclusions"] for k in r["excluded"]]
    stress_grid=[]
    stress_bills=[]
    gaps=[]
    for factor,s in sensitivity["energy"].items():
        for row in s["grid"]:
            stress_grid.append(dict(scale=factor,design=row["design"],status=row["status"],
                                    failed_weeks=[w["week"] for w in row["weeks"] if w["status"]=="infeasible"]))
        stress_bills.extend(dict(scale=factor,**r) for r in s["bills"])
        gaps.extend(dict(scale=factor,week=w,date=k[0],vehicle_id=k[1])
                    for w,keys in s["baseline_individually_lost"].items() for k in keys)
    prices=sensitivity["settlements"]
    reprice=[dict(case=c,**v) for c,g in prices.items() for v in g["points"]]
    ranks=[dict(case=c,**v) for c,g in prices.items() for v in g["ranks"]]
    outputs={"rule_outputs.csv":table(rule_rows),"cost_benchmarks.csv":table(benchmark),
            "counterfactual_segments.csv":table(warehouse),"maximum_facility_exclusions.csv":table(exclusions),
            "rated_costs.csv":table(rules["rated_bills"]),"energy_grid.csv":table(stress_grid),
            "energy_bills.csv":table(stress_bills),"baseline_gaps.csv":table(gaps),
            "repriced_points.csv":table(reprice),"repriced_designs.csv":table(ranks)}
    if (folder/"fine.json").is_file():
        fine=json_file(folder/"fine.json")
        fine_points=[{k:v for k,v in r.items() if k!="weeks"} for r in fine["points"]]
        outputs.update({"fine_points.csv":table(fine_points),"fine_bills.csv":table(fine["bills"]),
                        "fine_other_cases.csv":table(fine["other_tariffs"])})
    return outputs


def inventory(folder):
    starts={p.stem for p in (folder/"starts").glob("*.json")}
    ids={p.name.removesuffix(".json.gz") for p in (folder/"certificates").glob("*.json.gz")}
    if starts!=ids:
        raise ValueError("Started requests and certificates differ")
    journal=[]
    stats=Counter()
    for label in sorted(ids):
        body=read_envelope(folder,label)
        start=json_file(folder/"starts"/(label+".json"))
        if start["job"]!=body["job"]:
            raise ValueError("Start record differs from the certificate")
        job=body["job"]
        stat=body["result"]["stats"]
        key=job["request"]
        status=stat["status"]
        if (status=="unresolved" and stat["status_code"]==1 and body["result"]["audit"] is not None
                and stat["absolute_gap"] is not None and stat["absolute_gap"]<=.10):
            status="bounded"
        stats[status]+=1
        journal.append(dict(id=label,date_utc=stat["started_utc"],week=key["week"],kind=job["mode"],
                input_sha256=job["input"],design=key["design"],caps=key["caps"],registered=len(key["fixed"]),
                status=status,native_code=stat["status_code"],lower=stat["objective_lower"],upper=stat["objective_upper"],
                gap=stat["absolute_gap"],seconds=stat["seconds"],cpu_seconds=stat["cpu_seconds"],pid=stat["worker_pid"]))
    summary=dict(unique_requests=len(ids),status=dict(stats),first_native_utc=min(r["date_utc"] for r in journal),
                 request_seconds=sum(r["seconds"] for r in journal),cpu_seconds=sum(r["cpu_seconds"] for r in journal))
    return {"solves.csv":table(journal),"compute_statistics.json":e._encoded(summary)}
