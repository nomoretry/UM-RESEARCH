"""Penalty, breakpoint, re-registration and unquoted charger analyses on fixed duties."""
from functools import lru_cache
import json
import math

from . import m10_breakpoint as bp, m10_costs, m10_final_bills, m10_final_run, m10_inputs, m10_warehouse_price
from . import m11_robustness as robust, m11_rule_study as rs, m11_rules as rules, site_sizing as ss
from .m11_leftover_evidence import energy_job, registration_job
from .m11_rule_evidence import json_file, period_digest


BASES=("new","existing")
F40=ss.Design(1,40,20)
F20=ss.Design(1,20,20)


def interval(subset):
    if not subset:
        return None,None
    lows=[r["lower"] for r in subset if r["lower"] is not None]
    highs=[r["upper"] for r in subset if r["upper"] is not None]
    return min(lows,default=None),min(highs,default=None)


def difference(a,b):
    lo=a[0]-b[1] if a[0] is not None and b[1] is not None else None
    hi=a[1]-b[0] if a[1] is not None and b[0] is not None else None
    return [lo,hi]


def rank(rows):
    results=[]
    for basis in BASES:
        subset=[r for r in rows if r["basis"]==basis and r["status"]!="infeasible"]
        designs={}
        for r in subset:
            designs.setdefault(r["design"],[]).append(r)
        ranges={d:interval(group) for d,group in designs.items()}
        for d,(lo,hi) in ranges.items():
            others=[v for key,v in ranges.items() if key!=d]
            best=1+sum(up is not None and lo is not None and up<lo-ss.EPS for _,up in others)
            worst=1+sum(low is None or hi is None or low<=hi+ss.EPS for low,_ in others)
            group=designs[d]
            results.append(dict(basis=basis,design=d,lower=lo,upper=hi,rank_best=best,rank_worst=worst,
                                possible_caps=[r["caps"] for r in group if hi is None or r["lower"] is None
                                               or r["lower"]<=hi+ss.EPS]))
    return results


