"""Certify the reoptimized operating value over nonnegative uniform demand rates."""
from functools import cache
import math


def gain_interval(equipment,a,b,point,factor):
    """Enclose the uniform objective gain on a finite interval using both endpoint solves."""
    base=[point("one",r) for r in (a,b)]
    new=[point(equipment,r) for r in (a,b)]
    def line(x,r):
        return x["energy"]+factor*r*x["peak"]
    knots=[a,b]
    slope=factor*(new[0]["peak"]-new[1]["peak"])
    if slope:
        cross=(new[1]["energy"]-new[0]["energy"])/slope
        if a<cross<b:
            knots.append(cross)
    def chord(r):
        return base[0]["lower"] if a==b else base[0]["lower"]+(r-a)/(b-a)*(base[1]["lower"]-base[0]["lower"])
    lower=max(0.,min(chord(r)-min(line(x,r) for x in new) for r in knots))
    upper=min(max(line(x,r)-new[i]["lower"] for i,r in enumerate((a,b))) for x in base)
    status=("strictly_positive" if lower>1e-5 else "zero_to_tolerance" if upper<=1e-5
            else "unresolved_at_solver_precision")
    return dict(from_rate=a,to_rate=b,status=status,lower_bound_2025_eur=lower,
                uniform_objective_gain_upper_eur_2025=upper)


