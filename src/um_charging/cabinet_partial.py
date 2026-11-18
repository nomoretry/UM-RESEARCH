"""Lower bounds on E1 dispatch from a subset of port reservation hours."""
from collections import defaultdict
from itertools import product
from math import fsum
from time import perf_counter

from . import cabinet_model as cm
from .energy_boundary import Matrix
from .fleet_service import SITES, _events, subset_case


def _rank_hours(p, spec, fixed, pool):
    """Rank conflicted hours by energy a single owner per quarter cannot deliver.

    This ranking ignores trip endpoints inside an hour. It selects inequalities
    only. The model used to certify the bound retains every trip and SOC state.
    """
    peak = pool["audit"]["site_peak_kw"]["PORT"]
    power = min(50., spec.truck_kw)
    targets, occupants = defaultdict(lambda: defaultdict(float)), defaultdict(set)
    for row in pool["schedule"]:
        if row["site"] == "PORT":
            day, v = row["date"], row["vehicle_id"]
            quarter = row["reservation_slot"]-p.offset[day]//15
            targets[day, quarter//4][v] += row["power_kw"]*(row["end_min"]-row["start_min"])/60
            occupants[day, quarter].add(v)
    conflicts = {(day, q//4) for (day, q), vs in occupants.items() if len(vs)>1}
    availability = defaultdict(lambda: [defaultdict(float) for _ in range(4)])
    for day, whole in p.cases.items():
        case = subset_case(whole, [v for v in whole["trucks"] if (day, v) in fixed])
        for a, b, eligible in _events(case):
            q = int(a//15)
            key = day, q//4
            if key in conflicts:
                for v in eligible["PORT"]:
                    if v in targets[key]:
                        availability[key][q%4][v] += power*(b-a)/60
    scores = []
    for key in sorted(conflicts):
        needed = targets[key]
        slots = availability[key]
        largest = 0.
        for owners in product(*(list(slot) or [None] for slot in slots)):
            supply = defaultdict(float)
            for slot, v in zip(slots, owners):
                if v is not None:
                    supply[v] += min(peak/4, slot[v])
            largest = max(largest, fsum(min(supply[v], e) for v, e in needed.items()))
        scores.append(dict(date=key[0], hour=key[1], shortfall_kwh=max(0., fsum(needed.values())-largest)))
    return sorted(scores, key=lambda row: -row["shortfall_kwh"])


def _capped_hours(p, spec, rule, fixed, energy_weight, peak_weights, cutoff, bounds, hours):
    """Return min(cutoff, partial-model optimum on the competitive meter box)."""
    m = Matrix()
    levels = cm._levels(m, p, spec, rule, fixed, False)
    peaks = {s: m.var(bounds["lower_kw"].get(s, 0.), bounds["upper_kw"].get(s, 50.), peak_weights[s])
             for s in SITES}
    # An artificial zero-service option costs exactly the tested cutoff.
    # Equal chain endpoints force zero energy when all trip draws are zero.
    # At positive peak weights each artificial meter then takes its lower bound.
    dummy = m.var(0, 1, cutoff-fsum(peak_weights[s]*m.lower[i] for s, i in peaks.items()), integer=True)
    for served, _, _ in levels.values():
        m.lower[served] = 0
        m.add([(served, 1.), (dummy, 1.)], 1., 1.)
    charged = defaultdict(list)
    for day, whole in p.cases.items():
        case = subset_case(whole, [v for v in whole["trucks"] if (day, v) in fixed])
        for site in SITES:
            for count, parts in cm._groups(case, site):
                hour = int(parts[0][0]//60)
                exact = site == "PORT" and (day, hour) in hours
                # Integer E1 owners in the selected hours. For groups of
                # identical quarters, energy per assigned quarter is bounded
                # by the meter *upper* bound. The common continuous meter
                # still bounds the group's mean. Both are necessary for E1.
                decisions, _ = cm._limits(m, (count, parts, cm._equipment_at(site, "one"), peaks[site], spec), exact)
                for _, b, v, i, _ in decisions:
                    charged[day, v].append((b+15*(count-1), i))
                    m.cost[i] = energy_weight*p.prices[day][hour]/1000
        cm._balance(m, case, day, levels, charged, spec)
    start = perf_counter()
    result = cm._bounded_mip(m, cutoff, 1e-5)
    if result.status != 0:
        raise ArithmeticError(("capped partial reservation bound", result.message))
    raw_lower = getattr(result, "mip_dual_bound", None)
    lower = min(cutoff, result.fun, raw_lower if raw_lower is not None else result.fun)
    return dict(status_code=result.status, status=result.message, objective=result.fun, dual_bound=lower,
                mip_dual_bound=raw_lower,
                gap=getattr(result, "mip_gap", None), seconds=perf_counter()-start,
                artificial=bool(result.x[dummy]>.5), integer_variables=sum(m.integer), hour_count=len(hours))


def partial_e1_bound(p, spec, rule, fixed, pool, *, energy_weight, peak_weights, upgrade_upper, e1_upper):
    """Certify E1 lower bounds independently of its feasible schedule.

    pool supplies an audited E4 optimum and its solver bound. The supplied
    annual upper bounds come from replayed hardware schedules at these weights.
    Only the returned lower_bound can be used as a lower bound for E1.
    """
    fixed = set(fixed)
    if any(peak_weights.get(site, 0.)<=0 for site in SITES):
        raise ValueError("Partial reservation supports require positive meter weights")
    raw = pool["stats"].get("dual_bound")
    base = min(pool["stats"]["objective"], raw if raw is not None else pool["stats"]["objective"])
    continuous=cm.relaxation(p,"one",spec,rule,fixed,energy_weight=energy_weight,peak_weights=peak_weights)
    lower=max(base,continuous["stats"]["objective"])
    ranked = _rank_hours(p, spec, fixed, pool)
    trials = []
    margin = max(0., e1_upper-upgrade_upper)
    if not ranked or margin <= 1e-7:
        return dict(lower_bound=lower, continuous=continuous["stats"], ranked_hours=ranked, trials=trials)
    near = min(e1_upper, max(base, upgrade_upper)+min(.02, margin/2))
    span = max(.25, 2.*max(0., near-base))
    cutoffs = sorted({near, min(e1_upper, near+span), min(e1_upper, near+4*span)})
    for cutoff in cutoffs:
        if cutoff <= lower+1e-6:
            continue
        limits = cm.relaxation(p, "one", spec, rule, fixed, energy_weight=energy_weight,
                               peak_weights=peak_weights, objective_upper=cutoff)
        stage = dict(cutoff=cutoff, meter_support=limits, solves=[])
        for n in sorted({min(20,len(ranked)), min(32,len(ranked))}):
            hours = {(x["date"], x["hour"]) for x in ranked[:n]}
            solve = _capped_hours(p, spec, rule, fixed, energy_weight, peak_weights, cutoff, limits, hours)
            stage["solves"].append(solve)
            lower = max(lower, solve["dual_bound"])
            if lower >= cutoff-2e-5:
                break
        trials.append(stage)
        if lower < cutoff-2e-5:
            break
    if lower > e1_upper+1e-6:
        raise ArithmeticError(("partial E1 lower exceeds replayed upper", lower, e1_upper))
    return dict(lower_bound=lower, continuous=continuous["stats"], ranked_hours=ranked, trials=trials)


def decision_e1_bound(p, spec, rule, fixed, pool, *, incumbent, energy_weight, peak_weights,
                      upgrade_upper, nominal_rate, wall_seconds=45*60):
    """Bound a high-rate annual E1 objective, with an independently replayed upper bound.

    Selected port hours provide a global lower bound. Improving reservations in one
    week changes only the feasible upper bound. Continuous reoptimization on the
    whole period restores the two common meters and every inter-day SOC link.
    The caller enforces the combination wall clock and checks invoice decisions.
    """
    from .cabinet_audit import replay, schedule_on_clock
    from .cabinet_incumbent import polish_e1
    from .energy_boundary import Period, components

    if nominal_rate<80 or not 0<wall_seconds<=45*60:
        raise ValueError(("High-rate decision bounds require the registered rate and time limits",
                          nominal_rate,wall_seconds))
    start=perf_counter()
    deadline=start+wall_seconds
    fixed=set(fixed)
    weights=dict(energy_weight=energy_weight,peak_weights=peak_weights)
    replay(p,"two_shared_pool",spec,rule,pool,fixed=fixed,**weights)
    best={k:incumbent[k] for k in ("states","schedule")}
    audit=replay(p,"one",spec,rule,best,fixed=fixed,check_objective=False,**weights)
    upper=energy_weight*audit["purchase_eur"]+fsum(peak_weights[s]*audit["site_peak_kw"][s] for s in SITES)
    initial_upper=upper
    proof=partial_e1_bound(p,spec,rule,fixed,pool,upgrade_upper=upgrade_upper,e1_upper=upper,**weights)
    lower=proof["lower_bound"]
    weekly=[]
    caps=None
    for days in components(p.days,p.links):
        if (upper-lower<=1. and lower>upgrade_upper+1e-6) or perf_counter()>=deadline:
            break
        if caps is None:
            proxy=cm.relaxation(p,"one",spec,rule,fixed,**weights)
            caps={s:max(proxy["peak_kw"][s],audit["site_peak_kw"][s]) for s in SITES}
        local=Period(days,p.prices)
        # The original witness is feasible under these fixed meter ceilings. Its
        # price in this component is a valid ceiling for the weekly price search.
        budget=fsum(audit["daily_eur"].get(d,0.) for d in local.offset)
        entry=dict(start=days[0]["date"],peak_caps_kw=caps,price_ceiling_eur_2021=budget)
        weekly.append(entry)
        try:
            result=cm.solve(local,"one",spec,rule,local.keys&fixed,peak_bounds=caps,
                            force_exact=True,objective_upper=budget+1e-6,absolute_gap=.002,
                            _weekly_deadline=min(deadline,perf_counter()+60.))
        except TimeoutError as exc:
            entry["stop_reason"]=str(exc)
            break
        replay(local,"one",spec,rule,result,fixed=local.keys&fixed)
        schedule=[row for row in best["schedule"] if row["date"] not in local.offset]
        schedule.extend(schedule_on_clock(p,local,result["schedule"]))
        improved=polish_e1(p,spec,rule,fixed,dict(schedule=schedule),energy_weight,peak_weights)
        value=improved["stats"]["objective"]
        entry.update(weekly_price_solver=result["stats"],whole_period_polish=improved["stats"],
                     replayed_upper_eur_2025=value)
        if value<upper:
            upper=value
            best={k:improved[k] for k in ("states","schedule")}
    if lower>upper+1e-6:
        raise ArithmeticError(("Decision lower exceeds replayed upper bound",lower,upper))
    gap=max(0.,upper-lower)
    stats=dict(status="bounded",objective=upper,dual_bound=min(upper,lower),
               gap=gap/max(abs(upper),1e-10),absolute_gap_eur_2025=gap,seconds=perf_counter()-start,
               initial_replayed_upper_eur_2025=initial_upper,
               uniform_objective_decision_certified=gap<=1. and lower>upgrade_upper+1e-6,
               nominal_capacity_price=nominal_rate,selected_hour_certificate=proof,weekly_improvements=weekly)
    result=dict(**best,stats=stats)
    result["audit"]=replay(p,"one",spec,rule,result,fixed=fixed,**weights)
    return result
