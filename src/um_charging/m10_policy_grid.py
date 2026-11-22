"""Compare fixed-service immediate and daily rolling dispatch on the registered priced grid."""
from collections import Counter, defaultdict
import math

from . import site_sizing as ss
from .m10_costs import _parameters
from .m10_immediate import simulate_week
from .m10_policy_costs import DISCLOSURE, invoices, operating_caps, point_key, surplus_disclosure
from .m10_rolling import rolling_requests, rolling_week
from .site_sizing_screen import COST_MARGIN_EUR


FROZEN = {ss.Design(1,20,20): (20,20), ss.Design(1,40,20): (40,20)}
TABLES = ("policy_points", "policy_weeks", "policy_days", "policy_vehicles", "policy_annual",
          "policy_minima", "policy_design_ranks", "policy_cross_checks", "policy_schedules",
          "policy_surplus_days", "policy_surplus_segments", "policy_surplus_vehicles", "policy_comparison")


def _dispatch_week(period, design, caps, reference, evidence):
    # Equal feasible regions can have different price-optimal meter traces.
    # The evidence layer may reuse only this exact native request identity.
    requests = rolling_requests(period,design,caps,reference)
    week = rolling_week(period,design,caps,reference,evidence.batch(requests))
    for row in week["days"]:
        row.update(certificate_design=design.label, certificate_caps_kw=list(caps),
                   meter_selection="deterministic_native_request")
    states = {(r["date"],r["vehicle_id"]) for r in week["states"]}
    previous = {right:left for chain in period.chains for left,right in zip(chain,chain[1:])
                if left in reference and right in reference}
    unknown, conditional = set(), set()
    for group in week["days"]:
        keys = [tuple(key) for key in group["fixed"]]
        if any(previous.get(key) in unknown for key in keys):
            conditional.add(group["date"])
        if group["date"] in conditional or any(key not in states for key in keys):
            unknown.update(keys)
        group["conditional_on_unobserved_predecessor"] = group["date"] in conditional
    for field in ("schedule","states"):
        week["conditional_"+field] = [r for r in week[field] if r["date"] in conditional]
        week[field] = [r for r in week[field] if r["date"] not in conditional]
    return week


def _day_template(policy, design, caps, week, date, vehicle):
    return dict(policy=policy, **point_key(design,caps), week=week, date=date, vehicle_id=vehicle,
                status=None, completed=None, group_status=None, evidence_id=None, segment_start=None,
                segment_end=None, is_segment_end=None, start_soc_kwh=None, end_soc_kwh=None,
                last_observed_soc_kwh=None, failure=None, site_grid_kwh=None, site_purchase_eur_2021=None,
                terminal_excess_kwh=None, terminal_excess_grid_kwh=None)


def _rolling_days(period, week, design, caps):
    states = {(r["date"],r["vehicle_id"]):r for r in week["states"]}
    grid, expense = defaultdict(lambda:dict.fromkeys(ss.SITES,0.)), defaultdict(lambda:dict.fromkeys(ss.SITES,0.))
    for row in week["schedule"]:
        day, v, site = row["date"],row["vehicle_id"],row["site"]
        energy = row["power_kw"]*(row["end_min"]-row["start_min"])/60
        hour = math.floor((row["start_min"]-period.offset[day])/60)
        grid[day,v][site] += energy
        expense[day,v][site] += energy*period.prices[day][hour]/1000
    days = []
    for group in week["days"]:
        for day, vehicle in group["fixed"]:
            key = day, vehicle
            row = _day_template("rolling",design,caps,week["week"],day,vehicle)
            state = states.get(key)
            if state is not None:
                row.update(status="complete", completed=True, start_soc_kwh=state["x"], end_soc_kwh=state["y"],
                           last_observed_soc_kwh=state["y"], site_grid_kwh=grid[key], site_purchase_eur_2021=expense[key],
                           terminal_excess_kwh=0., terminal_excess_grid_kwh=0.)
            else:
                row["status"] = ("conditional_after_unobserved_day" if group["conditional_on_unobserved_predecessor"]
                                 else "joint_day_infeasible" if group["status"] == "infeasible" else "joint_day_unresolved")
            row.update(group_status=group["status"],evidence_id=group["id"])
            days.append(row)
    return days


