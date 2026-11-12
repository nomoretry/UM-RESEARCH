"""Convert six paired energy bills' weekly differences into an investment ceiling."""
import json
import math
from numbers import Real
from pathlib import Path


COST_INPUT = Path(__file__).resolve().parents[2] / "studies/day-ahead/connector_cost.json"


def break_even(weekly_savings, *, price_year=2021):
    """Use six nonoverlapping operating weeks in one price-year's euros.

    The caller supplies one comparable-service total per registered week, including
    zeros. The 52-week repeat is a scenario. Rates of growth and residual value are
    zero. The capex ceiling sets incremental annual maintenance to zero; with an
    annual fixed expense M, the available capital budget is (annual saving - M)/CRF.
    """
    inputs = json.loads(COST_INPUT.read_text(encoding="utf-8"))
    repeat = inputs["repeat_scenario"]
    reference = inputs["whole_charger_reference"]
    cpi = inputs["price_level"]["cpi"]

    weeks = list(weekly_savings)
    if len(weeks) != repeat["observed_weeks"]:
        raise ValueError("Supply one same-service bill difference for each of the six registered weeks")
    if any(isinstance(w, bool) or not isinstance(w, Real) or not math.isfinite(w)
           or w < -1e-7 for w in weeks):
        raise ValueError("Each week requires a finite, nonnegative paired saving in euros")
    weeks = [max(0.0, float(w)) for w in weeks]
    if type(price_year) is not int or str(price_year) not in cpi:
        raise ValueError("No registered price-level conversion for this delivery year")

    mean_weekly = math.fsum(weeks) / len(weeks)
    weeks_per_year = repeat["weeks_per_year"]
    annual_saving = weeks_per_year * mean_weekly
    to_reference_eur = cpi[str(reference["year"])] / cpi[str(price_year)]
    annual_saving_2025 = annual_saving * to_reference_eur

    rate = reference["discount_rate"]
    life = reference["equipment_life_years"]
    recovery_factor = rate / (1 - (1 + rate) ** -life)
    installed = reference["equipment_eur"] * (1 + reference["installation_share_of_equipment"])
    annual_capital = installed * recovery_factor
    maintenance = reference["equipment_eur"] * reference["maintenance_share_of_equipment_per_year"]
    annual_cost = annual_capital + maintenance
    return {
        "price_year": price_year,
        "weekly_savings_eur": weeks,
        "mean_weekly_savings_eur": mean_weekly,
        "weekly_range_eur": [min(weeks), max(weeks)],
        "repeat_weeks_per_year": weeks_per_year,
        "annual_cost_ceiling_eur": annual_saving,
        "capital_ceiling_zero_maintenance_eur": annual_saving / recovery_factor,
        "conversion_to_2025_eur": to_reference_eur,
        "annual_cost_ceiling_2025_eur": annual_saving_2025,
        "capital_ceiling_zero_maintenance_2025_eur": annual_saving_2025 / recovery_factor,
        "benchmark": {
            "source_input": "studies/day-ahead/connector_cost.json",
            "equipment_scope": "additional independent 50 kW DC charger",
            "benchmark_price_year": reference["year"],
            "discount_rate": rate,
            "equipment_life_years": life,
            "capital_recovery_factor": recovery_factor,
            "installed_capital_2025_eur": installed,
            "annual_capital_2025_eur": annual_capital,
            "annual_maintenance_2025_eur": maintenance,
            "annual_cost_2025_eur": annual_cost,
            "required_weekly_saving_2025_eur": annual_cost / weeks_per_year,
            "required_weekly_saving_input_year_eur": annual_cost / (weeks_per_year * to_reference_eur),
        },
        "covers_benchmark_in_repeat_scenario": annual_saving_2025 >= annual_cost,
    }
