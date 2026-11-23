"""Evaluate the registered rules and settle identical service at both official access bases."""
from collections import defaultdict
import csv
from itertools import product
import math

from . import m10_costs, m10_final_bills, m10_evidence as e, m11_rules as rules, site_sizing as ss
from .m11_rule_evidence import json_file


def csv_rows(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))


def point_status(rows):
    if any(r["status"]=="infeasible" for r in rows):
        return "infeasible"
    if all(r.get("physical") for r in rows):
        return "feasible"
    return "unresolved"


def archived_row(row):
    stat=row["status"]
    obj=dict(week=row["week"],status=stat,source="archived_M10",id=row["evidence_id"],
             physical=stat in ss.ENERGY_ACCEPTED)
    if obj["physical"]:
        obj.update(lower=float(row["purchase_lower"]),upper=float(row["purchase_upper"]),
                   grid=dict(zip(ss.SITES,[float(row[k]) for k in ("port_kwh","warehouse_kwh")])),
                   peak=dict(zip(ss.SITES,[float(row[k]) for k in ("port_peak_kw","warehouse_peak_kw")])))
    return obj


def settle(periods,design,rows):
    if len(periods)!=len(rows) or any(r["status"] not in ss.ENERGY_ACCEPTED for r in rows):
        return []
    network,materials=m10_costs._parameters(periods)
    low=high=0.
    for p,r in zip(periods,rows,strict=True):
        if r["week"]!=rules.week(p):
            raise ValueError("Billing order differs from calendar")
        years={d["date"][:4] for d in p.days}
        if len(years)>1:
            if any(r["grid"].values()) or abs(r["upper"])+abs(r["lower"])>ss.EPS:
                raise ValueError("Cross-year weekly cost is not zero")
            continue
        factor=m10_final_bills.PRICE_YEAR/m10_final_bills.PRICE_INDEX[years.pop()]
        low+=min(r["upper"],r["lower"])*factor
        high+=r["upper"]*factor
    grid={s:math.fsum(r["grid"][s] for r in rows) for s in ss.SITES}
    peak={s:max(r["peak"][s] for r in rows) for s in ss.SITES}
    bill=ss.settle(network,0.,grid,peak,"official")
    ss.audit_settlement(network,0.,grid,peak,"official",bill)
    equip,missing,conn=ss.annual_capital_costs(design,materials)
    if missing:
        raise ValueError("Unquoted facility in cost comparison")
    out=[]
    for basis in ("new","existing"):
        fixed=math.fsum([equip,conn[basis],bill["annual_network_energy_eur_2025"],bill["annual_capacity_eur_2025"]])
        out.append(dict(design=design.label,scenario="official",connection_basis=basis,missing_ratings_kw=[],
                        total_lower=fixed+low*52/len(rows),total_upper=fixed+high*52/len(rows),
                        equipment=equip,connection=conn[basis],network_energy=bill["annual_network_energy_eur_2025"],
                        demand=bill["annual_capacity_eur_2025"],purchase_lower=low*52/len(rows),
                        purchase_upper=high*52/len(rows)))
    return out


class Study:
    def __init__(self,runs,ledger):
        self.runs,self.ledger=runs,ledger
        self.coarse=runs/"20261122_m10_selection_coarse2"/"formal"
        self.refine=runs/"20261122_m10_refine"/"formal"
        self.periods,self.ref=rules.cohorts(runs/"20261123_m10_second_holdout"/"formal"/"outcome.json")
        self.base={rules.week(p):p for p in self.periods}
        self.training=set(map(rules.week,self.periods[:12]))
        self.archive=m10_costs._archived_batches(self.coarse)
        self.selection=json_file(self.coarse/"selection.json")
        self.service=json_file(self.coarse/"service_summary.json")
        self.designs={d.label:d for d in rules.GRID}
        self.points={}
        self.scenarios={1:self.periods}
        self.proofs={}

    def periods_for(self,factor):
        if factor not in self.scenarios:
            self.scenarios[factor]=[rules.scaled(p,factor) for p in self.periods]
        return self.scenarios[factor]

    def weekly(self,ps,ref,d,caps,mode,*,scale=1):
        output={}
        native=[]
        for p in ps:
            w=rules.week(p)
            f=ref&p.keys
            archived=self.archive.get((d.label,tuple(caps)),{}).get(w)
            if scale==1 and w in self.training and f==(p.keys&self.ref) and archived and (
                    archived["status"] in ss.ENERGY_ACCEPTED or archived["status"]=="infeasible"):
                output[w]=archived_row(archived)
                continue
            if not f:
                zero=dict.fromkeys(ss.SITES,0.)
                output[w]=dict(week=w,status="certified",source="empty_register",physical=True,
                               id=None,lower=0.,upper=0.,grid=zero,peak=zero)
                continue
            # Single-truck feasibility uses physical rating. A quarter-average cap
            # does not impose that instantaneous rating on a partial window.
            if not rules.relaxed(p,f,d):
                output[w]=dict(week=w,status="infeasible",source="single_truck_relaxation",physical=False,id=None)
                continue
            key=(w,scale,tuple(sorted(f)),d,tuple(caps))
            if mode=="service" and key in self.points:
                output[w]=self.points[key]
                continue
            native.append((p,mode,d,caps,f))
        for args,row in zip(native,self.ledger.batch(native),strict=True):
            p,_,design,cap,f=args
            w=rules.week(p)
            output[w]=row
            self.points[w,scale,tuple(sorted(f)),design,tuple(cap)]=row
        return [output[rules.week(p)] for p in ps]

    def maximum_register(self,ps,reference,d,scale):
        retained=set()
        records=[]
        for p in ps:
            w=rules.week(p)
            f=reference&p.keys
            alts=rules.feasible_subsets(p,f,d)
            options=list(product(*alts.values()))
            feasible=[]
            for combination in options:
                subset={k for group in combination for k in group}
                row,=self.weekly([p],subset,d,d.caps,"service",scale=scale)
                if row["physical"]:
                    feasible.append(subset)
                elif row["status"]!="infeasible":
                    raise ss.fc.StudyLimit("Unique maximum registration remains unverified")
            if len(feasible)!=1:
                return None,dict(week=w,reason="maximum_subset_not_unique" if feasible else "joint_limit",
                                 options=[sorted(x) for x in feasible],per_truck=alts,
                                 previous_weeks=records)
            keep,=feasible
            retained.update(keep)
            records.append(dict(week=w,excluded=sorted(f-keep),selected=sorted(keep)))
        return retained,records


