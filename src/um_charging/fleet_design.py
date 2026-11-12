"""Choose fixed hardware on design vehicle-days and replay it on subsequent days."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
from statistics import median
import subprocess
from time import perf_counter

import scipy

from .__main__ import checked_output
from .changeover_study import hardware_key
from .day_ahead import ROOT
from .fleet_service import (
    BOUNDARY_KWH, CAPACITY_KWH, EFFICIENCY, RESERVE_KWH, TRUCK_KW, build_case,
    dispatch, max_service, menu,
)


def typical_day(design_days):
    if not design_days or any(d["split"] != "design" for d in design_days):
        raise ValueError("Select the typical day using design dates alone")
    energy = {d["date"]: sum(t["energy_kwh"] for v in d["vehicles"] for t in v["trips"]) for d in design_days}
    target = median(energy.values())
    return min(design_days,key=lambda d: (round(abs(energy[d["date"]]-target),9),d["date"]))


def _dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n",encoding="utf-8")


def select_build(days, releases, port_additions_only=False, evidence=None):
    """First maximize covered whole vehicle-days, then minimize synthetic investment.

    Maximum menu hardware contains every allowed build. Its per-scenario maxima
    give a joint upper bound, attained by installing that same hardware once.
    """
    if not days or not releases or any(d["split"] != "design" for d in days):
        raise ValueError("Facility selection uses design days and predeclared release scenarios only")
    if len({d["date"] for d in days}) != len(days) or len(set(releases)) != len(releases):
        raise ValueError("Duplicate design scope")
    if evidence is not None:
        evidence = Path(evidence); evidence.mkdir()
    scenarios = sorted([build_case(d,r) for r in releases for d in days],
                       key=lambda c:(-c["warehouse_release_min"],-len(c["trucks"]),c["date"]))
    options = [(cost,h) for cost,h in menu() if not port_additions_only or h["WAREHOUSE"] == {"interfaces":1,"power_kw":75}]
    largest = {s: {field:max(h[s][field] for _,h in options) for field in ("interfaces","power_kw")} for s in ("PORT","WAREHOUSE")}
    cache, elapsed = {}, []
    def solve_once(i,h,partial):
        key=(i,hardware_key(h),partial)
        if key not in cache:
            case=scenarios[i]
            res=(max_service if partial else dispatch)(case,h)
            cache[key]=(res["completed_count"],res["status"],res["mip_gap"])
            elapsed.append(res["seconds"])
            if evidence is not None:
                _dump(evidence/f"solve_{len(cache):05d}.json",{"date":case["date"],"release":case["warehouse_release_min"],
                                                             "hardware":h,"partial":partial,"result":res})
        return cache[key]
    goals=[]
    for i,case in enumerate(scenarios):
        count,status,_=solve_once(i,largest,False)
        if status=="infeasible":
            count,_,_=solve_once(i,largest,True)
        goals.append(count)
    winners=[]; tried=[]; investment=None
    for cost,h in options:
        if investment is not None and cost>investment:
            break
        failed=None
        for i,case in enumerate(scenarios):
            if goals[i] == 0:
                continue
            count,status,_=solve_once(i,h,goals[i]<len(case["trucks"]))
            if count<goals[i]:
                failed={"date":case["date"],"release_min":case["warehouse_release_min"],
                        "required_vehicle_days":goals[i],"full_dispatch_status":status,
                        "completion_gap_proved":True}
                break
        tried.append({"hardware":h,"investment":cost,"first_failure":failed})
        if failed is None:
            investment=cost; winners.append(h)
    if not winners: raise RuntimeError("The maximal build did not attain its own coverage bound")
    requested=sum(len(c["trucks"]) for c in scenarios)
    result={"investment":investment,"hardware":winners[0],"ties":winners,
            "full_coverage_possible":sum(goals)==requested,"covered_vehicle_day_scenarios":sum(goals),
            "requested_vehicle_day_scenarios":requested,"menu_size":len(options),"examined_builds":len(tried),
            "unexamined_strictly_costlier":len(options)-len(tried),"optimization_calls":len(cache),
            "solve_seconds":sum(elapsed),"slowest_solve_seconds":max(elapsed,default=0.),
            "max_reported_gap":max((g for _,_,g in cache.values() if g is not None),default=0.),
            "scenarios":[{"date":c["date"],"release_min":c["warehouse_release_min"],
                          "requested":len(c["trucks"]),"max_complete":n,
                          "maximal_build_failure":failure_reasons(c,largest) if n<len(c["trucks"]) else []}
                         for c,n in zip(scenarios,goals)]}
    if evidence is not None: _dump(evidence/"menu.json",tried)
    return result


def failure_reasons(case,hardware):
    """Translate a failed joint dispatch into single-truck reachability or contention evidence."""
    failures=[]
    for v,t in case["trucks"].items():
        # Single-truck reachable SOC is a closed interval: a stop extends its
        # upper endpoint, and the subsequent signed leg shifts both endpoints.
        events=[(a,0,b,s) for a,b,s in t["windows"]]+[(a,1,b,e) for a,b,e,_ in t["trips"]]
        low=high=BOUNDARY_KWH
        for a,is_trip,b,quantity in sorted(events):
            if not is_trip:
                site=hardware[quantity]
                if site["interfaces"]:
                    high=min(CAPACITY_KWH,high+(b-a)/60*min(TRUCK_KW,site["power_kw"])*EFFICIENCY)
            else:
                low=max(RESERVE_KWH, low-quantity); high=min(CAPACITY_KWH,high-quantity)
                if low>high+1e-6:
                    trip_id=next(track for start,end,_,track in t["trips"] if (start,end)==(a,b))
                    failures.append({"vehicle_id":v,"cause":"single_truck_leg_boundary","track_id":trip_id,"trip_end_min":b,
                                     "reachable_raw_upper_kwh":high,"required_min_kwh":low})
                    break
        else:
            if not (low-1e-6<=BOUNDARY_KWH<=high+1e-6):
                failures.append({"vehicle_id":v,"cause":"single_truck_terminal_energy",
                                 "reachable_terminal_interval_kwh":[low,high],"required_terminal_kwh":BOUNDARY_KWH})
    return failures or [{"cause":"shared_connectors_or_site_power",
                         "evidence":"Every truck is individually reachable under its windows; the complete joint schedule is infeasible."}]


def replay_days(days,releases,hardware,evidence=None):
    rows=[]
    if evidence is not None: evidence.mkdir()
    for d in days:
        for r in releases:
            case=build_case(d,r)
            full=dispatch(case,hardware)
            reasons=[]
            if full["status"]=="optimal":
                partial=full
            else:
                reasons=failure_reasons(case,hardware)
                partial=max_service(case,hardware)
            rows.append({"date":d["date"],"release_min":r,"status":full["status"],
                         "requested_vehicle_days":len(case["trucks"]),"completed_vehicle_days":partial["completed_count"],
                         "completed_ids":partial["selected_ids"],"failure_reasons":reasons,
                         "full_gap":full["mip_gap"],"service_gap":partial["mip_gap"],"solve_seconds":full["seconds"]+
                         (partial["seconds"] if partial is not full else 0.)})
            if evidence is not None:
                _dump(evidence/f"{d['date']}_{r}.json",{"full_dispatch":full,"maximum_service":partial if partial is not full else None})
    return rows


def check_spatial_break(design, selected, output):
    """Veto eligibility at the audited 4423 -> 4425 discontinuity, retaining both trips."""
    modified=deepcopy(design)
    day, = (d for d in modified if d["date"]=="2021-09-17")
    vehicle, = (v for v in day["vehicles"] if v["vehicle_id"]=="3")
    removed, = (s for s in vehicle["stops"] if (s["arrival_track_id"],s["next_track_id"])==("4423","4425"))
    vehicle["stops"].remove(removed)
    _, largest=menu()[-1]
    hardware=selected["hardware"]
    rows=[]
    for delay in (0,45):
        case=build_case(day,delay)
        for name,build in (("selected",hardware),("maximal",largest)):
            res=max_service(case,build)
            rows.append({"release_min":delay,"build":name,"completed":res["completed_count"],
                         "requested":len(case["trucks"]),"gap":res["mip_gap"],"audit":res["audit"]["passed"]})
            if output:
                _dump(output/f"spatial_veto_{name}_{delay}.json",res)
    original = {s["release_min"]:s["max_complete"] for s in selected["scenarios"] if s["date"]==day["date"]}
    retained=all(x["completed"]==y["completed"]==original[x["release_min"]]
                 for x,y in zip(rows[::2],rows[1::2]))
    design_result=selected if retained else select_build(modified,[0,45],evidence=output/"veto_design" if output else None)
    return {"vehicle_id":"3","date":day["date"],"arrival_track_id":"4423","next_track_id":"4425",
            "removed_site":removed["site"],"selection_retained":retained,"investment":design_result["investment"],
            "hardware":design_result["hardware"],"checks":rows}


def run(duties_path,output=None):
    t0=perf_counter()
    data=json.loads(Path(duties_path).read_text(encoding="utf-8-sig"))
    days=data["days"]; design=[d for d in days if d["split"]=="design"]; holdout=[d for d in days if d["split"]=="holdout"]
    if not design or not holdout or max(d["date"] for d in design)>=min(d["date"] for d in holdout):
        raise ValueError("Require temporally separated design and holdout days")
    if output is not None:
        dirty = subprocess.check_output(["git","-C",str(ROOT),"status","--porcelain"], encoding="utf-8")
        if dirty.strip():
            raise ValueError("Commit the source and input before recording a canonical fleet run")
        output=checked_output(Path(output),ROOT);output.mkdir(parents=True)
    selected={}
    for label,releases in (("immediate_release_design",[0]),("shared_release_design",[0,45])):
        picked=select_build(design,releases,evidence=output/label if output else None)
        picked["holdout"]=replay_days(holdout,[0,45],picked["hardware"],output/(label+"_holdout") if output else None)
        selected[label]=picked
    scaling=[]
    for n in sorted({1,min(3,len(design)),len(design)}):
        prefix=sorted(design,key=lambda d:d["date"])[:n]
        solved=(selected["shared_release_design"] if n==len(design) else
                select_build(prefix,[0,45],evidence=output/f"scale_{n}" if output else None))
        scaling.append({"design_dates":n,"vehicle_days":sum(len(d["vehicles"]) for d in prefix),
                        "trips":sum(len(v["trips"]) for d in prefix for v in d["vehicles"]),
                        **{k:solved[k] for k in ("investment","optimization_calls","solve_seconds","slowest_solve_seconds",
                                                 "max_reported_gap","covered_vehicle_day_scenarios","requested_vehicle_day_scenarios")}})
    result={"duties_sha256":hashlib.sha256(Path(duties_path).read_bytes()).hexdigest(),
            "investment_config_sha256":hashlib.sha256((ROOT/"configs/port_warehouse_investment.json").read_bytes()).hexdigest(),
            "source_commit":subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip(),
            "assumptions":{"boundaries_kwh":BOUNDARY_KWH,"capacity_kwh":CAPACITY_KWH,"reserve_kwh":RESERVE_KWH,
                           "truck_grid_kw":TRUCK_KW,"efficiency":EFFICIENCY,"release_min":[0,45],
                           "connector_reservation_min":15,"changeover_min":0},
            "design_dates":[d["date"] for d in design],"holdout_dates":[d["date"] for d in holdout],
            "typical_date":typical_day(design)["date"],"scale_comparison":scaling,"designs":selected,
            "audited_gap_veto":check_spatial_break(design,selected["shared_release_design"],output),
            "wall_seconds":perf_counter()-t0}
    if output:
        _dump(output/"environment.json",{"python":platform.python_version(),"scipy":scipy.__version__,
                                         "utc":datetime.now(timezone.utc).isoformat()})
        _dump(output/"result.json",result)
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duties",type=Path,default=ROOT/"studies/fleet-service/duties.json")
    parser.add_argument("--output",type=Path,help="Fresh directory in the existing offline Git")
    args=parser.parse_args()
    print(json.dumps(run(args.duties,args.output),indent=2,allow_nan=False))
