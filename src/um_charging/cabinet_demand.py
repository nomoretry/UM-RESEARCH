"""Value the second port connector on the registered, identical fleet service."""
import argparse
from collections import defaultdict
from dataclasses import asdict
import json
import math
import multiprocessing
from pathlib import Path
import platform
import subprocess
from time import perf_counter
import traceback

import numpy as np
import scipy

from . import energy_boundary as eb
from .__main__ import checked_output, digest, write_json
from .cabinet_audit import audit_cabinets, audit_settlement, close, replay, schedule_on_clock
from .cabinet_model import EQUIPMENT, relaxation, solve
from .cabinet_partial import partial_e1_bound
from .cabinet_shared import shared_peak_witness
from .cabinet_incumbent import build_incumbent, e1_peak_witness, high_band_interval, low_band_interval, polish_e1
from .cabinet_tariff import NETWORK_INPUT, annual_factors, fixed_dispatch_zero, load_network, settle
from .cabinet_threshold import certify_p2, gain_interval
from .connector_cost import COST_INPUT, break_even


BASELINE = eb.WEEKS.with_name("energy_boundary.json")
PILOT_DAY = "2021-10-26"
BOUNDED_RATE = 80.
MAX_COMBINATION_SECONDS = 45 * 60
# Extra witnesses only tighten a continuous-price certificate. The registered
# equipment bills have already been solved and do not depend on these trials.
AUXILIARY_WITNESS_SECONDS = 30.


def decision_record(lower, upper, seconds, *, bounded=False):
    """Record an annual dispatch objective and its proved global lower bound."""
    if not all(math.isfinite(v) for v in (lower, upper, seconds)) or seconds < 0 or lower > upper + 1e-8:
        raise ValueError(("Invalid dispatch bounds or elapsed time", lower, upper, seconds))
    gap = max(0., upper - lower)
    if bounded and (gap > 1. + 1e-8 or seconds > MAX_COMBINATION_SECONDS):
        raise ValueError(("Decision precision or wall-clock limit exceeded", lower, upper, seconds))
    return dict(status="bounded" if bounded else "optimal", objective_lower_eur_2025=min(lower, upper),
                objective_upper_eur_2025=upper, absolute_gap_eur_2025=gap,
                relative_gap=gap / max(abs(upper), 1e-10), wall_seconds=seconds)


def classify_decision_bounds(lower, upper, cost):
    """Stop if the full-invoice savings interval cannot decide sign or investment."""
    if not all(math.isfinite(v) for v in (lower, upper, cost)) or lower > upper:
        raise ValueError(("Invalid operating-value interval", lower, upper, cost))
    if lower <= 0 <= upper or lower <= cost <= upper:
        raise ValueError(("Inconclusive operating or investment decision", lower, upper, cost))
    return dict(sign="positive" if lower > 0 else "negative", cost_comparison="below" if upper < cost else "above")


def invoice_line(row):
    def fmt(value, bounds):
        return f"{value:.2f}" if value is not None else f"[{bounds[0]:.6f}, {bounds[1]:.6f}]"
    total=fmt(row["annual_total_eur_2025"],row["annual_total_interval_eur_2025"])
    gain=fmt(row["annual_operating_value_eur_2025"],row["annual_operating_value_interval_eur_2025"])
    return (f"{row['scenario']} {row['policy']} {row['equipment']} {row['status']} served={row['completed']}/73 "
            f"replayed_six_week_EUR={row['six_week_energy_eur_2021']:.6f} annual_total_EUR2025={total} "
            f"value_EUR2025={gain} objective_gap={row['absolute_gap_eur_2025']:.6f} seconds={row['wall_seconds']:.2f}")


def _budget_worker(connection, function, args, kwargs):
    try:
        connection.send((True, function(*args, **kwargs)))
    except Exception:
        connection.send((False, traceback.format_exc()))
    finally:
        connection.close()


def budget_call(deadline, function, *args, **kwargs):
    """Use one interruptible worker for a registered high-rate solver call."""
    if deadline is None:
        return function(*args, **kwargs)
    if perf_counter() >= deadline:
        raise TimeoutError("High-rate combination reached its 45-minute wall-clock limit")
    ctx = multiprocessing.get_context("spawn")
    read, write = ctx.Pipe(duplex=False)
    worker = ctx.Process(target=_budget_worker, args=(write, function, args, kwargs))
    worker.start()
    write.close()
    try:
        if not read.poll(max(0., deadline-perf_counter())):
            raise TimeoutError("High-rate combination reached its 45-minute wall-clock limit")
        success, result = read.recv()
        if not success:
            raise RuntimeError(result)
        if perf_counter()>deadline:
            raise TimeoutError("High-rate combination reached its 45-minute wall-clock limit")
        return result
    finally:
        read.close()
        worker.join(timeout=0)
        if worker.is_alive():
            worker.terminate()
        worker.join()


def hardware_table(net):
    cost = eb.read_json(COST_INPUT)
    rules = {
        "one": ("solo", "Existing reference; no incremental purchase."),
        "two_independent": ("independent", cost["whole_charger_reference"]["source"]),
        "two_shared_rule": ("solo 50; two positive simultaneously each <=25 kW",
                            net["power_sharing_evidence"]["url"]),
        "two_shared_pool": ("continuous allocation of 50 kW combined; UM sensitivity",
                            "No manufacturer allocation claim for this scenario."),
    }
    table = {}
    for equipment, (interfaces, kw) in EQUIPMENT.items():
        rule, source = rules[equipment]
        table[equipment] = dict(port_interfaces=interfaces, port_cabinets=int(kw/50),
            cabinet_kw_each=50, combined_cabinet_kw=kw, port_interface_kw=50, port_connection_kw=100,
            warehouse_interfaces=1, warehouse_connection_kw=75, allocation=rule, evidence=source,
            cost_source=cost["whole_charger_reference"]["url"] if equipment=="two_independent" else None,
            cost_status={"one":"existing", "two_independent":"literature benchmark"}.get(equipment, "no retrofit quote"))
    return table


def source_state():
    def git(*args):
        return subprocess.check_output(["git", "-C", str(eb.ROOT), *args], encoding="utf-8").strip()
    return dict(commit=git("rev-parse", "HEAD"), dirty=bool(git("status", "--porcelain")))


class Evidence:
    def __init__(self, output):
        self.output = output
        self.statistics = {}

    def record(self, label, period, equipment, spec, rule, fixed, result, **weights):
        audit = replay(period, equipment, spec, rule, result, fixed=fixed, **weights)
        result["audit"] = audit
        self.statistics[label] = result["stats"]
        if self.output:
            write_json(self.output / (label+".json"), result)
            print(f"audited {label} objective={result['stats']['objective']:.9f}",flush=True)
        return result

    def solve(self, label, period, equipment, spec, rule, fixed, **weights):
        result = solve(period, equipment, spec, rule, fixed, **weights)
        objective = {k:weights[k] for k in ("energy_weight","peak_weights","site_energy_weights") if k in weights}
        return self.record(label, period, equipment, spec, rule, fixed, result, **objective)


