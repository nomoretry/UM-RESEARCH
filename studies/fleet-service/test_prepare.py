"""Check the archived fleet input, with an optional independent comparison to the pinned CSV."""
import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path

import pytest

from prepare import classify, day_bounds, duty, timestamp, Trip


def trip(trip_id, start, end, energy=20, home=True, industrial=True):
    return Trip(str(trip_id), timestamp(start + "+02:00"), timestamp(end + "+02:00"), energy, home, industrial)


DAY = date(2021, 9, 13)


def test_stops_require_two_records_and_preserve_original_arrival():
    records = [
        trip(1, "2021-09-12T23:00", "2021-09-12T23:50"),
        trip(2, "2021-09-13T01:10", "2021-09-13T02:01", home=False),
        trip(3, "2021-09-13T02:41", "2021-09-13T04:50", home=False, industrial=False),
        trip(4, "2021-09-13T05:15", "2021-09-13T08:00"),
    ]
    valid, rejected = classify(records)
    assert not rejected
    result = duty("1", records, valid[DAY], DAY)
    port, warehouse = result["stops"]
    assert port["site"] == "PORT" and warehouse["site"] == "WAREHOUSE"
    assert port["arrival"] == records[0].end.isoformat()
    assert port["start"] == day_bounds(DAY)[0].isoformat()
    assert port["end"] == records[1].start.isoformat()
    assert result["unmapped_gaps"][0]["arrival_track_id"] == "3"
    assert all(g["arrival_track_id"] != "4" for g in result["stops"])


def test_incomplete_vehicle_days_and_cross_midnight_on_both_dates():
    crossing = trip(1, "2021-09-12T23:50", "2021-09-13T00:05")
    later = trip(2, "2021-09-13T13:10", "2021-09-13T14:01")
    missing = trip(3, "2021-09-13T14:40", "2021-09-13T15:01", energy=None)
    overlapping = trip(4, "2021-09-13T14:00", "2021-09-13T15:00")
    assert classify([crossing, later]) == ({}, {date(2021, 9, 12): "trip_crosses_local_midnight",
                                                DAY: "trip_crosses_local_midnight"})
    assert classify([later, missing]) == ({}, {DAY: "missing_or_nonfinite_original_simulated_energy"})
    assert classify([later, overlapping]) == ({}, {DAY: "overlapping_records"})


def test_selected_dates_counts_and_totals():
    data = json.loads(Path(__file__).with_name("duties.json").read_text(encoding="utf-8"))
    counts = Counter()
    trip_ids = set()
    sums = {}
    for day in data["days"]:
        assert len(day["vehicles"]) >= 2
        value = Decimal(0)
        for vehicle in day["vehicles"]:
            counts[day["split"], "vehicle_days"] += 1
            for record in vehicle["trips"]:
                assert record["track_id"] not in trip_ids
                trip_ids.add(record["track_id"])
                counts[day["split"], "trips"] += 1
                value += Decimal(str(record["energy_kwh"]))
        sums[day["date"]] = value
    assert list(sums) == [f"2021-09-{i}" for i in (13, 14, 15, 16, 17, 20, 21, 22, 23)]
    assert counts == {("design", "vehicle_days"): 13, ("design", "trips"): 56,
                      ("holdout", "vehicle_days"): 8, ("holdout", "trips"): 45}
    assert sum(sums.values()) == Decimal("3254.041040")


@pytest.mark.skipif("UM_TUM_TRACKS" not in os.environ, reason="set UM_TUM_TRACKS to the pinned source CSV")
def test_against_original_trip_rows_and_every_adjacent_gap():
    data = json.loads(Path(__file__).with_name("duties.json").read_text(encoding="utf-8"))
    by_vehicle = defaultdict(list)
    with Path(os.environ["UM_TUM_TRACKS"]).open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            if row["freight_forwarder"] == "1":
                by_vehicle[row["vehicle_id"]].append(row)
    for rows in by_vehicle.values():
        rows.sort(key=lambda r: (datetime.fromisoformat(r["start_time"]), int(r["track_id"])))
    # Check the split from the full five-vehicle input, independently of prepare.extract.
    eligible = defaultdict(set)
    for vehicle in sorted(by_vehicle, key=int)[:5]:
        dated = defaultdict(list)
        for row in by_vehicle[vehicle]:
            start, end = (datetime.fromisoformat(row[k]) for k in ("start_time", "stop_time"))
            for offset in range(1 + (end.date() - start.date()).days):
                dated[start.date() + timedelta(days=offset)].append((start, end, row["energy_consumption_kwh"]))
        for day, rows in dated.items():
            left, right = day_bounds(day)
            if right.astimezone(timezone.utc) - left.astimezone(timezone.utc) != timedelta(days=1):
                continue
            if any(s.date() != e.date() or e <= s or not kwh or not Decimal(kwh).is_finite() for s, e, kwh in rows):
                continue
            if all(a[1] <= b[0] for a, b in zip(rows, rows[1:])):
                eligible[day.isoformat()].add(vehicle)
    expected = sorted(d for d, vehicles in eligible.items() if len(vehicles) >= 2)
    assert len(expected) == 79
    assert expected[:9] == [d["date"] for d in data["days"]]
    for day in data["days"]:
        left, right = map(datetime.fromisoformat, (day["start"], day["end"]))
        assert eligible[day["date"]] == {v["vehicle_id"] for v in day["vehicles"]}
        for vehicle in day["vehicles"]:
            rows = by_vehicle[vehicle["vehicle_id"]]
            observed = [r for r in rows if left <= datetime.fromisoformat(r["start_time"]) < right]
            assert [r["track_id"] for r in observed] == [t["track_id"] for t in vehicle["trips"]]
            for row, record in zip(observed, vehicle["trips"]):
                assert datetime.fromisoformat(row["start_time"]) == datetime.fromisoformat(record["start"])
                assert datetime.fromisoformat(row["stop_time"]) == datetime.fromisoformat(record["end"])
                assert Decimal(row["energy_consumption_kwh"]) == Decimal(str(record["energy_kwh"]))
            published = {(s["arrival_track_id"], s["next_track_id"]): s
                         for s in vehicle["stops"] + vehicle["unmapped_gaps"]}
            for a, b in zip(rows, rows[1:]):
                arrival, departure = datetime.fromisoformat(a["stop_time"]), datetime.fromisoformat(b["start_time"])
                start, end = max(arrival, left), min(departure, right)
                if end <= start:
                    continue
                gap = published.pop((a["track_id"], b["track_id"]))
                assert [datetime.fromisoformat(gap[k]) for k in ("arrival", "next_departure", "start", "end")] == [
                    arrival, departure, start, end]
                site = "PORT" if a["home_base"] == "True" else "WAREHOUSE" if a["industrial_area"] == "True" else None
                assert gap.get("site") == site
            assert not published