def certify_p2(rate_point, min_peak, network_factor, seed_rates=(0., 22.79, 208.38), *, may_refine=lambda: True):
    """Bound reoptimized wholesale-plus-capacity costs at 2024 EUR/kW/year.

    Each callback returns feasible annual wholesale 'energy' (2025 EUR) and
    sum of metered 'peak' (kW). rate_point's optional 'lower' is its global
    annual objective lower bound at the queried rate (2025 EUR). min_peak's
    'lower' is its global minimum sum-of-peaks lower bound (kW). Omitting
    'lower' asserts that the feasible objective was proved optimal. A feasible
    line is always an upper bound, even when a solver stops at a positive gap.
    """
    rates = sorted(set(seed_rates))
    if not rates or rates[0] != 0 or len(rates) < 2 or network_factor <= 0:
        raise ValueError("Require nonnegative rates starting at zero and a positive CPI factor")
    point, minimum = cache(rate_point), cache(min_peak)
    money_tol, kw_tol = 1e-5, 1e-8

    def value(profile, rate):
        return profile["energy"] + network_factor * rate * profile["peak"]

    def lower(profile, upper, tol):
        bound = profile.get("lower", upper)
        if not math.isfinite(bound) or bound > upper + tol:
            raise ValueError(("Invalid lower bound for feasible objective", bound, upper))
        return min(bound, upper)

    def cost_bound(profile, rate):
        return lower(profile, value(profile, rate), money_tol)

    def gap(equipment, r):
        baseline, upgrade = point("one", r), point(equipment, r)
        low = cost_bound(baseline, r) - value(upgrade, r)
        high = value(baseline, r) - cost_bound(upgrade, r)
        if high < -money_tol:
            raise ArithmeticError(("Certified upgrade bound exceeds feasible E1 cost", equipment, r, high))
        # The upgrade can always reproduce the one-connector schedule.
        return [max(0., low), max(0., high)]

    def crossing(left, right, a, b):
        change = network_factor * (left["peak"] - right["peak"])
        if change:
            r = (right["energy"] - left["energy"]) / change
            if a < r < b:
                return r
        return None

    def zero_plateau(equipment, a, b):
        # An E1 feasible line minus the upgrade's chord of certified lower
        # bounds is affine; its maximum is attained at an endpoint.
        new_a, new_b = point(equipment, a), point(equipment, b)
        return min(max(value(base, a)-cost_bound(new_a, a), value(base, b)-cost_bound(new_b, b))
                   for base in (point("one", a), point("one", b)))

    def finite(equipment, a, b, records):
        left, right = point("one", a), point("one", b)
        upgraded = point(equipment, a), point(equipment, b)
        x = crossing(*upgraded, a, b)
        probes = sorted({a, b, (a+b)/2, *([] if x is None else [x])})
        low_a, low_b = cost_bound(left, a), cost_bound(right, b)
        # Concavity gives a lower chord for E1; the better of two feasible
        # upgrade lines supplies an upper envelope. Test endpoints and kink.
        margins = [low_a+(r-a)/(b-a)*(low_b-low_a)-min(value(v, r) for v in upgraded)
                   for r in probes]
        if min(margins) > money_tol:
            records.append(dict(from_rate=a, to_rate=b, status="strictly_positive",
                                lower_bound_2025_eur=min(margins), tested_rates=probes))
            return
        upper = zero_plateau(equipment, a, b)
        if upper <= money_tol:
            records.append(dict(from_rate=a, to_rate=b, status="zero_to_tolerance",
                                upper_bound_2025_eur=upper))
            return
        gaps = [gap(equipment, r) for r in (a, b)]
        zeros = [r for r, (_, hi) in zip((a, b), gaps) if hi <= money_tol]
        if (min(margins) >= 0 and all(m > money_tol for r, m in zip(probes, margins) if r not in zeros)):
            records.append(dict(from_rate=a, to_rate=b, status="positive_except_listed_endpoints",
                                zero_endpoints=zeros, tested_rates=probes, margins_2025_eur=margins))
            return
        if any(lo <= money_tol < hi for lo, hi in gaps):
            records.append(dict(from_rate=a, to_rate=b, status="unresolved_at_solver_precision",
                                endpoint_bounds_2025_eur=gaps))
            return
        if b-a <= 1e-7:
            records.append(dict(from_rate=a, to_rate=b, status="unresolved_within_rate_tolerance",
                                endpoint_bounds_2025_eur=gaps))
            return
        if not may_refine():
            records.append(dict(from_rate=a,to_rate=b,status="unresolved_at_solver_precision",
                                endpoint_bounds_2025_eur=gaps,lower_bound_2025_eur=max(0.,min(margins)),
                                stop="auxiliary curve time budget"))
            return
        choices = (x, crossing(left, right, a, b))
        split = next((s for s in choices if s is not None and 1e-7 < (s-a)/(b-a) < 1.-1e-7), (a+b)/2)
        finite(equipment, a, split, records)
        finite(equipment, split, b, records)

    def infinite(equipment, prices):
        high = prices[-1]
        base_min = minimum("one")
        base_floor = lower(base_min, base_min["peak"], kw_tol)
        upgrade = point(equipment, high)
        ray = upgrade
        if ray["peak"] > base_floor:
            ray = minimum(equipment)
            # The E1 minimum cannot be lower than the upgrade minimum.
            upgrade_floor = lower(ray, ray["peak"], kw_tol)
            base_floor = max(base_floor, upgrade_floor)
        else:
            upgrade_floor = None
        for _ in range(36):
            base = point("one", high)
            low = cost_bound(base, high) - value(ray, high)
            slope = network_factor * (base_floor - ray["peak"])
            if low > money_tol and slope >= 0:
                return dict(from_rate=high, to_rate=None, status="strictly_positive",
                            lower_bound_at_start_2025_eur=low, lower_slope_2025=slope,
                            baseline_min_peak_lower_kw=base_floor, feasible_upgrade=ray)
            hi = gap(equipment, high)[1]
            if hi <= money_tol:
                if upgrade_floor is not None and base["peak"] <= upgrade_floor:
                    return dict(from_rate=high, to_rate=None, status="zero_to_tolerance",
                                upper_bound_2025_eur=hi, baseline=base, upgrade=upgrade)
                # This point alone answers existence; nothing beyond it is inferred.
                return dict(from_rate=high, to_rate=high, status="zero_to_tolerance",
                            upper_bound_2025_eur=hi)
            if (slope < 0 or (slope == 0 and
                    (gap(equipment, high)[0] <= money_tol or base["peak"] <= base_floor))):
                break
            step = max(high, (1.-low)/slope) if slope > 0 and low < 0 else high
            if not may_refine():
                if slope>0:
                    beginning=high+max(0.,(2*money_tol-low)/slope)
                    return dict(from_rate=beginning,to_rate=None,status="strictly_positive",
                                lower_bound_at_start_2025_eur=low+(beginning-high)*slope,lower_slope_2025=slope,
                                baseline_min_peak_lower_kw=base_floor,feasible_upgrade=ray,
                                support_start=high)
                break
            high += step
            prices.append(high)
            upgrade = point(equipment, high)
            if upgrade["peak"] <= base_floor:
                ray = upgrade
        return dict(from_rate=high, to_rate=None, status="unresolved_tail",
                    baseline_min_peak_lower_kw=base_floor, feasible_upgrade=ray,
                    bounds_at_start_2025_eur=gap(equipment, high))

    output = {}
    for equipment in ("two_independent", "two_shared_rule", "two_shared_pool"):
        zeros = [r for r in rates if gap(equipment, r)[1] <= money_tol]
        records = [dict(from_rate=r, to_rate=r, status="zero_to_tolerance",
                        upper_bound_2025_eur=gap(equipment, r)[1]) for r in zeros]
        if zeros:
            for a, b in zip(zeros, zeros[1:]):
                upper = zero_plateau(equipment, a, b)
                if upper <= money_tol:
                    records.append(dict(from_rate=a, to_rate=b, status="zero_to_tolerance",
                                        upper_bound_2025_eur=upper))
        else:
            prices = list(rates)
            tail = infinite(equipment, prices)
            for a, b in zip(prices, prices[1:]):
                finite(equipment, a, b, records)
            if tail["from_rate"]>prices[-1]:
                records.append(dict(from_rate=prices[-1],to_rate=tail["from_rate"],
                                    status="unresolved_at_solver_precision",lower_bound_2025_eur=0.,
                                    stop="auxiliary curve time budget"))
            records.append(tail)
        for record in records:
            if record["to_rate"] is not None and "stop" not in record:
                record["uniform_objective_gain_upper_eur_2025"]=zero_plateau(
                    equipment,record["from_rate"],record["to_rate"])
        output[equipment] = records
    return dict(objective="annual wholesale energy plus a uniform price per metered peak kW",
                scope="A listed zero is sufficient. Other prices may also give zero outside the reported intervals.",
                capacity_rate_units="2024 EUR/kW/year", money_tolerance_eur=money_tol,
                peak_tolerance_kw=kw_tol, intervals=output)
