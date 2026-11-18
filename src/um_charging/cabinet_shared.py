"""Exact E3 dispatch over identical whole meter quarters for two or three trucks."""
from collections import deque
from itertools import combinations
from math import fsum


def _product(model, peak, shares, n, lower, upper):
    """Express P*k by binary expansion of the integer k in [0, 2n]."""
    bits, products = [], []
    for position in range((2*n).bit_length()):
        weight = 2**position
        bit = model.var(0, 1, integer=True)
        product = model.var(0, upper)
        model.add([(product, 1), (bit, -upper)], high=0)
        model.add([(product, 1), (bit, -lower)], low=0)
        model.add([(product, 1), (peak, -1), (bit, -lower)], high=-lower)
        model.add([(product, 1), (peak, -1), (bit, -upper)], low=-upper)
        bits.append((bit, weight))
        products.append((product, weight))
    model.add(bits+[(shares, -1)], 0, 0)
    return products


def add_shared_block(model, count, part, peak):
    """Use two integer reservation shares per quarter, including unused shares.

    One solo truck owns both shares, or two trucks own one each. For t
    shares, a subset can draw at most f(t) = min(H*t, (P-H)*t+n*(2H-P))
    in kW summed over n quarters, where H=min(25,P). Its total cannot
    exceed n*P. Singletons and their complements exhaust all nontrivial
    subsets for at most three trucks. The construction in unpack_shared_block
    attains these subset capacities simultaneously. This argument does not
    extend to four trucks. Variable P is supported here only for P >= 25.
    """
    start, end, trucks = part
    hours = (end-start)/60
    lower, upper = model.lower[peak], model.upper[peak]
    if not (len(trucks) in (2, 3) and 0 <= lower <= upper <= 50 and (lower == upper or lower >= 25)):
        raise ValueError(("Unsupported shared block", trucks, lower, upper))
    energy = [model.var(0, hours*count*upper) for _ in trucks]
    shares = [model.var(0, 2*count, integer=True) for _ in trucks]
    model.add([(k, 1) for k in shares], 2*count, 2*count)
    half = min(upper, 25.)
    products = []
    if lower != upper:
        products = [_product(model, peak, k, count, lower, upper) for k in shares]
        model.add([term for terms in products for term in terms]+[(peak, -2*count)], 0, 0)
    for pos, (i, k) in enumerate(zip(energy, shares)):
        others = [(j, 1) for j in energy if j != i]
        model.add([(i, 1), (k, -hours*half)], high=0)
        model.add(others+[(k, hours*half)], high=hours*2*count*half)
        if lower == upper:
            remainder = upper-half
            model.add([(i, 1), (k, -hours*remainder)], high=hours*count*(2*half-upper))
            model.add(others+[(k, hours*remainder)], high=hours*count*upper)
        else:
            model.add([(i, 1), (k, hours*half), (peak, hours*count)]
                      + [(j, -hours*w) for j,w in products[pos]], high=2*half*hours*count)
            model.add(others+[(k, -hours*half), (peak, -hours*count)]
                      + [(j, hours*w) for j,w in products[pos]], high=0)
    model.add([(i, 1) for i in energy]+[(peak, -hours*count)], high=0)
    return [(start, end, truck, i, None) for truck,i in zip(trucks, energy)]


def _modes(shares, count):
    """Make the quarter counts for each solo / simultaneous operating mode."""
    if len(shares) == 2:
        k = shares[0]
        return [((0,), max(0, k-count)), ((1,), max(0, count-k)), ((0, 1), min(k, 2*count-k))]
    dominant = max(range(3), key=shares.__getitem__)
    if shares[dominant] > count:
        return [((dominant,), shares[dominant]-count)] + [
            ((i, dominant), k) for i,k in enumerate(shares) if i != dominant]
    return [((i,j), count-shares[3-i-j]) for i,j in combinations(range(3), 2)]


def _flow(powers, modes, peak):
    """Send each truck's block demand through allowed modes to the shared meter."""
    n = len(powers)
    source, sink = n+len(modes), n+len(modes)+1
    residual = [[0.]*(sink+1) for _ in range(sink+1)]
    for truck, demand in enumerate(powers):
        residual[source][truck] = max(0., demand)
    for mode, (trucks, length) in enumerate(modes, n):
        residual[mode][sink] = length*peak
        limit = peak if len(trucks) == 1 else min(25., peak)
        for truck in trucks:
            residual[truck][mode] = length*limit
    while True:
        parents = {source: None}
        pending = deque([source])
        while pending and sink not in parents:
            u = pending.popleft()
            for v, capacity in enumerate(residual[u]):
                if capacity > 1e-10 and v not in parents:
                    parents[v] = u
                    pending.append(v)
        if sink not in parents:
            return residual
        path, v = [], sink
        while v != source:
            u = parents[v]
            path.append((u, v))
            v = u
        increment = min(residual[u][v] for u,v in path)
        for u,v in path:
            residual[u][v] -= increment
            residual[v][u] += increment


