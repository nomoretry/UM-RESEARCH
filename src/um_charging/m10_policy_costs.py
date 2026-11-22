"""Comparable fleet bills and disclosure of immediate charging's terminal inventory."""
import math

from . import site_sizing as ss
from .cabinet_tariff import annual_factors, annual_repeats
from .m10_costs import _parameters


DISCLOSURE = ("Same-truck, same-segment metered purchases weighted by grid kWh. "
              "Surplus battery kWh divided by 0.9. Includes wholesale energy and applicable "
              "per-kWh network charges and taxes in the modeled invoice. The tariff input "
              "excludes taxes. Excludes peak, capacity, connection and equipment charges. "
              "Already included in the invoice; disclosure only.")


def operating_caps(design, policy):
    if policy == "immediate":
        return [design.caps]
    if policy != "rolling":
        raise ValueError(f"Unknown operating policy {policy}")
    frozen = ((20, 20), (40, 20))
    return sorted({design.caps, *(caps for caps in frozen if all(
        value <= rated for value, rated in zip(caps, design.caps, strict=True)))})


def point_key(design, caps):
    return dict(design=design.label, port_cap_kw=caps[0], warehouse_cap_kw=caps[1])


def invoices(periods, design, weeks, *, parameters=None):
    """Settle complete meter traces independently at each meter; omit unknown equipment."""
    network, materials = parameters or _parameters(periods)
    if len(weeks) != len(periods) or not weeks:
        raise ValueError("One complete meter trace is required for every calendar week")
    purchase = math.fsum(w["audit"]["purchase_eur"] for w in weeks)
    lower = math.fsum(min(w["purchase_lower"], w["audit"]["purchase_eur"]) for w in weeks)
    grid = {s: math.fsum(w["audit"]["site_grid_kwh"][s] for w in weeks) for s in ss.SITES}
    peaks = {s: max(w["audit"]["site_quarter_peak_kw"][s] for w in weeks) for s in ss.SITES}
    equipment, missing, connection = ss.annual_capital_costs(design, materials)
    factor, grid_factor = annual_factors(network)
    bills = []
    for scenario in ("N0", *network["tariffs"], *network["capacity_sensitivities_eur_per_kw_year"]):
        metered = ss.settle(network, purchase, grid, peaks, scenario)
        ss.audit_settlement(network, purchase, grid, peaks, scenario, metered)
        rates = {s: grid_factor * metered["sites"][s]["energy_eur_per_kwh"] for s in ss.SITES}
        for basis, fixed in connection.items():
            upper = math.fsum([metered["annual_total_eur_2025"], equipment, fixed])
            low = upper - (purchase - lower) * factor
            bills.append(dict(scenario=scenario, connection_basis=basis,
                              known_lower=low, known_upper=upper, missing_ratings_kw=missing,
                              total_lower=None if missing else low, total_upper=None if missing else upper,
                              equipment=equipment, connection=fixed,
                              purchase=metered["annual_energy_eur_2025"],
                              network_energy=metered["annual_network_energy_eur_2025"],
                              demand=metered["annual_capacity_eur_2025"], grid_kwh=grid,
                              quarter_peak_kw=peaks, volumetric_rates=rates))
    return bills


def surplus_disclosure(periods, weeks, design, caps, paid_bills=None, *, parameters=None, details=False):
    """Use actual attempted meter bands for failed designs without publishing a same-service bill."""
    from .m10_immediate import surplus_costs, _aggregate_costs

    network, materials = parameters or _parameters(periods)
    repeat = annual_repeats(network)
    energy_factor = annual_factors(network)[0] / repeat
    bills = paid_bills if paid_bills is not None else invoices(
        periods, design, [dict(audit=w["audit"], purchase_lower=w["audit"]["purchase_eur"]) for w in weeks],
        parameters=(network, materials))
    by_case = {b["scenario"]: b["volumetric_rates"] for b in bills}
    daily, disclosure, segments, vehicles = [], [], [], []
    for scenario, rates in by_case.items():
        group = []
        for w in weeks:
            assigned = surplus_costs(w, purchase_factor_to_2025=energy_factor,
                                     volumetric_rates_eur_2025_per_kwh=rates)
            for day in assigned["days"]:
                daily.append(dict(**point_key(design, caps), scenario=scenario, week=w["week"], **day))
            for s in assigned["segments"]:
                group.append(s)
                segments.append(dict(**point_key(design, caps), scenario=scenario, week=w["week"], **s))
        for vehicle in sorted({s["vehicle_id"] for s in group}, key=int):
            vehicles.append(dict(**point_key(design, caps), scenario=scenario, vehicle_id=vehicle,
                                 **_aggregate_costs([s for s in group if s["vehicle_id"] == vehicle])))
        totals = _aggregate_costs(group)
        annual = {f"annual_{k}": None if v is None else v*repeat for k,v in totals.items()
                  if k.endswith(("_kwh","_eur_2025"))}
        for basis in ("new", "existing"):
            disclosure.append(dict(**point_key(design, caps), scenario=scenario, connection_basis=basis,
                                   policy="immediate", same_service=all(w["summary"]["same_service"] for w in weeks),
                                   **totals, **annual, accounting=DISCLOSURE))
    return (daily, disclosure, segments, vehicles) if details else (daily, disclosure)
