"""Settle only registered-service dispatches at the three predeclared facilities."""
import math

from . import site_sizing as ss
from .cabinet_audit import audit_settlement
from .cabinet_tariff import annual_factors, annual_repeats, settle


FIXED = (ss.Design(1, 20, 0), ss.Design(1, 40, 0), ss.BASELINE)


def _week_status(result):
    if result is None:
        return "unresolved"
    stats = result["stats"]
    if stats["status"] == "infeasible":
        if stats["status_code"] != 2:
            raise ValueError("Fixed-service infeasibility requires a solver certificate")
        return "infeasible"
    if not (result["audit"] and result["audit"]["passed"]):
        if stats["status"] in ss.ENERGY_ACCEPTED:
            raise ValueError("Accepted dispatch lacks independent replay")
        return "unresolved"
    lo, hi = stats["objective_lower"], stats["objective_upper"]
    if lo is None or hi is None:
        return "unresolved"
    purchase = result["audit"]["purchase_eur"]
    if (not all(math.isfinite(x) for x in (lo, hi, purchase)) or lo > hi + ss.EPS
            or abs(hi - purchase) > ss.EPS):
        raise ValueError("Invalid bounds on the replayed wholesale purchase")
    gap = max(0., hi - lo)
    if (stats["status_code"] == 0 and stats["status"] == "certified"
            and (gap <= ss.fc.ABSOLUTE_COST_GAP + 1e-9 or
                 (stats["relative_gap"] is not None
                  and stats["relative_gap"] <= ss.fc.RELATIVE_COST_GAP + 1e-12))):
        return "certified"
    if (stats["status_code"] == 1 and "time limit" in stats["message"].lower()
            and gap <= ss.TIMEOUT_COST_GAP_EUR + 1e-9):
        return "bounded"
    return "unresolved"


def _operating_point(weeks, runs, caps, annual_grid_kwh, repeats):
    results = [runs.get(week) for week in weeks]
    states = [_week_status(r) for r in results]
    policy = dict(caps_kw=list(caps), week_status=dict(zip(weeks, states, strict=True)))
    if "infeasible" in states:
        return dict(**policy, status="infeasible")
    if "unresolved" in states:
        return dict(**policy, status="unresolved")
    audits = [r["audit"] for r in results]
    kwh = {s: math.fsum(a["site_grid_kwh"][s] for a in audits) for s in ss.SITES}
    peaks = {s: max(a["site_quarter_peak_kw"][s] for a in audits) for s in ss.SITES}
    if any(peaks[s] > limit + ss.EPS for s, limit in zip(ss.SITES, caps, strict=True)):
        raise ValueError("Meter replay exceeds a registered software limit")
    if not math.isclose(math.fsum(kwh.values()) * repeats, annual_grid_kwh,
                        rel_tol=0., abs_tol=ss.EPS * len(weeks) * repeats):
        raise ValueError("Meter replay disagrees with registered-service annual grid kWh")
    upper = math.fsum(a["purchase_eur"] for a in audits)
    lower = math.fsum(min(r["stats"]["objective_lower"], r["audit"]["purchase_eur"])
                      for r in results)
    return dict(**policy, status="bounded" if "bounded" in states else "certified",
                purchase_eur_2021_bounds=[lower, upper], site_grid_kwh=kwh,
                site_quarter_peak_kw=peaks)


def _bill(point, design, materials, network, scenario, basis):
    lo, hi = point["purchase_eur_2021_bounds"]
    kwh, peaks = point["site_grid_kwh"], point["site_quarter_peak_kw"]
    invoice = settle(network, hi, kwh, peaks, scenario)
    audit_settlement(network, hi, kwh, peaks, scenario, invoice)
    equipment, unpriced, connection = ss.annual_capital_costs(design, materials)
    if unpriced:
        raise ValueError(f"No registered equipment price for {unpriced}")
    if design == ss.BASELINE:
        connection = dict(new=sum(ss.EXISTING_KW) * materials["annual_bkz_eur_2025_per_kw"],
                          existing=0.)
    parts = dict(chargers=equipment, connection=connection[basis],
                 wholesale=invoice["annual_energy_eur_2025"],
                 network_energy=invoice["annual_network_energy_eur_2025"],
                 demand=invoice["annual_capacity_eur_2025"])
    total = math.fsum(parts.values())
    return dict(status=point["status"], caps_kw=point["caps_kw"], components_eur=parts,
                annual_total_eur=total,
                annual_total_eur_bounds=[total - (hi - lo) * annual_factors(network)[0], total],
                purchase_eur_2021_bounds=[lo, hi],
                peaks_kw=[peaks[s] for s in ss.SITES],
                bands=[invoice["sites"][s]["band"] for s in ss.SITES])


