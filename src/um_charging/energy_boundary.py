"""Multi-day fleet dispatch on native Berlin delivery hours. All energy is kWh."""
import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
from itertools import groupby
import math
from pathlib import Path
import platform
import subprocess
import warnings
from time import perf_counter

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .__main__ import checked_output, digest, write_json
from .connector_value import NATIVE, RELEASE, csv_rows, hourly_curve
from .day_ahead import ROOT, read_json
from .fleet_service import DEFAULT_SPEC, EPS, SITES, VehicleSpec, _events, build_case, dispatch, subset_case
from .service_gap import REFERENCE, WEEKS

GAP = WEEKS.with_name("service_gap.json")
A, B, C = "daily_fixed", "carry_over", "daily_cyclic_free"
SPECS = dict(S300=DEFAULT_SPEC, S900a=VehicleSpec(900, 30, 150),
             S900b=VehicleSpec(900, 30, 450), S900c=VehicleSpec(900, 90, 450))
UNRESERVED_ENERGY_TOLERANCE_KWH = 1e-8


def calendar(days):
    """Index only complete tasks. Retain the evidence on either side of every break."""
    by_date = {d["date"]: d for d in days}
    rows = {(d["date"], v["vehicle_id"]): v for d in days if d["availability"] == "complete_tasks"
            for v in d["vehicles"]}
    chains, links, breaks = [], [], []
    for vehicle in sorted({v for _, v in rows}):
        previous = None
        for day, v in sorted(k for k in rows if k[1] == vehicle):
            key = day, v
            reason = None
            if previous:
                left = previous[0]
                distance = (date.fromisoformat(day) - date.fromisoformat(left)).days
                if distance != 1:
                    missing = []
                    for i in range(1, distance):
                        stamp = (date.fromisoformat(left) + timedelta(days=i)).isoformat()
                        record = by_date.get(stamp)
                        cause = "outside supplied calendar"
                        if record:
                            cause = record["other_observed_vehicle_days_excluded"].get(v, "no trip records")
                        missing.append([stamp, cause])
                    reason = {"intervening_dates": missing}
                else:
                    first = rows[key]["trips"][0]["track_id"]
                    gaps = rows[previous]["stops"] + rows[previous]["unmapped_gaps"]
                    matches = [g for g in gaps if g["next_track_id"] == first]
                    if matches:
                        gap, = matches
                        links.append(dict(vehicle_id=v, left=left, right=day,
                                          site=gap.get("site"), arrival_track_id=gap["arrival_track_id"],
                                          next_track_id=first))
                    else:
                        reason = {"first_track_id": first, "unmatched_next_track_ids":
                                  [g["next_track_id"] for g in gaps]}
                if reason:
                    breaks.append(dict(vehicle_id=v, left=left, right=day, **reason))
            if previous is None or reason:
                chains.append([])
            chains[-1].append(key)
            previous = key
    return chains, links, breaks


def components(days, links):
    weeks = {d["date"]: d["week_start"] for d in days}
    groups = [{w} for w in sorted(set(weeks.values()))]
    for link in links:
        touched = [g for g in groups if g & {weeks[link["left"]], weeks[link["right"]]}]
        if len(touched) == 2:
            touched[0].update(touched[1])
            groups.remove(touched[1])
    return [[d for d in days if weeks[d["date"]] in g] for g in groups]


