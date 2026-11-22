"""Settle the sealed holdout without applying the 2021 CPI to 2022 deliveries."""
from collections import defaultdict
import math

from . import site_sizing as ss
from .cabinet_tariff import annual_repeats
from .m10_costs import _parameters
from .m10_immediate import _aggregate_costs, surplus_costs
from .m10_policy_costs import DISCLOSURE


PRICE_INDEX = {"2021": 103.1, "2022": 110.2}
PRICE_YEAR = 121.9


def _weeks(periods, weeks):
    if len(periods) not in (6, 7) or len(periods) != len(weeks):
        raise ValueError("Expected every calendar week (six in rehearsal, seven in holdout)")
    for period, invoice_week in zip(periods, weeks, strict=True):
        dates = {d["date"] for d in period.days}
        if len(dates) != 7 or period.days[0]["week_start"] != invoice_week["week"]:
            raise ValueError("Invoice weeks and the complete delivery calendar differ")
        yield period, dates, invoice_week


def procurement(periods, weeks, *, immediate=False):
    """Return original currency subtotals and sample-period bounds in EUR 2025."""
    totals = defaultdict(list)
    lower, upper = [], []
    for _, dates, w in _weeks(periods, weeks):
        meter = w["audit"]
        if not meter or not meter["passed"]:
            raise ValueError("A complete audited metering trace is required")
        annual_years = {date[:4] for date in dates}
        if not annual_years <= PRICE_INDEX.keys():
            raise ValueError("An unregistered wholesale price year entered the invoice")
        if immediate:
            daily = defaultdict(list)
            for row in w["days"]:
                daily[row["date"]].extend(row["site_purchase_eur_2021"].values())
            native = {date: math.fsum(parts) for date, parts in daily.items()}
        else:
            native = meter["daily_eur"]
        if not native.keys() <= dates:
            raise ValueError("Purchase entries outside their registered delivery week")
        high_nominal = math.fsum(native.values())
        ss.close(high_nominal, meter["purchase_eur"], "native daily purchase subtotals")
        nominal_lo = high_nominal if immediate else w["purchase_lower"]
        if nominal_lo is None or not math.isfinite(nominal_lo) or nominal_lo > high_nominal + ss.EPS:
            raise ValueError("An invoice requires an admitted native purchase bound")
        if len(annual_years) != 1:
            if (any(meter["site_grid_kwh"].values()) or any(native.values()) or abs(nominal_lo) > ss.EPS):
                raise ValueError("The registered cross-year week is an empty operating week")
            low = 0.
        else:
            year, = annual_years
            low = min(nominal_lo, high_nominal) * PRICE_YEAR / PRICE_INDEX[year]
        lower.append(low)
        upper.append(math.fsum(euro * PRICE_YEAR / PRICE_INDEX[date[:4]] for date, euro in native.items()))
        for date, euro in native.items():
            totals[date[:4]].append(euro)
    return dict(by_delivery_year={year: math.fsum(values) for year, values in sorted(totals.items())},
                lower=math.fsum(lower), upper=math.fsum(upper))


def capital(design, materials, basis, *, baseline=False):
    equipment, missing, connection = ss.annual_capital_costs(design, materials)
    if missing:
        raise ValueError(f"Published equipment price absent for {missing}")
    if baseline:
        if design != ss.BASELINE:
            raise ValueError("The 100/75 kW connection asset belongs only to the dual-site baseline")
        connection = dict(new=sum(ss.EXISTING_KW) * materials["annual_bkz_eur_2025_per_kw"], existing=0.)
    return equipment, connection[basis]


def _energy_rates(network, bill):
    cpi = network["price_level"]["cpi"]
    return {s: bill["sites"][s]["energy_eur_per_kwh"] * cpi["2025"] / cpi["2024"] for s in ss.SITES}


def invoice(periods, design, weeks, *, scenario, basis, baseline=False, immediate=False, parameters=None):
    network, materials = parameters or _parameters(periods)
    repeat = annual_repeats(network)
    if repeat != 52 / len(periods):
        raise ValueError("Repetition factor does not match the full calendar denominator")
    spot = procurement(periods, weeks, immediate=immediate)
    grid = {site: math.fsum(w["audit"]["site_grid_kwh"][site] for w in weeks) for site in ss.SITES}
    peak = {site: max(w["audit"]["site_quarter_peak_kw"][site] for w in weeks) for site in ss.SITES}
    # Meter charges depend on the annual energy and effective peak. Use the
    # original independent settlement checker with zero wholesale, then add
    # the year-specific wholesale total exactly once.
    network_bill = ss.settle(network, 0., grid, peak, scenario)
    ss.audit_settlement(network, 0., grid, peak, scenario, network_bill)
    equipment, connection = capital(design, materials, basis, baseline=baseline)
    parts = dict(equipment=equipment, connection=connection, procurement=spot["upper"] * repeat,
                 network_energy=network_bill["annual_network_energy_eur_2025"],
                 demand=network_bill["annual_capacity_eur_2025"])
    fixed = math.fsum(v for key, v in parts.items() if key != "procurement")
    return dict(parts_eur_2025=parts, annual_total_lower=fixed + spot["lower"] * repeat,
                annual_total_upper=math.fsum(parts.values()), annual_fixed=equipment + connection,
                procurement_nominal_by_year=spot["by_delivery_year"], annualization=repeat,
                site_grid_kwh=grid, site_quarter_peak_kw=peak,
                site_energy_rate_eur_2025=_energy_rates(network, network_bill))


def immediate_disclosure(periods, weeks, scenario, *, parameters=None):
    network, _ = parameters or _parameters(periods)
    grid = {s: math.fsum(w["audit"]["site_grid_kwh"][s] for w in weeks) for s in ss.SITES}
    peak = {s: max(w["audit"]["site_quarter_peak_kw"][s] for w in weeks) for s in ss.SITES}
    bill = ss.settle(network, 0., grid, peak, scenario)
    ss.audit_settlement(network, 0., grid, peak, scenario, bill)
    rates = _energy_rates(network, bill)
    segments, daily = [], []
    for _, dates, w in _weeks(periods, weeks):
        years = {date[:4] for date in dates}
        if not years <= PRICE_INDEX.keys():
            raise ValueError("Unregistered delivery year in the disclosure calendar")
        if len(years) == 1:
            year, = years
        elif w["segments"] or any(w["audit"]["site_grid_kwh"].values()):
            raise ValueError("The registered cross-year week has no service segments")
        else:
            continue
        portion = surplus_costs(w, purchase_factor_to_2025=PRICE_YEAR / PRICE_INDEX[year],
                                volumetric_rates_eur_2025_per_kwh=rates)
        segments.extend(portion["segments"])
        daily.extend(portion["days"])
    by_vehicle = defaultdict(list)
    for value in segments:
        by_vehicle[value["vehicle_id"]].append(value)
    totals = _aggregate_costs(segments)
    repeat = annual_repeats(network)
    return dict(rule=DISCLOSURE, days=daily, segments=segments,
                vehicles=[dict(vehicle_id=v, **_aggregate_costs(values))
                          for v, values in sorted(by_vehicle.items(), key=lambda x: int(x[0]))],
                sample=totals, annual={k: None if v is None else v*repeat for k, v in totals.items()
                                      if k.endswith(("_kwh", "_eur_2025"))})


def difference(left, right, *, disclosure=0.):
    """Compare only admitted, identical-service invoices using opposite endpoints."""
    if left is None or right is None or disclosure is None:
        return None
    return [left["annual_total_lower"] - right["annual_total_upper"] - disclosure,
            left["annual_total_upper"] - right["annual_total_lower"] - disclosure]