def pilot_witness(period, result):
    """Hand-construct one equal-cost physical schedule for the registered pilot.

    The two vehicles have flexible overlapping early port stops. Split the
    first and last quarter of 03:00 between both trucks, and settle their
    residual energy in the next hour. Exact replay must reproduce the optimum.
    """
    grid = {v:math.fsum(t[2] for t in period.cases[PILOT_DAY]["trucks"][v]["trips"])
              /eb.DEFAULT_SPEC.efficiency for v in ("3","5")}
    rows = []
    remaining = grid.copy()
    def give(truck, quarters, kw):
        for q in quarters:
            rows.append(dict(date=PILOT_DAY,site="PORT",vehicle_id=truck,
                             reservation_slot=q,start_min=q*15,end_min=(q+1)*15,power_kw=kw))
            remaining[truck] -= kw*.25
    give("3",range(4),50.)
    for v in ("3","5"):
        give(v,(12,15),25.)
    give("3",(13,14),50.)
    give("5",range(88,96),50.)
    give("3",(16,17,18),remaining["3"]/.75)
    give("5",(19,),remaining["5"]/.25)
    return {**result,"schedule":rows,
            "witness":"Constructed for 2021-10-26; independent replay checks feasibility and exact equality to the solver objective."}


def pilot(days, prices, evidence):
    day = next(d for d in days if d["date"]==PILOT_DAY)
    group = {**day, "vehicles":[v for v in day["vehicles"] if v["vehicle_id"] in ("3","5")]}
    p = eb.Period([group], prices)
    table = []
    for q in range(96):
        table.append(dict(local_start=f"{q//4:02}:{q%4*15:02}", port_kw={}))
    metrics = {}
    for name in EQUIPMENT:
        r = evidence.solve("pilot-"+name, p, name, eb.DEFAULT_SPEC, eb.B, p.keys)
        if name=="two_shared_rule":
            r = evidence.record("pilot-"+name+"-equal-share",p,name,eb.DEFAULT_SPEC,eb.B,
                                p.keys,pilot_witness(p,r))
        by_quarter = defaultdict(float)
        for s in r["schedule"]:
            if s["site"]=="PORT":
                by_quarter[s["reservation_slot"],s["vehicle_id"]] += s["power_kw"]*(s["end_min"]-s["start_min"])/15
        for q,t in enumerate(table):
            t["port_kw"][name] = [by_quarter[q,v] for v in ("3","5")]
        metrics[name] = dict(day_eur=r["audit"]["purchase_eur"], peak_kw=r["audit"]["site_peak_kw"],
            port_grid_kwh_by_truck={v:sum(by_quarter[q,v] for q in range(96))/4 for v in ("3","5")})
    return dict(date=PILOT_DAY, vehicles=["3","5"], boundary="One sampled day, chain start/end 150 kWh",
                dispatch="Energy-only optimum; for E3 show an audited equal-cost 2 x 25 kW schedule.",
                metrics=metrics, quarters=table)


def solver_lower(stats):
    bound = stats.get("dual_bound")
    if bound is None:
        if stats.get("integer_variables",0) and stats.get("gap") is not None:
            raise ValueError(("missing MIP bound", stats))
        bound = stats["objective"]
    return min(bound,stats["objective"])


def selected_statistics(statistics):
    """Keep large search trees in their run files and retain the result and bounds here."""
    selected={}
    for label,tree in statistics.items():
        if len(json.dumps(tree,allow_nan=False))<=24000:
            selected[label]=tree
            continue
        backend=[]
        def walk(item):
            if isinstance(item,dict):
                if "status_code" in item:
                    backend.append(item)
                for v in item.values():
                    walk(v)
            elif isinstance(item,(list,tuple)):
                for v in item:
                    walk(v)
        walk(tree)
        root={k:v for k,v in tree.items() if isinstance(v,(str,int,float,bool)) or v is None} if isinstance(tree,dict) else {}
        gaps=[r["gap"] for r in backend if r.get("gap") is not None]
        selected[label]=dict(**root,recorded_status_count=len(backend),
            maximum_recorded_gap=max(gaps,default=None),full_statistics_run_file=label+".json")
    return selected


def reduced(audit, schedule, stats):
    reserved = defaultdict(set)
    for row in schedule:
        if row["site"]=="PORT":
            reserved[row["reservation_slot"]].add(row["vehicle_id"])
    return dict(purchase_eur=audit["purchase_eur"], site_grid_kwh=audit["site_grid_kwh"],
                site_peak_kw=audit["site_peak_kw"],lower_objective=solver_lower(stats),
                second_port_reserved_quarters=sum(len(v)>1 for v in reserved.values()))


def weekly_dispatch(periods, name, rule, keys, evidence, one_bills=None, *, whole=None):
    started = perf_counter()
    audits = []
    witness = dict(schedule=[],states=[])
    for i,p in enumerate(periods):
        options = {}
        if name=="two_shared_rule" and one_bills is not None:
            options=dict(objective_upper=one_bills[i]+1e-7,force_exact=True,absolute_gap=5e-5)
        r = evidence.solve(f"dispatch-{rule}-{name}-{i+1}",p,name,eb.DEFAULT_SPEC,rule,p.keys & keys,**options)
        audits.append(reduced(r["audit"],r["schedule"],r["stats"]))
        if whole is not None:
            witness["schedule"].extend(schedule_on_clock(whole,p,r["schedule"]))
            witness["states"].extend(r["states"])
    return dict(wall_seconds=perf_counter()-started, purchase_eur=math.fsum(a["purchase_eur"] for a in audits),
                weekly_eur=[a["purchase_eur"] for a in audits],witness=witness,
                lower_objective=math.fsum(a["lower_objective"] for a in audits),
                site_grid_kwh={s:math.fsum(a["site_grid_kwh"][s] for a in audits) for s in eb.SITES},
                site_peak_kw={s:max(a["site_peak_kw"][s] for a in audits) for s in eb.SITES},
                second_port_reserved_quarters=sum(a["second_port_reserved_quarters"] for a in audits))


