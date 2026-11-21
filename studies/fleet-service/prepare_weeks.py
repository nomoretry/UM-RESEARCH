"""Extract the registered chronological samples of complete Berlin calendar weeks."""
import argparse
from collections import Counter
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

from prepare import HERE, classify, day_bounds, duty, read_cohort

WEEKS = 6
BASELINE = HERE / "duties.json"
OPERATING = HERE / "operating_weeks.json"
HOLDOUT = HERE / "holdout_weeks.json"
ANCHORS = (BASELINE.name, OPERATING.name, HOLDOUT.name)
STATUSES = ("complete_tasks", "observed_excluded_only", "no_recorded_tasks")


def summary(days):
    vehicles = [v for day in days for v in day["vehicles"]]
    rejected = Counter(reason for d in days for reason in d["other_observed_vehicle_days_excluded"].values())
    status = Counter(d["availability"] for d in days)
    return {
        "calendar_dates": len(days),
        "date_status_counts": {s: status[s] for s in STATUSES},
        "cohort_vehicle_date_slots": sum(len(d["vehicles"]) + len(d["other_observed_vehicle_days_excluded"])
                                         + len(d["unobserved_vehicle_ids"]) for d in days),
        "complete_vehicle_days": len(vehicles),
        "quality_excluded_vehicle_days": sum(rejected.values()),
        "counts_by_exclusion": dict(sorted(rejected.items())),
        "unobserved_vehicle_date_slots": sum(len(d["unobserved_vehicle_ids"]) for d in days),
        "vehicle_ids_with_complete_tasks": sorted({v["vehicle_id"] for v in vehicles}, key=int),
        "trips": sum(len(v["trips"]) for v in vehicles),
    }