class Period:
    def __init__(self, days, prices, *, warehouse_release_min=None):
        release = RELEASE if warehouse_release_min is None else warehouse_release_min
        self.days = days
        self.prices = prices
        self.chains, self.links, self.breaks = calendar(days)
        origin = date.fromisoformat(days[0]["date"])
        self.offset = {d["date"]: 1440 * (date.fromisoformat(d["date"]) - origin).days for d in days}
        self.cases = {d["date"]: build_case(d, release) for d in days if d["availability"] == "complete_tasks"}
        self.keys = {(d, v) for d, case in self.cases.items() for v in case["trucks"]}
        # Reassemble released dwell bounds by the original arrival record. Each day's
        # event grid still splits the merged window at midnight for accounting.
        self.windows = defaultdict(list)
        self.nights = []
        for day in days:
            d = day["date"]
            if d not in self.cases:
                continue
            offset = self.offset[d]
            origin_time = datetime.fromisoformat(day["start"])
            for truck in day["vehicles"]:
                v = truck["vehicle_id"]
                for stop in truck["stops"]:
                    def minute(field):
                        return (datetime.fromisoformat(stop[field]) - origin_time) / timedelta(minutes=1)
                    site = stop["site"]
                    a = max(minute("start"), minute("arrival") + (release if site == "WAREHOUSE" else 0))
                    b = minute("end")
                    if a >= b:
                        continue
                    key = v, site, stop["arrival_track_id"]
                    parts = self.windows[key]
                    if parts and parts[-1][1] == offset+a:
                        parts[-1] = (parts[-1][0], offset+b)
                    else:
                        parts.append((offset+a, offset+b))
                    if minute("arrival") < 0 or minute("next_departure") > 1440:
                        self.nights.append(((d,v), site, offset+a, offset+b,
                                            "after" if minute("arrival") < 0 else "before"))


class Matrix:
    def __init__(self):
        self.lower, self.upper, self.cost, self.integer = [], [], [], []
        self.row, self.col, self.data, self.lb, self.ub = [], [], [], [], []

    def var(self, low, high, cost=0., integer=False):
        self.lower.append(low)
        self.upper.append(high)
        self.cost.append(cost)
        self.integer.append(integer)
        return len(self.cost)-1

    def add(self, terms, low=-np.inf, high=np.inf):
        for i, coef in terms:
            self.row.append(len(self.lb))
            self.col.append(i)
            self.data.append(coef)
        self.lb.append(low)
        self.ub.append(high)

    def solve(self):
        mat = coo_matrix((self.data, (self.row,self.col)), shape=(len(self.lb),len(self.cost))).tocsr()
        # SciPy forwards native HiGHS options to the backend. Tight feasibility
        # is needed when converting short-interval energy back to instantaneous kW.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Unrecognized options detected.*", category=RuntimeWarning)
            return milp(self.cost, integrality=self.integer, bounds=Bounds(self.lower,self.upper),
                        constraints=LinearConstraint(mat,self.lb,self.ub),
                        options={"mip_rel_gap":0., "mip_feasibility_tolerance":1e-9,
                                 "primal_feasibility_tolerance":1e-9})


