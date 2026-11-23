"""Settlement-only monthly/price sensitivities, energy stress and local hardware scans."""
from collections import defaultdict
from itertools import product
import math

from . import m10_costs, m11_rules as rules, m11_rule_study as rs, service_gap, site_sizing as ss
from .m11_rule_evidence import json_file
from . import m10_evidence as evidence


def prior_points(study):
    """Use R012 when both exist, verifying all overlapping R011 meter fields."""
    earlier=study.runs/"20261122_m10_selection_coarse"/"formal"
    original=m10_costs._archived_batches(earlier)
    for k,weeks in original.items():
        for w,r in weeks.items():
            dest=study.archive[k][w]
            for field in ("port_peak_kw","warehouse_peak_kw","port_kwh","warehouse_kwh"):
                if dest[field]!=r[field]:
                    raise ValueError(("Archived meter changed",k,w,field))
    return study.archive


def repricing(study):
    data=prior_points(study)
    periods=study.periods[:12]
    net,_=m10_costs._parameters(periods)
    cpi=net["price_level"]["cpi"]
    raw=rs.csv_rows(study.coarse/"annual_costs.csv")
    scenarios={case:[] for case in ("annual","monthly","equipment_0.7","equipment_1.3")}
    for x in raw:
        if x["scenario"]!="official":
            continue
        label=x["design"]
        caps=(int(x["port_cap_kw"]),int(x["warehouse_cap_kw"]))
        w=data[label,caps]
        row=dict(design=label,port_cap_kw=caps[0],warehouse_cap_kw=caps[1],scenario="official",
                 connection_basis=x["connection_basis"],status=x["status"],missing_ratings_kw=x["missing_ratings_kw"],
                 original_demand=None,demand=None,block_peaks=None,total_lower=None,total_upper=None)
        if x["status"] not in ss.ENERGY_ACCEPTED:
            if x["status"]!="infeasible":
                raise ValueError("Unsettled archived point needs a monthly lower bound")
            for rows in scenarios.values():
                rows.append(dict(row))
            continue
        weeks=[w[rules.week(p)] for p in periods]
        if len(weeks)!=12 or any(r["status"] not in ss.ENERGY_ACCEPTED for r in weeks):
            raise ValueError("Expected 12 complete meter weeks")
        block={}
        annual=monthly=0.
        for s,col,kwh in zip(ss.SITES,("port_peak_kw","warehouse_peak_kw"),("port_kwh","warehouse_kwh"),strict=True):
            block[s]=[max(float(r[col]) for r in weeks[i:i+4]) for i in (0,4,8)]
            peak=max(block[s])
            volume=math.fsum(float(r[kwh]) for r in weeks)*52/12
            from .cabinet_tariff import select_band, network_rates
            band=select_band(net,volume/peak if peak else 0,"official")
            rate,_=network_rates(net,"official",band)
            rate*=cpi["2025"]/cpi["2024"]
            annual+=peak*rate
            monthly+=sum(block[s])*rate/3
        ss.close(annual,float(x["demand"]),"archived annual demand")
        for case,rows in scenarios.items():
            expense=monthly if case=="monthly" else annual
            step={"equipment_0.7":-.3,"equipment_1.3":.3}.get(case,0.)
            delta=expense-annual+step*float(x["equipment"])
            rows.append(dict(row,original_demand=annual,demand=expense,block_peaks=block,
                             total_lower=float(x["total_lower"])+delta,total_upper=float(x["total_upper"])+delta))
    result={}
    for case,rows in scenarios.items():
        ranks,best=m10_costs._rank_designs(rows)
        result[case]=dict(points=rows,ranks=ranks,minima=best)
    return result


def individually_lost(period, fixed, design):
    lost=[]
    for segment,_ in rules.trucks(period,fixed):
        for i,k in enumerate(segment):
            if not any(rules.reachable(rules.hi._segment_truck(period,segment[a:b+1]),design)
                       for a in range(i+1) for b in range(i,len(segment))):
                lost.append(k)
    return sorted(lost)


def sensitivity(study,outputs):
    wanted={r["design"] for r in outputs["cohorts"]["12"]["rules"] if r["design"]} | {"p1-40-w20","p1-20-w20"}
    old={(r["design"],r["connection_basis"]):tuple(r["caps_kw"]) for r in study.selection["design_ranks"]
         if r["scenario"]=="official" and r["caps_kw"] is not None}
    values={}
    for factor in (.8,.9,1.1,1.2):
        ps=study.periods_for(factor)[:12]
        grid=[]
        for d in rules.GRID:
            rows=study.weekly(ps,study.ref,d,d.caps,"service",scale=factor)
            grid.append(dict(design=d.label,status=rs.point_status(rows),weeks=rows))
        bills=[]
        for label in sorted(wanted):
            d=study.designs[label]
            item,=[g for g in grid if g["design"]==label]
            if item["status"]!="feasible":
                continue
            for caps in sorted({old.get((label,b),d.caps) for b in ("new","existing")} | {d.caps}):
                rows=study.weekly(ps,study.ref,d,caps,"energy",scale=factor)
                for b in rs.settle(ps,d,rows):
                    if caps in (d.caps,old.get((label,b["connection_basis"]))):
                        bills.append(dict(b,port_cap_kw=caps[0],warehouse_cap_kw=caps[1]))
        lost={rules.week(p):individually_lost(p,p.keys&study.ref,ss.BASELINE) for p in ps}
        base,=[g for g in grid if g["design"]==ss.BASELINE.label]
        residual=[]
        for p,row in zip(ps,base["weeks"],strict=True):
            if row["status"]!="infeasible":
                continue
            remaining=(p.keys&study.ref)-set(lost[rules.week(p)])
            checked,=study.weekly([p],remaining,ss.BASELINE,ss.BASELINE.caps,"service",scale=factor)
            residual.append(dict(week=rules.week(p),joint_after_individual_exclusions=checked))
        values[str(factor)]=dict(grid=grid,bills=bills,baseline_individually_lost=lost,baseline_residual=residual)
    return dict(energy=values,settlements=repricing(study))


