"""Recalculate charger costs and the annual energy balance for Milan."""
import csv
from pathlib import Path

# Table 5: initial euros per unit and annual maintenance euros per unit.
CHARGERS = {"ac_units": (2000, 20), "dc_units": (16000, 160), "v2g_units": (10000, 100)}
CAPITAL_RECOVERY_FACTOR = 0.087


def summarize(row):
    initial = sum(row[name] * costs[0] for name, costs in CHARGERS.items())
    maintenance = sum(row[name] * costs[1] for name, costs in CHARGERS.items())
    annual = initial * CAPITAL_RECOVERY_FACTOR + maintenance
    supply = sum(row[name] for name in ("pv_kwh", "bess_discharge_kwh", "ev_discharge_kwh", "grid_import_kwh"))
    use = sum(row[name] for name in ("site_load_kwh", "bess_charge_kwh", "ev_charge_kwh", "grid_export_kwh"))
    return initial, maintenance, annual, supply - use


def main():
    print("scenario,charger_investment_eur,maintenance_eur_per_year,annual_charger_cost_eur,residual_kwh")
    with Path(__file__).with_name("milan.csv").open(encoding="utf-8", newline="") as source:
        for record in csv.DictReader(source):
            row = {name: int(value) for name, value in record.items()}
            initial, maintenance, annual, residual = summarize(row)
            print(f"{row['scenario']},{initial},{maintenance},{annual:.2f},{residual}")


if __name__ == "__main__":
    main()
