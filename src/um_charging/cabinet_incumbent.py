"""Construct and replay a feasible E1 schedule for bounding each nested facility."""
import math
from collections import Counter, defaultdict
from copy import copy
from itertools import groupby, product

from . import cabinet_model
from .cabinet_audit import close, replay, schedule_on_clock
from .cabinet_tariff import annual_factors
from .fleet_service import SITES


def screen_e1_peak_sum(local, spec, rule, fixed, total_kw):
    """Exclude an E1 peak sum using a continuous relaxation of chain reservations.

    Each selected chain returns to its initial SOC. Its grid energy is known.
    Each is credited independently with its maximum possible warehouse energy.
    At the port, entire aligned quarters have only one owner. For short access
    windows the number of additional full quarters is rounded *before* taking
    the convex hull. A zero-deficit solution is necessary for real service.
    """
    from .energy_boundary import A, Matrix
    from .fleet_service import _events
    proof = cabinet_model.relaxation(local, "one", spec, rule, fixed, energy_weight=0.,
                                     peak_weights=dict.fromkeys(SITES, 1.), objective_upper=total_kw)
    rating = min(spec.truck_kw, cabinet_model.EQUIPMENT["one"][1])
    # A single-day relaxation skips coordinate support solves. Nonnegativity
    # still bounds either meter by the full tested sum.
    caps = {s: min(total_kw, rating, proof["upper_kw"].get(s, rating)) for s in SITES}
    full = min(rating, caps["PORT"])/4
    if full <= 0:
        raise ValueError("Port meter upper bound must be positive")
    chains = ([[key] for key in sorted(fixed)] if rule == A else
              [list(run) for chain in local.chains for active, run in groupby(chain, fixed.__contains__) if active])
    owner = {key: i for i, chain in enumerate(chains) for key in chain}
    budgets = [{s: defaultdict(float) for s in SITES} for _ in chains]
    for day, case in local.cases.items():
        for a, b, eligible in _events(case):
            for s in SITES:
                for v in eligible[s]:
                    if (day, v) in owner:
                        budgets[owner[day, v]][s][day, int(a//15)] += (b-a)*rating/60
    residual = []
    port = defaultdict(list)
    for i, (chain, access) in enumerate(zip(chains, budgets)):
        grid = math.fsum(k for d, v in chain for _, _, k, _ in local.cases[d]["trucks"][v]["trips"])/spec.efficiency
        warehouse = math.fsum(min(k, caps["WAREHOUSE"]/4) for k in access["WAREHOUSE"].values())
        residual.append(max(0., grid-warehouse))
        for quarter, kwh in access["PORT"].items():
            port[quarter].append((i, min(full, kwh+1e-10)))

    m = Matrix()
    missing = m.var(0., max((math.ceil(k/full) for k in residual), default=0), cost=1.)
    terms = [[] for _ in chains]
    types = Counter(tuple(edges) for edges in port.values())
    for edges, count in types.items():
        shared = []
        for i, kwh in edges:
            x = m.var(0., count)
            shared.append((x, 1.))
            terms[i].append((x, kwh))
        m.add(shared, high=count)
    combination_counts = []
    for kwh, edges in zip(residual, terms):
        m.add(edges + [(missing, full)], low=kwh)
        m.add([(x, 1.) for x, _ in edges] + [(missing, 1.)], low=math.ceil(kwh/full-1e-8))
        short = [(x, e) for x, e in edges if e < full]
        counts = [range(m.upper[x]+1) for x, _ in short]
        combinations = math.prod(map(len, counts))
        combination_counts.append(combinations)
        if not short or combinations > 4096:
            continue
        cases = list(product(*counts))
        weights = [m.var(0., 1.) for _ in cases]
        m.add([(z, 1.) for z in weights], 1., 1.)
        for j, (x, _) in enumerate(short):
            m.add([(x, 1.)] + [(z, -option[j]) for z, option in zip(weights, cases)], 0., 0.)
        required = [max(0, math.ceil((kwh-math.fsum(n*e for n, (_, e) in zip(option, short)))/full-1e-8))
                    for option in cases]
        m.add([(x, 1.) for x, e in edges if e == full] + [(missing, 1.)]
              + [(z, -n) for z, n in zip(weights, required)], low=0.)
    solution = m.solve()
    if solution.status != 0:
        raise ArithmeticError(("chain reservation deficit LP", solution.message))
    return dict(tested_peak_sum_kw=total_kw, excluded=solution.fun>1e-6,
                minimum_artificial_quarter_deficit=float(solution.fun), status_code=solution.status,
                status=solution.message, meter_upper_kw=caps, continuous_meter_support=proof,
                chain_count=len(chains), port_quarter_types=len(types), short_window_combinations=combination_counts)


def polish_e1(period,spec,rule,fixed,witness,energy_weight,peak_weights,*,peak_bounds=None):
    """Optimize both meter peaks and all continuous decisions at feasible E1 reservations."""
    owner = {(r["date"],r["site"],r["reservation_slot"]-period.offset[r["date"]]//15):r["vehicle_id"]
             for r in witness["schedule"]}
    restricted = copy(period)
    restricted.cases = {}
    for day,case in period.cases.items():
        active = cabinet_model.subset_case(case,[v for v in case["trucks"] if (day,v) in fixed])
        trucks = {}
        for v,task in sorted(active["trucks"].items()):
            windows = []
            for left,right,site in task["windows"]:
                for q in range(int(left//15),math.ceil(right/15)):
                    if owner.setdefault((day,site,q),v)!=v:
                        continue
                    a,b = max(left,q*15),min(right,(q+1)*15)
                    if windows and windows[-1][1]==a and windows[-1][2]==site:
                        windows[-1]=(windows[-1][0],b,site)
                    else:
                        windows.append((a,b,site))
            trucks[v]={**task,"windows":windows}
        restricted.cases[day]={**active,"trucks":trucks}
    weights=dict(energy_weight=energy_weight,peak_weights=peak_weights)
    result=cabinet_model.solve(restricted,"one",spec,rule,fixed,force_exact=True,peak_bounds=peak_bounds,**weights)
    audited=replay(period,"one",spec,rule,result,fixed=fixed,**weights)
    if peak_bounds and any(audited["site_peak_kw"][s]>limit+1e-6 for s,limit in peak_bounds.items()):
        raise ArithmeticError("Polished schedule exceeded its meter limit")
    return {**result,"audit":audited}


def e1_peak_witness(p, periods, spec, rule, fixed):
    """A replayed common-peak upper bound and a separate certified global lower bound."""
    from .energy_boundary import B
    keys = set(fixed)
    by_week = [w.keys & keys for w in periods]
    owner = {key: j for j, subset in enumerate(by_week) for key in subset}
    if set(owner) != keys or sum(map(len, by_week)) != len(keys):
        raise ValueError("Peak proof requires one owner for every selected duty")
    if rule == B and any(owner[a] != owner[b] for ch in p.chains for a, b in zip(ch, ch[1:])
                         if a in keys and b in keys):
        raise ValueError("Peak proof would split a selected battery chain")
    weights = dict.fromkeys(SITES, 1.)
    proxy = cabinet_model.relaxation(p, "one", spec, rule, keys, energy_weight=0., peak_weights=weights)
    lower = proxy["stats"]["objective"]
    rate = min(cabinet_model.EQUIPMENT["one"][1], spec.truck_kw)
    caps = {s: min(rate, max(0., math.ceil(proxy["peak_kw"][s]-1e-9))) for s in SITES}
    attempts = []
    while True:
        joined = {"states": [], "schedule": []}
        for local, selected in zip(periods, by_week):
            witness = cabinet_model.solve(local, "one", spec, rule, selected, energy_weight=0.,
                                          _guide=(caps, 0., {}))
            attempts.append(dict(start=local.days[0]["date"], upper_kw=caps, stats=witness["stats"]))
            if witness["stats"]["objective"] > .5:
                close(witness["stats"]["dual_bound"], 1., "unattainable E1 meter ceilings")
                break
            replay(local, "one", spec, rule, witness, fixed=selected, check_objective=False)
            joined["states"].extend(witness["states"])
            joined["schedule"].extend(schedule_on_clock(p, local, witness["schedule"]))
        else:
            break
        next_caps = {s: min(rate, math.ceil((cap+rate)/2)) for s, cap in caps.items()}
        if next_caps == caps:
            raise ArithmeticError("E1 cannot replay the fixed duties at rated power")
        caps = next_caps
    priced = polish_e1(p, spec, rule, keys, joined, 1., {}, peak_bounds=caps)
    upper = math.fsum(priced["audit"]["site_peak_kw"].values())
    middle = math.floor((upper+lower)*50)/100
    screens = []
    if middle > lower+1e-6:
        rankings = []
        for local, selected in zip(periods, by_week):
            bound = cabinet_model.relaxation(local, "one", spec, rule, selected, energy_weight=0.,
                                             peak_weights=weights)
            rankings.append((bound["stats"]["objective"], local.days[0]["date"], local, selected))
        for _, day, local, selected in sorted(rankings, key=lambda item: -item[0]):
            screen = screen_e1_peak_sum(local, spec, rule, selected, middle)
            screens.append(dict(start=day, **screen))
            if screen["excluded"]:
                lower = middle
                break
    if lower > upper+1e-6:
        raise ArithmeticError(("Inverted E1 peak bounds", lower, upper))
    stats = dict(status="Replayed upper bound and auxiliary LP lower certificate",
                 objective=upper, dual_bound=lower, gap=max(0., upper-lower)/max(1., abs(upper)),
                 min_peak_proven=abs(upper-lower)<=1e-6, all_period_relaxation=proxy,
                 weekly_recovery=attempts, reservation_screens=screens, fixed_allocation_cost=priced["stats"])
    result = dict(states=priced["states"], schedule=priced["schedule"], stats=stats)
    result["audit"] = replay(p, "one", spec, rule, result, fixed=keys, energy_weight=0., peak_weights=weights)
    return result


def _weekly_witness(local, spec, rule, keys, limits):
    """Find a physical schedule near the continuous lower bound at these caps."""
    # At the single-cabinet rating or at zero, a meter cap permits the full
    # vehicle power or deactivates the site. Direct weekly price optimization
    # at these bounds gives the tightest witness for this particular pair.
    single_rating = min(spec.truck_kw, cabinet_model.EQUIPMENT["one"][1])
    if all(limit == 0 or limit >= single_rating for limit in limits.values()):
        result = cabinet_model.solve(local, "one", spec, rule, keys, peak_bounds=limits, force_exact=True)
        audit = replay(local, "one", spec, rule, result, fixed=keys)
        for site, ceiling in limits.items():
            if audit["site_peak_kw"][site] > ceiling + 1e-6:
                raise ValueError(("Fixed meter ceiling exceeded", site, ceiling, audit["site_peak_kw"]))
        return dict(**result, audit=audit, method="fixed-peak weekly energy optimum", preceding_trials=[])
    lower = cabinet_model.relaxation(local, "one", spec, rule, keys, peak_bounds=limits)
    lower_bill = lower["stats"]["objective"]
    trials = []
    # These budgets control the search for a feasible upper bound only. The
    # registered energy and capacity objective is optimized separately.
    for margin in (.00005, .0001, .00025, .0005, .001, .005):
        budget = lower_bill + max(1e-6, abs(lower_bill)*margin)
        result = cabinet_model.solve(local, "one", spec, rule, keys, _guide=(limits, budget, {}))
        if result["stats"].get("certificate") is False:
            # The rejected budget returns a binary lower-bound certificate
            # and no physical schedule. Keep it as an infeasible search target.
            close(result["stats"]["objective"], 1., "rejected budget objective")
            close(result["stats"]["dual_bound"], 1., "rejected budget lower bound")
            trials.append(dict(stats=result["stats"], budget_eur=budget))
            continue
        audit = replay(local, "one", spec, rule, result, fixed=keys, check_objective=False)
        within = (audit["purchase_eur"] <= budget+1e-6 and
                  all(audit["site_peak_kw"][s] <= ceiling+1e-6 for s, ceiling in limits.items()))
        close(result["stats"]["objective"], int(not within), "binary peak and energy budget feasibility")
        item = dict(**result, audit=audit, budget_eur=budget)
        if within:
            return dict(**item, method="replayed energy-budget witness", relaxation=lower, preceding_trials=trials)
        trials.append(item)
    # A rounded relaxed peak need not admit the integral truck reservations.
    # The original fixed service is known feasible on E1. Its price dispatch
    # still yields a valid upper bound using its actual meter peaks.
    unrestricted = cabinet_model.solve(local, "one", spec, rule, keys)
    audit = replay(local, "one", spec, rule, unrestricted, fixed=keys)
    return dict(**unrestricted, audit=audit, method="unrestricted energy optimum", relaxation=lower,
                preceding_trials=trials, budget_eur=None)


def build_incumbent(period, periods, spec, rule, fixed, *, energy_weight, peak_weights):
    """Search at the relaxed and upward-rounded meter peaks and replay each witness.

    The rounding supplies a trial ceiling for each meter. Only peaks measured
    from the feasible dispatch enter the objective upper bound. Components may
    be solved separately here because the two common demand ceilings are fixed.
    """
    periods = tuple(periods)
    selected = set(fixed)
    relaxed = cabinet_model.relaxation(period, "one", spec, rule, selected,
                                       energy_weight=energy_weight, peak_weights=peak_weights)
    continuous={s:max(0.,relaxed["peak_kw"].get(s,spec.truck_kw)) for s in SITES}
    rounded={s:math.ceil(x) for s,x in continuous.items()}
    choices=[rounded] if rounded==continuous else [rounded,continuous]
    trials=[_at_peaks(period,periods,spec,rule,selected,limits,energy_weight,peak_weights) for limits in choices]
    best=min(trials,key=lambda r:r["objective_upper"])
    return dict(**best,relaxed=relaxed,other_peak_trials=[t for t in trials if t is not best])


def _at_peaks(period,periods,spec,rule,selected,limits,energy_weight,peak_weights):
    coverage = set()
    weeks = []
    for local in periods:
        keys = local.keys & selected
        if keys & coverage:
            raise ValueError("Overlapping components in the E1 upper-bound dispatch")
        coverage.update(keys)
        weeks.append(dict(start=local.days[0]["date"], **_weekly_witness(local, spec, rule, keys, limits)))
    if coverage != selected:
        raise ValueError("E1 upper-bound dispatch missed fixed duties")
    # A component split through a live chain would impose an extra 0 net
    # change at midnight. Check all links, including such a join, on the
    # original full-period clock before using the upper bound.
    schedule, states = [], []
    for local, week in zip(periods, weeks):
        schedule.extend(schedule_on_clock(period, local, week["schedule"]))
        states.extend(week["states"])
    priced = math.fsum(week["audit"]["purchase_eur"] for week in weeks)
    peaks = {s: max((w["audit"]["site_peak_kw"][s] for w in weeks), default=0.) for s in SITES}
    upper = energy_weight*priced + math.fsum(peak_weights.get(s, 0.)*peaks[s] for s in SITES)
    whole = replay(period, "one", spec, rule,
                   dict(states=states, schedule=schedule, stats=dict(objective=upper)), fixed=selected,
                   energy_weight=energy_weight, peak_weights=peak_weights)
    polished=polish_e1(period,spec,rule,selected,dict(schedule=schedule),energy_weight,peak_weights)
    if polished["stats"]["objective"]>upper+1e-6:
        raise ArithmeticError(("fixed assignments exclude their own E1 witness",upper,polished["stats"]))
    audit=polished["audit"]
    return dict(objective_upper=polished["stats"]["objective"],trial_peak_limits_kw=limits,
                purchase_eur=audit["purchase_eur"],site_peak_kw=audit["site_peak_kw"],polished=polished,
                weeks=weeks,starting_audit=whole,audit=audit)


def low_band_interval(period, fixed, spec, rule, network, endpoint_rate, witness):
    """Certify cancellation of both volumetric charges over [0, endpoint_rate]."""
    repeat = network["annualization"]["weeks_per_year"] / network["annualization"]["sample_weeks"]
    annual_kwh = math.fsum(leg[2] for d, v in fixed for leg in period.cases[d]["trucks"][v]["trips"])
    annual_kwh *= repeat / spec.efficiency
    threshold = network["full_load_hours_boundary"]
    wh_slots = {(d, q) for d, v in fixed for a, b, site in period.cases[d]["trucks"][v]["windows"]
                if site == "WAREHOUSE" for q in range(int(a//15), math.ceil(b/15))}
    wh_hours = len(wh_slots)*.25*repeat
    electricity, money = annual_factors(network)
    # In either tariff's high port band, PORT kW <= annual port kWh / 2500
    # <= total annual kWh / 2500. Drop all port connector integrality and
    # permit two independent cabinets. This is a superset of all high-port plans.
    cap = annual_kwh / threshold
    checks = []
    for rate in (0., endpoint_rate):
        relaxed = cabinet_model.relaxation(period, "two_independent", spec, rule, fixed,
                                           energy_weight=electricity, peak_weights=dict.fromkeys(SITES, rate*money),
                                           peak_bounds={"PORT": cap+1e-8})
        stats = relaxed["stats"]
        lower = stats["objective"] if stats["dual_bound"] is None else stats["dual_bound"]
        feasible = witness["purchase_eur"]*electricity + rate*money*math.fsum(witness["site_peak_kw"].values())
        checks.append(dict(rate=rate, high_port_lower_eur_2025=lower, e1_upper_eur_2025=feasible,
                           margin_eur_2025=lower-feasible, relaxation=stats))
    # The high-port minimum of affine schedule costs is concave in the
    # uniform capacity rate. Its endpoint chord stays above the *same*
    # feasible E1 schedule's affine cost when both endpoint margins are positive.
    proven = wh_hours < threshold and all(r["margin_eur_2025"] > 1e-6 for r in checks)
    wh_energy_max = min(annual_kwh, wh_hours*min(spec.truck_kw, cabinet_model.EQUIPMENT["one"][1]))
    site_errors = {}
    if proven:
        for basis, tariff in network["tariffs"].items():
            per_site = tariff["bands"]["low"]["energy_eur_per_kwh"]*wh_energy_max*money
            site_errors[basis] = dict.fromkeys(SITES, per_site)
    return dict(from_rate=0., to_rate=endpoint_rate, all_sites_low_proved=proven,
                annual_grid_kwh=annual_kwh, warehouse_hours_upper=wh_hours, high_port_peak_upper_kw=cap,
                per_site_abs_annual_volumetric_difference_upper_eur_2025=site_errors,
                combined_abs_annual_volumetric_difference_upper_eur_2025=0. if proven else None,
                checks=checks)


def high_band_interval(period, fixed, spec, rule, network, from_rate, to_rate, witness, low_proof):
    """Bound the volumetric fee difference for high-port, low-warehouse dispatch."""
    annual = low_proof["annual_grid_kwh"]
    wh_hours = low_proof["warehouse_hours_upper"]
    threshold = network["full_load_hours_boundary"]
    electricity, money = annual_factors(network)
    checks = {}

    def check(rate):
        if rate not in checks:
            ceiling = electricity*witness["purchase_eur"] + rate*money*sum(witness["site_peak_kw"].values())
            relaxed = cabinet_model.relaxation(period, "two_independent", spec, rule, fixed,
                                               energy_weight=electricity, peak_weights=dict.fromkeys(SITES, rate*money),
                                               objective_upper=ceiling+1e-6)
            bounds = relaxed["upper_kw"]
            # A low port band implies Q_total <= threshold*Pport + annual
            # warehouse kWh. The latter cannot exceed hours_of_access*Pwh.
            max_low_kwh = threshold*bounds["PORT"] + wh_hours*bounds["WAREHOUSE"]
            checks[rate] = dict(rate=rate, e1_upper_eur_2025=ceiling, upper_kw=bounds,
                                low_port_annual_kwh_upper=max_low_kwh,
                                high_port_proved=max_low_kwh < annual-1e-6,
                                support_lps=relaxed["supports"], relaxation=relaxed["stats"])
        return checks[rate]

    last = check(to_rate)
    ranges = []
    if last["high_port_proved"] and wh_hours < threshold:
        a = from_rate
        for _ in range(12):
            left = check(a)
            if left["high_port_proved"]:
                break
            a = (a+to_rate)/2
        else:
            a = to_rate
        # For each physical schedule, its cost minus this same E1 schedule's
        # cost is affine. If nonpositive inside an interval it is nonpositive
        # at least at one endpoint. The union of the two endpoint sublevel
        # sets therefore covers every hardware optimum throughout the interval.
        for left_rate in sorted({a, (a+to_rate)/2}):
            left = check(left_rate)
            if not left["high_port_proved"]:
                continue
            wh_upper = max(left["upper_kw"]["WAREHOUSE"], last["upper_kw"]["WAREHOUSE"])
            energy_upper = min(annual, wh_hours*wh_upper)
            errors, site_errors = {}, {}
            for basis, tariff in network["tariffs"].items():
                lo, hi = (tariff["bands"][band]["energy_eur_per_kwh"] for band in ("low", "high"))
                # Each bill is hi*Q_total + (lo-hi)*Q_warehouse. Differences
                # between two warehouse readings in [0, bound] are <= bound.
                errors[basis] = abs(lo-hi)*energy_upper*money
                site_errors[basis] = {"PORT": hi*energy_upper*money, "WAREHOUSE": lo*energy_upper*money}
            ranges.append(dict(from_rate=left_rate, to_rate=to_rate, warehouse_kwh_upper=energy_upper,
                               per_site_abs_annual_volumetric_difference_upper_eur_2025=site_errors,
                               max_abs_annual_volumetric_difference_eur_2025=errors))
    return dict(annual_grid_kwh=annual, warehouse_hours_upper=wh_hours, intervals=ranges,
                checks=[checks[r] for r in sorted(checks)])
