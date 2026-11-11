"""Settle the same four-hour truck service on every January 2025 delivery date."""
import argparse
import calendar
import csv
import math
import platform
import sys

import numpy
import scipy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .__main__ import checked_output, digest, write_json
from .day_ahead import ROOT, STUDY, aligned_prices, charge_on_arrival, evaluate, frozen_case, read_json
from .model import solve


def price_windows(path, metadata):
    """Verify the complete, ordered January morning sample before solving."""
    if digest(path) != metadata["price_csv_sha256"]:
        raise ValueError("Price CSV differs from the cited snapshot")
    cet = timezone(timedelta(hours=1))  # Berlin in January 2025.
    first = date(2025, 1, 1)
    days = calendar.monthrange(first.year, first.month)[1]
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 4 * days:
        raise ValueError("Expected 31 complete four-hour windows")
    for index in range(days):
        day = first + timedelta(days=index)
        intervals = []
        for offset, row in enumerate(rows[4 * index:4 * index + 4]):
            start = datetime.fromisoformat(row["start_berlin"])
            expected = datetime(day.year, day.month, day.day, 8 + offset, tzinfo=cet)
            if start != expected or start.utcoffset() != expected.utcoffset():
                raise ValueError(f"Unexpected price timestamp at {expected}")
            intervals.append({"start": row["start_berlin"], "end": (start + timedelta(hours=1)).isoformat(),
                              "price_eur_per_mwh": float(row["eur_per_mwh"])})
        monday = day - timedelta(days=day.weekday())
        week_start = int(datetime.combine(monday, datetime.min.time(), tzinfo=cet).timestamp()) * 1000
        url, = [item["url"] for item in metadata["sources"] if item["url"].endswith(f"_{week_start}.json")]
        yield day, {**metadata, "source_url": url,
                    "intervals": intervals}


def checked_optimum(result):
    if result["status"] != "optimal" or result["mip_gap"] is None or abs(result["mip_gap"]) > 1e-7:
        raise ValueError("Daily comparison needs a proven optimal solution")
    return result


def run_month(output=None):
    study = read_json(STUDY / "case.json")
    case = frozen_case(study)
    source = read_json(STUDY / "january_2025_source.json")
    prices = STUDY / "january_2025_prices.csv"
    arrival = charge_on_arrival(case)
    peak = checked_optimum(solve(case, minimize_site_peak=True))
    if output is not None:
        output = checked_output(output, ROOT)
        output.mkdir(parents=True)
        write_json(output / "manifest.json", {
            "python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
            "inputs_sha256": {str(p.relative_to(ROOT)): digest(p) for p in
                              (STUDY / "case.json", prices, STUDY / "january_2025_source.json",
                               ROOT / study["base_config"], ROOT / study["facility_results"])},
            "source_sha256": {p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
            "solver": "SciPy milp / HiGHS; relative MIP gap 0 and time limit 60 s per solve",
            "market_information": "Historical hourly day-ahead prices known for the entire synthetic service."
        })
        write_json(output / "physical_case.json", case)
        write_json(output / "arrival_solution.json", arrival)
        write_json(output / "peak_solution.json", peak)
    rows = []
    for day, market in price_windows(prices, source):
        curve = aligned_prices(market, case)
        rates = [slot["price_eur_per_mwh"] for slot in curve]
        cheapest = checked_optimum(solve(case, market_prices_eur_per_mwh=rates))
        balanced = checked_optimum(solve(case, market_prices_eur_per_mwh=rates, minimize_site_peak=True,
                                          purchase_ceiling_eur=cheapest["objective"]))
        replay = [evaluate(case, curve, policy, raw) for policy, raw in
                  (("immediate", arrival), ("peak_shaving", peak), ("day_ahead", cheapest), ("peak_shaving", balanced))]
        immediate, shave, priced, both = replay
        if not math.isclose(priced["purchase_eur"], both["purchase_eur"], abs_tol=1e-7, rel_tol=0):
            raise ValueError(f"{day}: second-stage schedule differs from minimum price")
        data = {"date": day.isoformat(), "warehouse_eur_mwh": rates[4], "port_eur_mwh": rates[12]}
        for label, policy in zip(("arrival", "peak", "cost", "cost_then_peak"), replay, strict=True):
            for field, value in (("eur", policy["purchase_eur"]), ("port_kw", policy["site_peak_kw"]["PORT"]),
                                 ("warehouse_kw", policy["site_peak_kw"]["WAREHOUSE"]),
                                 ("warehouse_kwh", policy["site_energy_kwh"]["WAREHOUSE"])):
                data[label + "_" + field] = round(value, 8) or 0.0
        data["physical_checks"] = sum(policy["physical_checks"] for policy in replay)
        rows.append(data)
        if output is not None:
            write_json(output / f"{day}.json", {"price_slots": curve, "cheapest": cheapest, "cost_then_peak": balanced,
                                                 "replay_order": ["arrival", "peak", "cost", "cost_then_peak"],
                                                 "replay": replay})
    return rows


def write_summary(rows, handle):
    writer = csv.DictWriter(handle, fieldnames=rows[0], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Fresh directory in an existing local-only Git for detailed schedules")
    args = parser.parse_args()
    write_summary(run_month(args.output), sys.stdout)