class Study:
    def __init__(self,archive,evidence):
        self.runs=archive.parent
        self.evidence=evidence
        self.main=m10_inputs.load_inputs()
        self.sensitive=m10_inputs.load_inputs(sensitivity=True)
        self.old=self.runs/"20261122_m10_selection_coarse2"/"formal"
        self.bp=self.runs/"20261122_m10_holdout_prep"/"breakpoint_sensitivity"
        self.original={rules.week(p):p for p in self.main.periods}
        self.service=json_file(self.old/"service_summary.json")
        self.archive=m10_costs._archived_batches(self.old)
        self.chosen={(r["design"],r["connection_basis"]):tuple(r["caps_kw"])
                     for r in json_file(self.old/"selection.json")["design_ranks"]
                     if r["scenario"]=="official" and r["caps_kw"] is not None}
        self.invoice={(r["design"],(int(r["port_cap_kw"]),int(r["warehouse_cap_kw"])),r["connection_basis"]):r
                      for r in rs.csv_rows(self.old/"annual_costs.csv") if r["scenario"]=="official"}
        self.bp_weeks={(r["design"],r["week"]):r for r in rs.csv_rows(self.bp/"weekly_points.csv")}
        report=json_file(self.bp/"summary.json")
        self.break_ref={tuple(k) for g in report["registration"] for k in g["selected"]}
        if (len(self.break_ref)!=104 or len(self.sensitive.excluded_intervals)!=23 or
                report["excluded_intervals"]!=self.sensitive.excluded_intervals):
            raise ValueError("Frozen breakpoint calendar or register differs")
        self.break_period={rules.week(p):p for p in self.sensitive.periods}

    def original_bill(self,d,caps,basis):
        r=self.invoice[d.label,tuple(caps),basis]
        if r["status"] not in ss.ENERGY_ACCEPTED:
            raise ValueError("Expected accepted reference invoice")
        return float(r["total_lower"]),float(r["total_upper"])

    def archived(self,p,d,caps,fixed):
        w=rules.week(p)
        raw=self.archive.get((d.label,caps),{}).get(w)
        if (raw and w in self.original and fixed==self.main.main_reference&p.keys
                and period_digest(p)==period_digest(self.original[w])
                and (raw["status"] in ss.ENERGY_ACCEPTED or raw["status"]=="infeasible")):
            return rs.archived_row(raw)
        raw=self.bp_weeks.get((d.label,w))
        if (raw and caps==d.caps and fixed==set(map(tuple,json.loads(raw["registered"])))
                and period_digest(p)==period_digest(self.break_period[w])):
            row=dict(week=w,status=raw["status"],id=raw["evidence_id"],source="archived_breakpoint",
                     physical=raw["status"] in ss.ENERGY_ACCEPTED)
            if row["physical"]:
                meter=json.loads(raw["meter"])
                row.update(grid=meter["site_grid_kwh"],peak=meter["site_quarter_peak_kw"],
                           lower=float(raw["purchase_lower"]),upper=float(raw["purchase_upper"]))
            return row
        return None

    @lru_cache(maxsize=4096)
    def segments(self,p,fixed):
        return list(rules.trucks(p,set(fixed)))

    def point(self,ps,ref,d,caps,*,omit=None):
        caps=tuple(caps)
        weeks={}
        pending=[]
        for p in ps:
            w=rules.week(p)
            fixed=ref&p.keys
            row=self.archived(p,d,caps,fixed)
            if row is not None:
                weeks[w]=row
            elif not fixed:
                zero=dict.fromkeys(ss.SITES,0.)
                weeks[w]=dict(week=w,status="certified",source="empty_register",id=None,physical=True,
                              lower=0.,upper=0.,grid=zero,peak=zero)
            else:
                failed=next((seg for seg,t in self.segments(p,tuple(sorted(fixed)))
                             if not robust.relaxed_segment(t,d,caps)),None)
                if failed is not None:
                    weeks[w]=dict(week=w,status="infeasible",source="optimistic_single_truck",
                                  segment=failed,id=None,physical=False)
                else:
                    pending.append((p,energy_job(p,d,caps,fixed)))
        for (p,_),row in zip(pending,self.evidence.batch(pending),strict=True):
            weeks[rules.week(p)]=row
        rows=[weeks[rules.week(p)] for p in ps]
        states={r["status"] for r in rows}
        status="unresolved" if "unresolved" in states else "infeasible" if "infeasible" in states else "billed"
        if status=="billed" and not states<=ss.ENERGY_ACCEPTED:
            raise ValueError("Unexpected weekly state")
        bills=rs.settle(ps,d,rows,omit_unquoted=omit) if status=="billed" else []
        bounds=self.lower(ps,ref,d,rows) if status=="unresolved" else {}
        return dict(design=d.label,caps=list(caps),status=status,weeks=rows,bills=bills,lower=bounds)

    def lower(self,ps,ref,d,rows):
        _,materials=m10_costs._parameters(ps)
        eq,_,conn=ss.annual_capital_costs(d,materials)
        cost=0.
        for p,row in zip(ps,rows,strict=True):
            grid=math.fsum(t[2] for day,v in ref&p.keys for t in p.cases[day]["trucks"][v]["trips"])
            grid/=ss.eb.DEFAULT_SPEC.efficiency
            if abs(grid)<ss.EPS:
                continue
            years={day["date"][:4] for day in p.days}
            if len(years)!=1:
                raise ValueError("Nonempty cross-year week needs date-specific bounds")
            nominal=min(price for prices in p.prices.values() for price in prices)*grid/1000
            if row.get("lower") is not None:
                nominal=max(nominal,row["lower"])
            cost+=(nominal-ss.EPS)*m10_final_bills.PRICE_YEAR/m10_final_bills.PRICE_INDEX[years.pop()]
        return {b:eq+conn[b]+cost*52/len(ps)-ss.EPS for b in BASES}


