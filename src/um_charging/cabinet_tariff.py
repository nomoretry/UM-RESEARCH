"""Annual settlement of two separately metered six-week charging traces."""
import json
import math
from pathlib import Path


NETWORK_INPUT = Path(__file__).resolve().parents[2] / "studies/day-ahead/network_charges.json"


def load_network():
    return json.loads(NETWORK_INPUT.read_text(encoding="utf-8"))


def annual_repeats(config):
    repeat = config["annualization"]
    return repeat["weeks_per_year"] / repeat["sample_weeks"]


def annual_factors(config):
    """Multipliers for six-week 2021 electricity and annual 2024 grid fees."""
    cpi = config["price_level"]["cpi"]
    return (
        annual_repeats(config) * cpi["2025"] / cpi["2021"],
        cpi["2025"] / cpi["2024"],
    )


def select_band(config, full_load_hours, basis="frank"):
    if not math.isfinite(full_load_hours) or full_load_hours < 0:
        raise ValueError("Full-load hours must be finite and nonnegative")
    boundary = config["full_load_hours_boundary"]
    low_at_boundary = config["tariffs"][basis]["low_includes_boundary"]
    if full_load_hours < boundary or (low_at_boundary and full_load_hours == boundary):
        return "low"
    return "high"


def network_rates(config, scenario, band):
    """Return capacity and energy rates for a tariff, in its original price level."""
    if scenario == "N0":
        return 0., 0.
    basis = "official" if scenario == "official" else "frank"
    rates = config["tariffs"][basis]["bands"][band]
    sensitivities = config["capacity_sensitivities_eur_per_kw_year"]
    return sensitivities.get(scenario, rates["capacity_eur_per_kw_year"]), rates["energy_eur_per_kwh"]


def settle(config, purchase_eur_2021, six_week_kwh_by_site, peak_kw_by_site, scenario):
    """Bill replayed quarter maxima without rounding at metering or CPI steps."""
    sensitivities = config["capacity_sensitivities_eur_per_kw_year"]
    if scenario not in {"N0", *config["tariffs"], *sensitivities}:
        raise ValueError(f"Unknown network settlement scenario: {scenario}")
    if not math.isfinite(purchase_eur_2021):
        raise ValueError("Six-week energy bill must be finite")
    meter_names = config["metering"]["sites"]
    if set(six_week_kwh_by_site) != set(meter_names) or set(peak_kw_by_site) != set(meter_names):
        raise ValueError("Both energy and peak are required at every registered meter")

    basis = "official" if scenario == "official" else "frank"
    repeat = config["annualization"]
    sites = {}
    for site in meter_names:
        kwh = six_week_kwh_by_site[site]
        peak = peak_kw_by_site[site]
        if not all(math.isfinite(x) and x >= 0 for x in (kwh, peak)) or (peak == 0) != (kwh == 0):
            raise ValueError(f"Inconsistent metering at {site}: {kwh} kWh with {peak} kW peak")
        annual_kwh = kwh * repeat["weeks_per_year"] / repeat["sample_weeks"]
        hours = annual_kwh / peak if peak else 0.0
        band = select_band(config, hours, basis)
        capacity_rate, energy_rate = network_rates(config, scenario, band)
        sites[site] = dict(
            six_week_kwh=kwh, annual_kwh=annual_kwh, peak_kw=peak,
            full_load_hours=hours, band=band,
            capacity_eur_per_kw_year=capacity_rate, energy_eur_per_kwh=energy_rate,
            annual_capacity_eur_2024=peak * capacity_rate,
            annual_network_energy_eur_2024=annual_kwh * energy_rate,
        )

    electricity_factor, network_factor = annual_factors(config)
    electricity = purchase_eur_2021 * electricity_factor
    capacity = math.fsum(m["annual_capacity_eur_2024"] for m in sites.values()) * network_factor
    network_energy = math.fsum(m["annual_network_energy_eur_2024"] for m in sites.values()) * network_factor
    return dict(
        scenario=scenario, sites=sites, six_week_energy_eur_2021=purchase_eur_2021,
        annual_energy_eur_2025=electricity, annual_capacity_eur_2025=capacity,
        annual_network_energy_eur_2025=network_energy,
        annual_total_eur_2025=math.fsum((electricity, capacity, network_energy)),
    )


def fixed_dispatch_zero(config, base, upgrade):
    """Operating-value zeros for a *fixed* schedule pair at a uniform capacity rate.

    Keep the actual metered energy charges. Remove the capacity part from each
    bill so the intercept is independent of the input scenario's capacity price.
    Draw the slope from the two site peaks, in their 2025 purchasing-power basis.
    """
    no_capacity_difference = (
        base["annual_energy_eur_2025"] - upgrade["annual_energy_eur_2025"]
        + base["annual_network_energy_eur_2025"] - upgrade["annual_network_energy_eur_2025"]
    )
    extra_peak = math.fsum(
        upgrade["sites"][site]["peak_kw"] - base["sites"][site]["peak_kw"]
        for site in config["metering"]["sites"]
    )
    if abs(extra_peak) <= 1e-8:
        status = "all_nonnegative_rates" if abs(no_capacity_difference) <= 1e-6 else "no_nonnegative_zero"
        rate = None
    else:
        crossing = no_capacity_difference / (annual_factors(config)[1] * extra_peak)
        status = "single_zero" if crossing >= -1e-8 else "no_nonnegative_zero"
        rate = max(0.0, crossing) if status == "single_zero" else None
    return dict(status=status, capacity_eur_per_kw_year_2024=rate,
                value_at_zero_eur_2025=no_capacity_difference, extra_meter_peak_kw=extra_peak)