def fine(study):
    periods=study.periods[:12]
    all_designs=study.designs
    materials=m10_costs._parameters(periods)[1]
    ratings=sorted({0,*[k for k in materials["annual_charger_eur_2025_by_kw"] if 0<k<=50]})
    facilities=set()
    for cap in (20,40):
        d=ss.Design(1,cap,20)
        facilities.add(d)
        for side in range(2):
            pos=ratings.index(d.caps[side])
            for i in (pos-1,pos+1):
                if 0<=i<len(ratings):
                    p,w=(ratings[i],20) if side==0 else (cap,ratings[i])
                    facilities.add(ss.Design(int(p>0),p,w))
    sc=rs.csv_rows(study.refine/"screen_points.csv")
    prices=rs.csv_rows(study.refine/"screen_tariffs.csv")
    def key(r):
        return r["design"],(int(r["port_cap_kw"]),int(r["warehouse_cap_kw"]))
    screening={key(r):r for r in sc}
    tariff=defaultdict(list)
    for r in prices:
        tariff[key(r)].append(r)
    failures=[(all_designs[label],caps) for (label,caps),w in study.archive.items()
              if any(x["point_status"]=="infeasible" for x in w.values())]
    caps_best={r["connection_basis"]:r["minimum_upper"] for r in study.selection["winners"]
               if r["scenario"]=="official"}
    rows=[]
    bills=[]
    # Only R013 bounds are applied to the other ten cases; no new native request.
    others=[]
    for d in sorted(facilities):
        if not study.ledger.verify:
            print("fine hardware",d.label,"completed points",len(rows),flush=True)
        for caps in product(range(0,d.port_kw+1,5),range(0,d.warehouse_kw+1,5)):
            k=d.label,caps
            proof=screening.get(k,{})
            bound={r["connection_basis"]:float(r["annual_lower_eur_2025"]) for r in tariff[k]
                   if r["scenario"]=="official" and r["annual_lower_eur_2025"]}
            if k not in study.archive:
                for w in study.selection["winners"]:
                    if w["scenario"]=="official":
                        continue
                    entry=next((r for r in tariff[k] if r["scenario"]==w["scenario"] and
                                r["connection_basis"]==w["connection_basis"]),{})
                    low=entry.get("annual_lower_eur_2025")
                    physical=proof.get("reason") in ("infeasible_superset","weekly_window_capacity","infeasible_network_relaxation")
                    others.append(dict(design=d.label,caps=caps,scenario=w["scenario"],basis=w["connection_basis"],
                        lower=float(low) if low else None,upper=w["minimum_upper"],
                        decision="excluded" if physical or low and float(low)>w["minimum_upper"]+1e-6 else "not_excluded"))
            if not study.service.get(d.label,{}).get("same_service",True) or any(
                    m10_costs._contains(large,limit,ss._active_build(d,caps),caps) for large,limit in failures):
                rows.append(dict(design=d.label,caps=caps,status="infeasible_containment"))
                continue
            if proof.get("reason") in ("infeasible_superset","weekly_window_capacity","infeasible_network_relaxation"):
                rows.append(dict(design=d.label,caps=caps,status="infeasible_R013"))
                continue
            if len(bound)==2 and all(bound[b]>caps_best[b]+1e-6 for b in bound):
                rows.append(dict(design=d.label,caps=caps,status="above_R013",lower=bound))
                continue
            week_rows=study.weekly(periods,study.ref,d,caps,"energy")
            status=rs.point_status(week_rows)
            paid=rs.settle(periods,d,week_rows)
            if status=="infeasible":
                failures.append((d,caps))
            for b in paid:
                bills.append(dict(b,port_cap_kw=caps[0],warehouse_cap_kw=caps[1]))
                caps_best[b["connection_basis"]]=min(caps_best[b["connection_basis"]],b["total_upper"])
            rows.append(dict(design=d.label,caps=caps,status=status if paid or status=="infeasible" else "unresolved",weeks=week_rows))
        if not study.ledger.verify:
            target=study.ledger.folder/"fine_checkpoint.json"
            temp=target.with_suffix(".tmp")
            temp.write_bytes(evidence._encoded(dict(last_design=d.label,points=rows,bills=bills,other_tariffs=others)))
            temp.replace(target)
    ranks,minima=m10_costs._rank_designs(bills)
    return dict(points=rows,bills=bills,facilities=sorted(d.label for d in facilities),billed_ranks=ranks,
                billed_minima=minima,other_tariffs=others,unsettled=sum(r["status"]=="unresolved" for r in rows))


def evaluate(study,stage,folder):
    if stage=="sensitivity":
        return sensitivity(study,json_file(folder/"rules.json"))
    if stage=="fine":
        return fine(study)
    raise ValueError(stage)