def _counts(rows):
    known = sum(r["completed"] is True for r in rows)
    unknown = sum(r["completed"] is None for r in rows)
    return dict(registered_vehicle_days=len(rows), known_completed_vehicle_days=known,
                completed_vehicle_days=None if unknown else known, unclassified_vehicle_days=unknown)


def _point(tables, inputs, evidence, parameters, policy, design, caps, checkpoint):
    ref = inputs.registered
    key = dict(policy=policy, **point_key(design,caps))
    weeks, all_days = [], []
    for period in inputs.periods:
        evidence.check()
        if policy == "immediate":
            w = simulate_week(period,design,ref)
            w.update(status="certified" if w["summary"]["same_service"] else "infeasible",
                     purchase_lower=w["audit"]["purchase_eur"],purchase_upper=w["audit"]["purchase_eur"])
            daily = []
            for d in w["days"]:
                row = _day_template(policy,design,caps,w["week"],d["date"],d["vehicle_id"])
                row.update(d)
                daily.append(row)
        else:
            w = _dispatch_week(period,design,caps,ref,evidence)
            daily = _rolling_days(period,w,design,caps)
        same = False if w["status"]=="infeasible" else True if w["audit"] is not None else None
        weekly = dict(**key, week=w["week"], status=w["status"], same_service=same, **_counts(daily),
                      purchase_lower=w["purchase_lower"], purchase_upper=w["purchase_upper"])
        snapshot = dict(**weekly, schedule=w["schedule"], states=w.get("states",[]), days=w["days"],
                        segments=w.get("segments",[]), audit=w["audit"], summary=w.get("summary"),
                        conditional_schedule=w.get("conditional_schedule",[]),conditional_states=w.get("conditional_states",[]))
        tables["policy_schedules"].append(snapshot)
        if checkpoint:
            checkpoint("policy_schedules", snapshot)
        if policy == "rolling":
            evidence.record_rolling_week(w)
        weeks.append(w)
        all_days.extend(daily)
        tables["policy_weeks"].append(weekly)
    tables["policy_days"].extend(all_days)
    for v in sorted({d["vehicle_id"] for d in all_days},key=int):
        batch = [d for d in all_days if d["vehicle_id"] == v]
        tables["policy_vehicles"].append(dict(**key,vehicle_id=v,**_counts(batch),
                                             statuses=dict(Counter(d["status"] for d in batch))))
    statuses = [w["status"] for w in weeks]
    has_all_meters = all(w["audit"] is not None for w in weeks)
    status = ("infeasible" if "infeasible" in statuses else "unresolved" if "unresolved" in statuses
              else "bounded" if "bounded" in statuses else "certified")
    same = False if status=="infeasible" else True if has_all_meters else None
    point = dict(**key, status=status, same_service=same, **_counts(all_days),
                 infeasible_weeks=[w["week"] for w in weeks if w["status"]=="infeasible"],
                 unresolved_weeks=[w["week"] for w in weeks if w["status"]=="unresolved"])
    tables["policy_points"].append(point)
    if design in FROZEN:
        tables["policy_cross_checks"].append(dict(**point, frozen_caps_kw=list(FROZEN[design]),
                                                  at_frozen_caps=(caps==FROZEN[design])))
    bills = None
    if same is True:
        settlement = []
        for p,w in zip(inputs.periods,weeks,strict=True):
            lower = w["purchase_lower"]
            if lower is None:
                energy = math.fsum(w["audit"]["site_grid_kwh"].values())
                lower = min(price for prices in p.prices.values() for price in prices) * energy / 1000
            settlement.append(dict(audit=w["audit"],purchase_lower=lower))
        bills = invoices(inputs.periods,design,settlement,parameters=parameters)
    network, materials = parameters
    equipment, missing, connection = ss.annual_capital_costs(design,materials)
    if missing:
        raise ValueError(("Unpriced hardware in the priced grid",design))
    if bills is None:
        bills_for_table = [dict(scenario=scenario,connection_basis=basis,known_lower=None,known_upper=None,
            missing_ratings_kw=missing,total_lower=None,total_upper=None,equipment=equipment,connection=fee,
            purchase=None,network_energy=None,demand=None,grid_kwh=None,quarter_peak_kw=None,volumetric_rates=None)
            for scenario in ("N0",*network["tariffs"],*network["capacity_sensitivities_eur_per_kw_year"])
            for basis,fee in connection.items()]
    else:
        bills_for_table = bills
    if policy == "immediate":
        daily, disclosure, segments, vehicles = surplus_disclosure(inputs.periods,weeks,design,caps,bills,
                                                                   parameters=parameters,details=True)
        for name,rows in (("policy_surplus_days",daily),("policy_surplus_segments",segments),
                          ("policy_surplus_vehicles",vehicles)):
            tables[name].extend(dict(policy=policy,**r) for r in rows)
    else:
        disclosure = []
    by_case = {(r["scenario"],r["connection_basis"]):r for r in disclosure}
    for bill in bills_for_table:
        annual = dict(**point, **bill, witness_conditioned_lower=bill["total_lower"],
                      witness_conditioned_upper=bill["total_upper"])
        if status == "unresolved":
            # A meter trace can establish physical service while still missing
            # the weekly procurement admission threshold. It cannot certify a rank.
            annual.update(total_lower=None,total_upper=None)
        tables["policy_annual"].append(annual)
        dis = by_case.get((bill["scenario"],bill["connection_basis"]))
        comparison = dict(**key,scenario=bill["scenario"],connection_basis=bill["connection_basis"],
                          status=status,same_service=same)
        for item in ("whole_invoice","terminal_surplus_included"):
            full = item=="whole_invoice"
            costs = ("terminal_excess_kwh","terminal_excess_grid_kwh","terminal_excess_cost_eur_2025",
                     "unattributed_grid_kwh","above_metered_grid_kwh","known_terminal_excess_cost_eur_2025")
            amounts = {}
            for prefix in ("","annual_"):
                for name in costs:
                    amounts[prefix+name] = (None if full else dis[prefix+name] if dis is not None
                                            else 0. if same is True else None)
            tables["policy_comparison"].append(dict(**comparison,item=item,
                invoice_lower_eur_2025_per_year=annual["total_lower"] if full else None,
                invoice_upper_eur_2025_per_year=annual["total_upper"] if full else None,
                **amounts,accounting=None if full else DISCLOSURE))


