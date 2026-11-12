"""Build chronological UM fleet duties from the pinned German BETOS trip export."""
import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

SHA256 = "d92ab77cafe21c1aad3e9be8de1e26b453846a677f91b07ee0ac5f652ec8c50e"
COMMIT = "2763d5aa04365958b54ec014c8b4cf47ea1a75fd"
URL = f"https://raw.githubusercontent.com/TUMFTM/truck_fleet_electrification/{COMMIT}/output/csvs/tracks_with_energy.csv"
HERE = Path(__file__).resolve().parent
BERLIN = ZoneInfo("Europe/Berlin")


@dataclass(frozen=True)
class Trip:
    track_id: str
    start: datetime
    end: datetime
    energy: float | None
    home: bool
    industrial: bool


def timestamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError("Source timestamp lacks an offset")
    return stamp.astimezone(BERLIN)


def flag(value):
    if value not in {"True", "False"}:
        raise ValueError(f"Unknown source stop flag {value!r}")
    return value == "True"


def day_bounds(day):
    return (datetime.combine(day, time.min, BERLIN),
            datetime.combine(day + timedelta(days=1), time.min, BERLIN))


def read_cohort(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
        raise ValueError("Expected published tracks_with_energy.csv at the pinned SHA-256")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len({r["track_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate source track_id")
    fleet = min(int(r["freight_forwarder"]) for r in rows)
    fleet_rows = [r for r in rows if int(r["freight_forwarder"]) == fleet]
    vehicles = sorted({int(r["vehicle_id"]) for r in fleet_rows})[:5]
    selected = defaultdict(list)
    for row in fleet_rows:
        if int(row["vehicle_id"]) in vehicles:
            energy = row["energy_consumption_kwh"]
            trip = Trip(row["track_id"], timestamp(row["start_time"]), timestamp(row["stop_time"]),
                        float(energy) if energy != "" else None, flag(row["home_base"]), flag(row["industrial_area"]))
            selected[row["vehicle_id"]].append(trip)
    for records in selected.values():
        records.sort(key=lambda x: (x.start, int(x.track_id)))
    return selected, {"source_trips": len(rows), "freight_forwarder": fleet, "fleet_trips": len(fleet_rows),
                      "cohort_vehicle_ids": vehicles, "cohort_trips": sum(map(len, selected.values()))}


def classify(records):
    """Quality rejection applies to the entire vehicle-day, including trips arriving from yesterday."""
    groups = defaultdict(list)
    for idx, trip in enumerate(records):
        day = trip.start.date()
        while day <= max(trip.end.date(), trip.start.date()):
            groups[day].append(idx)
            day += timedelta(days=1)
    valid, excluded = {}, {}
    for day, indices in groups.items():
        start, end = day_bounds(day)
        trips = [records[i] for i in indices]
        if any(x.start.date() != x.end.date() for x in trips):
            reason = "trip_crosses_local_midnight"
        elif (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)) != timedelta(hours=24):
            reason = "clock_change_day"
        elif any(x.end <= x.start for x in trips):
            reason = "nonpositive_trip_duration"
        elif any(a.end > b.start for a, b in zip(trips, trips[1:])):
            reason = "overlapping_records"
        elif any(x.energy is None or not math.isfinite(x.energy) for x in trips):
            reason = "missing_or_nonfinite_original_simulated_energy"
        else:
            valid[day] = indices
            continue
        excluded[day] = reason
    return valid, excluded


def duty(vehicle_id, records, indices, day):
    left, right = day_bounds(day)
    trips = [{"track_id": records[i].track_id, "start": records[i].start.isoformat(),
              "end": records[i].end.isoformat(), "energy_kwh": records[i].energy} for i in indices]
    stops, unmapped = [], []
    for i in range(max(0, indices[0] - 1), min(len(records) - 1, indices[-1] + 1)):
        a, b = records[i:i+2]
        start, end = max(left, a.end), min(right, b.start)
        if end <= start:
            continue
        site = "PORT" if a.home else ("WAREHOUSE" if a.industrial else None)
        gap = {"arrival_track_id": a.track_id, "next_track_id": b.track_id, "arrival": a.end.isoformat(),
               "next_departure": b.start.isoformat(), "start": start.isoformat(), "end": end.isoformat(),
               "home_base": a.home, "industrial_area": a.industrial}
        if site is None:
            unmapped.append(gap)
        else:
            stops.append({**gap, "site": site})
    return {"vehicle_id": vehicle_id, "trips": trips, "stops": stops, "unmapped_gaps": unmapped}


def extract(path):
    cohort, coverage = read_cohort(path)
    eligible = defaultdict(dict)
    exclusions = defaultdict(dict)
    for vehicle, records in cohort.items():
        valid, rejected = classify(records)
        for day, indices in valid.items():
            eligible[day][vehicle] = indices
        for day, reason in rejected.items():
            exclusions[day][vehicle] = reason
    joint_days = sorted(d for d in eligible if len(eligible[d]) >= 2)
    if len(joint_days) < 9:
        raise ValueError("Predeclared cohort has fewer than nine concurrent dates")
    days = []
    for i, day in enumerate(joint_days[:9]):
        left, right = day_bounds(day)
        vehicles = [duty(v, cohort[v], eligible[day][v], day) for v in sorted(eligible[day], key=int)]
        days.append({"date": day.isoformat(), "start": left.isoformat(), "end": right.isoformat(),
                     "split": "design" if i < 6 else "holdout", "vehicles": vehicles,
                     "other_observed_vehicle_days_excluded": exclusions.get(day, {})})
    all_rejections = Counter(reason for record in exclusions.values() for reason in record.values())
    complete = sum(map(len,eligible.values()))
    coverage.update({"observed_cohort_vehicle_dates": complete + sum(all_rejections.values()),
                     "excluded_vehicle_dates_by_first_applicable_reason": dict(sorted(all_rejections.items())),
                     "complete_vehicle_dates": complete, "dates_with_two_or_more_complete_vehicles": len(joint_days),
                     "complete_vehicle_dates_outside_selected_dates": complete - sum(len(d["vehicles"]) for d in days),
                     "selected_date_quality_exclusions": sum(len(d["other_observed_vehicle_days_excluded"]) for d in days)})
    for split in ("design", "holdout"):
        subset = [d for d in days if d["split"] == split]
        vs = [v for d in subset for v in d["vehicles"]]
        coverage[split] = {"dates": len(subset), "distinct_vehicles": sorted({v["vehicle_id"] for v in vs},key=int),
                           "vehicle_days": len(vs), "trips": sum(len(v["trips"]) for v in vs)}
    return {"source": {"url": URL, "sha256": SHA256, "attribution": "TUMFTM truck_fleet_electrification / DT-CARGO; BETOS trip-level simulation",
                       "terms": "See DATA.md for source licensing and derived-database attribution."},
            "timezone": "Europe/Berlin", "coverage": coverage, "days": days}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tracks", type=Path)
    parser.add_argument("--output", type=Path, help="Write the timestamped study input; default prints it")
    args = parser.parse_args()
    result = json.dumps(extract(args.tracks), indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.write_bytes(result.encode("utf-8"))
    else:
        print(result, end="")