def _ranking(bills, m8, rated_verified):
    priced = {d: b["annual_total_eur_bounds"] for d, b in bills.items()
              if b["status"] in ss.ENERGY_ACCEPTED}
    order = sorted(priced, key=lambda d: priced[d][1])
    complete = rated_verified and all(
        b["status"] in ss.ENERGY_ACCEPTED or b["status"] == "service_gap"
        for b in bills.values())
    rank_bounds = {}
    winner = None
    status = "unresolved"
    if complete and order:
        for d, (lower, upper) in priced.items():
            ahead = sum(priced[other][1] < lower for other in order if other != d)
            behind = sum(upper < priced[other][0] for other in order if other != d)
            rank_bounds[d] = [1 + ahead, len(order) - behind]
        if rank_bounds[order[0]] == [1, 1]:
            winner = order[0]
        if winner == m8:
            status = "unchanged"
        elif m8 in priced and any(priced[d][1] < priced[m8][0] for d in priced if d != m8):
            status = "changed"
    if bills[m8]["status"] == "service_gap":
        status = "changed"
    return dict(winner=winner, recommendation_status=status, replay_order=order,
                rank_bounds=rank_bounds)


def annual_bills(weeks, runs, service_status, *, annual_grid_kwh):
    """Consume fixed-R week results already matched to their design and operating limit.

    Intervals propagate purchase bounds at the independently replayed meter traces.
    A missing or unresolved week never earns zero euros or justifies a fallback.
    """
    network = ss.load_network()
    repeats = annual_repeats(network)
    if len(weeks) != network["annualization"]["sample_weeks"] or len(set(weeks)) != len(weeks):
        raise ValueError("Expected the six distinct registered weeks")
    if (set(service_status) != {d.label for d in FIXED}
            or not set(service_status.values()) <= {"matched", "service_gap", "unresolved"}):
        raise ValueError("Expected all three registered service determinations")
    if not math.isfinite(annual_grid_kwh) or annual_grid_kwh < 0:
        raise ValueError("Expected nonnegative annual registered-service energy")
    materials = ss._load_costs(ss.CONNECTION_INPUT, network)
    m8 = ss.eb.read_json(ss.eb.WEEKS.with_name("site_sizing.json"))
    baseline = ss.BASELINE
    frozen = {r["scenario"]: tuple(r["caps_kw"]) for r in m8["cost_rows"]
              if r["design"] == baseline.label}
    points = {}
    for design in FIXED:
        caps_set = sorted(set(frozen.values()) | {design.caps}) if design == baseline else (design.caps,)
        for caps in caps_set:
            if service_status[design.label] == "matched":
                point = _operating_point(weeks, runs.get((design.label, caps), {}), caps,
                                         annual_grid_kwh, repeats)
            else:
                point = dict(status=service_status[design.label], caps_kw=list(caps))
            points[design.label, caps] = point

    rated = points[baseline.label, baseline.caps]
    rated_runs = runs.get((baseline.label, baseline.caps), {})
    rated_verified = service_status[baseline.label] == "matched" and all(
        rated_runs.get(w) and rated_runs[w]["audit"] and rated_runs[w]["audit"]["passed"]
        for w in weeks)
    cases = []
    for original in m8["winners"]:
        scenario, basis = original["scenario"], original["connection_basis"]
        bills = {}
        for design in FIXED:
            caps = frozen[scenario] if design == baseline else design.caps
            point = points[design.label, caps]
            policy = "frozen"
            if design == baseline and point["status"] == "infeasible" and caps != baseline.caps:
                point, policy = rated, "rated_fallback"
            if point["status"] in ss.ENERGY_ACCEPTED:
                row = _bill(point, design, materials, network, scenario, basis)
            else:
                row = dict(status=point["status"], caps_kw=point["caps_kw"])
            if (design == baseline and point["status"] == "unresolved"
                    and caps != baseline.caps and rated["status"] in ss.ENERGY_ACCEPTED):
                row["rated_comparator"] = _bill(rated, design, materials, network, scenario, basis)
            bills[design.label] = dict(**row, policy=policy, frozen_caps_kw=list(caps))
        cases.append(dict(scenario=scenario, connection_basis=basis, m8_winner=original["design"],
                          bills=bills, **_ranking(bills, original["design"], rated_verified)))
    return dict(cases=cases, rated_baseline_service_verified=rated_verified,
                operating_points=[dict(design=d, **p) for (d, _), p in points.items()])