def _rank(tables):
    cases = defaultdict(list)
    for row in tables["policy_annual"]:
        cases[row["policy"],row["scenario"],row["connection_basis"]].append(row)
    for (policy,scenario,basis), points in sorted(cases.items()):
        case = dict(policy=policy,scenario=scenario,connection_basis=basis)
        ranks = []
        for design in sorted({p["design"] for p in points}):
            eligible = [p for p in points if p["design"]==design and p["status"]!="infeasible"]
            upper = min((p["total_upper"] for p in eligible if p["total_upper"] is not None),default=None)
            lower = (min(p["total_lower"] for p in eligible) if eligible and
                     all(p["total_lower"] is not None for p in eligible) else None)
            ranks.append(dict(**case,design=design,lower_eur_2025_per_year=lower,upper_eur_2025_per_year=upper,
                              has_possible_service=bool(eligible),rank_best=None,rank_worst=None,
                              conditional_rank_best=None,conditional_rank_worst=None,
                              rank_status="infeasible" if not eligible else
                              "unresolved" if upper is None else "admitted_interval"))
        viable = [r for r in ranks if r["has_possible_service"]]
        for r in viable:
            low, high = r["lower_eur_2025_per_year"],r["upper_eur_2025_per_year"]
            best = 1+sum(o["upper_eur_2025_per_year"] is not None and low is not None and
                o["upper_eur_2025_per_year"] < low-COST_MARGIN_EUR for o in viable if o is not r)
            worst = 1+sum(o["lower_eur_2025_per_year"] is None or high is None or
                o["lower_eur_2025_per_year"] <= high+COST_MARGIN_EUR for o in viable if o is not r)
            if high is None:
                r.update(conditional_rank_best=best, conditional_rank_worst=worst)
            else:
                r.update(rank_best=best, rank_worst=worst)
        tables["policy_design_ranks"].extend(ranks)
        available = [p for p in points if p["status"]!="infeasible"]
        upper = min((p["total_upper"] for p in available if p["total_upper"] is not None),default=None)
        lower = (min(p["total_lower"] for p in available) if available and
                 all(p["total_lower"] is not None for p in available) else None)
        possible = [p for p in available if upper is None or p["total_lower"] is None or
                    p["total_lower"] <= upper+COST_MARGIN_EUR]
        unresolved = sum(p["status"]=="unresolved" for p in possible)
        classification = ("no_same_service" if not possible else "unresolved" if unresolved
                          else "intervals_overlap" if len(possible)>1 else "unique")
        for p in possible or [{}]:
            tables["policy_minima"].append(dict(**case,design=p.get("design"),port_cap_kw=p.get("port_cap_kw"),
                warehouse_cap_kw=p.get("warehouse_cap_kw"),status=classification,point_status=p.get("status"),
                minimum_lower=lower,minimum_upper=upper,point_lower=p.get("total_lower"),point_upper=p.get("total_upper"),
                unresolved_points=unresolved,possible_designs=sorted({x["design"] for x in possible})))