def blocks(case, site, hardware, spec, *, unpooled=()):
    """Pool identical whole quarters within one hour. Integer reservation counts
    unpack by round robin when every connector can simultaneously supply truck_kw.
    A quarter with an internal event always retains its exact subintervals.
    """
    spans = defaultdict(list)
    for a,b,available in _events(case):
        spans[int(a//15)].append((a,b,tuple(sorted(available[site]))))
    def signature(item):
        q, parts = item
        if q not in unpooled and len(parts)==1 and hardware["power_kw"] >= hardware["interfaces"]*spec.truck_kw:
            return q//4, parts[0][2]
        return (q,)
    for _, group in groupby(spans.items(), signature):
        group = list(group)
        parts = group[0][1]
        yield len(group), parts


def reservation_slots(count, reservations, solution):
    """Assign interchangeable whole quarters to reserved trucks in round-robin order."""
    cursor = 0
    slots = {}
    for truck, column in reservations.items():
        number = round(solution[column])
        slots[truck] = [(cursor + j) % count for j in range(number)]
        cursor += number
    return slots


def solve(p, hw, spec, rule, fixed=None):
    """fixed=None maximizes physical service. Otherwise only the supplied duties participate."""
    start = perf_counter()
    model = Matrix()
    levels, pieces, charged = {}, [], defaultdict(list)
    cap, reserve, e0 = spec.capacity_kwh, spec.reserve_kwh, spec.boundary_kwh
    active = p.keys if fixed is None else set(fixed)
    if not active <= p.keys or rule not in (A,B,C):
        raise ValueError("Unknown duty or rule")
    for key in sorted(active):
        s = model.var(int(fixed is not None),1,-1 if fixed is None else 0, fixed is None)
        lo, hi = (e0,e0) if rule==A else (reserve,cap) if rule==C else (0,cap)
        x,y = model.var(lo,hi),model.var(lo,hi)
        levels[key] = s,x,y
        if rule==C:
            model.add([(x,1),(y,-1)],0,0)
    def pin(i, other=None):
        if other is None:
            model.add([(i,1)],e0,e0)
        else:
            model.add([(i,1),(other,-cap)],high=e0)
            model.add([(i,1),(other,cap)],low=e0)
    if rule==B:
        for chain in p.chains:
            for j,key in enumerate(chain):
                if key not in active:
                    continue
                s,x,y = levels[key]
                pin(x,s)
                pin(y,s)
                prev = levels.get(chain[j-1]) if j else None
                nxt = levels.get(chain[j+1]) if j+1<len(chain) else None
                pin(x,prev[0] if prev else None)
                pin(y,nxt[0] if nxt else None)
                if nxt:
                    for sign in (-1,1):
                        model.add([(y,sign),(nxt[1],-sign),(s,cap),(nxt[0],cap)],high=2*cap)
    for d,case in p.cases.items():
        case = subset_case(case,[v for v in case["trucks"] if (d,v) in active])
        for site in SITES:
            h = hw[site]
            n = h["interfaces"]
            rate = min(spec.truck_kw,h["power_kw"])
            if n==0 or rate==0:
                continue
            for count,parts in blocks(case,site,h,spec):
                vs = sorted({v for _,_,vehicles in parts for v in vehicles})
                reservations = {}
                if len(vs)>n:
                    reservations = {v:model.var(0,count,integer=True) for v in vs}
                    model.add([(i,1) for i in reservations.values()],high=n*count)
                decisions = []
                for a,b,vehicles in parts:
                    duration = (b-a)/60
                    terms = []
                    for v in vehicles:
                        cost = 0 if fixed is None else p.prices[d][int(a//60)]/1000
                        i = model.var(0,rate*duration*count,cost)
                        terms.append((i,1))
                        charged[d,v].append((b+15*(count-1),i))
                        decisions.append((a,b,v,i))
                        if reservations:
                            model.add([(i,1),(reservations[v],-rate*duration)],high=0)
                    if terms:
                        model.add(terms,high=h["power_kw"]*duration*count)
                pieces.append((d,site,count,reservations,decisions))
        for v,t in case["trucks"].items():
            key = d,v
            s,x,y = levels[key]
            def balance(time,draw):
                return [(x,1),(s,-draw)] + [(i,spec.efficiency) for end,i in charged[key] if end<=time]
            draw = 0.
            for a,b,e,_ in t["trips"]:
                model.add(balance(a,draw),reserve,cap)
                draw += e
                model.add(balance(b,draw),reserve,cap)
            model.add(balance(1440,draw)+[(y,-1)],0,0)
    if not levels:
        model.var(0,0)
    res = model.solve()
    stats = dict(status=res.message, status_code=res.status, gap=getattr(res,"mip_gap",None),
                 seconds=perf_counter()-start, objective=res.fun, dual_bound=getattr(res,"mip_dual_bound",None))
    if res.status!=0:
        raise ValueError(f"{rule} fixed={fixed} {stats}")
    rows = []
    for d,site,count,reservations,decisions in pieces:
        slots = reservation_slots(count, reservations, res.x)
        for a,b,v,i in decisions:
            energy = res.x[i]
            if energy <= 1e-10:
                continue
            assigned = slots.get(v,range(count))
            if not assigned:
                if energy > UNRESERVED_ENERGY_TOLERANCE_KWH:
                    raise ValueError(("positive energy without reservation",d,v,energy))
                continue
            power = energy*60/((b-a)*len(assigned))
            for j in assigned:
                left = p.offset[d]+a+15*j
                rows.append(dict(date=d,vehicle_id=v,site=site,start_min=left,
                                 end_min=p.offset[d]+b+15*j,reservation_slot=int(left//15),power_kw=power))
    states = [dict(date=d,vehicle_id=v,served=res.x[s]>.5,x=float(res.x[x]),y=float(res.x[y]))
              for (d,v),(s,x,y) in levels.items()]
    for r in states:
        r["served"] = bool(r["served"])
    result = dict(stats=stats,states=states,schedule=rows)
    result["audit"] = audit(p,hw,spec,rule,result,physical=fixed is None)
    return result

def audit(p,hw,spec,rule,result,physical=False):
    """Replay positive power independently of optimization variables and rows."""
    states = {(r["date"],r["vehicle_id"]):r for r in result["states"]}
    loads,vehicle_intervals,reserved = defaultdict(lambda:defaultdict(float)),defaultdict(list),defaultdict(set)
    bills,grid = defaultdict(float),defaultdict(float)
    nights = defaultdict(lambda:dict(before=0.,after=0.))
    def require(ok,detail):
        if not ok:
            raise ValueError(f"Replay failed: {detail}")
    def close(a,b,detail):
        require(abs(a-b)<=EPS,(detail,a,b))
    for row in result["schedule"]:
        d,v,site = row["date"],row["vehicle_id"],row["site"]
        key = d,v
        a,b,kw,q = (row[k] for k in ("start_min","end_min","power_kw","reservation_slot"))
        require(key in states and states[key]["served"] and site in SITES, ("inactive",row))
        require(0<kw<=spec.truck_kw+EPS and q*15<=a<b<=(q+1)*15 and
                p.offset[d]<=a<b<=p.offset[d]+1440,("row",row))
        require(any(left<=a and b<=right for (truck,s,_),parts in p.windows.items()
                    if (truck,s)==(v,site) for left,right in parts),("window",row))
        reserved[site,q].add(v)
        require(len(reserved[site,q])<=hw[site]["interfaces"],("connectors",site,q))
        loads[site][a] += kw
        loads[site][b] -= kw
        energy = kw*(b-a)/60
        vehicle_intervals[key].append((a,b,energy))
        grid[key] += energy
        for hour in range(int((a-p.offset[d])//60),math.ceil((b-p.offset[d])/60)):
            left = p.offset[d]+60*hour
            bills[d] += kw*(min(b,left+60)-max(a,left))/60*p.prices[d][hour]/1000
        for duty,s,left,right,side in p.nights:
            if duty==key and s==site:
                nights[key][side] += kw*max(0,min(right,b)-max(left,a))/60
    peaks = {}
    for s in SITES:
        level = peak = 0.
        for t,delta in sorted(loads[s].items()):
            level += delta
            peak = max(peak,level)
        require(peak<=hw[s]["power_kw"]+EPS,("site kW",s,peak))
        peaks[s] = peak
    draws = {}
    for (d,v),r in states.items():
        key = d,v
        x,y = r["x"],r["y"]
        lower = spec.reserve_kwh if rule==C else 0.
        require(all(lower-EPS<=e<=spec.capacity_kwh+EPS for e in (x,y)),("boundary range",key))
        if rule==A or (rule==B and not r["served"]):
            for e in (x,y):
                close(e,spec.boundary_kwh,key)
        if rule==C:
            close(x,y,key)
        power = sorted(vehicle_intervals[key])
        require(all(a[1]<=b[0] for a,b in zip(power,power[1:])),("double charging",key))
        draw = 0.
        for a,b,e,_ in p.cases[d]["trucks"][v]["trips"]:
            for t,debit in ((a,0.),(b,e)):
                draw += debit*r["served"]
                level = x+spec.efficiency*sum(k for _,end,k in power if end<=p.offset[d]+t)-draw
                require(spec.reserve_kwh-EPS<=level<=spec.capacity_kwh+EPS,("trip SOC",key,t,level))
        draws[key] = draw
        close(y,x+spec.efficiency*grid[key]-draw,("day conservation",key))
    segments = []
    for chain in p.chains:
        for served,items in groupby(chain,lambda k:k in states and states[k]["served"]):
            if not served:
                continue
            keys = list(items)
            for segment in ([keys] if rule==B else [[k] for k in keys]):
                start,end = states[segment[0]]["x"],states[segment[-1]]["y"]
                if rule==B:
                    close(start,spec.boundary_kwh,("chain start",segment))
                    close(end,spec.boundary_kwh,("chain end",segment))
                    for left,right in zip(segment,segment[1:]):
                        close(states[left]["y"],states[right]["x"],("midnight",right))
                residual = end-start-spec.efficiency*sum(grid[k] for k in segment)+sum(draws[k] for k in segment)
                close(residual,0.,("chain conservation",segment))
                segments.append(dict(keys=segment,start=start,end=end,residual_kwh=residual))
    bill = sum(bills.values())
    close(result["stats"]["objective"],-sum(r["served"] for r in states.values()) if physical else bill,"objective")
    return dict(passed=True,segments=segments,purchase_eur=bill,daily_eur=dict(bills),site_peak_kw=peaks,
                night=[dict(date=d,vehicle_id=v,**nights[d,v]) for d,v in sorted(states)])


def selected(result):
    return {(r["date"],r["vehicle_id"]) for r in result["states"] if r["served"]}


def pilot_runs(days,prices,hw,log):
    pilots = {}
    for name,v,start in (("P1","5","2021-09-27"),("P2","3","2021-10-20")):
        group = [{**d,"vehicles":[r for r in d["vehicles"] if r["vehicle_id"]==v]}
                 for d in days if 0<=(date.fromisoformat(d["date"])-date.fromisoformat(start)).days<3]
        p = Period(group,prices)
        if len(p.chains)!=1 or len(p.chains[0])!=3:
            raise ValueError(f"Pilot chain changed: {p.chains}")
        pilots[name] = {}
        for rule in (A,B,C):
            first = solve(p,hw,DEFAULT_SPEC,rule)
            final = solve(p,hw,DEFAULT_SPEC,rule,selected(first))
            log(name+"-"+rule,[first,final])
            daily = []
            for key in p.chains[0]:
                d,_ = key
                state = next((r for r in final["states"] if r["date"]==d),
                             next(r for r in first["states"] if r["date"]==d))
                night = next((r for r in final["audit"]["night"] if r["date"]==d),dict(before=0.,after=0.))
                row = dict(**state,night_before_kwh=night["before"],night_after_kwh=night["after"],
                           bill=final["audit"]["daily_eur"].get(d,0.))
                if rule==A:
                    old = dispatch(p.cases[d],hw,prices[d])
                    log(name+"-daily-"+d,old)
                    require_optimal = old["status"]=="optimal"
                    if require_optimal != state["served"]:
                        raise ValueError(("pilot dispatch status",key,old["status"]))
                    row["legacy_status"] = old["status"]
                    if require_optimal:
                        legacy = old["audit"]["purchase_eur"]
                        row.update(legacy_eur=legacy,delta_eur=row["bill"]-legacy,
                                   bill_bit_equal=row["bill"].hex()==legacy.hex(),
                                   legacy_peak_kw=old["audit"]["site_peak_kw"])
                        rows = [dict(vehicle_id=r["vehicle_id"],site=r["site"],
                                     start_min=r["start_min"]-p.offset[d],end_min=r["end_min"]-p.offset[d],
                                     reservation_slot=r["reservation_slot"]-p.offset[d]//15,power_kw=r["power_kw"])
                                for r in final["schedule"] if r["date"]==d]
                        row["schedule_exact_equal"] = rows==old["schedule"]
                        if abs(row["delta_eur"])>EPS:
                            raise ValueError(row)
                daily.append(row)
            pilots[name][rule] = dict(daily=daily,**final,physical_stats=first["stats"])
            if rule == A:
                legacy = sum(r.get("legacy_eur",0.) for r in daily)
                joint = final["audit"]["purchase_eur"]
                pilots[name][A]["daily_dispatch_sum"] = dict(joint_hex=joint.hex(),legacy_hex=legacy.hex(),
                    delta_eur=joint-legacy,bit_equal=joint.hex()==legacy.hex())
    return pilots


def run(pilot=False,output=None):
    days = read_json(WEEKS)["days"]
    ref = read_json(REFERENCE)
    hw = ref["hardware"]
    records = csv_rows(NATIVE)
    prices = {d["date"]:hourly_curve(records,d) for d in days if d["availability"]=="complete_tasks"}
    chains,links,breaks = calendar(days)
    groups = components(days,links)
    def log(label,result):
        if output:
            write_json(output/(label+".json"),result)
    summary = dict(source=dict(commit=subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],
                         text=True).strip(),dirty=bool(subprocess.check_output(["git","-C",str(ROOT),"status","--porcelain"]))),
        inputs_sha256={f.relative_to(ROOT).as_posix():digest(f) for f in (WEEKS,REFERENCE,NATIVE,GAP)},
        python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,hardware=hw,
        specs={k:asdict(v) for k,v in SPECS.items()},chains=chains,links=links,breaks=breaks,
        module_sha256=digest(Path(__file__)),excluded_or_unobserved=[
            {k:d[k] for k in ("date","other_observed_vehicle_days_excluded","unobserved_vehicle_ids")}
            for d in days], components=[sorted({d["week_start"] for d in g}) for g in groups],price_information=
        "DE-LU, Europe/Berlin, native EUR/MWh, historical perfect foresight over the solve period; "
        "carry_over knows prices of every day of the chain. Bills in EUR over supplied dates.",
        assumptions="Warehouse release 45 min from arrival. Unserved duties split carry_over at E0. "
        "C repeats independent representative days. Night grid kWh include clipped overnight stops at sample edges.",
        pilots=pilot_runs(days,prices,hw["one"],log),full=[],checks={})
    if pilot:
        summary["checks"] = dict(pilot_service_and_cost=True,pilot_replay=True)
        return summary
    periods = [Period(g,prices) for g in groups]
    reference = {r["date"]:r for r in ref["days"] if r["date"] in prices}
    historical = next(r for r in read_json(GAP)["fleet"] if r["capacity_kwh"]==900)
    checks = summary["checks"]
    for specname,spec in SPECS.items():
        for facility,h in hw.items():
            runs = {rule:[] for rule in (A,B,C)}
            scope = specname+"-"+facility
            for idx,p in enumerate(periods):
                results,sets = {},{}
                for rule in runs:
                    first = solve(p,h,spec,rule)
                    keys = selected(first)
                    final = solve(p,h,spec,rule,keys)
                    log(f"{scope}-{idx}-{rule}-physical",[first,final])
                    sets[rule] = keys
                    results[rule] = first,final
                common = set.intersection(*sets.values())
                if len(sets[B])<len(sets[A]):
                    raise ValueError(("physical dominance",scope,idx,sets))
                for rule,(first,final) in results.items():
                    paired = final if common==sets[rule] else solve(p,h,spec,rule,common)
                    log(f"{scope}-{idx}-{rule}-common",paired)
                    runs[rule].append(dict(selected=sorted(sets[rule]),common=sorted(common),
                        common_eur=paired["audit"]["purchase_eur"],common_audit=paired["audit"],
                        states=final["states"],physical_states=first["states"],
                        audit=final["audit"],stats=[r["stats"] for r in (first,final,paired)],
                        added=sorted(sets[rule]-sets[A]),removed=sorted(sets[A]-sets[rule])))
                if runs[B][-1]["common_eur"]>runs[A][-1]["common_eur"]+EPS:
                    raise ValueError(("cost dominance",scope,idx,sorted(common),runs[B][-1],runs[A][-1]))
                if specname=="S300":
                    matched = {(d,v) for d in p.cases for v in reference[d]["matched_ids"]}
                    fixed = solve(p,h,spec,A,matched)
                    log(f"{scope}-{idx}-matched",fixed)
                    for d in p.cases:
                        old = reference[d]
                        count = sum(k[0]==d for k in sets[A])
                        if count!=old["facilities"][facility]["max_vehicle_days"]:
                            raise ValueError(("daily service",d,facility,count))
                        bill = fixed["audit"]["daily_eur"].get(d,0.)
                        euro = old["prices"]["concurrent"][facility]["optimal_eur"] if old["matched_ids"] else None
                        if abs(bill-(euro or 0.))>EPS:
                            raise ValueError(("matched price",d,facility,bill,euro))
                        checks.setdefault("matched_days",[]).append(dict(date=d,facility=facility,count=count,
                            expected_eur=euro,actual_eur=bill,stats=fixed["stats"]))
            for rule,weeks in runs.items():
                count = sum(len(w["selected"]) for w in weeks)
                if rule==A and ((specname=="S300" and count!=54) or
                                (specname=="S900c" and count!=historical[facility])):
                    raise ValueError(("total",scope,count))
                row = dict(spec=specname,facility=facility,rule=rule,completed=count,weeks=weeks,
                    common_count=sum(len(w["common"]) for w in weeks),
                    common_eur=sum(w["common_eur"] for w in weeks),
                    delta_eur=sum(w["common_eur"]-a["common_eur"] for w,a in zip(weeks,runs[A])),
                    night_kwh=sum(n["before"]+n["after"] for w in weeks for n in w["audit"]["night"]),
                    peaks={s:max(w["audit"]["site_peak_kw"][s] for w in weeks) for s in SITES})
                statistics = [st for w in weeks for st in w["stats"][:2]]
                statistics.extend(w["stats"][2] for w in weeks if w["common"]!=w["selected"])
                row["solver_seconds"] = sum(st["seconds"] for st in statistics)
                row["reported_gaps"] = [st["gap"] for st in statistics]
                row["midnight_kwh"] = {side:[r[side] for w in weeks for r in w["states"]]
                                       for side in ("x","y")}
                summary["full"].append(row)
                gaps = [g for g in row["reported_gaps"] if g is not None]
                max_gap = max(gaps, default=None)
                print(f"{specname} {facility} {rule} served={count}/73 common={row['common_count']} "
                      f"common_EUR={row['common_eur']:.6f} delta_EUR={row['delta_eur']:.6f} "
                      f"night_kWh={row['night_kwh']:.3f} peak_kW={row['peaks']['PORT']:.1f}/{row['peaks']['WAREHOUSE']:.1f} "
                      f"status=optimal max_reported_gap={max_gap} solve_s={row['solver_seconds']:.3f}",flush=True)
    checks.update(daily_service=True,matched_cost=True,scaled_900=True,physical_dominance=True,
                  common_cost_dominance=True,all_audited=True,optimal=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot",action="store_true")
    parser.add_argument("--summary",type=Path)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    output = checked_output(args.output,ROOT) if args.output else None
    if output:
        if subprocess.check_output(["git","-C",str(ROOT),"status","--porcelain"]).strip():
            raise ValueError("--output requires a clean committed source tree")
        output.mkdir(parents=True)
    result = run(args.pilot,output)
    if args.pilot:
        print("pilot rule date vehicle served start_kWh end_kWh night_before_kWh night_after_kWh EUR")
        for name,rules in result["pilots"].items():
            for rule,run_data in rules.items():
                for r in run_data["daily"]:
                    print(name,rule,r["date"],r["vehicle_id"],int(r["served"]),
                          *(f"{r[k]:.6f}" for k in ("x","y","night_before_kwh","night_after_kwh","bill")))
        print("pilot rule first_x last_y total_EUR peak_PORT_kW peak_WAREHOUSE_kW max_abs_residual_kWh")
        for name,rules in result["pilots"].items():
            for rule,r in rules.items():
                a = r["audit"]
                values = (r["daily"][0]["x"],r["daily"][-1]["y"],a["purchase_eur"],
                          *(a["site_peak_kw"][s] for s in SITES))
                residual = max(abs(s["residual_kwh"]) for s in a["segments"])
                print(name,rule,*(f"{v:.6f}" for v in values),f"{residual:.3e}")
        print("pilot A date new_EUR legacy_EUR delta_EUR bill_bits_equal schedule_exact_equal")
        for name,rules in result["pilots"].items():
            for r in rules[A]["daily"]:
                print(name,"A",r["date"],repr(r["bill"]),repr(r["legacy_eur"]),
                      f"{r['delta_eur']:.3e}",r["bill_bit_equal"],r["schedule_exact_equal"])
            c = rules[A]["daily_dispatch_sum"]
            print(name,"A sum",c["joint_hex"],c["legacy_hex"],f"{c['delta_eur']:.3e}",c["bit_equal"])
    if args.summary:
        write_json(args.summary,result)
    if output:
        write_json(output/"summary.json",result)


if __name__=="__main__":
    main()