def charges(point,bases=BASES):
    rows=[]
    for b in bases:
        bill=next((r for r in point["bills"] if r["connection_basis"]==b),{})
        rows.append(dict(design=point["design"],caps=point["caps"],basis=b,status=point["status"],
                         lower=bill.get("total_lower",point["lower"].get(b)),upper=bill.get("total_upper")))
    return rows


def penalty(s):
    ref=s.main.main_reference-{("2021-11-26","1")}
    if len(ref)!=105:
        raise ValueError("Expected the known missed vehicle-day")
    points=[]
    fees=[]
    grid=ss.DispatchGrid([],set(),{},None)
    other=[]
    for d in rules.GRID:
        original=s.service[d.label]
        if d.port_plugs and not d.warehouse_kw:
            if original["lost_vs_reference"]!=[["2021-11-26","1"]] or original["completed_registered"]!=105:
                raise ValueError("Published port-only service gap differs")
            for caps in [d.caps,*[c for c in grid.options(d,ss.COARSE_KW) if c!=d.caps]]:
                p=s.point(s.main.periods,ref,d,caps)
                points.append(p)
                fees.extend(charges(p))
                if caps==d.caps and p["status"]=="infeasible":
                    break
        elif not original["same_service"]:
            other.append(dict(design=d.label,completed=original["completed_registered"],
                              missing=106-original["completed_registered"],lost=original["lost_vs_reference"],
                              unresolved=original["unresolved_vs_reference"]))
    results=rank(fees)
    for r in results:
        for key,d in (("f40",F40),("f20",F20)):
            diff=difference(s.original_bill(d,d.caps,r["basis"]),(r["lower"],r["upper"]))
            r[key+"_savings"]=diff
            r[key+"_penalty"]=[v*12/52 if v is not None else None for v in diff]
    return dict(points=points,fees=fees,ranks=results,other_gaps=other)


def grid_study(s,ps,ref,extra):
    points=[]
    fees=[]
    for d in rules.GRID:
        rated=s.point(ps,ref,d,d.caps)
        points.append(rated)
        fees.extend(charges(rated))
        if extra and rated["status"]!="infeasible":
            chosen={b:s.chosen.get((d.label,b)) for b in BASES}
            for caps in sorted({c for c in chosen.values() if c and c!=d.caps}):
                p=s.point(ps,ref,d,caps)
                points.append(p)
                fees.extend(charges(p,[b for b,c in chosen.items() if c==caps]))
    return dict(points=points,fees=fees,ranks=rank(fees))


def breakpoint(s):
    return grid_study(s,s.sensitive.periods,s.break_ref,True)


def scaled(s,factor):
    ps=[rules.scaled(p,factor) for p in s.main.periods]
    jobs=[(p,registration_job(p,bp._request("breakpoint_m8_registration",p,
                      preferred=s.main.main_reference&p.keys))) for p in ps[:6]]
    records=s.evidence.batch(jobs)
    ref={tuple(k) for r in records if r["status"]=="certified" for k in r["selected"]}
    locked=[{} for _ in ps[6:]]
    days=[sorted({d for d,_ in p.keys}) for p in ps[6:]]
    blocked=set()
    for step in range(max(map(len,days))):
        indices=[i for i,dates in enumerate(days) if i not in blocked and step<len(dates)]
        jobs=[]
        for i in indices:
            p=ps[6+i]
            req=bp._request("breakpoint_m9_registration",p,design=ss.BASELINE,day=days[i][step],locked=locked[i])
            jobs.append((p,registration_job(p,req)))
        for i,r in zip(indices,s.evidence.batch(jobs),strict=True):
            records.append(r)
            if r["status"]!="certified":
                blocked.add(i)
                continue
            today={k for k in ps[6+i].keys if k[0]==days[i][step]}
            selected=today&set(map(tuple,r["selected"]))
            locked[i].update({k:k in selected for k in today})
            ref.update(selected)
    result=dict(factor=factor,registration_proofs=records)
    if any(r["status"]!="certified" for r in records):
        return dict(**result,status="registration_unresolved",points=[],fees=[],ranks=[])
    return dict(**result,status="registered",count=len(ref),registered=sorted(ref),
                added=sorted(ref-s.main.main_reference),removed=sorted(s.main.main_reference-ref),
                **grid_study(s,ps,ref,False))