def _check_keys(rows, fields, expected, table):
    observed = [tuple(row[k] for k in fields) for row in rows]
    if len(observed) != len(expected) or set(observed) != expected:
        raise ValueError(f"Incomplete, duplicate or unregistered {table} output")


def _verify_coverage(tables, inputs, designs, parameters):
    """Require each registered policy point, week, duty and bill exactly once."""
    network, _ = parameters
    fields = ("policy", "design", "port_cap_kw", "warehouse_cap_kw")
    points = {(policy, design.label, *caps) for design in designs for policy in ("immediate", "rolling")
              for caps in operating_caps(design, policy)}
    cohorts = {period.days[0]["week_start"]: period.keys & inputs.registered for period in inputs.periods}
    if len(cohorts) != len(inputs.periods):
        raise ValueError("Duplicate policy calendar weeks")
    weeks = {(*point, week) for point in points for week in cohorts}
    days = {(*point, week, day, vehicle) for point in points for week, duties in cohorts.items()
            for day, vehicle in duties}
    cases = {(scenario, basis) for scenario in
             ("N0", *network["tariffs"], *network["capacity_sensitivities_eur_per_kw_year"]) for basis in ("new", "existing")}
    if len(cases) != 12:
        raise ValueError("The registered fleet comparison uses twelve tariff and connection cases")
    bills = {(*point, *case) for point in points for case in cases}
    comparisons = {(*bill, item) for bill in bills for item in ("whole_invoice", "terminal_surplus_included")}
    _check_keys(tables["policy_points"], fields, points, "point")
    for name in ("policy_weeks", "policy_schedules"):
        _check_keys(tables[name], (*fields, "week"), weeks, name)
        if any(row["registered_vehicle_days"] != len(cohorts[row["week"]]) for row in tables[name]):
            raise ValueError("Weekly policy duty count differs from the frozen service registration")
    _check_keys(tables["policy_days"], (*fields, "week", "date", "vehicle_id"), days, "vehicle-day")
    billing_fields = (*fields, "scenario", "connection_basis")
    _check_keys(tables["policy_annual"], billing_fields, bills, "annual bill")
    _check_keys(tables["policy_comparison"], (*billing_fields, "item"), comparisons, "invoice disclosure")
    if any(row["registered_vehicle_days"] != sum(map(len, cohorts.values())) for row in tables["policy_points"]):
        raise ValueError("Policy point omits registered vehicle-days")


def policy_grid(inputs, evidence, *, progress=None, checkpoint=None):
    """Return all policy tables. A checkpoint callback receives each replayed weekly record before a stop."""
    tables = {name:[] for name in TABLES}
    grid = ss.design_grid(ss.COARSE_KW)
    parameters = _parameters(inputs.periods)
    designs = sorted(grid,key=lambda d:(d not in FROZEN,d))
    for policy in ("immediate","rolling"):
        for design in designs:
            for caps in operating_caps(design,policy):
                _point(tables,inputs,evidence,parameters,policy,design,caps,checkpoint)
            if progress:
                progress(f"{policy} {design.label} 已回放 {len(operating_caps(design,policy))} 个运行点。")
    _rank(tables)
    _verify_coverage(tables, inputs, designs, parameters)
    return tables