def collect_weeks(path, *, after=BASELINE.name):
    if after not in ANCHORS:
        raise ValueError(f"Unknown calendar anchor: {after}")
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    previous_days = baseline["days"]
    holdout = after != BASELINE.name
    second_holdout = after == HOLDOUT.name
    for name in ANCHORS[1:ANCHORS.index(after) + 1]:
        previous = json.loads((HERE / name).read_text(encoding="utf-8"))
        if (previous["source"] != baseline["source"]
                or previous["cohort"]["cohort_vehicle_ids"] != baseline["coverage"]["cohort_vehicle_ids"]):
            raise ValueError(f"{name} must use the original source and cohort")
        previous_days = previous_days + previous["days"]
    last = max(date.fromisoformat(d["date"]) for d in previous_days)
    first_monday = last + timedelta(days=7-last.weekday())
    cohort, source_coverage = read_cohort(path)
    if baseline["coverage"]["cohort_vehicle_ids"] != source_coverage["cohort_vehicle_ids"]:
        raise ValueError("The cohort differs from the original design/holdout")
    quality = {v: classify(rows) for v, rows in cohort.items()}
    week_count = WEEKS
    if second_holdout:
        # A week is complete only if the fixed cohort's observation horizon reaches
        # its next Monday. Count elapsed calendar weeks, including weeks without trips.
        last_arrival = max(trip.end for trips in cohort.values() for trip in trips)
        week_count = (last_arrival.date() - first_monday).days // 7
        if week_count < 1:
            raise ValueError("No complete week remains after the first holdout")
    days, weeks = [], []
    for week in range(week_count):
        monday = first_monday + timedelta(weeks=week)
        week_days = []
        for offset in range(7):
            day = monday + timedelta(days=offset)
            left, right = day_bounds(day)
            vehicles, omitted, unobserved = [], {}, []
            for v in sorted(cohort, key=int):
                eligible, excluded = quality[v]
                if day in eligible:
                    vehicles.append(duty(v, cohort[v], eligible[day], day))
                elif day in excluded:
                    omitted[v] = excluded[day]
                else:
                    unobserved.append(v)
            status = "complete_tasks" if vehicles else ("observed_excluded_only" if omitted else "no_recorded_tasks")
            week_days.append({
                "date": day.isoformat(), "start": left.isoformat(), "end": right.isoformat(),
                "split": "second_holdout" if second_holdout else "holdout",
                "week_start": monday.isoformat(), "availability": status,
                "vehicles": vehicles, "other_observed_vehicle_days_excluded": omitted,
                "unobserved_vehicle_ids": unobserved,
            })
        days.extend(week_days)
        weeks.append({"week_start": monday.isoformat(), "week_end": week_days[-1]["date"], **summary(week_days)})

    def track_ids(period):
        return [t["track_id"] for d in period for v in d["vehicles"] for t in v["trips"]]

    tracks = track_ids(days)
    if len(tracks) != len(set(tracks)) or set(tracks).intersection(track_ids(previous_days)):
        raise ValueError("A transport task occurs more than once in the chronological split")

    with path.open(encoding="utf-8", newline="") as handle:
        distances = {r["track_id"]: float(r["track_gap"]) if r["track_gap"] else None
                     for r in csv.DictReader(handle)}
    spatial_gaps, unmapped_spatial_gaps = [], []
    weekly_mapping = {w["week_start"]: Counter() for w in weeks}
    missing_distance = Counter()
    for d in days:
        counts = weekly_mapping[d["week_start"]]
        for v in d["vehicles"]:
            counts["unmapped"] += len(v["unmapped_gaps"])
            counts.update(stop["site"] for stop in v["stops"])
            for stop in v["stops"] + (v["unmapped_gaps"] if holdout else []):
                distance = distances[stop["arrival_track_id"]]
                site = stop.get("site")
                if distance is None:
                    missing_distance["mapped" if site else "unmapped"] += 1
                elif distance >= 1000:
                    gaps = spatial_gaps if site else unmapped_spatial_gaps
                    gaps.append({
                        "date": d["date"], "vehicle_id": v["vehicle_id"], "site": site,
                        "arrival_track_id": stop["arrival_track_id"], "next_track_id": stop["next_track_id"],
                        "track_gap_m": distance,
                    })
    stop_counts = Counter()
    for week in weeks:
        counts = weekly_mapping[week["week_start"]]
        if second_holdout:
            counts.update({"PORT": 0, "WAREHOUSE": 0, "unmapped": 0})
        stop_counts.update(counts)
        if holdout:
            week["intervals_by_mapping"] = dict(sorted(counts.items()))
    result = {
        "source": baseline["source"], "timezone": baseline["timezone"],
        "baseline_duties_sha256": hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
        "period_rule": "First six consecutive full Monday–Sunday blocks after the last baseline date. "
                       "Every complete cohort vehicle-day enters, including singleton dates. Same carrier, later dates.",
        "cohort": source_coverage,
        "coverage": summary(days),
        "parking_bounds": {"intervals_by_mapping": dict(sorted(stop_counts.items())),
                           "mapped_intervals_missing_gap_distance": missing_distance["mapped"],
                           "mapped_intervals_at_least_1km": spatial_gaps},
        "weeks": weeks, "days": days,
    }
    if holdout:
        result["period_rule"] = (
            "First six complete consecutive Monday–Sunday weeks after the M8 operating weeks. "
            "Keep every date in the denominator. Include all complete vehicle-days from the original carrier "
            "and vehicles under the same quality rules, including singleton dates."
        )
        result["operating_weeks_sha256"] = hashlib.sha256(OPERATING.read_bytes()).hexdigest()
        result["parking_bounds"]["unmapped_intervals_missing_gap_distance"] = missing_distance["unmapped"]
        result["parking_bounds"]["unmapped_intervals_at_least_1km"] = unmapped_spatial_gaps
    if second_holdout:
        result["period_rule"] = (
            "All complete Berlin Monday–Sunday weeks after the first six-week holdout through the "
            "last recorded arrival of the original carrier and vehicle cohort. Keep weeks and dates "
            "without complete tasks in the denominator. Apply the original vehicle-day quality rules."
        )
        result["holdout_weeks_sha256"] = hashlib.sha256(HOLDOUT.read_bytes()).hexdigest()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tracks", type=Path)
    parser.add_argument("--after", choices=ANCHORS, default=BASELINE.name,
                        help="Start at the first full week after this committed sample")
    parser.add_argument("--output", type=Path, help="Write a new UTF-8 JSON file; default prints the input")
    args = parser.parse_args()
    text = json.dumps(collect_weeks(args.tracks, after=args.after), indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("xb") as out:
            out.write(text.encode("utf-8"))
    else:
        print(text, end="")
