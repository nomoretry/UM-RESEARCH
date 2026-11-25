"""Time-limited fine-grid robustness scan on the original twelve training weeks."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from itertools import product
import json
import math
import os
from pathlib import Path

from . import m10_costs, m10_evidence as e, m10_inputs, m11_rules as rules, m11_rule_study as rs
from . import m11_rule_tables as tables, site_sizing as ss
from .cabinet_tariff import annual_factors
from .m11_rule_evidence import clock, compact, json_file, period_digest, read_envelope, work
from .site_sizing_bounds import AnnualBillBounds, network_lower_bound


def hardware(materials):
    ratings=sorted({0,*materials["annual_charger_eur_2025_by_kw"]})
    designs=[]
    for port in (40,20):
        axes=(port,20)
        neighbors=[axes]
        for side,rating in enumerate(axes):
            i=ratings.index(rating)
            for other in ratings[max(0,i-1):i]+ratings[i+1:i+2]:
                neighbors.append((port,other) if side else (other,20))
        for p,w in neighbors:
            d=ss.Design(int(p>0),p,w)
            if d not in designs:
                designs.append(d)
    return designs


def relaxed_segment(truck,design,caps):
    """Optimistic independently rechargeable windows; each touched quarter offers its full cap."""
    spec=ss.eb.DEFAULT_SPEC
    limits={s:(min(spec.truck_kw,r),c) for s,r,c in zip(ss.SITES,design.caps,caps,strict=True)}
    events=[(a,b,None,site) for a,b,site in truck["windows"]]+list(truck["trips"])
    low=high=spec.boundary_kwh
    for a,b,energy,source in sorted(events,key=lambda entry:entry[:2]):
        if energy is None:
            rating,cap=limits[source]
            quarters=range(math.floor(a/15),math.ceil(b/15))
            delivered=math.fsum(min(cap/4,rating*(min(b,15*q+15)-max(a,15*q))/60)
                                for q in quarters)
            high=min(spec.capacity_kwh,high+spec.efficiency*delivered)
        else:
            low=max(spec.reserve_kwh,low-energy)
            high=min(spec.capacity_kwh,high-energy)
            if low>high+ss.EPS:
                return False
    return low-ss.EPS<=spec.boundary_kwh<=high+ss.EPS


@dataclass
class Point:
    design: ss.Design
    caps: tuple
    rows: dict=field(default_factory=dict)
    jobs: dict=field(default_factory=dict)
    certificate_ids: dict=field(default_factory=dict)
    proof: str=""
    lower: dict=field(default_factory=dict)

    def status(self):
        statuses={r["status"] for r in self.rows.values()}
        if "unresolved" in statuses:
            return "unresolved"
        if "infeasible" in statuses or self.proof.startswith("infeasible"):
            return "infeasible"
        if len(self.rows)==12 and statuses<=ss.ENERGY_ACCEPTED:
            return "billed"
        if self.proof=="annual_lower_bound":
            return "excluded_cost"
        return "pending"


class Scan:
    def __init__(self,archive):
        self.formal=archive/"formal"
        self.folder=archive/"continuation"/"fine"
        inputs=m10_inputs.load_inputs()
        self.periods=inputs.periods
        self.reference=inputs.main_reference
        coarse=archive.parent/"20261122_m10_selection_coarse2"/"formal"
        refine=archive.parent/"20261122_m10_refine"/"formal"
        self.coarse_points=m10_costs._archived_batches(coarse)
        self.service=json_file(coarse/"service_summary.json")
        self.weeks={rules.week(p):p for p in self.periods}
        self.network,self.materials=m10_costs._parameters(self.periods)
        self.bounds=AnnualBillBounds(self.periods,self.reference,self.network,self.materials)
        self.purchase_factor=annual_factors(self.network)[0]
        self.segments={w:list(rules.trucks(p,p.keys&self.reference)) for w,p in self.weeks.items()}
        self.designs=hardware(self.materials)
        self.baseline={w["connection_basis"]:w["minimum_upper"] for w in json_file(coarse/"selection.json")["winners"]
                       if w["scenario"]=="official"}
        self.evidence={}
        for source in (self.formal,self.folder):
            for path in (source/"starts").glob("*.json"):
                if path.stem in self.evidence:
                    raise ValueError("Native request repeated across the checkpoint")
                self.evidence[path.stem]=source
        coarse_designs={d.label:d for d in rules.GRID}
        self.failures=[(coarse_designs[label],caps) for (label,caps),items in self.coarse_points.items()
                       if any(r["point_status"]=="infeasible" for r in items.values())]
        self.duals=defaultdict(list)
        for (label,caps),items in self.coarse_points.items():
            for week,r in items.items():
                if r["status"] in ss.ENERGY_ACCEPTED:
                    self.duals[week].append((coarse_designs[label],caps,float(r["purchase_lower"])))
        def key(r):
            return r["design"],(int(r["port_cap_kw"]),int(r["warehouse_cap_kw"]))
        self.screen={key(r):r["reason"] for r in rs.csv_rows(refine/"screen_points.csv")}
        self.tariffs=defaultdict(dict)
        for r in rs.csv_rows(refine/"screen_tariffs.csv"):
            if r["scenario"]=="official" and r["annual_lower_eur_2025"]:
                self.tariffs[key(r)][r["connection_basis"]]=float(r["annual_lower_eur_2025"])
        self.points=[]
        for d in self.designs:
            limits=product(range(0,d.port_kw+1,5),range(0,d.warehouse_kw+1,5))
            for caps in sorted(limits,reverse=True):
                self.points.append(self.prepare(d,caps))

    def prepare(self,d,caps):
        point=Point(d,caps)
        key=d.label,caps
        active=ss._active_build(d,caps)
        for w,p in self.weeks.items():
            fixed=p.keys&self.reference
            req=e.Request.make(p,d,"energy",caps,fixed=fixed)
            job=json.loads(e._encoded(dict(input=period_digest(p),mode="energy",request=asdict(req))))
            label=e._hash(job)
            point.certificate_ids[w]=label
            row=self.coarse_points.get(key,{}).get(w)
            if label in self.evidence:
                body=read_envelope(self.evidence[label],label)
                if body["job"]!=job:
                    raise ValueError("Fine-grid input differs")
                e.replay(p,req,body["result"])
                point.rows[w]=compact(p,job,body["result"],label)
            elif row and (row["status"] in ss.ENERGY_ACCEPTED or row["status"]=="infeasible"):
                point.rows[w]=rs.archived_row(row)
            elif not fixed:
                zero=dict.fromkeys(ss.SITES,0.)
                point.rows[w]=dict(week=w,source="empty_register",status="certified",physical=True,
                                   id=None,lower=0.,upper=0.,grid=zero,peak=zero)
            else:
                point.jobs[w]=job
        reason=self.screen.get(key)
        if reason in ("infeasible_superset","weekly_window_capacity","infeasible_network_relaxation"):
            point.proof="infeasible_R013_"+reason
        elif not self.service.get(d.label,{}).get("same_service",True) or any(
                m10_costs._contains(large,limit,active,caps) for large,limit in self.failures):
            point.proof="infeasible_coarse_containment"
        if not point.proof:
            for w in point.jobs:
                for segment,truck in self.segments[w]:
                    if not relaxed_segment(truck,d,caps):
                        point.proof="infeasible_single_truck:"+w+":"+str(segment)
                        break
                if point.proof:
                    break
        self.price_floor(point)
        return point

    def price_floor(self,point):
        d,caps=point.design,point.caps
        active=ss._active_build(d,caps)
        weekly=[]
        for w in self.weeks:
            lows=[self.bounds.weekly_floor[w]]
            lows.extend(x for large,limit,x in self.duals[w] if m10_costs._contains(large,limit,active,caps))
            exact=point.rows.get(w,{}).get("lower")
            if exact is not None:
                lows.append(exact)
            weekly.append(max(lows)-ss.EPS)
        purchase=math.fsum(weekly)*self.purchase_factor
        network=network_lower_bound(self.network,"official",caps,self.bounds.annual_hours,self.bounds.annual_kwh)
        equip,missing,conn=ss.annual_capital_costs(d,self.materials)
        if missing:
            raise ValueError("Expected priced hardware")
        if not math.isfinite(network):
            point.proof=point.proof or "infeasible_network_relaxation"
            network=0.  # Nonnegative fee floor for conditional disclosure.
        original=self.tariffs[d.label,caps]
        point.lower={b:max(purchase+network+equip+conn[b]-ss.EPS,original.get(b,-math.inf)) for b in conn}
        if not point.proof and all(point.lower[b]>self.baseline[b]+ss.EPS for b in self.baseline):
            point.proof="annual_lower_bound"

    def run(self,deadline):
        os.environ.update(e.WORKER_ENV)
        with ProcessPoolExecutor(max_workers=e.WORKERS) as pool:
            for design in self.designs:
                active={}
                tasks=iter((point,w,job) for point in self.points if point.design==design
                           for w,job in point.jobs.items())
                for_more=True
                while active or for_more:
                    while len(active)<e.WORKERS and for_more:
                        task=next(tasks,None)
                        if task is None or (deadline-clock()).total_seconds()<=320:
                            for_more=False
                            break
                        point,w,job=task
                        if point.status()!="pending":
                            continue
                        future=pool.submit(work,self.folder,self.weeks[w],job,deadline)
                        active[future]=(point,w)
                    if active:
                        done,_=wait(active,return_when=FIRST_COMPLETED)
                        for future in done:
                            point,w=active.pop(future)
                            point.rows[w]=future.result()
                print(design.label,clock().isoformat(),flush=True)

    def outputs(self):
        points,bills,weeks=[],[],[]
        for point in self.points:
            self.price_floor(point)
            status=point.status()
            base=dict(design=point.design.label,port_cap_kw=point.caps[0],warehouse_cap_kw=point.caps[1])
            if status=="billed":
                paid=rs.settle(self.periods,point.design,[point.rows[w] for w in self.weeks])
                for b in paid:
                    if point.lower[b["connection_basis"]]>b["total_upper"]+ss.EPS:
                        raise ValueError("Point lower bound exceeds its own feasible bill")
                    bills.append({**base,**b})
            points.append(dict(**base,status=status,proof=point.proof,lower_new=point.lower["new"],
                               lower_existing=point.lower["existing"],
                               unresolved_weeks=[w for w in self.weeks if point.rows.get(w,{}).get("status")=="unresolved"]))
            for w in self.weeks:
                row=point.rows.get(w,{})
                recorded=row.get("source","")
                if recorded=="native":
                    label=row["id"]
                    recorded="frozen_native" if self.evidence.get(label)==self.formal else "continuation_native"
                disposition=recorded or ("not_started_time_limit" if status=="pending" else "not_required_"+status)
                weeks.append(dict(**base,week=w,request_id=point.certificate_ids[w],disposition=disposition,
                                  status=row.get("status"),proof_id=row.get("id"),lower=row.get("lower"),upper=row.get("upper")))
        minima={}
        for basis in self.baseline:
            subset=[b for b in bills if b["connection_basis"]==basis]
            best=min(b["total_upper"] for b in subset)
            possible=[{k:b[k] for k in ("design","port_cap_kw","warehouse_cap_kw","total_lower","total_upper")}
                      for b in subset if b["total_lower"]<=best+ss.EPS]
            minima[basis]=dict(minimum_lower=min(b["total_lower"] for b in subset),minimum_upper=best,
                               possible_points=possible)
        outstanding=[row for row in weeks if row["disposition"]=="not_started_time_limit"]
        counts=Counter(p["status"] for p in points)
        summary=dict(points=len(points),status=dict(counts),decided_billed_minima=minima,
                     time_deferred_requests=len(outstanding),hardware=[d.label for d in self.designs])
        return {"points.csv":tables.table(points),"bills.csv":tables.table(bills),"weeks.csv":tables.table(weeks),
                "unstarted.csv":tables.table(outstanding,list(weeks[0])),"summary.json":e._encoded(summary)}


def verify(archive):
    scan=Scan(archive)
    timer=json_file(scan.folder/"clock.json")
    start,end,global_end=(datetime.fromisoformat(timer[k]) for k in ("start","deadline","round_deadline"))
    if end!=min(global_end,start+timedelta(minutes=90)) or timer["addendum_sha256"]!=addendum_digest(archive):
        raise ValueError("Robustness clock or method binding differs")
    seen={r["id"] for p in scan.points for r in p.rows.values() if r.get("source")=="native"}
    starts={p.stem for p in (scan.folder/"starts").glob("*.json")}
    if not starts<=seen:
        raise ValueError("Continuation contains an out-of-scope request")
    for label in starts:
        body=read_envelope(scan.folder,label)
        native=datetime.fromisoformat(body["result"]["stats"]["started_utc"])
        finished=native+timedelta(seconds=body["result"]["stats"]["seconds"])
        if not start<=native<=finished<=end:
            raise ValueError("Weekly request outside robustness budget")
    outputs=scan.outputs()
    if starts:
        outputs.update(tables.inventory(scan.folder))
    for name,value in outputs.items():
        if (scan.folder/name).read_bytes()!=value:
            raise ValueError("Robustness replay differs: "+name)
    return {"requests":len(starts),**json.loads(outputs["summary.json"])}


def addendum_digest(archive):
    import hashlib
    return hashlib.sha256((archive/"PREREG_M11_R2_ADDENDUM.md").read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive",required=True,type=Path)
    parser.add_argument("--deadline",required=True,type=datetime.fromisoformat)
    args=parser.parse_args()
    folder=args.archive/"continuation"/"fine"
    folder.mkdir()
    for sub in ("certificates","starts"):
        (folder/sub).mkdir()
    start=clock()
    deadline=min(start+timedelta(minutes=90),args.deadline)
    e._publish(folder/"clock.json",e._encoded(dict(start=start.isoformat(),deadline=deadline.isoformat(),
               round_deadline=args.deadline.isoformat(),addendum_sha256=addendum_digest(args.archive))))
    scan=Scan(args.archive)
    scan.run(deadline)
    # Reconstruct from disk, including all workers that finished before pool shutdown.
    scan=Scan(args.archive)
    outputs=scan.outputs()
    if any((folder/"starts").glob("*.json")):
        outputs.update(tables.inventory(folder))
    for name,content in outputs.items():
        e._publish(folder/name,content)
    print(outputs["summary.json"].decode(),flush=True)


if __name__=="__main__":
    main()