def service_900(periods, reference, evidence):
    rows = []
    for label in ("S900a","S900b","S900c"):
        one, two = (reference[label,n,eb.B] for n in ("one","two"))
        for name in EQUIPMENT:
            selected = set()
            proofs = []
            for i,p in enumerate(periods):
                low,high = (p.keys & set(map(tuple,r["selected"])) for r in (one,two))
                if name=="two_independent":
                    keys, proof = high, "archived two independent optimum"
                elif name=="one" or len(low)==len(high):
                    keys = low
                    proof = "archived one optimum" if name=="one" else "one feasible; two independent upper bound attained"
                else:
                    r = evidence.solve(f"service-{label}-{name}-{i+1}",p,name,eb.SPECS[label],eb.B,None)
                    keys, proof = eb.selected(r), "audited shared-cabinet maximum"
                    if not len(low)<=len(keys)<=len(high):
                        raise ValueError(("service inclusion", label,name,i,low,keys,high))
                selected.update(keys)
                proofs.append(dict(week=p.days[0]["week_start"],proof=proof,lower=len(low),upper=len(high)))
            rows.append(dict(spec=label,equipment=name,completed=len(selected),selected=sorted(selected),proofs=proofs,
                             oct18=[v for d,v in sorted(selected) if d=="2021-10-18"]))
    return rows