def rule_phase(study):
    """Reuse the M10 complete 12-week service matrix; bill 19-week rated competitors."""
    orig=study.periods
    ref=study.ref
    stressed=study.periods_for(1.2)
    kept,exclusions=study.maximum_register(stressed,ref,ss.LARGEST,1.2)
    if kept is None:
        return dict(stop="rule4_registration",detail=exclusions)
    stage=dict(exclusions=exclusions,cohorts={},rated_bills=[],rated_service=[])
    train_served={d:study.service[d.label]["same_service"] for d in rules.GRID}
    post_service={}
    for d in rules.GRID:
        # Rule 1 need not respect shared interfaces. Its post hoc test can also
        # require a design that did not retain the entire twelve-week training set.
        rows=study.weekly(orig[12:],ref,d,d.caps,"service")
        post_service[d]=point_status(rows)
        stage["rated_service"].append(dict(design=d.label,posthoc=post_service[d],weeks=rows))
    for n in (12,19):
        ps=orig[:n]
        sample_ref=set.union(*(p.keys for p in ps)) & ref
        first,thresholds=rules.single_rules(ps,sample_ref)
        second=None
        for d in rules.GRID:
            if train_served[d] and (n==12 or post_service[d]=="feasible"):
                second=d
                break
            if train_served[d] and n==19 and post_service[d]=="unresolved":
                break
        third=None if second is None else ss.Design(second.port_plugs,second.port_kw,
                  max([second.warehouse_kw]+[t["warehouse_kw"] for t in thresholds if t["warehouse_kw"] is not None]))
        fourth=None
        margin_service=[]
        for d in rules.GRID:
            rows=study.weekly(stressed[:n],kept,d,d.caps,"service",scale=1.2)
            status=point_status(rows)
            margin_service.append(dict(design=d.label,status=status,weeks=rows))
            if status!="infeasible":
                if status=="feasible":
                    fourth=d
                break
        choices=[first,second,third,fourth]
        # All priced rated points in the combined-sample comparison.
        bills=[]
        missing_bill=[]
        for d in rules.GRID:
            if n==12 and d not in choices:
                continue
            if not train_served[d] or n==19 and post_service[d]=="infeasible":
                continue
            rows=study.weekly(ps,sample_ref,d,d.caps,"energy")
            b=settle(ps,d,rows)
            if not b:
                missing_bill.append(d.label)
            for x in b:
                x.update(port_cap_kw=d.port_kw,warehouse_cap_kw=d.warehouse_kw)
            bills.extend(b)
        if n==12:
            benchmarks=[w for w in study.selection["winners"] if w["scenario"]=="official"]
        else:
            _,benchmarks=m10_costs._rank_designs(bills)
        outputs=[]
        for i,d in enumerate(choices,1):
            money=[dict(b) for b in bills if d and b["design"]==d.label]
            for b in money:
                best,=[w for w in benchmarks if w["connection_basis"]==b["connection_basis"]]
                inc=best["incumbent"]
                if missing_bill:
                    b["premium"]=None
                elif inc["design"]==d.label and list(d.caps)==inc["caps_kw"] and len(best["possible_minimum_designs"])==1:
                    b["premium"]=[0.,0.]
                else:
                    b["premium"]=[b["total_lower"]-best["minimum_upper"],b["total_upper"]-best["minimum_lower"]]
            outputs.append(dict(rule=i,design=None if d is None else d.label,bills=money,
                                posthoc_49=post_service.get(d) if n==12 else None))
        stage["cohorts"][str(n)]=dict(count=len(sample_ref),rules=outputs,warehouse_segments=thresholds,
            margin_service=margin_service,benchmark=benchmarks,missing_bills=missing_bill)
        stage["rated_bills"].extend(dict(weeks=n,**b) for b in bills)
    return stage