def unpack_shared_block(demands, count, peak):
    """Return actual (quarter offset, kW) per truck or None if infeasible.

    Inputs are truck kW summed across quarters. For each truck the singleton
    bound is increasing in its share count, the complement bound decreasing.
    Their feasible integer counts form an interval. Assigning a total of 2n
    shares within these intervals gives all the subset bounds, hence max-flow
    feasibility for the constructed modes.
    """
    if len(demands) not in (2, 3):
        raise ValueError(("Expected two or three shared-cabinet trucks", len(demands)))
    tolerance = 2e-7
    half = min(25., peak)
    total = sum(demands)
    if total > count*peak+tolerance:
        return None
    def capacity(k):
        return min(half*k, (peak-half)*k+count*(2*half-peak))
    bounds = []
    for demand in demands:
        allowed = [k for k in range(2*count+1) if demand <= capacity(k)+tolerance
                   and total-demand <= capacity(2*count-k)+tolerance]
        if not allowed:
            return None
        bounds.append((allowed[0], allowed[-1]))
    shares = [lo for lo, _ in bounds]
    left = 2*count-sum(shares)
    if left < 0 or 2*count > sum(hi for _,hi in bounds):
        return None
    for i, (_, hi) in enumerate(bounds):
        extra = min(left, hi-shares[i])
        shares[i] += extra
        left -= extra
    modes = [(owners, length) for owners,length in _modes(shares, count) if length]
    residual = _flow(demands, modes, peak)
    if max(residual[-2]) > tolerance:
        return None
    result = [[] for _ in demands]
    start = 0
    for mode, (trucks, length) in enumerate(modes, len(demands)):
        for truck in trucks:
            kw = residual[mode][truck]/length
            if kw > 1e-9:
                result[truck].extend((q, kw) for q in range(start, start+length))
        start += length
    return result


def shared_peak_witness(period, periods, spec, rule, fixed, caps, energy_weight, peak_weights):
    """Seek a replayable E3 upper bound at the two given full-period meter caps.

    At fixed caps independent service chains can be solved separately. A
    binary feasibility solve either delivers an energy budget at those caps
    or returns the zero-service fallback. The budgets are only search targets.
    A failure returns no new bound; it places no restriction on the subsequent
    unrestricted E3 optimization.
    """
    from .cabinet_model import relaxation, solve
    from .cabinet_audit import replay, schedule_on_clock
    from .fleet_service import SITES

    equipment = "two_shared_rule"
    states, schedule, statistics = [], [], []
    cost_by_week = []
    for local in periods:
        keys = local.keys & fixed
        relaxed = relaxation(local, equipment, spec, rule, keys, peak_bounds=caps)
        lower = relaxed["stats"]["objective"]
        trials = []
        statistics.append(dict(start=local.days[0]["date"], relaxation=relaxed["stats"], trials=trials))
        # Euro tolerances refer to one component's sampled wholesale bill.
        for margin in (1e-6, .003, .006, .012, .05):
            budget = lower+margin
            trial = solve(local, equipment, spec, rule, keys, peak_bounds=caps, _guide=(caps, budget, {}))
            trials.append(dict(energy_budget=budget, stats=trial["stats"]))
            if trial["stats"]["objective"] > .5:
                continue
            audit = replay(local, equipment, spec, rule, trial, fixed=keys, check_objective=False)
            if (audit["purchase_eur"] > budget+1e-6 or
                    any(audit["site_peak_kw"][site] > caps[site]+1e-6 for site in SITES)):
                raise ArithmeticError(("Shared cabinet witness violates its budget", budget, caps, audit))
            states.extend(trial["states"])
            schedule.extend(schedule_on_clock(period, local, trial["schedule"]))
            cost_by_week.append((audit["purchase_eur"], audit["site_peak_kw"]))
            break
        else:
            return dict(feasible=False, caps_kw=caps, weeks=statistics)
    energy = fsum(eur for eur, _ in cost_by_week)
    peaks = {s:max((meters[s] for _, meters in cost_by_week), default=0.) for s in SITES}
    upper = energy_weight*energy+fsum(peak_weights.get(s, 0.)*peaks[s] for s in SITES)
    result = dict(states=states, schedule=schedule, stats=dict(objective=upper))
    audit = replay(period, equipment, spec, rule, result, fixed=fixed, energy_weight=energy_weight,
                   peak_weights=peak_weights)
    return dict(feasible=True, caps_kw=caps, weeks=statistics, objective_upper=upper, audit=audit,
                states=states, schedule=schedule)