def expensive_band_check(p, keys, net, evidence, rows):
    # Each active quarter supplies at most its metered peak times .25 h.
    eligible_quarters = set()
    for d,v in keys:
        for left,right,site in p.cases[d]["trucks"][v]["windows"]:
            if site=="WAREHOUSE":
                eligible_quarters.update((d,q) for q in range(int(left//15), math.ceil(right/15)))
    repeat = net["annualization"]["weeks_per_year"]/net["annualization"]["sample_weeks"]
    warehouse_hours = len(eligible_quarters)*.25*repeat
    if warehouse_hours>=net["full_load_hours_boundary"]:
        raise ValueError("Warehouse high-band possibility requires separate optimization")
    energy, money = annual_factors(net)
    bands = net["tariffs"]["frank"]["bands"]
    coefficients = {s:money*bands[b]["capacity_eur_per_kw_year"] for s,b in
                    (("PORT","high"),("WAREHOUSE","low"))}
    # Drop the high-band eligibility condition; expand any build to the two
    # independent cabinets. The optimal objective is a lower bound in that branch.
    r=evidence.solve("contract-high-port-lower-bound",p,"two_independent",eb.DEFAULT_SPEC,eb.B,keys,
                     energy_weight=energy,peak_weights=coefficients)
    year_kwh=math.fsum(r["audit"]["site_grid_kwh"].values())*repeat
    proof={}
    for basis,tariff in net["tariffs"].items():
        for band in ("low","high"):
            close(tariff["bands"][band]["capacity_eur_per_kw_year"],
                  bands[band]["capacity_eur_per_kw_year"],"common contract capacity rates")
        lower=solver_lower(r["stats"])+money*year_kwh*min(b["energy_eur_per_kwh"] for b in tariff["bands"].values())
        feasible=next(row["annual_total_eur_2025"] for row in rows if
                      (row["equipment"],row["policy"],row["scenario"])==("one","P2",basis))
        if lower<=feasible+1e-6:
            raise ValueError(("high-band total not excluded",basis,lower,feasible))
        proof[basis]=dict(high_port_total_lower_eur_2025=lower,
                          low_port_feasible_all_builds_eur_2025=feasible)
    return dict(warehouse_eligible_quarters=len(eligible_quarters),warehouse_hours_upper=warehouse_hours,
                high_port_energy_capacity_lower_eur_2025=solver_lower(r["stats"]),contracts=proof)


def run(output=None, pilot_only=False):
    started = perf_counter()
    net = load_network()
    days = eb.read_json(eb.WEEKS)["days"]
    native = eb.csv_rows(eb.NATIVE)
    prices = {d["date"]:eb.hourly_curve(native,d) for d in days if d["availability"]=="complete_tasks"}
    periods = [eb.Period(g,prices) for g in eb.components(days,eb.calendar(days)[1])]
    p = eb.Period(days,prices)
    evidence = Evidence(output)
    summary = dict(source=source_state(),python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,
        inputs_sha256={f.relative_to(eb.ROOT).as_posix():digest(f) for f in
                       (eb.WEEKS,eb.NATIVE,eb.REFERENCE,BASELINE,COST_INPUT,NETWORK_INPUT)},
        market="DE-LU; Europe/Berlin, native 2021 delivery EUR/MWh; every task and price in the horizon known.",
        window="PORT release on arrival; WAREHOUSE 45 minutes; connectors reserved by clock quarter, zero exchange time.",
        service_boundary="Matched consecutive tracks, selected duties only, chain endpoints at initial energy.",
        batteries={name:asdict(spec) for name,spec in eb.SPECS.items()},equipment=hardware_table(net),network=net,
        pilot=pilot(days,prices,evidence),solver_statistics=evidence.statistics)
    if pilot_only:
        return summary
    baseline = eb.read_json(BASELINE)
    refs = {(r["spec"],r["facility"],r["rule"]):r for r in baseline["full"]}
    keys = set(map(tuple,refs["S300","one",eb.B]["selected"]))
    for n in ("one","two"):
        for boundary in (eb.A,eb.B):
            if keys!=set(map(tuple,refs["S300",n,boundary]["selected"])):
                raise ValueError(("different reference selected duties", n,boundary))
    summary.update(common_service=sorted(keys), sample_truck_days=len(p.keys),
                   observed_vehicles=sorted({v for _,v in p.keys}),complete_task_dates=sorted(p.cases),
                   week_starts=sorted({d["week_start"] for d in days}),carriers=1,
                   service_proof="Every schedule serves the same 54 duties. Archived E2 maximum bounds all four feasible sets.")
    checks = {}
    regression = []
    dispatch = {}
    for boundary in (eb.A,eb.B):
        pair = {}
        for name in (("one","two_independent") if boundary==eb.A else EQUIPMENT):
            r = weekly_dispatch(periods,name,boundary,keys,evidence,pair.get("one"),whole=p if boundary==eb.B else None)
            if boundary==eb.B:
                dispatch[name,"P1",0] = r
            if name in ("one","two_independent"):
                old = refs["S300","one" if name=="one" else "two",boundary]
                exp = old["common_eur"]
                close(r["purchase_eur"],exp,"archived common EUR")
                for site in eb.SITES:
                    close(r["site_peak_kw"][site],old["site_peak_kw"][site],site)
                pair[name]=r["weekly_eur"]
                regression.append(dict(boundary=boundary,equipment=name,expected_eur=exp,
                                       actual_eur=r["purchase_eur"],delta_eur=r["purchase_eur"]-exp,
                                       expected_peaks=old["site_peak_kw"],actual_peaks=r["site_peak_kw"]))
        saving = break_even([a-b for a,b in zip(pair["one"],pair["two_independent"])])
        exp_ann,exp_cap = (330.85,2554.72) if boundary==eb.A else (391.24,3021.03)
        for field,expected in (("annual_cost_ceiling_2025_eur",exp_ann),("capital_ceiling_zero_maintenance_2025_eur",exp_cap)):
            close(round(saving[field],2),expected,field)
        checks[boundary]=saving
    checks["regression"]=regression
    chain = ["two_independent","two_shared_pool","two_shared_rule","one"]
    for left,right in zip(chain,chain[1:]):
        if dispatch[left,"P1",0]["purchase_eur"]>dispatch[right,"P1",0]["purchase_eur"]+1e-6:
            raise ValueError(("energy ordering",left,right,dispatch[left,"P1",0],dispatch[right,"P1",0]))
    electricity, money = annual_factors(net)
    rates = net["capacity_sensitivities_eur_per_kw_year"]
    low_rate = net["tariffs"]["frank"]["bands"]["low"]["capacity_eur_per_kw_year"]
    # An optimum over a larger hardware set is a lower bound on a restricted
    # build. When its actual schedule passes that build's replay it also attains
    # the bound. Keep the source label instead of inventing another solver run.
    solutions, feasible_e1 = {}, []
    def optimal_at(name,rate):
        key=name,"P2",rate
        if key in dispatch:
            return dispatch[key]
        tick = perf_counter()
        auxiliary=rate not in rates.values()
        deadline=(tick+AUXILIARY_WITNESS_SECONDS if auxiliary else
                  tick+MAX_COMBINATION_SECONDS if rate>=BOUNDED_RATE else None)
        weights=dict(energy_weight=electricity,peak_weights=dict.fromkeys(eb.SITES,rate*money))
        label=f"annual-P2-{name}-{rate:.15g}"
        for larger in chain[:chain.index(name)]:
            if (larger,rate) not in solutions:
                continue
            old=solutions[larger,rate]
            try:
                audit_cabinets(name,old["schedule"])
            except ValueError:
                continue
            r=evidence.record(label,p,name,eb.DEFAULT_SPEC,eb.B,keys,
                              {**old,"optimality_from_superset":larger},**weights)
            break
        else:
            available = feasible_e1 + [a for (eq,_,_),a in dispatch.items() if chain.index(eq)>=chain.index(name)]
            def objective(a):
                return electricity*a["purchase_eur"]+rate*money*sum(a["site_peak_kw"].values())
            best=min(available,key=objective)
            upper=objective(best)
            options={"absolute_gap":.001} if rate < BOUNDED_RATE and name in ("one","two_shared_rule") else {}
            if name=="one":
                options["incumbent"]=best["witness"]
            if name=="two_shared_rule" and ("two_shared_pool",rate) in solutions:
                caps=solutions["two_shared_pool",rate]["audit"]["site_peak_kw"]
                shared=budget_call(deadline,shared_peak_witness,p,periods,eb.DEFAULT_SPEC,eb.B,keys,
                                   caps,electricity,weights["peak_weights"])
                key_label=f"feasible-E3-{rate:.15g}"
                evidence.statistics[key_label]=shared["weeks"]
                if output:
                    write_json(output/(key_label+".json"),shared)
                if shared["feasible"]:
                    upper=min(upper,shared["objective_upper"])
            try:
                raw=budget_call(deadline,solve,p,name,eb.DEFAULT_SPEC,eb.B,keys,
                                objective_upper=upper+1e-7,**options,**weights)
            except TimeoutError:
                if not auxiliary:
                    raise
                relaxed=relaxation(p,name,eb.DEFAULT_SPEC,eb.B,keys,**weights)
                raw={**best["witness"],"stats":dict(status="Auxiliary feasible dispatch and LP lower bound",
                     objective=upper,dual_bound=solver_lower(relaxed["stats"]),relaxation=relaxed["stats"])}
            r=evidence.record(label,p,name,eb.DEFAULT_SPEC,eb.B,keys,raw,**weights)
        solutions[name,rate]=r
        dispatch[key]=reduced(r["audit"],r["schedule"],r["stats"])
        dispatch[key]["wall_seconds"]=perf_counter()-tick
        dispatch[key]["witness"]={k:r[k] for k in ("states","schedule")}
        return dispatch[key]
    for name in EQUIPMENT:
        dispatch[name,"P2",0]=dispatch[name,"P1",0]
    def solve_rate(rate):
        tick=perf_counter()
        deadline=tick+MAX_COMBINATION_SECONDS if rate>=BOUNDED_RATE else None
        weights=dict(energy_weight=electricity,peak_weights=dict.fromkeys(eb.SITES,rate*money))
        witness=budget_call(deadline,build_incumbent,p,periods,eb.DEFAULT_SPEC,eb.B,keys,**weights)
        feasible_e1.append(dict(purchase_eur=witness["purchase_eur"],site_peak_kw=witness["site_peak_kw"],
            witness={k:witness["polished"][k] for k in ("states","schedule")}))
        label=f"feasible-E1-{rate}"
        evidence.statistics[label]=dict(relaxation=witness["relaxed"]["stats"],
                                        weeks=[w["stats"] for w in witness["weeks"]],
                                        polished=witness["polished"]["stats"])
        checks[label]={k:witness[k] for k in ("objective_upper","purchase_eur","site_peak_kw","trial_peak_limits_kw")}
        evidence.statistics[label]["other_peak_trials"]=[
            dict(weeks=[w["stats"] for w in t["weeks"]],polished=t["polished"]["stats"])
            for t in witness["other_peak_trials"]]
        if output:
            write_json(output/(label+".json"),witness)
        if rate == low_rate:
            checks["uniform_low_band_interval"] = low_band_interval(
                p,keys,eb.DEFAULT_SPEC,eb.B,net,rate,witness)
        elif rate == max(rates.values()):
            checks["uniform_high_band_intervals"] = budget_call(deadline,high_band_interval,
                p,keys,eb.DEFAULT_SPEC,eb.B,net,low_rate,rate,witness,checks["uniform_low_band_interval"])
        seed_seconds=perf_counter()-tick
        for name in chain[:-1]:
            optimal_at(name,rate)
        solving=perf_counter()
        if deadline is None:
            optimal_at("one",rate)
        else:
            from .cabinet_partial import decision_e1_bound
            deadline=solving+MAX_COMBINATION_SECONDS-seed_seconds
            pool=solutions["two_shared_pool",rate]
            upgrade_upper=max(solutions[name,rate]["stats"]["objective"] for name in chain[:-1])
            try:
                raw=budget_call(deadline,decision_e1_bound,p,eb.DEFAULT_SPEC,eb.B,keys,pool,
                                incumbent=feasible_e1[-1]["witness"],upgrade_upper=upgrade_upper,
                                nominal_rate=rate,wall_seconds=max(0.,deadline-perf_counter()),**weights)
            except TimeoutError:
                # The larger build's lower bound still holds for E1. Preserve
                # this and the last audited feasible seed, even when rejected.
                raw={**feasible_e1[-1]["witness"],"stats":dict(status="45-minute limit",
                    objective=witness["objective_upper"],dual_bound=solver_lower(pool["stats"]))}
            r=evidence.record(f"annual-P2-one-{rate:.15g}",p,"one",eb.DEFAULT_SPEC,eb.B,keys,raw,**weights)
            solutions["one",rate]=r
            dispatch["one","P2",rate]=dict(**reduced(r["audit"],r["schedule"],r["stats"]),bounded=True,
                                           witness={k:r[k] for k in ("states","schedule")})
        dispatch["one","P2",rate]["wall_seconds"]=seed_seconds+perf_counter()-solving
        if deadline is not None:
            decision_record(solver_lower(r["stats"]),r["stats"]["objective"],
                            dispatch["one","P2",rate]["wall_seconds"],bounded=True)
    rows = []
    benchmark = checks[eb.B]["benchmark"]
    crf = benchmark["capital_recovery_factor"]
    high_supports={}
    for policy in ("P1","P2"):
        for scenario in ("N0","frank","official",*rates):
            rate = rates.get(scenario,0 if scenario=="N0" else low_rate)
            if policy=="P2" and ("one",policy,rate) not in dispatch:
                solve_rate(rate)
            options = {}
            totals = {}
            for name in EQUIPMENT:
                a = dispatch[name,policy,rate if policy=="P2" else 0]
                args = (net,a["purchase_eur"],a["site_grid_kwh"],a["site_peak_kw"],scenario)
                bill = settle(*args)
                audit_settlement(*args,bill)
                if policy=="P2" and scenario in ("official","frank") and any(
                        m["capacity_eur_per_kw_year"]!=low_rate for m in bill["sites"].values()):
                    raise ValueError(("lower-rate optimum does not certify endogenous tier",name,scenario,bill))
                total = bill["annual_total_eur_2025"]
                options[name]=total
                value = options["one"]-total
                obj = electricity*a["purchase_eur"] + rate*money*sum(a["site_peak_kw"].values())
                raw_bound = a["lower_objective"] if policy=="P2" and rate else electricity*a["lower_objective"]
                row = dict(equipment=name,policy=policy,common_set="common_service",completed=len(keys),
                           second_port_reserved_quarters=a["second_port_reserved_quarters"],
                           reservation_denominator_complete_date_quarters=len(p.cases)*96,
                           second_port_reservation_share=a["second_port_reserved_quarters"]/(len(p.cases)*96),**bill,
                           annual_operating_value_eur_2025=value)
                upper=obj if policy=="P2" else electricity*a["purchase_eur"]
                bounded=bool(a.get("bounded",False))
                extra_time=0.
                if policy=="P2" and rate>=BOUNDED_RATE:
                    check=next(v for v in checks["uniform_high_band_intervals"]["checks"] if v["rate"]==rate)
                    if not check["high_port_proved"] or checks["uniform_high_band_intervals"]["warehouse_hours_upper"]>=net["full_load_hours_boundary"]:
                        raise ValueError(("Uncertified high-rate meter bands",name,rate))
                    # Both endogenously selected energy rates must be included.
                    # A dispatch that minimizes the fixed-rate objective lies
                    # in the sublevel set of its replayed feasible upper bound.
                    tick=perf_counter()
                    deadline=tick+MAX_COMBINATION_SECONDS-a["wall_seconds"]
                    rel=budget_call(deadline,relaxation,p,name,eb.DEFAULT_SPEC,eb.B,keys,
                          energy_weight=electricity,peak_weights=dict.fromkeys(eb.SITES,rate*money),
                          objective_upper=upper+1e-6,_warehouse_energy_upper=True)
                    extra_time=perf_counter()-tick
                    if a["wall_seconds"]+extra_time>MAX_COMBINATION_SECONDS:
                        raise TimeoutError(("High-rate combination exceeded wall budget",name,rate))
                    high_supports[name]=rel["warehouse_energy_support"]
                    repeat=net["annualization"]["weeks_per_year"]/net["annualization"]["sample_weeks"]
                    wh=repeat*high_supports[name]["six_week_kwh_upper"]
                    bands=net["tariffs"]["frank"]["bands"]
                    high=bands["high"]["energy_eur_per_kwh"]
                    low=bands["low"]["energy_eur_per_kwh"]
                    floor=checks["uniform_low_band_interval"]["annual_grid_kwh"]*money*high
                    totals[name]=[raw_bound+floor,upper+floor+wh*money*(low-high)]
                elif policy=="P1":
                    # P1 is the invoice of its published, fixed energy-only schedule.
                    totals[name]=[total,total]
                else:
                    totals[name]=[total-max(0.,upper-raw_bound),total]
                row.update(decision_record(raw_bound,upper,a["wall_seconds"]+extra_time,bounded=bounded))
                row["dispatch_optimality_gap_eur_2025"]=row["absolute_gap_eur_2025"]
                row["annual_total_interval_eur_2025"]=totals[name]
                row["annual_operating_value_interval_eur_2025"]=([0.,0.] if name=="one" else
                      [totals["one"][0]-totals[name][1],totals["one"][1]-totals[name][0]])
                if name=="two_independent":
                    row["after_equipment_cost_eur_2025"]=value-benchmark["annual_cost_2025_eur"]
                if name.startswith("two_shared"):
                    row["affordable_annual_charge_eur_2025"]=max(0.,value)
                    row["zero_maintenance_capex_eur_2025"]=max(0.,value)/crf
                if policy=="P2":
                    before=next(b for b in rows if (b["equipment"],b["policy"],b["scenario"])==(name,"P1",scenario))
                    if max(total,totals[name][1])>before["annual_total_eur_2025"]+1e-6:
                        raise ValueError(("P2 invoice exceeds P1",row,before))
                value_bounded=(policy=="P2" and rate>=BOUNDED_RATE and name!="one" and
                               (bounded or dispatch["one","P2",rate].get("bounded",False)))
                row["value_status"]="bounded" if value_bounded else "optimal"
                if bounded:
                    row["replayed_annual_total_eur_2025"]=row["annual_total_eur_2025"]
                    row["annual_total_eur_2025"]=None
                if value_bounded:
                    lo,hi=row["annual_operating_value_interval_eur_2025"]
                    try:
                        row["decision_check"]=classify_decision_bounds(lo,hi,benchmark["annual_cost_2025_eur"])
                    except ValueError as exc:
                        raise ValueError((policy,name,rate,str(exc))) from exc
                    row["replayed_annual_operating_value_eur_2025"]=value
                    row["annual_operating_value_eur_2025"]=None
                    if name=="two_independent":
                        row["after_equipment_cost_interval_eur_2025"]=[x-benchmark["annual_cost_2025_eur"] for x in (lo,hi)]
                        row["after_equipment_cost_eur_2025"]=None
                    else:
                        row["affordable_annual_charge_interval_eur_2025"]=[max(0.,x) for x in (lo,hi)]
                        row["zero_maintenance_capex_interval_eur_2025"]=[max(0.,x)/crf for x in (lo,hi)]
                        row["affordable_annual_charge_eur_2025"]=row["zero_maintenance_capex_eur_2025"]=None
                rows.append(row)
                print(invoice_line(row),flush=True)
    checks["registered_high_rate_warehouse_energy_supports"]=high_supports
    zero_bills = {r["equipment"]:r for r in rows if r["policy"]=="P1" and r["scenario"]=="capacity_0"}
    critical = {"P1":{n:fixed_dispatch_zero(net,zero_bills["one"],bill) for n,bill in zero_bills.items() if n!="one"}}
    checks["contract_global_total"]=expensive_band_check(p,keys,net,evidence,rows)
    curve_start=perf_counter()
    def may_refine():
        return perf_counter()-curve_start<MAX_COMBINATION_SECONDS
    def profile(audit):
        return dict(energy=electricity*audit["purchase_eur"],peak=math.fsum(audit["site_peak_kw"].values()))

    meter_points={}
    low_power_profile={}
    bounded_shared={}
    def critical_shared(rate):
        if rate in bounded_shared:
            return bounded_shared[rate]
        weights=dict(energy_weight=electricity,peak_weights=dict.fromkeys(eb.SITES,rate*money))
        optimal_at("two_independent",rate)
        pool=optimal_at("two_shared_pool",rate)
        larger=solutions["two_shared_pool",rate]
        try:
            audit_cabinets("two_shared_rule",larger["schedule"])
        except ValueError:
            def at_rate(a):
                return electricity*a["purchase_eur"]+rate*money*sum(a["site_peak_kw"].values())
            old=min(feasible_e1+[v for (eq,_,_),v in dispatch.items() if eq in ("one","two_shared_rule")],
                    key=at_rate)
            upper=at_rate(old)
            witness=old["witness"]
            try:
                trial=budget_call(perf_counter()+AUXILIARY_WITNESS_SECONDS,shared_peak_witness,p,periods,
                                  eb.DEFAULT_SPEC,eb.B,keys,pool["site_peak_kw"],electricity,weights["peak_weights"])
            except TimeoutError:
                trial=dict(feasible=False,weeks=[],stop="optional shared witness wall-clock budget")
            if trial["feasible"] and trial["objective_upper"]<upper:
                upper=trial["objective_upper"]
                witness={k:trial[k] for k in ("schedule","states")}
            raw=dict(**witness,stats=dict(status="Feasible shared dispatch and flexible-pool lower bound",
                objective=upper,dual_bound=pool["lower_objective"],weeks=trial["weeks"],
                witness_stop=trial.get("stop")))
        else:
            raw={**larger,"optimality_from_superset":"two_shared_pool"}
        record=evidence.record(f"critical-shared-bound-{rate:.15g}",p,"two_shared_rule",eb.DEFAULT_SPEC,
                               eb.B,keys,raw,**weights)
        a=reduced(record["audit"],record["schedule"],record["stats"])
        bounded_shared[rate]=a
        return a

    def rate_point(name,rate):
        if (name,rate) in meter_points:
            return meter_points[name,rate]
        if name=="one" and rate not in rates.values():
            weights=dict.fromkeys(eb.SITES,rate*money)
            def cost(a):
                return electricity*a["purchase_eur"]+money*rate*sum(a["site_peak_kw"].values())
            seed=min(feasible_e1+[d for (eq,_,_),d in dispatch.items() if eq=="one"],key=cost)
            deadline=perf_counter()+MAX_COMBINATION_SECONDS if rate>=BOUNDED_RATE else None
            improved=budget_call(deadline,polish_e1,p,eb.DEFAULT_SPEC,eb.B,keys,seed["witness"],electricity,weights)
            upper=improved["stats"]["objective"]
            upgrade=cost(critical_shared(rate))
            # The auxiliary target certifies separation. It never replaces
            # either registered annual minimum or its audited monetary bound.
            desired=min(upper,upgrade+max(1e-4,min(.1,(upper-upgrade)/3)))
            extrapolated=[]
            if "minimum_peak_lower" in low_power_profile:
                extrapolated=[x["lower"]+(rate-r)*money*low_power_profile["minimum_peak_lower"]
                              for (eq,r),x in meter_points.items() if eq=="one" and r<=rate]
            prior=sorted((r,x["lower"]) for (eq,r),x in meter_points.items() if eq=="one")
            chord=[x+(y-x)*(rate-a)/(b-a) for a,x in prior for b,y in prior if a<rate<b]
            lower=max([solver_lower(solutions["two_shared_pool",rate]["stats"]),*extrapolated,*chord])
            certificate={}
            if lower<desired:
                try:
                    certificate=budget_call(perf_counter()+AUXILIARY_WITNESS_SECONDS,partial_e1_bound,p,eb.DEFAULT_SPEC,
                        eb.B,keys,solutions["two_shared_pool",rate],energy_weight=electricity,peak_weights=weights,
                        upgrade_upper=upgrade,e1_upper=upper)
                except TimeoutError:
                    certificate=dict(lower_bound=lower,stop="optional separation wall-clock budget")
                lower=max(lower,certificate["lower_bound"])
            if lower>upper+1e-6:
                raise ArithmeticError(("auxiliary lower exceeds replayed E1 bill",rate,lower,upper))
            separated=lower>upgrade+1e-5 or lower>=desired
            raw={**improved,"stats":dict(status=("Auxiliary peak and selected-hour lower certificates" if separated
                 else "Auxiliary separation not certified"), objective=upper,dual_bound=min(upper,lower),
                 gap=max(0.,upper-lower)/max(1.,abs(upper)))}
            raw["stats"]["selected_hour_certificate"]=certificate
            if extrapolated:
                raw["stats"]["minimum_peak_extrapolated_lower"]=max(extrapolated)
            label=f"critical-E1-bound-{rate:.15g}"
            r=evidence.record(label,p,"one",eb.DEFAULT_SPEC,eb.B,keys,raw,
                              energy_weight=electricity,peak_weights=weights)
            a=reduced(r["audit"],r["schedule"],r["stats"])
            feasible_e1.append({**a,"witness":{k:r[k] for k in ("schedule","states")}})
        elif name=="two_shared_rule" and rate not in rates.values():
            a=critical_shared(rate)
        else:
            a=optimal_at(name,rate)
        volume=settle(net,a["purchase_eur"],a["site_grid_kwh"],a["site_peak_kw"],"capacity_0")
        entry=dict(**profile(a),lower=a["lower_objective"]*(1 if rate else electricity),
                   volume=volume["annual_network_energy_eur_2025"])
        meter_points[name,rate]=entry
        return entry

    def min_peak(name):
        if name=="one":
            raw=e1_peak_witness(p,periods,eb.DEFAULT_SPEC,eb.B,keys)
            r=evidence.record("minimum-peak-bounds-one",p,name,eb.DEFAULT_SPEC,eb.B,keys,raw,
                              energy_weight=0.,peak_weights=dict.fromkeys(eb.SITES,1.))
            feasible_e1.append({**reduced(r["audit"],r["schedule"],r["stats"]),
                                "witness":{k:r[k] for k in ("schedule","states")}})
            low_power_profile.update(profile(r["audit"]))
            low_power_profile["minimum_peak_lower"]=solver_lower(r["stats"])
            return dict(**profile(r["audit"]),lower=solver_lower(r["stats"]))
        best=min(feasible_e1+[a for (eq,_,_),a in dispatch.items() if chain.index(eq)>=chain.index(name)],
                 key=lambda a:sum(a["site_peak_kw"].values()))
        upper=sum(best["site_peak_kw"].values())
        r=evidence.solve("minimum-peak-"+name,p,name,eb.DEFAULT_SPEC,eb.B,keys,
                         energy_weight=0.,peak_weights=dict.fromkeys(eb.SITES,1.),objective_upper=upper+1e-7,
                         incumbent=None)
        # A lower wholesale bill at the same metered peaks gives a tighter
        # feasible line at high tariffs without changing the pure-peak bound.
        caps=r["audit"]["site_peak_kw"]
        cheap=evidence.solve("minimum-peak-energy-"+name,p,name,eb.DEFAULT_SPEC,eb.B,keys,
                             peak_bounds=caps)
        return dict(**profile(cheap["audit"]),lower=solver_lower(r["stats"]))

    critical["P2"]=certify_p2(rate_point,min_peak,money,tuple(rates.values()),may_refine=may_refine)
    if low_power_profile:
        terminal=terminal_volume_band(p,keys,net,max(rates.values()),low_power_profile,
                                      checks["uniform_low_band_interval"])
        checks["uniform_high_band_intervals"]["terminal_supports"]=terminal["supports"]
        checks["uniform_high_band_intervals"]["intervals"].extend(terminal["intervals"])
    volume_checks={}
    def warehouse_max(a,b):
        # One fixed E1 dispatch is feasible for every build throughout the
        # interval. A cheaper schedule at an interior rate is in at least one
        # of the two endpoint sublevel sets of that same affine cost line.
        profiles=[profile(x) for x in feasible_e1]+[profile(x) for (eq,_,_),x in dispatch.items() if eq=="one"]
        seed=min(profiles,key=lambda x:x["energy"]+money*(a+b)*.5*x["peak"])
        pair=[]
        for r in (a,b):
            upper=seed["energy"]+money*r*seed["peak"]
            key=(r,upper)
            if key not in volume_checks:
                rel=relaxation(p,"two_independent",eb.DEFAULT_SPEC,eb.B,keys,energy_weight=electricity,
                     peak_weights=dict.fromkeys(eb.SITES,r*money),objective_upper=upper+1e-6,
                     _warehouse_energy_upper=True)
                volume_checks[key]=dict(rate=r,e1_upper=upper,**rel["warehouse_energy_support"])
            pair.append(volume_checks[key]["six_week_kwh_upper"])
        repeat=net["annualization"]["weeks_per_year"]/net["annualization"]["sample_weeks"]
        return max(pair)*repeat
    critical["P2"]["billed_intervals"]=bill_intervals(
        critical["P2"]["intervals"],checks["uniform_low_band_interval"],
        checks["uniform_high_band_intervals"],net,warehouse_max)
    # Where both endpoints exclude zero but an interval bound is too wide,
    # query intermediate rates down to the source tariff's cent precision.
    def recertify(name,a,b):
        bounds=gain_interval(name,a,b,rate_point,money)
        return bill_intervals({name:[bounds]},checks["uniform_low_band_interval"],
                              checks["uniform_high_band_intervals"],net,warehouse_max)[name]
    def refine(name,row):
        a,b=row["from_rate"],row["to_rate"]
        if row["status"]!="unresolved_across_meter_bands" or b is None or b-a<=.01 or not may_refine():
            return [row]
        resolved={"strictly_positive","no_zero_in_either_band_assignment","zero_to_tolerance"}
        if any(recertify(name,r,r)[0]["status"] not in resolved for r in (a,b)):
            return [row]
        middle=(a+b)/2
        return [s for left,right in ((a,middle),(middle,b)) for item in recertify(name,left,right)
                for s in refine(name,item)]
    for name,pieces in critical["P2"]["billed_intervals"].items():
        critical["P2"]["billed_intervals"][name]=[s for row in pieces for s in refine(name,row)]
    critical["P2"]["feasible_bills_at_evaluated_rates"]=[]
    for (name,rate),profile_at_rate in sorted(meter_points.items()):
        if name=="one" or ("one",rate) not in meter_points:
            continue
        base=meter_points["one",rate]
        def bill_value(x):
            return x["energy"]+rate*money*x["peak"]+x["volume"]
        critical["P2"]["feasible_bills_at_evaluated_rates"].append(dict(
            equipment=name,rate=rate,net_eur_2025=bill_value(base)-bill_value(profile_at_rate),
            e1_energy_capacity_primal_minus_lower_eur_2025=bill_value(base)-base["volume"]-base["lower"],
            volumetric_difference_eur_2025=base["volume"]-profile_at_rate["volume"]))
    checks["p2_warehouse_energy_supports"]=list(volume_checks.values())
    critical["P2"]["auxiliary_refinement"]=dict(seconds=perf_counter()-curve_start,
        refinement_time_budget_seconds=MAX_COMBINATION_SECONDS,optional_witness_seconds=AUXILIARY_WITNESS_SECONDS,
        scope="Only continuous-price zero searches use this budget. Unresolved intervals retain the last certified bounds.")
    def verify_statuses(node):
        if isinstance(node,dict):
            if "status_code" in node and node["status_code"]!=0:
                raise ArithmeticError(("non-optimal backend status",node))
            for sub in node.values():
                verify_statuses(sub)
        elif isinstance(node,(list,tuple)):
            for sub in node:
                verify_statuses(sub)
    large=service_900(periods,refs,evidence)
    verify_statuses(evidence.statistics)
    verify_statuses(checks)
    if len(keys)!=54 or len(p.keys)!=73:
        raise ValueError(("Unexpected service denominator",len(keys),len(p.keys)))
    checks.update(same_selected_54=True,all_physical_dispatches_replayed=True,all_recorded_backend_status_codes_zero=True,
                  energy_order_E2_E4_E3_E1=True,P2_total_at_most_P1=True,annual_settlements_replayed=True)
    summary.update(checks=checks, main=rows, critical_capacity_price=critical,
                   run_wall_seconds=perf_counter()-started,
                   precision_policy=dict(high_rate_threshold_eur_2024_per_kw_year=BOUNDED_RATE,
                       max_high_rate_wall_seconds=MAX_COMBINATION_SECONDS,max_bounded_objective_gap_eur_2025=1.,
                       objective="P1 annual wholesale electricity; P2 annual wholesale plus both metered capacity charges.",
                       billing="A bounded comparison has no scalar optimum. The replayed feasible schedule and separate bill intervals are retained.",
                       timing="Elapsed dispatch calculation and replay for each hardware/rate. Reused P1/P2-zero and contract rows reference the same dispatch; do not sum invoice rows."),
                   solver_statistics=selected_statistics(evidence.statistics),
                   large_batteries=large,
                   portfolio_objective="P2 minimizes annual wholesale energy and capacity charges in 2025 EUR. "
                   "The complete contract invoice is certified by excluding the high-port branch in "
                   "checks.contract_global_total and retaining each low-band row's dispatch_optimality_gap_eur_2025.",
                   benchmark=benchmark)
    return summary


def bill_intervals(intervals, low, high, net, warehouse_max=None):
    """Transfer objective certificates to the actual, separately banded meters."""
    money=annual_factors(net)[1]
    tariff=net["tariffs"]["frank"]["bands"]
    unrestricted_error=low["annual_grid_kwh"]*money*abs(
        tariff["low"]["energy_eur_per_kwh"]-tariff["high"]["energy_eur_per_kwh"])
    bands=[]
    if low["all_sites_low_proved"]:
        bands.append((low["from_rate"],low["to_rate"],0.))
    bands.extend((row["from_rate"],float("inf") if row["to_rate"] is None else row["to_rate"],
                  row["max_abs_annual_volumetric_difference_eur_2025"]["frank"])
                 for row in high["intervals"])
    result={}
    for name,items in intervals.items():
        result[name]=[]
        for item in items:
            a=item["from_rate"]
            b=float("inf") if item["to_rate"] is None else item["to_rate"]
            cuts={a,b,*[x for left,right,_ in bands for x in (left,right) if a<x<b]}
            slope=item.get("lower_slope_2025",0.)
            if slope>0:
                safe=a+(unrestricted_error+2e-5-item["lower_bound_at_start_2025_eur"])/slope
                if a<safe<b:
                    cuts.add(safe)
            cuts=sorted(cuts)
            for left,right in (zip(cuts,cuts[1:]) if len(cuts)>1 else [(a,b)]):
                err=min([unrestricted_error,*[error for c,d,error in bands if c<=left and right<=d]])
                lower=item.get("lower_bound_2025_eur")
                slope=item.get("lower_slope_2025")
                if lower is None and slope is not None and slope>=0:
                    lower=item["lower_bound_at_start_2025_eur"]+(left-a)*slope
                proven=item["status"] if err==0 else "unresolved_across_meter_bands"
                if lower is not None and lower>err+1e-5:
                    proven="strictly_positive"
                details={}
                if err==0 and "zero_endpoints" in item:
                    details["zero_endpoints"]=[v for v in item["zero_endpoints"] if left<=v<=right]
                if (warehouse_max is not None and proven=="unresolved_across_meter_bands"
                        and math.isfinite(right) and lower is not None):
                    wh=warehouse_max(left,right)
                    spread=abs(tariff["low"]["energy_eur_per_kwh"]-tariff["high"]["energy_eur_per_kwh"])*money
                    # A high-port bill is high_rate * total + spread * WH,
                    # whereas the low-port bill is simply low_rate * total.
                    same_band_error=spread*wh
                    cross_band_difference=spread*max(0.,low["annual_grid_kwh"]-wh)
                    margin=item.get("uniform_objective_gain_upper_eur_2025")
                    if (lower>same_band_error+1e-5 and margin is not None
                            and cross_band_difference>margin+1e-5):
                        proven="no_zero_in_either_band_assignment"
                    if err<unrestricted_error and lower>same_band_error+1e-5:
                        proven="strictly_positive"
                        err=min(err,same_band_error)
                    details=dict(warehouse_annual_kwh_upper=wh,same_band_error_eur_2025=same_band_error,
                        different_bands_absolute_volume_difference_lower_eur_2025=cross_band_difference)
                result[name].append(dict(from_rate=left,to_rate=right if math.isfinite(right) else None,
                    status=proven,capacity_energy_status=item["status"],max_abs_volumetric_difference_eur_2025=err,
                    billed_lower_eur_2025=None if lower is None else lower-err,**details))
    return result


def terminal_volume_band(p,keys,net,first_rate,witness,low):
    """At any later rate a winner beats this E1 line at the start or in its slope."""
    energy,money=annual_factors(net)
    repeat=net["annualization"]["weeks_per_year"]/net["annualization"]["sample_weeks"]
    supports=[]
    def envelope(energy_weight,peak_weight,upper):
        relaxed=relaxation(p,"two_independent",eb.DEFAULT_SPEC,eb.B,keys,energy_weight=energy_weight,
              peak_weights=dict.fromkeys(eb.SITES,peak_weight),objective_upper=upper+1e-6,_warehouse_energy_upper=True)
        supports.append(relaxed)
        return (relaxed["upper_kw"]["PORT"],repeat*relaxed["warehouse_energy_support"]["six_week_kwh_upper"])
    slope= envelope(0.,1.,witness["peak"])
    ranges=[]
    rate=first_rate
    for _ in range(12):
        start=envelope(energy,rate*money,witness["energy"]+rate*money*witness["peak"])
        if all(low["annual_grid_kwh"] > net["full_load_hours_boundary"]*kw+wh+1e-6 for kw,wh in (slope,start)):
            wh=max(slope[1],start[1])
            errors={basis:money*wh*abs(t["bands"]["low"]["energy_eur_per_kwh"]-t["bands"]["high"]["energy_eur_per_kwh"])
                    for basis,t in net["tariffs"].items()}
            ranges.append(dict(from_rate=rate,to_rate=None,warehouse_kwh_upper=wh,
                              max_abs_annual_volumetric_difference_eur_2025=errors))
            break
        rate*=2
    return dict(supports=supports,intervals=ranges)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--summary",type=Path)
    parser.add_argument("--pilot",action="store_true")
    args=parser.parse_args()
    output=checked_output(args.output,eb.ROOT) if args.output else None
    if output:
        if source_state()["dirty"]:
            raise ValueError("Formal cabinet run requires a clean source commit")
        output.mkdir(parents=True)
    try:
        result=run(output,args.pilot)
    except (ValueError,TimeoutError) as exc:
        if output:
            write_json(output/"stopped.json",dict(status="stopped",reason=str(exc)))
        raise
    lines=[]
    for name,r in result["pilot"]["metrics"].items():
        lines.append(f"pilot {PILOT_DAY} {name} EUR={r['day_eur']:.6f} port_kW={r['peak_kw']['PORT']:.3f}")
    if "run_wall_seconds" in result:
        lines.append(f"full study wall seconds={result['run_wall_seconds']:.2f}")
    for line in lines:
        print(line,flush=True)
    lines.extend(invoice_line(r) for r in result.get("main",[]))
    if output:
        write_json(output/"summary.json",result)
        (output/"cli.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    if args.summary:
        write_json(args.summary,result)


if __name__=="__main__":
    main()
