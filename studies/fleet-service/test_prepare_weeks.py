"""Independent checks of chronological sampling and the raw trip/stop evidence."""
import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import hashlib
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

from prepare import BERLIN

HERE = Path(__file__).resolve().parent


def read_duties(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(("filename", "first", "statuses", "trip_count", "weekly_complete", "previous_files"), [
    ("operating_weeks.json", date(2021, 9, 27), (30, 4, 8), 355, [12, 13, 12, 14, 16, 6], ["duties.json"]),
    ("holdout_weeks.json", date(2021, 11, 8), (28, 10, 4), 282, [9, 16, 13, 8, 8, 9],
     ["duties.json", "operating_weeks.json"]),
])
def test_calendar_partition_and_disjoint_trips(filename, first, statuses, trip_count, weekly_complete, previous_files):
    result = read_duties(filename)
    assert [d["date"] for d in result["days"]] == [str(first + timedelta(days=i)) for i in range(42)]
    assert [w["week_start"] for w in result["weeks"]] == [str(first + timedelta(weeks=i)) for i in range(6)]
    assert result["coverage"]["date_status_counts"] == {
        "complete_tasks": statuses[0], "observed_excluded_only": statuses[1], "no_recorded_tasks": statuses[2]}
    assert all(day["split"] == "holdout" for day in result["days"])
    ids = set()
    for week in result["weeks"]:
        days = [d for d in result["days"] if d["week_start"] == week["week_start"]]
        assert len(days) == 7
        assert week["cohort_vehicle_date_slots"] == 35
        assert week["complete_vehicle_days"] == sum(len(d["vehicles"]) for d in days)
        assert week["quality_excluded_vehicle_days"] == sum(len(d["other_observed_vehicle_days_excluded"]) for d in days)
        assert week["unobserved_vehicle_date_slots"] == sum(len(d["unobserved_vehicle_ids"]) for d in days)
        if filename == "holdout_weeks.json":
            trucks = [truck for day in days for truck in day["vehicles"]]
            mapped = Counter(stop["site"] for truck in trucks for stop in truck["stops"])
            mapped["unmapped"] = sum(len(truck["unmapped_gaps"]) for truck in trucks)
            assert week["intervals_by_mapping"] == mapped
            assert week["counts_by_exclusion"] == Counter(
                reason for day in days for reason in day["other_observed_vehicle_days_excluded"].values())
        for d in days:
            categories = ([v["vehicle_id"] for v in d["vehicles"]] + d["unobserved_vehicle_ids"]
                          + list(d["other_observed_vehicle_days_excluded"]))
            assert sorted(categories) == list("12345")
            status = "complete_tasks" if d["vehicles"] else (
                "observed_excluded_only" if d["other_observed_vehicle_days_excluded"] else "no_recorded_tasks")
            assert d["availability"] == status
            for truck in d["vehicles"]:
                for trip in truck["trips"]:
                    assert trip["track_id"] not in ids
                    ids.add(trip["track_id"])
    for previous_file in previous_files:
        previous = {t["track_id"] for d in read_duties(previous_file)["days"] for v in d["vehicles"] for t in v["trips"]}
        assert ids.isdisjoint(previous)
    assert len(ids) == trip_count
    assert [w["complete_vehicle_days"] for w in result["weeks"]] == weekly_complete


@pytest.mark.skipif("UM_TUM_TRACKS" not in os.environ, reason="set UM_TUM_TRACKS to the pinned source CSV")
@pytest.mark.parametrize("filename", ["operating_weeks.json", "holdout_weeks.json"])
def test_every_vehicle_day_trip_and_adjacent_window_against_source(filename):
    data = read_duties(filename)
    rows = defaultdict(list)
    with Path(os.environ["UM_TUM_TRACKS"]).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["freight_forwarder"] == "1" and row["vehicle_id"] in set("12345"):
                start, end = [datetime.fromisoformat(row[k]).astimezone(BERLIN) for k in ("start_time", "stop_time")]
                rows[row["vehicle_id"]].append((start, end, row))
    for trips in rows.values():
        trips.sort(key=lambda t: (t[0], int(t[2]["track_id"])))
    far = defaultdict(list)
    for day in data["days"]:
        left, right = [datetime.fromisoformat(day[k]).astimezone(BERLIN) for k in ("start","end")]
        included = {v["vehicle_id"]:v for v in day["vehicles"]}
        for v, trips in rows.items():
            touched = [(a,b,t) for a,b,t in trips if a.date() <= left.date() <= b.date()]
            if not touched:
                assert v in day["unobserved_vehicle_ids"]
                continue
            reason = None
            if any(a.date() != b.date() for a,b,_ in touched):
                reason = "trip_crosses_local_midnight"
            elif right.astimezone(timezone.utc)-left.astimezone(timezone.utc) != timedelta(days=1):
                reason = "clock_change_day"
            elif any(b <= a for a,b,_ in touched):
                reason = "nonpositive_trip_duration"
            elif any(previous[1] > following[0] for previous,following in zip(touched,touched[1:])):
                reason = "overlapping_records"
            elif any(not t["energy_consumption_kwh"] or not math.isfinite(float(t["energy_consumption_kwh"])) for _,_,t in touched):
                reason = "missing_or_nonfinite_original_simulated_energy"
            if reason:
                assert day["other_observed_vehicle_days_excluded"][v] == reason
                continue
            task = included[v]
            assert [r["track_id"] for _,_,r in touched] == [r["track_id"] for r in task["trips"]]
            for (a,b,tr), emitted in zip(touched, task["trips"]):
                assert [a.isoformat(), b.isoformat()] == [emitted["start"], emitted["end"]]
                assert Decimal(tr["energy_consumption_kwh"]) == Decimal(str(emitted["energy_kwh"]))
            intervals = {(r["arrival_track_id"],r["next_track_id"]):r for r in task["stops"] + task["unmapped_gaps"]}
            for (_,end,prev),(start,_,nxt) in zip(trips,trips[1:]):
                a,b = max(left,end),min(right,start)
                if a >= b:
                    continue
                entry = intervals.pop((prev["track_id"],nxt["track_id"]))
                assert [t.isoformat() for t in (end,start,a,b)] == [entry[k] for k in ("arrival","next_departure","start","end")]
                site = "PORT" if prev["home_base"]=="True" else ("WAREHOUSE" if prev["industrial_area"]=="True" else None)
                assert entry.get("site") == site
                if prev["track_gap"] and float(prev["track_gap"]) >= 1000:
                    far["mapped" if site else "unmapped"].append(
                        (day["date"],v,site,prev["track_id"],nxt["track_id"],float(prev["track_gap"])))
            assert not intervals
    for mapping in (("mapped", "unmapped") if filename == "holdout_weeks.json" else ("mapped",)):
        expected = [(r["date"],r["vehicle_id"],r["site"],r["arrival_track_id"],r["next_track_id"],r["track_gap_m"])
                    for r in data["parking_bounds"][f"{mapping}_intervals_at_least_1km"]]
        assert sorted(far[mapping]) == sorted(expected)


@pytest.mark.skipif("UM_TUM_TRACKS" not in os.environ, reason="set UM_TUM_TRACKS to the pinned source CSV")
@pytest.mark.parametrize(("args", "filename", "expected_hash"), [
    ([], "operating_weeks.json", "901b0dcf25f3af092c3400bd4982498d9a0b026e56495d365f5c78be6abd2c07"),
    (["--after", "operating_weeks.json"], "holdout_weeks.json",
     "6c4c4483961f957604b564ee7b1b423895d016526535e807d384be60cde69413"),
])
def test_script_reproduces_exact_published_bytes(args, filename, expected_hash, tmp_path):
    rebuilt = tmp_path / filename
    subprocess.run([sys.executable, HERE / "prepare_weeks.py", os.environ["UM_TUM_TRACKS"],
                    *args, "--output", rebuilt], check=True)
    result = rebuilt.read_bytes()
    assert hashlib.sha256(result).hexdigest() == expected_hash
    assert result == (HERE / filename).read_bytes()