def allowance(fees,comparison,basis,factor):
    options=[]
    unresolved=[]
    for row in fees:
        if row["basis"]!=basis:
            continue
        if row["status"]=="unresolved":
            unresolved.append(row["caps"])
        if row["status"]=="billed":
            options.append(dict(port_cap_kw=row["caps"][0],warehouse_cap_kw=row["caps"][1],
                                known_lower=row["lower"],known_upper=row["upper"]))
    if not options:
        return dict(status="unresolved" if unresolved else "infeasible",unresolved_points=unresolved)
    return m10_warehouse_price.price_interval(dict(zip(("total_lower","total_upper"),comparison)),
                                              options,unresolved,factor)


def prices(s):
    ps=s.main.periods
    ref=s.main.main_reference
    factor=ss.eb.read_json(ss.eb.WEEKS.with_name("site_sizing.json"))["model_policy"]["equipment_cost_from_net_2026_to_annual_2025"]
    points=[]
    fees=[]
    thresholds=[]
    for d in (ss.Design(1,35,20),ss.Design(1,40,35)):
        local=[]
        for cap in range(35,-1,-5):
            caps=(cap,20) if d.port_kw==35 else (40,cap)
            p=s.point(ps,ref,d,caps,omit=35)
            points.append(p)
            local.extend(charges(p))
            if cap==35 and p["status"]=="infeasible":
                break
        fees.extend(local)
        for b in BASES:
            thresholds.append(dict(design=d.label,basis=b,**allowance(local,s.original_bill(F40,F40.caps,b),b,factor)))
    upgrade=ss.Design(1,40,40)
    upgrade_costs=[]
    for b in BASES:
        for name,caps in (("selected",s.chosen[upgrade.label,b]),("rated",upgrade.caps)):
            value=s.original_bill(upgrade,caps,b)
            upgrade_costs.append(dict(design=upgrade.label,point=name,caps=caps,basis=b,lower=value[0],
                                      upper=value[1],premium=difference(value,s.original_bill(F40,F40.caps,b))))
    return dict(points=points,fees=fees,thresholds=thresholds,upgrade=upgrade_costs,factor=factor)


def posthoc(s,prices_result):
    from .__main__ import digest
    outcome=s.runs/"20261123_m10_second_holdout"/"formal"/"outcome.json"
    ps,ref=rules.cohorts(outcome)
    d=ss.Design(1,40,35)
    p=s.point(ps[12:],ref,d,d.caps,omit=35)
    # A seven-week service check is followed by the separate 19-week financial comparison.
    fees=[]
    thresholds=[]
    pts=[p]
    if p["status"]=="billed":
        combined=s.point(ps,ref,d,d.caps,omit=35)
        pts.append(combined)
        fees=charges(combined)
        frozen=json_file(s.runs/"20261123_m11_rules"/"formal"/"rules.json")
        for b in BASES:
            old,=[r for r in frozen["rated_bills"] if r["weeks"]==19 and r["design"]=="p1-40-w40"
                  and r["connection_basis"]==b]
            thresholds.append(dict(basis=b,**allowance(fees,(old["total_lower"],old["total_upper"]),b,
                                                       prices_result["factor"])))
    return dict(posthoc=True,registered=len(set.union(*(x.keys for x in ps[12:]))&ref),service=p["status"],
                outcome_sha256=digest(outcome),input_sha256={path.name:digest(path) for path in m10_final_run.SEALED},
                points=pts,fees=fees,thresholds=thresholds)
