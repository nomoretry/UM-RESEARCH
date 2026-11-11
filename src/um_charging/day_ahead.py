"""Settle three fixed-facility charging policies on one historical delivery curve."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import platform
import subprocess

import numpy as np
import scipy

from .__main__ import checked_output, digest, reject_duplicate_keys, write_json
from .eligibility_stress import build_case, make_reference
from .model import solve, validate_input
from .timegrid import physical_event_ledger, schedule_rows
from .validation import check_solution


ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "studies/day-ahead"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=reject_duplicate_keys)


def frozen_case(study):
    reference = make_reference(read_json(ROOT / study["base_config"]))
    history = read_json(ROOT / study["facility_results"])
    rows = [r for r in history["cases"] if r["delay_minutes"] == study["delay_minutes"]]
    if len(rows) != 1 or rows[0]["status"] != "optimal" or len(rows[0]["optimal_facilities"]) != 1:
        raise ValueError("The selected historical row must identify a single verified facility build")
    hardware = {s["site_id"]: s for s in rows[0]["optimal_facilities"][0]}
    if set(hardware) != set(study["site_ids"]):
        raise ValueError("Saved build and study sites differ")
    plugs = {key: site["total_interfaces"] for key, site in hardware.items()}
    case = build_case(reference, plugs, study["delay_minutes"], study["delayed_vehicle_ids"])
    for site in case["sites"]:
        installed = hardware[site["id"]]
        if not installed["active"] or site["available_power_kw"] != [installed["existing_power_kw"]] * case["slot_count"]:
            raise ValueError("Baseline site capacity does not match the saved facility build")
        site["available_power_kw"] = [installed["total_available_power_kw"]] * case["slot_count"]
        # The physical checker retains the legacy input schema. Settlement and
        # dispatch objectives use the separate timestamped wholesale price curve.
        site["price_per_kwh"] = [0.0] * case["slot_count"]
    case["instance_id"] = "day_ahead_frozen_" + case["instance_id"]
    case["provenance"]["assumed"].extend(study["assumptions"])
    validate_input(case)
    return case


def aligned_prices(market, case):
    """Accept signed delivery prices integral in model slots, without interpolation."""
    if market["currency_unit"] != "EUR/MWh" or not all(market[k] for k in ("market_area", "timezone", "source_url")):
        raise ValueError("Specify delivery area, time zone, price source and EUR/MWh")
    step = timedelta(hours=case["slot_hours"])
    slots = []
    previous_end = None
    for interval in market["intervals"]:
        start, end = (datetime.fromisoformat(interval[k]) for k in ("start", "end"))
        if start.utcoffset() is None or end.utcoffset() is None:
            raise ValueError("Delivery interval timestamps require UTC offsets")
        start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        if previous_end is not None and start != previous_end:
            raise ValueError("Non-contiguous or unordered price intervals")
        count, remainder = divmod(end - start, step)
        price = interval["price_eur_per_mwh"]
        if count <= 0 or remainder or type(price) not in (int, float) or not math.isfinite(price):
            raise ValueError("Use a finite price and complete delivery slots")
        for index in range(count):
            slots.append({"start_utc": (start + index * step).isoformat(), "price_eur_per_mwh": price})
        previous_end = end
    if len(slots) != case["slot_count"]:
        raise ValueError("Price coverage must match exactly the entire transport horizon")
    return slots


def charge_on_arrival(case):
    """First eligible, first served; equal arrival slots ordered by vehicle ID."""
    vehicles, sites = case["vehicles"], case["sites"]
    ticks, dt = case["slot_count"], case["slot_hours"]
    if case["connector_policy"] != "slot_boundary_switching":
        raise ValueError("Immediate dispatch requires slot-boundary switching")
    power = np.zeros((len(vehicles), len(sites), ticks))
    energy = np.zeros((len(vehicles), ticks + 1))
    energy[:, 0] = [v["initial_energy_kwh"] for v in vehicles]
    arrived = {}
    for t in range(ticks):
        for index, vehicle in enumerate(vehicles):
            site_id = vehicle["charging_site"][t]
            if site_id is not None and (t == 0 or vehicle["charging_site"][t - 1] != site_id):
                arrived[index] = t
        for j, site in enumerate(sites):
            waiting = [v for v, vehicle in enumerate(vehicles) if vehicle["charging_site"][t] == site["id"]]
            waiting.sort(key=lambda v: (arrived[v], vehicles[v]["id"]))
            free_kw = site["available_power_kw"][t] if site["active"] else 0.0
            free_plugs = site["interfaces"]
            for v in waiting:
                if not free_plugs or free_kw <= 1e-10:
                    break
                vehicle = vehicles[v]
                headroom = (vehicle["energy_max_kwh"] - energy[v, t]) / (dt * vehicle["efficiency"])
                draw = min(headroom, free_kw, vehicle["power_limit_kw"][site["id"]])
                if draw > 1e-10:
                    power[v, j, t] = draw
                    free_kw -= draw
                    free_plugs -= 1
        for v, vehicle in enumerate(vehicles):
            energy[v, t + 1] = energy[v, t] + dt * vehicle["efficiency"] * power[v, :, t].sum() - vehicle["drive_energy_kwh"][t]
    return {"status": "dispatched", "has_solution": True, "objective": None, "dual_bound": None, "mip_gap": None,
            "solution": {"power_kw": power.tolist(), "occupancy": (power > 0).astype(int).tolist(),
                         "energy_kwh": energy.tolist(), "new_interfaces": [0] * len(sites),
                         "upgrade_selected": [[] for _ in sites]}}


def evaluate(case, curve, policy, result):
    if not result["has_solution"]:
        raise RuntimeError(f"{policy}: no schedule; solver status {result['status']}")
    # Check every physical row on a frozen, zero-tariff instance. The policy
    # objective is checked separately below, in its original units.
    check = check_solution(case, {**result, "objective": 0.0})
    if not check["passed"]:
        raise ValueError(f"{policy}: independent physical audit failed: {check['errors']}")
    dt = case["slot_hours"]
    bill = sum(p * dt * slot["price_eur_per_mwh"] / 1000
               for profile in check["site_power_kw"].values() for p, slot in zip(profile, curve, strict=True))
    peak = max(check["site_peak_kw"].values())
    objective = {"immediate": None, "peak_shaving": peak, "day_ahead": bill}[policy]
    if objective is not None and not math.isclose(objective, result["objective"], rel_tol=0, abs_tol=1e-7):
        raise ValueError(f"{policy}: objective differs from independent schedule replay")
    ledger = physical_event_ledger(case)
    completed = sum(event["activity"] == "drive" for events in ledger.values() for event in events)
    terminals = {v["id"]: trace[-1] for v, trace in zip(case["vehicles"], check["energy_kwh_recomputed"], strict=True)}
    return {"policy": policy, "status": result["status"], "trips_completed": completed,
            "vehicles_completed": len(terminals), "terminal_kwh": terminals, "grid_energy_kwh": check["grid_energy_kwh"],
            "site_energy_kwh": check["site_energy_kwh"], "purchase_eur": bill, "site_peak_kw": check["site_peak_kw"],
            "objective_unit": {"immediate": None, "peak_shaving": "kW", "day_ahead": "EUR"}[policy],
            "objective": objective, "dual_bound": result["dual_bound"], "mip_gap": result["mip_gap"],
            "checks_passed": True, "physical_checks": check["checks"]}


def run_study(config_path, prices_path, output=None):
    study, market = read_json(config_path), read_json(prices_path)
    case = frozen_case(study)
    curve = aligned_prices(market, case)
    rates = [slot["price_eur_per_mwh"] for slot in curve]
    policies = {"immediate": charge_on_arrival(case), "peak_shaving": solve(case, minimize_site_peak=True),
                "day_ahead": solve(case, market_prices_eur_per_mwh=rates)}
    rows = [evaluate(case, curve, policy, result) for policy, result in policies.items()]
    summary = {"market_area": market["market_area"], "timezone": market["timezone"],
               "delivery_start": market["intervals"][0]["start"], "delivery_end": market["intervals"][-1]["end"],
               "config_sha256": digest(config_path), "prices_sha256": digest(prices_path),
               "hardware": {s["id"]: {"interfaces": s["interfaces"], "available_power_kw": s["available_power_kw"][0]}
                            for s in case["sites"]}, "policies": rows}
    if output is not None:
        output = checked_output(output, ROOT)
        output.mkdir(parents=True)
        git_args = ["git", "-C", str(ROOT)]
        write_json(output / "manifest.json", {
            "source_commit": subprocess.check_output([*git_args, "rev-parse", "HEAD"], text=True).strip(),
            "source_dirty": bool(subprocess.check_output([*git_args, "status", "--porcelain"], encoding="utf-8").strip()),
            "created_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
            "numpy": np.__version__, "scipy": scipy.__version__, "solver": "SciPy milp/HiGHS, 60 s, relative gap 0",
            "source_sha256": {p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
            "base_config_sha256": digest(ROOT / study["base_config"]),
            "facility_results_sha256": digest(ROOT / study["facility_results"])})
        write_json(output / "metrics.json", summary)
        write_json(output / "physical_case.json", case)
        write_json(output / "market.json", market)
        write_json(output / "aligned_prices.json", curve)
        for policy, result in policies.items():
            write_json(output / f"{policy}_raw.json", result)
            write_json(output / f"{policy}_schedule.json", schedule_rows(case, result))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=STUDY / "case.json")
    parser.add_argument("--prices", type=Path, default=STUDY / "prices.json")
    parser.add_argument("--output", type=Path, help="Fresh directory in the existing local-only run repository")
    args = parser.parse_args()
    print(json.dumps(run_study(args.config, args.prices, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
