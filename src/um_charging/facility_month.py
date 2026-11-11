"""Re-dispatch two fixed 45-minute-delay builds on the same January prices."""
import argparse
import copy
import math
from pathlib import Path
import sys

from .__main__ import checked_output, write_json
from .day_ahead import ROOT, STUDY, aligned_prices, evaluate, read_json
from .day_ahead_month import checked_optimum, price_windows, write_summary
from .eligibility_stress import build_case, make_reference
from .model import solve
from .validation import check_solution


ENERGY = ROOT / "studies/truck-energy/metrics.json"
DELAY = ROOT / "configs/eligibility_stress.json"
BUILDS = ({"PORT": 3, "WAREHOUSE": 1}, {"PORT": 2, "WAREHOUSE": 2})


def fixed_cases():
    settings = read_json(DELAY)
    transfer = read_json(ENERGY)
    base = read_json(ROOT / settings["base_config"])
    for aux_kw in (5, 7):
        energy_case, = (r for r in transfer["cases"] if r["payload_t"] == 19.30 and r["aux_kw"] == aux_kw)
        scaled = copy.deepcopy(base)
        for vehicle in scaled["vehicles"]:
            vehicle["drive_energy_kwh"] = [e * energy_case["energy_ratio"] for e in vehicle["drive_energy_kwh"]]
            legs = [e for e in vehicle["drive_energy_kwh"] if e]
            if legs != [energy_case["leg_kwh"]] * 2:
                raise ValueError("Energy transfer must reproduce both published legs exactly")
        reference = make_reference(scaled)
        for plugs in BUILDS:
            capex = sum((plugs[s["id"]] - s["interfaces"]) * s["interface_cost"] for s in reference["sites"])
            case = build_case(reference, plugs, transfer["warehouse_delay_minutes"], settings["delayed_vehicle_ids"])
            for site in case["sites"]:
                site["price_per_kwh"] = [0.0] * case["slot_count"]
            case["instance_id"] += f"_aux{aux_kw}"
            case["provenance"]["derived"] = [
                f"Single-leg battery demand {energy_case['leg_kwh']} kWh from the archived 19.3 t / {aux_kw} kW transfer.",
                "Wholesale purchases use the January price input; installed equipment is sunk for dispatch.",
            ]
            yield energy_case["leg_kwh"], capex, case


def solve_day(case, curve):
    rates = [slot["price_eur_per_mwh"] for slot in curve]
    cost = checked_optimum(solve(case, market_prices_eur_per_mwh=rates))
    balanced = checked_optimum(solve(case, market_prices_eur_per_mwh=rates, minimize_site_peak=True,
                                     purchase_ceiling_eur=cost["objective"]))
    bill = evaluate(case, curve, "day_ahead", cost)
    peaks = evaluate(case, curve, "peak_shaving", balanced)
    if not math.isclose(bill["purchase_eur"], peaks["purchase_eur"], rel_tol=0, abs_tol=1e-7):
        raise ValueError("Peak tie-break changed the optimal bill")
    return cost, balanced, bill, peaks


def run_comparison(output=None):
    """One independent service per delivery date; physics is identical across dates."""
    if output is not None:
        output = checked_output(Path(output), ROOT)
        output.mkdir(parents=True)
    months = list(price_windows(STUDY / "january_2025_prices.csv", read_json(STUDY / "january_2025_source.json")))
    rows = []
    for leg, capex, case in fixed_cases():
        sites = {s["id"]: s for s in case["sites"]}
        port, warehouse = sites["PORT"], sites["WAREHOUSE"]
        # This case has a one-hour port window for all trucks. Before the last
        # warehouse slot only V3 can refill its first-leg battery deficit.
        eta = case["vehicles"][0]["efficiency"]
        grid_need = 6 * leg / eta
        port_limit = port["available_power_kw"][0]
        max_warehouse = leg / eta + case["slot_hours"] * min(
            warehouse["interfaces"] * case["vehicles"][0]["power_limit_kw"]["WAREHOUSE"],
            warehouse["available_power_kw"][0])
        min_port = grid_need - max_warehouse
        physical = solve(case)
        if min_port > port_limit + 1e-7:
            if physical["status"] != "infeasible":
                raise ValueError("Insufficient port energy disagrees with the physical solve")
        else:
            checked_optimum(physical)
            if not check_solution(case, physical)["passed"]:
                raise ValueError("Independent fixed-build feasibility check failed")

        if output:
            folder = output / case["instance_id"]
            folder.mkdir()
            write_json(folder / "physical.json", {"case": case, "feasibility": physical,
                                                "port_energy_lower_bound_kwh": min_port})
        for date, market in months:
            curve = aligned_prices(market, case)
            wh_rate, port_rate = curve[4]["price_eur_per_mwh"], curve[12]["price_eur_per_mwh"]
            row = {"date": date.isoformat(), "leg_kwh": leg, "port_plugs": port["interfaces"],
                   "warehouse_plugs": warehouse["interfaces"], "investment_synthetic_units": capex,
                   "warehouse_eur_mwh": wh_rate, "port_eur_mwh": port_rate,
                   "min_port_energy_bound_kwh": min_port, "status": physical["status"],
                   "purchase_eur": None, "port_peak_kw": None, "warehouse_peak_kw": None, "warehouse_kwh": None,
                   "trips_completed": None, "cost_bound_eur": None, "peak_bound_kw": None,
                   "cost_gap": None, "peak_gap": None}
            if physical["status"] == "optimal":
                cost, balanced, bill, peaks = solve_day(case, curve)
                # A price lower bound from energy balance and warehouse access.
                # Equality certifies the bill independently of the optimizer.
                w_energy = max_warehouse if wh_rate < port_rate else max(0, grid_need - port_limit)
                lower_bill = (w_energy * wh_rate + (grid_need - w_energy) * port_rate) / 1000
                if not math.isclose(bill["purchase_eur"], lower_bill, rel_tol=0, abs_tol=1e-7):
                    raise ValueError(f"{date}: energy-price certificate disagrees")
                row.update(purchase_eur=bill["purchase_eur"], port_peak_kw=peaks["site_peak_kw"]["PORT"],
                           warehouse_peak_kw=peaks["site_peak_kw"]["WAREHOUSE"],
                           warehouse_kwh=peaks["site_energy_kwh"]["WAREHOUSE"], trips_completed=peaks["trips_completed"],
                           cost_bound_eur=cost["dual_bound"], peak_bound_kw=balanced["dual_bound"],
                           cost_gap=cost["mip_gap"], peak_gap=balanced["mip_gap"])
                if output:
                    write_json(folder / f"{date}.json", {"curve": curve, "cost": cost, "cost_then_peak": balanced,
                                                        "cost_replay": bill, "peak_replay": peaks})
            rows.append(row)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Fresh dispatch directory within the existing offline Git archive")
    write_summary(run_comparison(parser.parse_args().output), sys.stdout)
