"""Cabinet dispatch on the fleet study's event grid and quarter reservations."""
from collections import defaultdict
from bisect import bisect_right
from itertools import combinations, groupby
from math import ceil, isfinite
from time import perf_counter
import warnings

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, OptimizeResult, linprog, milp
from scipy.sparse import coo_matrix, vstack

from .cabinet_audit import schedule_on_clock
from .cabinet_shared import add_shared_block, unpack_shared_block
from .energy_boundary import A, B, Matrix, Period, components
from .fleet_service import SITES, _events, subset_case


EQUIPMENT = {
    "one": (1, 50.),
    "two_independent": (2, 100.),
    "two_shared_rule": (2, 50.),
    "two_shared_pool": (2, 50.),
}


def hardware(equipment):
    interfaces, _ = EQUIPMENT[equipment]
    return {"PORT": {"interfaces": interfaces, "power_kw": 100.},
            "WAREHOUSE": {"interfaces": 1, "power_kw": 75.}}


def _groups(case, site, flat=False):
    """Only identical whole quarters may be permuted; paid-energy groups stay in one hour."""
    quarters = defaultdict(list)
    for a, b, eligible in _events(case):
        quarters[int(a // 15)].append((a, b, tuple(sorted(eligible[site]))))
    def signature(item):
        q, parts = item
        return (None if flat else q//4, parts[0][2]) if len(parts) == 1 else (q,)
    for _, grouped in groupby(quarters.items(), signature):
        entries = list(grouped)
        parts = entries[0][1]
        if any(trucks for _, _, trucks in parts):
            yield len(entries), parts


def _levels(model, period, spec, rule, active, physical):
    levels = {}
    cap, e0 = spec.capacity_kwh, spec.boundary_kwh
    for key in sorted(active):
        serve = model.var(int(not physical), 1, -int(physical), physical)
        bounds = (e0, e0) if rule == A else (0, cap)
        levels[key] = serve, model.var(*bounds), model.var(*bounds)
    if rule == A:
        return levels

    def pin(state, indicator):
        if indicator is None:
            model.add([(state, 1)], e0, e0)
        elif physical:
            model.add([(state, 1), (indicator, -cap)], high=e0)
            model.add([(state, 1), (indicator, cap)], low=e0)
    for chain in period.chains:
        for j, key in enumerate(chain):
            if key not in levels:
                continue
            s, x, y = levels[key]
            pin(x, s)
            pin(y, s)
            prev = levels.get(chain[j - 1]) if j else None
            nxt = levels.get(chain[j + 1]) if j + 1 < len(chain) else None
            pin(x, prev[0] if prev else None)
            pin(y, nxt[0] if nxt else None)
            if nxt:
                if physical:
                    for sign in (-1, 1):
                        model.add([(y, sign), (nxt[1], -sign), (s, cap), (nxt[0], cap)], high=2*cap)
                else:
                    model.add([(y, 1), (nxt[1], -1)], 0, 0)
    return levels


def _balance(model, case, day, levels, charged, spec):
    for truck, task in case["trucks"].items():
        key = day, truck
        served, start, end = levels[key]
        pieces = sorted(charged[key])
        previous, previous_draw, cursor = start, 0., 0
        for a, b, kwh, _ in task["trips"]:
            departure = model.var(spec.reserve_kwh,spec.capacity_kwh)
            terms = [(previous,1),(served,-previous_draw),(departure,-1)]
            while cursor < len(pieces) and pieces[cursor][0] <= a:
                terms.append((pieces[cursor][1],spec.efficiency))
                cursor += 1
            model.add(terms,0,0)
            model.add([(departure,1),(served,-kwh)],spec.reserve_kwh,spec.capacity_kwh)
            previous,previous_draw = departure,kwh
        model.add([(previous,1),(served,-previous_draw),(end,-1)]
                  + [(i,spec.efficiency) for _,i in pieces[cursor:]],0,0)


def _equipment_at(site, equipment):
    if site == "WAREHOUSE":
        return 1, 50., False
    n, kw = EQUIPMENT[equipment]
    return n, kw, equipment == "two_shared_rule"


def _limits(model, problem, exact, guide=None, meter_exact=False, pattern=None):
    """Return a relaxed or exact reservation formulation and its reconstruction data."""
    count, parts, inputs, peak, spec = problem
    n, cabinet_kw, split = inputs
    fixed_peak = model.upper[peak] if peak is not None and model.lower[peak] == model.upper[peak] else None
    port_kw = min(50., spec.truck_kw)
    trucks = sorted({truck for _, _, available in parts for truck in available})
    if pattern is not None or (len(trucks) <= n and (not split or len(trucks) == 1)):
        exact = False
    # In a whole-quarter group an exact mode consumes one quarter at a time.
    # Convex averaging is valid *within a mode* only. Counts are never pooled
    # across E3's single-vehicle 50 kW and simultaneous 2 x 25 kW modes.
    if exact and len(parts) == 1:
        a, b, eligible = parts[0]
        hours = (b-a)/60
        if (split and port_kw == 50 and 2 <= len(eligible) <= 3 and peak is not None
                and (guide is None or (fixed_peak is not None and fixed_peak <= guide[0]))
                and (fixed_peak is not None or model.lower[peak] >= 25.)):
            if fixed_peak is None and not meter_exact:
                # The upper meter bound admits every true mode. The master
                # still pays and caps the aggregate at its actual P. If that
                # P cannot be unpacked, the next stage enforces the products.
                upper = model.upper[peak]
                decisions = add_shared_block(model, count, parts[0], model.var(upper, upper))
                model.add([(i, 1) for _,_,_,i,_ in decisions]+[(peak, -count*hours)], high=0)
                return decisions, "shared_block"
            return add_shared_block(model, count, parts[0], peak), "shared_block"
        if split and port_kw == 50 and (peak is None or fixed_peak == 50) and (not guide or guide[0] == 50):
            # Two 25 kW shares per quarter: two shares assigned to the same
            # truck form its 50 kW solo mode. Two distinct owners receive one
            # share each. Integer share counts have this constructive inverse.
            shares = {v:model.var(0, 2*count, integer=True) for v in eligible}
            model.add([(z, 1) for z in shares.values()], high=2*count)
            decisions = []
            for truck, z in shares.items():
                i = model.var(0, port_kw*count*hours)
                model.add([(i, 1), (z, -25.*hours)], high=0)
                model.add([(i, 1), (z, -25.*hours)], low=-25.*hours)
                decisions.append((a, b, truck, i, z))
            return decisions, "halves"
        modes = [(v,) for v in eligible] + (list(combinations(eligible, 2)) if n == 2 else [])
        decisions, mode_slots, all_bits = [], [], []
        for mode in modes:
            bits = ([model.var(0, count, integer=True)] if not meter_exact or peak is None or fixed_peak is not None or guide else
                    [model.var(0, 1, integer=True) for _ in range(count)])
            for lower, higher in zip(bits, bits[1:]):
                model.add([(higher, 1), (lower, -1)], high=0)
            all_bits.extend(bits)
            rate = min(port_kw, 25.) if split and len(mode) == 2 else port_kw
            aggregate = min(cabinet_kw, rate*len(mode))
            if peak is not None:
                aggregate = min(aggregate, model.upper[peak])
            mode_slots.append(bits)
            variables = []
            for truck in mode:
                i = model.var(0, rate*hours*count)
                model.add([(i, 1)] + [(z, -hours*rate) for z in bits], high=0)
                decisions.append((a, b, truck, i, len(mode_slots)-1))
                variables.append((i, 1))
            model.add(variables + [(z, -hours*aggregate) for z in bits], high=0)
            if n == 1:
                # Empty extra slots are interchangeable. Choose the least
                # number sufficient at the realized meter power.
                floor_kw = min(aggregate,model.lower[peak]) if peak is not None else aggregate
                if guide:
                    floor_kw = min(floor_kw,guide[0])
                model.add(variables + [(z,-hours*floor_kw) for z in bits], low=-hours*floor_kw)
            if guide:
                target, slack = guide
                model.add(variables + [(z, -hours*target) for z in bits]
                          + [(slack, -count*hours*aggregate)], high=0)
            if meter_exact and peak is not None and fixed_peak is None:
                # Given k mode quarters, their total grid energy cannot exceed
                # k*h*P. The (k+1)th unary bit deactivates this bound for n>k.
                lower = min(model.lower[peak], aggregate)
                for k in range(1, count):
                    model.add(variables + [(peak, -k*hours)]
                              + [(z, -hours*aggregate) for z in bits[k:]]
                              + [(z, -hours*lower) for z in bits[:k]], high=-k*hours*lower)
                model.add(variables + [(peak, -count*hours)], high=0)
        model.add([(z, 1) for z in all_bits], high=count)
        if peak is not None:
            model.add([(i, 1) for _,_,_,i,_ in decisions] + [(peak, -count*hours)], high=0)
        if guide:
            model.add([(i, 1) for _,_,_,i,_ in decisions] + [(guide[1], -count*hours*cabinet_kw)],
                      high=count*hours*guide[0])
        return decisions, mode_slots

    reservations = {}
    if exact and len(trucks) > n:
        reservations = {v: model.var(0, 1, integer=True) for v in trucks}
        model.add([(z, 1) for z in reservations.values()], high=n)
    decisions, meter = [], []
    for a, b, eligible in parts:
        hours = (b-a)*count/60
        power = []
        on = {}
        if exact and split and len(eligible) > 1:
            on = {v: model.var(0, 1, integer=True) for v in eligible}
            model.add([(z, 1) for z in on.values()], high=2)
            if reservations:
                for v, z in on.items():
                    model.add([(z, 1), (reservations[v], -1)], high=0)
        for truck in eligible:
            i = model.var(0, port_kw*hours)
            if pattern is not None:
                mid = (a+b)/2
                occupied = {v for left,right,v in pattern if left <= mid < right}
                limit = (min(port_kw,25.) if split and len(occupied) == 2 else port_kw) if truck in occupied else 0.
                model.add([(i, 1), (guide[1], -port_kw*hours)], high=limit*hours)
            if truck in reservations:
                model.add([(i, 1), (reservations[truck], -hours*port_kw)], high=0)
            if on:
                model.add([(i, 1), (on[truck], -hours*port_kw)], high=0)
                # If either of the other trucks draws power, its flag must be 1.
                # Zero power need not claim a flag. Thus the projected set of
                # positive powers is precisely union(solo <=50, both <=25).
                model.add([(i, 1)] + [(on[v], hours*25.) for v in eligible if v != truck],
                          high=hours*50.)
            power.append((i, 1))
            decisions.append((a, b, truck, i, None))
        if power:
            model.add(power, high=cabinet_kw*hours)
            meter.extend(power)
    if peak is not None:
        # Grid kWh / (15/60 h); a truncated first/last eligible interval
        # contributes only its delivered energy to the full clock quarter.
        model.add(meter + [(peak, -.25*count)], high=0)
    if guide:
        model.add(meter + [(guide[1], -.25*count*cabinet_kw)], high=.25*count*guide[0])
    return decisions, []


def _reconstruct(group, solution, spec, guide_peak=None):
    """Return a realizable schedule, or request the exact block from the MILP."""
    day, site, count, parts, equipment, peak, decisions, mode_slots = group
    n, cabinet_kw, split = _equipment_at(site, equipment)
    peak_kw = cabinet_kw if peak is None else solution[peak]
    if guide_peak is not None:
        peak_kw = min(peak_kw, guide_peak)
    per_truck = min(50., spec.truck_kw)
    if (mode_slots == "shared_block" or
            (not mode_slots and split and per_truck == 50 and len(parts) == 1 and 2 <= len(decisions) <= 3)):
        a, b, _ = parts[0]
        packed = unpack_shared_block([solution[i]*60/(b-a) for _,_,_,i,_ in decisions], count,
                                     min(cabinet_kw, max(0., peak_kw)))
        if packed is not None:
            return [(a+15*q, b+15*q, truck, kw) for (_,_,truck,_,_), slots in zip(decisions, packed)
                    for q, kw in slots if kw > 1e-8]
        if mode_slots == "shared_block":
            return None
    if mode_slots == "halves":
        cursor, rows = 0, []
        for a,b,truck,i,z in decisions:
            count_shares = round(solution[z])
            assigned = defaultdict(int)
            for share in range(cursor, cursor+count_shares):
                assigned[share//2] += 1
            cursor += count_shares
            if solution[i] > 1e-8:
                rate = solution[i]*60/((b-a)*count_shares)
                rows.extend((a+15*j,b+15*j,truck,n*rate) for j,n in assigned.items())
        return rows
    if mode_slots:
        cursor, assigned = 0, {}
        loads = defaultdict(list)
        for a,b,truck,i,mode in decisions:
            if solution[i] > 1e-8:
                loads[mode].append(solution[i]/((b-a)/60))
        for mode, bits in enumerate(mode_slots):
            powers = loads[mode]
            if not powers:
                length = 0
            else:
                rate = min(per_truck,25.) if split and len(powers) > 1 else per_truck
                need = max(max(powers)/rate, sum(powers)/max(peak_kw,1e-12))
                length = max(1, ceil(need-1e-8))
            assigned[mode] = list(range(cursor, cursor+length))
            cursor += length
        if cursor > count:
            return None
        return [(a+15*j, b+15*j, truck, solution[i]*60/((b-a)*len(assigned[m])))
                for a,b,truck,i,m in decisions if solution[i] > 1e-8
                for j in assigned[m]]

    rows = [(a+15*j, b+15*j, v, solution[i]*60/((b-a)*count))
            for a,b,v,i,_ in decisions if solution[i] > 1e-8 for j in range(count)]
    quarter_drivers = defaultdict(set)
    interval = defaultdict(list)
    for a,b,v,kw in rows:
        quarter_drivers[int(a//15)].add(v)
        interval[a,b].append(kw)
    if (all(len(v) <= n for v in quarter_drivers.values()) and
            (not split or all(len(p) == 1 or max(p) <= 25.+1e-7 for p in interval.values()))):
        return rows

    if len(parts) == 1 and split and per_truck == 50 and peak_kw > 1e-9:
        a, b, _ = parts[0]
        # Equal half-peak shares give a directly feasible witness even at a
        # reduced peak. A failed packing simply asks for the exact union.
        share_kwh = min(25., peak_kw/2)*(b-a)/60
        cursor, packed = 0, []
        for _,_,v,i,_ in decisions:
            e = solution[i]
            if e <= 1e-8:
                continue
            needed = max(1, ceil((e-1e-10)/share_kwh))
            if cursor+needed > 2*count:
                break
            slots = defaultdict(int)
            for share in range(cursor, cursor+needed):
                slots[share//2] += 1
            packed.extend((a+15*j, b+15*j, v, n*e*60/((b-a)*needed)) for j,n in slots.items())
            cursor += needed
        else:
            return packed

    # Some uniform profiles conflict, but can be unpacked into disjoint single
    # reservations at the same energy, bill and metered peak upper bound.
    if len(parts) == 1 and peak_kw > 1e-9:
        a, b, _ = parts[0]
        limit = (b-a)/60*min(peak_kw, per_truck)
        if limit <= 0:
            return None
        cursor, singles = 0, []
        for _,_,v,i,_ in decisions:
            e = solution[i]
            if e <= 1e-8:
                continue
            slots = max(1, ceil((e-1e-10)/limit))
            if cursor+slots > count:
                return None
            singles.extend((a+15*j,b+15*j,v,e*60/((b-a)*slots)) for j in range(cursor,cursor+slots))
            cursor += slots
        return singles
    return None


def _hour_witness(groups, solution, period, spec):
    """Reassign one delivery hour at fixed truck energy between its trip endpoints.

    No charge moves to another meter, price, or side of a trip. Consequently
    both the bill and every battery endpoint are preserved. Exact quarter modes
    are tiny here (at most four quarters), and the master supplies the single
    peak bound shared by the whole sample. A shortfall asks the master to
    include the hour's discrete choices.
    """
    day,site,_,_,equipment,master_peak,_,_ = groups[0]
    hw = _equipment_at(site,equipment)
    cap = hw[1] if master_peak is None else max(0.,min(hw[1],float(solution[master_peak])))
    cuts = {v:[t for a,b,_,_ in task["trips"] for t in (a,b)]
            for v,task in period.cases[day]["trucks"].items()}
    model = Matrix()
    peak = model.var(cap,cap)
    targets, amounts = defaultdict(float), defaultdict(list)
    exact_groups = []
    for g in groups:
        count, parts = g[2:4]
        for a,b,v,i,_ in g[-2]:
            targets[v,bisect_right(cuts[v],a)] += solution[i]
        decisions, slots = _limits(model,(count,parts,hw,peak,spec),True,meter_exact=True)
        for a,b,v,i,_ in decisions:
            amounts[v,bisect_right(cuts[v],a)].append((i,1))
            model.cost[i] = -1
        exact_groups.append((day,site,count,parts,equipment,peak,decisions,slots))
    for key, terms in amounts.items():
        model.add(terms,high=max(0.,targets[key]))
    result = model.solve()
    stats = dict(status=result.message,status_code=result.status,objective=result.fun,
                 dual_bound=getattr(result,"mip_dual_bound",None),gap=getattr(result,"mip_gap",None),
                 day=day,site=site,hour=int(groups[0][3][0][0]//60))
    if result.status != 0:
        raise ValueError(("hour recovery",stats))
    if sum(targets.values()) + result.fun > 1e-8:
        return None, stats
    planned = []
    for g in exact_groups:
        rows = _reconstruct(g,result.x,spec)
        if rows is None:
            raise ArithmeticError(("hour recovery failed to unpack",stats))
        planned.extend(rows)
    return planned, stats


def _optimal_face(model, solution, groups):
    """Drop strictly positive-reduced-cost zero loads in a *primal recovery* only.

    Fix discrete counts of the returned restricted-master solution. Its LP
    optimum has the same objective. Complementary slackness identifies loads
    pinned at zero on that face; unrestricted master bounds are unaffected.
    """
    lower = np.asarray(model.lower,dtype=float).copy()
    upper = np.asarray(model.upper,dtype=float).copy()
    integer = np.asarray(model.integer,dtype=bool)
    lower[integer] = upper[integer] = np.rint(solution[integer])
    matrix = coo_matrix((model.data,(model.row,model.col)),shape=(len(model.lb),len(lower))).tocsr()
    lb,ub = np.asarray(model.lb),np.asarray(model.ub)
    equal = lb == ub
    le = np.isfinite(ub) & ~equal
    ge = np.isfinite(lb) & ~equal
    lp = linprog(model.cost, A_eq=matrix[equal], b_eq=ub[equal],
                 A_ub=vstack((matrix[le], -matrix[ge])), b_ub=np.r_[ub[le],-lb[ge]],
                 bounds=np.column_stack((lower,upper)), method="highs",
                 options={"primal_feasibility_tolerance":1e-9,"dual_feasibility_tolerance":1e-9})
    if not lp.success:
        raise ValueError(("optimal-face LP",lp.message))
    allowed, required = defaultdict(set), defaultdict(float)
    for day,site,count,parts,_,_,decisions,_ in groups:
        for a,b,v,i,_ in decisions:
            if lp.upper.marginals[i] < -1e-8 and lp.x[i] > 1e-8:
                required[day,site,a,b+15*(count-1),v] += lp.x[i]
            for j in range(count):
                q = int(a//15)+j
                key = day,site,q,a+15*j,b+15*j
                eligible = allowed[key]
                if lp.x[i] > 1e-8 or lp.lower.marginals[i] < 1e-8:
                    eligible.add(v)
    return allowed,required


def _bounded_mip(model, upper_cost, absolute_gap, start=None, *, time_limit=None):
    """Apply valid reduced-cost and row-slack bounds using a feasible cost ceiling."""
    a = coo_matrix((model.data,(model.row,model.col)),shape=(len(model.lb),len(model.cost))).tocsr()
    lower,upper = np.array(model.lower,dtype=float),np.array(model.upper,dtype=float)
    left,right = np.array(model.lb,dtype=float),np.array(model.ub,dtype=float)
    integers = np.array(model.integer,dtype=bool)
    for _ in range(2 if upper_cost is not None else 0):
        eq = left == right
        le = np.flatnonzero(np.isfinite(right) & ~eq)
        ge = np.flatnonzero(np.isfinite(left) & ~eq)
        lp = linprog(model.cost,A_ub=vstack((a[le],-a[ge])),b_ub=np.r_[right[le],-left[ge]],
                     A_eq=a[eq],b_eq=left[eq],bounds=np.column_stack((lower,upper)),method="highs",
                     options={"primal_feasibility_tolerance":1e-9,"dual_feasibility_tolerance":1e-9})
        if not lp.success:
            raise ValueError(("cost-ceiling relaxation",lp.message))
        gap = max(0.,upper_cost-lp.fun) + 1e-7
        active = lp.lower.marginals > 1e-7
        upper[active] = np.minimum(upper[active],lower[active]+gap/lp.lower.marginals[active]+1e-7)
        active = lp.upper.marginals < -1e-7
        lower[active] = np.maximum(lower[active],upper[active]+gap/lp.upper.marginals[active]-1e-7)
        prices = -lp.ineqlin.marginals
        high,low = prices[:len(le)],prices[len(le):]
        active = high > 1e-7
        ids = le[active]
        left[ids] = np.maximum(left[ids],right[ids]-gap/high[active]-1e-7)
        active = low > 1e-7
        ids = ge[active]
        right[ids] = np.minimum(right[ids],left[ids]+gap/low[active]+1e-7)
        lower[integers] = np.ceil(lower[integers]-1e-7)
        upper[integers] = np.floor(upper[integers]+1e-7)
    options = {"mip_rel_gap":0., "mip_feasibility_tolerance":1e-9,"primal_feasibility_tolerance":1e-9}
    if time_limit is not None:
        options["time_limit"] = time_limit
    if absolute_gap is not None:
        options["mip_abs_gap"] = absolute_gap
    if start is not None:
        # The SciPy milp entry point does not expose HiGHS' partial MIP start.
        # Use the backend pinned in this study to seed the exact same matrix.
        from scipy.optimize._highspy import _core as h
        matrix=a.tocsc()
        lp=h.HighsLp()
        lp.num_col_,lp.num_row_=matrix.shape[1],matrix.shape[0]
        lp.a_matrix_.num_col_,lp.a_matrix_.num_row_=lp.num_col_,lp.num_row_
        lp.a_matrix_.format_=h.MatrixFormat.kColwise
        lp.a_matrix_.start_,lp.a_matrix_.index_,lp.a_matrix_.value_=matrix.indptr,matrix.indices,matrix.data
        lp.col_cost_=model.cost
        lp.col_lower_,lp.col_upper_=lower,upper
        lp.row_lower_,lp.row_upper_=left,right
        lp.integrality_=[h.HighsVarType(int(flag)) for flag in integers]
        def loaded_solver(settings):
            solver=h._Highs()
            solver.setOptionValue("output_flag",False)
            for key,value in settings.items():
                if solver.setOptionValue(key,value)==h.HighsStatus.kError:
                    raise ArithmeticError(("HiGHS option",key,value))
            if solver.passModel(lp)==h.HighsStatus.kError:
                raise ArithmeticError("Failed to load weekly pricing MILP")
            return solver
        solver=loaded_solver(options)
        ids=np.flatnonzero(integers).astype(np.int32)
        if solver.setSolution(len(ids),ids,np.asarray(start,dtype=float)[ids])==h.HighsStatus.kError:
            raise ArithmeticError("Failed to submit known feasible reservation counts")
        run=solver.run()
        status=solver.getModelStatus()
        attempts=[]
        if status==h.HighsModelStatus.kSolveError:
            attempts.append(dict(start="warm",native_run_code=int(run),native_model_code=int(status),
                                 native_message=solver.modelStatusToString(status)))
            # The same tightened matrix and optimality tolerances apply. Rebuild
            # from scratch to discard the unusable search and presolve state.
            solver=loaded_solver({**options,"presolve":"off"})
            run=solver.run()
            status=solver.getModelStatus()
            attempts.append(dict(start="cold",presolve="off",native_run_code=int(run),
                                 native_model_code=int(status),native_message=solver.modelStatusToString(status)))
        if status!=h.HighsModelStatus.kOptimal:
            raise ArithmeticError(("weekly pricing MILP",solver.modelStatusToString(status),attempts))
        info=solver.getInfo()
        result=OptimizeResult(status=0,message=solver.modelStatusToString(status),
                              fun=info.objective_function_value,x=np.asarray(solver.getSolution().col_value),
                              mip_dual_bound=info.mip_dual_bound,mip_gap=info.mip_gap)
        if attempts:
            attempts[-1].update(objective=result.fun,dual_bound=result.mip_dual_bound,gap=result.mip_gap)
            result.native_attempts=attempts
        return result
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore",message="Unrecognized options detected.*",category=RuntimeWarning)
        return milp(model.cost,integrality=integers,bounds=Bounds(lower,upper),
                    constraints=LinearConstraint(a,left,right),options=options)


def solve(p, equipment, spec, rule, fixed=None, *, energy_weight=1., peak_weights=None,
          site_energy_weights=None, peak_bounds=None, objective_upper=None, total_peak_limit=None,
          force_exact=False, absolute_gap=None, incumbent=None, lower_target=None, _guide=None, _relax_only=False,
          _screened=False, _warehouse_energy_upper=False, _weekly_deadline=None):
    """Maximize served days, or minimize a weighted bill on the supplied identical service.

    Start with the aggregate linear relaxation, enforce exact discrete modes wherever
    reconstruction fails, then terminate only on a physically reconstructible optimum.
    Every iteration is a lower bound on the original minimization; the final schedule
    attains that bound. With P2 there is just one peak variable per site for all dates.
    """
    begin = perf_counter()
    if rule not in (A, B):
        raise ValueError("Expected daily_fixed or carry_over")
    physical = fixed is None
    active = p.keys if physical else set(fixed)
    weights = peak_weights or {}
    site_weights = site_energy_weights or {}
    bounds = peak_bounds or {}
    if not active <= p.keys or any(set(d)-set(SITES) for d in (weights, site_weights, bounds)):
        raise ValueError("Unknown service key or metering point")
    if any(not isfinite(x) or x < 0 for x in (*weights.values(), *bounds.values())):
        raise ValueError("Demand weights and bounds must be nonnegative and finite")
    if total_peak_limit is not None and (not isfinite(total_peak_limit) or total_peak_limit < 0):
        raise ValueError("Expected a finite, nonnegative sum-of-peaks bound")
    if absolute_gap is not None and (not isfinite(absolute_gap) or absolute_gap < 0 or physical or energy_weight == 0):
        raise ValueError("Absolute cost tolerance applies only to fixed-service monetary objectives")
    if physical and (weights or site_weights or bounds or objective_upper is not None or total_peak_limit is not None):
        raise ValueError("Physical selection takes no bill or peak terms")
    cases = {date:subset_case(case,[v for v in case["trucks"] if (date,v) in active])
             for date, case in p.cases.items()}
    screen_attempts=[]
    if (not physical and not _guide and not _relax_only and not _screened and energy_weight==0
            and not site_weights and not bounds and total_peak_limit is None
            and all(weights.get(s,0)>0 for s in SITES) and all("week_start" in day for day in p.days)):
        from .cabinet_audit import audit_cabinets
        independent=components(p.days,p.links)
        if len(independent)>1:
            periods=[Period(days,p.prices) for days in independent]
            relaxed=relaxation(p,equipment,spec,rule,active,energy_weight=0.,peak_weights=weights)
            caps=relaxed["peak_kw"]
            proof=relaxed["stats"]
            included=set()
            attempts=[proof]
            priced=None
            while len(included)<len(periods):
                joined={"states":[],"schedule":[]}
                if priced:
                    joined["states"].extend(priced["states"])
                    joined["schedule"].extend(schedule_on_clock(p,subperiod,priced["schedule"]))
                missing=set()
                for j,local in enumerate(periods):
                    if j in included:
                        continue
                    witness=solve(local,equipment,spec,rule,local.keys&active,energy_weight=0.,
                                  _guide=(caps,0.,{}))
                    attempts.append(witness["stats"])
                    if witness["stats"]["objective"]>.5:
                        missing.add(j)
                    else:
                        joined["states"].extend(witness["states"])
                        joined["schedule"].extend(schedule_on_clock(p,local,witness["schedule"]))
                if not missing:
                    _,_,peaks=audit_cabinets(equipment,joined["schedule"])
                    value=sum(weights[s]*peaks[s] for s in SITES)
                    lower=proof["dual_bound"] if proof["dual_bound"] is not None else proof["objective"]
                    if abs(value-lower)>1e-6:
                        raise ArithmeticError(("peak component certificate",value,lower))
                    joined["stats"]=dict(status="Optimal: component lower bound attained",status_code=0,
                                         objective=value,dual_bound=lower,gap=max(0.,value-lower)/max(1.,abs(value)),
                                         seconds=perf_counter()-begin,component_solves=attempts)
                    return joined
                included.update(missing)
                if len(included)==len(periods):
                    screen_attempts=attempts
                    break
                days=sorted((d for j in included for d in independent[j]),key=lambda d:d["date"])
                subperiod=Period(days,p.prices)
                priced=solve(subperiod,equipment,spec,rule,subperiod.keys&active,energy_weight=0.,
                             peak_weights=weights,objective_upper=objective_upper,_screened=True)
                proof=priced["stats"]
                attempts.append(proof)
                _,_,caps=audit_cabinets(equipment,priced["schedule"])
    flat=physical or energy_weight==0
    layout = [(day, site, count, parts) for day, case in cases.items() for site in SITES
              for count, parts in _groups(case, site, flat=flat)]
    patterns = _guide[2] if _guide else {}
    face,required = _guide[3] if _guide and len(_guide)>3 else ({},{})
    if patterns or face:
        expanded = []
        for day,site,count,parts in layout:
            q = int(parts[0][0]//15)
            if not face and (day,site,q) not in patterns:
                expanded.append((day,site,count,parts))
                continue
            if face and len(parts) == 1:
                a,b,vs = parts[0]
                eligible = [tuple(v for v in vs if v in face.get((day,site,q+j,a+15*j,b+15*j),()))
                            for j in range(count)]
                if all(x==eligible[0] for x in eligible):
                    if eligible[0]:
                        expanded.append((day,site,count,[(a,b,eligible[0])]))
                    continue
            for j in range(count):
                shifted = [(a+15*j,b+15*j,v) for a,b,v in parts]
                if face:
                    shifted = [(a,b,tuple(v for v in vs if v in face.get((day,site,q+j,a,b),())))
                               for a,b,vs in shifted]
                expanded.append((day,site,1,shifted))
        layout = expanded
    exact, metered, steps = set(), set(), []
    if force_exact:
        exact.update(range(len(layout)))
        metered.update(exact)
    if _guide or (physical and not weights and not bounds and total_peak_limit is None):
        exact.update(range(len(layout)))
    # A day can supply a constructive certificate even under B by retaining
    # *both* midnight states from the multi-day lower-bound solution. A failed
    # recovery never weakens the original carry-over constraints.
    periods = ([Period([day],p.prices) for day in p.days if day["date"] in cases]
               if not physical and not _guide and not force_exact and len(cases)>1 else [])
    certificates = {}
    lower_kw, upper_kw = {}, {}
    recovery_bill = None
    normalize = (not physical and not _guide and not _relax_only and equipment=="one"
                 and spec.truck_kw==50 and all(weights.get(s,0)>0 for s in SITES) and not bounds
                 and total_peak_limit is None and energy_weight >= 0)
    if (normalize or force_exact) and objective_upper is not None and len(cases)>1 and weights:
        proxy = relaxation(p,equipment,spec,rule,active,energy_weight=energy_weight,peak_weights=weights,
                           site_energy_weights=site_weights,peak_bounds=bounds,total_peak_limit=total_peak_limit,
                           objective_upper=objective_upper)
        lower_kw,upper_kw = proxy["lower_kw"],proxy["upper_kw"]
        steps.extend(proxy["supports"])
        if normalize and lower_kw.get("PORT",0)>0:
            from .cabinet_fractional import solve_port
            normalized=solve_port(p,equipment,spec,rule,active,energy_weight,weights,site_weights,
                                  objective_upper,proxy,absolute_gap,incumbent,lower_target)
            if screen_attempts:
                normalized["stats"]["component_screen"]=screen_attempts
            return normalized
    while True:
        t0 = perf_counter()
        model = Matrix()
        slack = model.var(0, 1, integer=True) if _guide else None
        if _guide and len(_guide)>4:
            levels = {}
            for key in sorted(active):
                s = model.var(0,1)
                endpoints = []
                for value in _guide[4][key]:
                    i = model.var(0,spec.capacity_kwh)
                    model.add([(i,1),(slack,value-spec.boundary_kwh)],value,value)
                    endpoints.append(i)
                levels[key] = s,*endpoints
        else:
            levels = _levels(model, p, spec, rule, active, physical)
        if _guide:
            # The artificial fallback serves no duties. Thus restrictions on
            # the proposed optimal face cannot make the certificate MILP
            # infeasible. A genuine witness necessarily serves every duty.
            for s,_,_ in levels.values():
                model.lower[s] = 0
                model.add([(s,1),(slack,1)],1,1)
        peaks = {}
        for site in SITES:
            _, cabinet_kw, _ = _equipment_at(site, equipment)
            if weights.get(site, 0) or site in bounds or total_peak_limit is not None:
                upper = min(cabinet_kw, bounds.get(site, cabinet_kw))
                upper = min(upper, upper_kw.get(site, upper))
                lower = upper if not weights.get(site, 0) and total_peak_limit is None else 0
                lower = max(lower, lower_kw.get(site, 0))
                peaks[site] = model.var(lower, upper, weights.get(site, 0))
        if total_peak_limit is not None:
            model.add([(i, 1) for i in peaks.values()], high=total_peak_limit)
        charged, groups = defaultdict(list), []
        for idx, (day, site, count, parts) in enumerate(layout):
            hw = _equipment_at(site, equipment)
            peak = peaks.get(site)
            guide = (_guide[0][site], slack) if _guide else None
            pattern = patterns.get((day,site,int(parts[0][0]//15)))
            decisions, slots = _limits(model, (count, parts, hw, peak, spec), idx in exact, guide, idx in metered,
                                      pattern)
            for a, b, v, i, _ in decisions:
                charged[day,v].append((b+15*(count-1), i))
                if not physical:
                    model.cost[i] = energy_weight*p.prices[day][int(a//60)]/1000 + site_weights.get(site, 0)
            groups.append((day,site,count,parts,equipment,peak,decisions,slots))
        for day, case in cases.items():
            _balance(model, case, day, levels, charged, spec)
        if required:
            for (d,site,left,right,v), kwh in required.items():
                terms=[(i,1) for group in groups if group[0]==d and group[1]==site
                       for a,b,truck,i,_ in group[-2] if v==truck and left<=a and b+15*(group[2]-1)<=right]
                model.add(terms+[(slack,kwh)],low=kwh)
        if not model.cost:
            model.var(0, 0)
        if objective_upper is not None:
            model.add([(i,c) for i,c in enumerate(model.cost) if c], high=objective_upper)
            if not steps and not physical and len(periods)>1 and peaks:
                # The objective cap admits the known feasible incumbent. The
                # continuous relaxation supplies rigorous, objective-specific
                # intervals for the two meter levels used in mode-count cuts.
                costs = model.cost.copy()
                for site, i in peaks.items():
                    for sign in (1., -1.):
                        model.cost = [0.]*len(costs)
                        model.cost[i] = sign
                        support = model.solve()
                        if support.status != 0:
                            raise ValueError(("meter range LP",site,sign,support.message))
                        steps.append(dict(status_code=support.status,status=support.message,
                                          objective=support.fun,dual_bound=getattr(support,"mip_dual_bound",None),
                                          gap=getattr(support,"mip_gap",None),site=site,sign=sign))
                        if sign == 1.:
                            lower_kw[site] = max(0., support.fun-1e-7)
                        else:
                            upper_kw[site] = min(model.upper[i], -support.fun+1e-7)
                    model.lower[i] = max(model.lower[i], lower_kw[site])
                    model.upper[i] = min(model.upper[i], upper_kw[site])
                model.cost = costs
        if _guide:
            # Set slack=1 to recover the unrestricted feasible weekly model.
            # Its minimum is zero exactly when the relaxed weekly bill and the
            # two *same* master peaks can all be attained on this component.
            terms = [(i,c) for i,c in enumerate(model.cost) if c]
            big = max(1., sum(max(0.,c)*model.upper[i] for i,c in terms) - _guide[1])
            model.add(terms + [(slack, -big)], high=_guide[1])
            model.cost = [0.]*len(model.cost)
            model.cost[slack] = 1.
        remaining=None if _weekly_deadline is None else _weekly_deadline-perf_counter()
        if remaining is not None and remaining<=0:
            raise TimeoutError("Weekly reservation improvement reached its time limit")
        res = (_bounded_mip(model,objective_upper,absolute_gap,time_limit=remaining) if not _guide and not _relax_only
               and (objective_upper is not None or absolute_gap is not None) and any(model.integer)
               else model.solve())
        stat = dict(status=res.message, status_code=res.status, objective=res.fun,
                    dual_bound=getattr(res, "mip_dual_bound", None), gap=getattr(res, "mip_gap", None),
                    seconds=perf_counter()-t0, exact_groups=len(exact),
                    integer_variables=sum(model.integer), variables=len(model.cost))
        steps.append(stat)
        if res.status==1 and _weekly_deadline is not None:
            raise TimeoutError(res.message)
        if res.status != 0:
            raise ValueError(f"Cabinet model {equipment} {rule}: {stat}")
        if _relax_only:
            result=dict(stats=stat, peak_kw={site:float(res.x[i]) for site,i in peaks.items()},
                        lower_kw=lower_kw,upper_kw=upper_kw,supports=steps[:-1])
            if _warehouse_energy_upper:
                model.cost=[0.]*len(model.cost)
                for group in groups:
                    if group[1]=="WAREHOUSE":
                        for _,_,_,i,_ in group[-2]:
                            model.cost[i]=-1.
                volume=model.solve()
                if volume.status!=0:
                    raise ArithmeticError(("warehouse energy upper bound",volume.message))
                result["warehouse_energy_support"]=dict(status_code=volume.status,status=volume.message,
                    objective=volume.fun,dual_bound=getattr(volume,"mip_dual_bound",None),
                    gap=getattr(volume,"mip_gap",None),six_week_kwh_upper=-volume.fun+1e-7)
            return result
        if _guide and res.fun > .5:
            return dict(stats={**stat, "solves":steps, "certificate":False}, schedule=[],states=[])
        invalid, schedule = set(), []
        for idx, group in enumerate(groups):
            guide_peak = None
            if _guide and res.fun < 1e-12:
                guide_peak = _guide[0][group[1]]
            rows = _reconstruct(group, res.x, spec, guide_peak)
            if rows is None:
                invalid.add(idx)
                continue
            day, site = group[:2]
            offset = p.offset[day]
            schedule.extend(dict(date=day, site=site, vehicle_id=v, start_min=offset+a,
                                 end_min=offset+b, reservation_slot=int((offset+a)//15), power_kw=kw)
                            for a,b,v,kw in rows)
        if invalid and not _guide and not force_exact and not flat:
            hours = defaultdict(list)
            for idx,g in enumerate(groups):
                hours[g[0],g[1],int(g[3][0][0]//60)].append(idx)
            for (day,site,hour), ids in hours.items():
                if not invalid.intersection(ids):
                    continue
                rows, proof = _hour_witness([groups[i] for i in ids], res.x, p, spec)
                stat.setdefault("hour_recovery", []).append(proof)
                if rows is None:
                    # Include every mode in the affected delivery hour in one
                    # step; another relaxed optimum can redistribute its kWh.
                    invalid.update(i for i in ids if i not in metered)
                    continue
                invalid.difference_update(ids)
                off = p.offset[day]
                schedule = [r for r in schedule if not (r["date"]==day and r["site"]==site
                            and (r["reservation_slot"]-off//15)//4==hour)]
                schedule.extend(dict(date=day,site=site,vehicle_id=v,start_min=off+a,end_min=off+b,
                                     reservation_slot=int((off+a)//15),power_kw=kw) for a,b,v,kw in rows)
        if invalid & metered or (_guide and invalid & exact):
            raise ArithmeticError(("exact group failed to unpack", invalid & (metered or exact)))
        alternate_states = {}
        if (invalid and not periods and not _guide and not physical and not weights and not bounds
                and total_peak_limit is None and len(steps) >= 3 and abs(steps[-2]["objective"]-res.fun) < 1e-9
                and (recovery_bill is None or abs(recovery_bill-res.fun)>1e-9)):
            recovery_bill = res.fun
            targets = {site:_equipment_at(site,equipment)[1] for site in SITES}
            face = _optimal_face(model,res.x,groups)
            witness = solve(p, equipment, spec, rule, active, energy_weight=energy_weight,
                            site_energy_weights=site_weights, _guide=(targets, recovery_bill, {}, face))
            stat.setdefault("component_recovery", []).append(witness["stats"])
            if witness["stats"]["objective"] < 0.5:
                schedule = witness["schedule"]
                alternate_states.update({(r["date"],r["vehicle_id"]):r for r in witness["states"]})
                invalid.clear()
        if invalid and periods:
            face = _optimal_face(model,res.x,groups)
            pinned = {k:(float(res.x[x]),float(res.x[y])) for k,(_,x,y) in levels.items()}
            targets = {site:(float(res.x[peaks[site]]) if site in peaks else _equipment_at(site, equipment)[1])
                       for site in SITES}
            for local in periods:
                in_period = {idx for idx in invalid if groups[idx][0] in local.offset}
                if not in_period:
                    continue
                target_bill = sum(res.x[i]*model.cost[i] for group in groups if group[0] in local.offset
                                  for _,_,_,i,_ in group[-2])
                local_states = tuple(pinned[k] for k in sorted(active & local.keys))
                cache_key = (local.days[0]["date"],tuple(targets.values()),target_bill,local_states)
                if cache_key not in certificates:
                    witness = solve(local, equipment, spec, rule, active & local.keys,
                                    energy_weight=energy_weight, site_energy_weights=site_weights,
                                    _guide=(targets, target_bill, {}, (face[0],{k:v for k,v in face[1].items()
                                                                             if k[0] in local.offset}),pinned))
                    certificates[cache_key] = witness
                    stat.setdefault("component_recovery", []).append(witness["stats"])
                witness = certificates[cache_key]
                if witness["stats"]["objective"] > 1e-12:
                    continue
                # The local calendar starts at its own Monday. Shift the
                # witness back onto the master's clock before independent replay.
                invalid -= in_period
                schedule = [row for row in schedule if row["date"] not in local.offset]
                schedule.extend(schedule_on_clock(p,local,witness["schedule"]))
                alternate_states.update({(r["date"],r["vehicle_id"]):r for r in witness["states"]})
        if not invalid:
            break
        metered.update(invalid & exact)
        exact.update(invalid)
    states = [dict(date=d, vehicle_id=v, served=bool(res.x[s]>.5), x=float(res.x[x]), y=float(res.x[y]))
              for (d,v),(s,x,y) in levels.items()]
    states = [alternate_states.get((r["date"], r["vehicle_id"]), r) for r in states]
    stats = {**stat, "seconds":perf_counter()-begin, "solves":steps}
    if screen_attempts:
        stats["component_screen"]=screen_attempts
    return dict(stats=stats, states=states, schedule=schedule)


def relaxation(p, equipment, spec, rule, fixed, **weights):
    """Continuous lower bound and relaxed peaks; does not certify a schedule."""
    return solve(p,equipment,spec,rule,fixed,_relax_only=True,**weights)


def prove_lower(p, spec, rule, fixed, *, energy_weight, peak_weights, incumbent, minimum_value,
                absolute_gap=.001):
    """E1 auxiliary bound. Return a feasible schedule and a certified lower objective.

    The target may be unattainable. The two registered annual point estimates
    use solve without this early exit. Here, a strict bound alone can settle
    the sign of an upgrade's value across a tariff interval.
    """
    from .cabinet_audit import replay
    audit=replay(p,"one",spec,rule,incumbent,fixed=fixed,check_objective=False)
    upper=energy_weight*audit["purchase_eur"]+sum(peak_weights[s]*audit["site_peak_kw"][s] for s in SITES)
    relaxed=relaxation(p,"one",spec,rule,fixed,energy_weight=energy_weight,peak_weights=peak_weights)
    lower=relaxed["stats"]["objective"]
    if lower>=minimum_value:
        return {**incumbent,"stats":dict(status="Auxiliary continuous lower bound certified",status_code=0,
                objective=upper,dual_bound=lower,gap=max(0.,upper-lower)/max(1.,abs(upper)),
                requested_lower=minimum_value,relaxation=relaxed["stats"])}
    return solve(p,"one",spec,rule,fixed,energy_weight=energy_weight,peak_weights=peak_weights,
                 incumbent=incumbent,objective_upper=upper+1e-7,lower_target=minimum_value,
                 absolute_gap=absolute_gap)
