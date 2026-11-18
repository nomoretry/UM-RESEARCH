"""Independent meter and cabinet replay from positive grid-side schedule rows."""
from collections import defaultdict
import math

from . import energy_boundary as eb
from .fleet_service import EPS, SITES, _events


def schedule_on_clock(period, local, rows):
    """Reconstruct absolute timestamps from each original day's exact event cuts.

    Adding an offset to an already shifted floating timestamp can produce a
    different last bit than adding the same event cut to the master day origin.
    """
    edges = {}
    shifted = []
    for row in rows:
        d = row["date"]
        if d not in edges:
            cuts = {t for a, b, _ in _events(local.cases[d]) for t in (a, b)}
            edges[d] = {local.offset[d]+t: period.offset[d]+t for t in cuts}
        left = edges[d][row["start_min"]]
        right = edges[d][row["end_min"]]
        shifted.append({**row, "start_min": left, "end_min": right, "reservation_slot": int(left//15)})
    return shifted


def close(actual, expected, label):
    if not math.isclose(actual, expected, abs_tol=EPS, rel_tol=0):
        raise ValueError(f"Replay failed: {label}: {actual} vs {expected}")


def audit_cabinets(equipment, schedule):
    """Reserve connectors for whole quarters. Sweep actual simultaneous power within each."""
    ports = {"one": 1, "two_independent": 2, "two_shared_rule": 2, "two_shared_pool": 2}
    hardware = {"PORT": dict(interfaces=ports[equipment], power_kw=100),
                "WAREHOUSE": dict(interfaces=1, power_kw=75)}
    grouped = defaultdict(list)
    for row in schedule:
        a, b, kw = (row[k] for k in ("start_min", "end_min", "power_kw"))
        if not (all(math.isfinite(v) for v in (a, b, kw)) and 0 <= a < b and kw > 0):
            raise ValueError(f"Replay failed: invalid grid interval {row}")
        q = math.floor(a / 15)
        if row["reservation_slot"] != q or b > 15*(q+1):
            raise ValueError(f"Replay failed: quarter reservation {row}")
        grouped[row["site"], q].append((a, b, row["vehicle_id"], kw))

    peaks = dict.fromkeys(SITES, 0.)
    site_kwh = dict.fromkeys(SITES, 0.)
    for (site, q), rows in grouped.items():
        if site not in hardware:
            raise ValueError(f"Replay failed: unknown site {site}")
        trucks = sorted({v for _, _, v, _ in rows})
        if len(trucks) > hardware[site]["interfaces"]:
            raise ValueError(f"Replay failed: connectors at {(site, q, trucks)}")
        # A quarter has at most one reserved truck per connector. The independent
        # 50 kW cabinets are interchangeable; assigning one to each truck gives
        # a consistent physical cabinet identity throughout the quarter.
        shared = site == "PORT" and equipment in ("two_shared_rule", "two_shared_pool")
        cabinet = {v: 0 if shared else index for index, v in enumerate(trucks)}
        ticks = sorted({time for a, b, _, _ in rows for time in (a, b)})
        energy = 0.
        for left, right in zip(ticks, ticks[1:]):
            active = [(v, kw) for a, b, v, kw in rows if a <= left and b >= right]
            groups = defaultdict(list)
            for v, kw in active:
                groups[cabinet[v]].append(kw)
            for powers in groups.values():
                if math.fsum(powers) > 50 + EPS:
                    raise ValueError(f"Replay failed: cabinet kW at {(site, left, right, powers)}")
                if shared and equipment == "two_shared_rule" and len(powers) > 1 and max(powers) > 25 + EPS:
                    raise ValueError(f"Replay failed: simultaneous 25 kW rule at {(site, left, right, powers)}")
            energy += math.fsum(kw for _, kw in active) * (right-left) / 60
        site_kwh[site] += energy
        peaks[site] = max(peaks[site], energy / .25)
    return hardware, site_kwh, peaks


def audit_settlement(network, purchase_eur, site_kwh, peaks, scenario, settled):
    """Recalculate both annual meter invoices from audited meter readings."""
    annual = network["annualization"]
    repeat = annual["weeks_per_year"] / annual["sample_weeks"]
    cpi = network["price_level"]["cpi"]
    basis = "official" if scenario == "official" else "frank"
    capacity_total = volume_total = 0.
    for site in SITES:
        annual_kwh = site_kwh[site] * annual["weeks_per_year"] / annual["sample_weeks"]
        peak = peaks[site]
        if not peak and annual_kwh:
            raise ValueError(f"Replay failed: positive consumption without demand at {site}")
        hours = annual_kwh / peak if peak else 0.
        threshold = network["full_load_hours_boundary"]
        low = hours < threshold if basis == "official" else hours <= threshold
        band = "low" if low else "high"
        rates = network["tariffs"][basis]["bands"][band]
        capacity_rate = rates["capacity_eur_per_kw_year"]
        volume_rate = rates["energy_eur_per_kwh"]
        if scenario == "N0":
            capacity_rate = volume_rate = 0.
        elif scenario in network["capacity_sensitivities_eur_per_kw_year"]:
            capacity_rate = network["capacity_sensitivities_eur_per_kw_year"][scenario]
        elif scenario not in ("official", "frank"):
            raise ValueError(f"Unknown tariff {scenario}")
        row = settled["sites"][site]
        if row["band"] != band:
            raise ValueError(f"Replay failed: {site} band {row['band']} vs {band}")
        capacity = capacity_rate * peak
        volume = volume_rate * annual_kwh
        for key, value in dict(six_week_kwh=site_kwh[site], annual_kwh=annual_kwh,
                               peak_kw=peak, full_load_hours=hours,
                               capacity_eur_per_kw_year=capacity_rate, energy_eur_per_kwh=volume_rate,
                               annual_capacity_eur_2024=capacity, annual_network_energy_eur_2024=volume).items():
            close(row[key], value, (scenario, site, key))
        capacity_total += capacity * cpi["2025"] / cpi["2024"]
        volume_total += volume * cpi["2025"] / cpi["2024"]
    market_total = purchase_eur * repeat * cpi["2025"] / cpi["2021"]
    for key, value in dict(six_week_energy_eur_2021=purchase_eur,
                           annual_energy_eur_2025=market_total,
                           annual_capacity_eur_2025=capacity_total,
                           annual_network_energy_eur_2025=volume_total,
                           annual_total_eur_2025=math.fsum((market_total, capacity_total, volume_total))).items():
        close(settled[key], value, (scenario, key))


def replay(p, equipment, spec, rule, result, *, fixed=None, energy_weight=1.,
           peak_weights=None, site_energy_weights=None, network=None, scenario="N0",
           check_objective=True):
    """Replay without optimizer variables, constraint matrix or reported meter peaks."""
    if rule not in (eb.A, eb.B):
        raise ValueError(f"Unexpected energy boundary {rule}")
    states = result["states"]
    keys = {(r["date"], r["vehicle_id"]) for r in states}
    served = eb.selected(result)
    expected = p.keys if fixed is None else set(fixed)
    if (len(states) != len(keys) or keys != expected or not keys <= p.keys or
            (fixed is not None and served != expected)):
        raise ValueError("Replay failed: missing, duplicate or unexpected physical duties")
    hardware, site_kwh, peaks = audit_cabinets(equipment, result["schedule"])
    # The existing independent SOC/eligibility replay also integrates native
    # delivery-hour overlaps. Its physical-mode objective checks only the served
    # count; separately compare the solver's unmodified objective below.
    comparison = {**result, "stats": {"objective": -len(served)}}
    physical = eb.audit(p, hardware, spec, rule, comparison, physical=True)
    purchase = physical["purchase_eur"]
    if fixed is None:
        objective = -len(served)
    else:
        objective = energy_weight * purchase
        for site in SITES:
            objective += (peak_weights or {}).get(site, 0.) * peaks[site]
            objective += (site_energy_weights or {}).get(site, 0.) * site_kwh[site]
    if check_objective:
        close(result["stats"]["objective"], objective, "weighted objective")
    audit = dict(passed=True, served=sorted(served), purchase_eur=purchase, daily_eur=physical["daily_eur"],
                 site_grid_kwh=site_kwh, site_peak_kw=peaks, site_instant_peak_kw=physical["site_peak_kw"],
                 segments=physical["segments"])
    if network is not None:
        from .cabinet_tariff import settle
        bill = settle(network, purchase, site_kwh, peaks, scenario)
        audit_settlement(network, purchase, site_kwh, peaks, scenario, bill)
        audit["settlement"] = bill
    return audit
