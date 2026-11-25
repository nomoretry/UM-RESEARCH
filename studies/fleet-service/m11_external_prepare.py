"""Phase-scoped projection of the pinned trip export for the 19-week study."""
from collections import Counter, defaultdict
import csv
from dataclasses import replace
from datetime import date, timedelta
import hashlib
import io
import json

from prepare import HERE, SHA256, Trip, classify, day_bounds, duty, flag, timestamp
from um_charging.m11_external_seal import RANKS, authorize, digest


START, CUT, END = (date.fromisoformat(d) for d in ("2021-09-27", "2021-12-20", "2022-02-07"))
BOUNDS = {"selection": (START, CUT), "evaluation": (CUT, END)}
ENERGY = "energy_consumption_kwh"


def rank_slice(identities, cohort):
    low, high = RANKS[cohort]
    ordered = sorted(set(identities), key=int)
    return frozenset(ordered[low:high])


def csv_rows(stream):
    # The binary cursor supplies exact record ranges, including quoted multiline fields.
    def lines():
        while line := stream.readline():
            raw.append(line)
            yield line.decode("utf-8")
    raw = []
    reader = csv.reader(lines(), strict=True)
    names = next(reader)
    if len(set(names)) != len(names):
        raise ValueError("Duplicate CSV column")
    while True:
        start = stream.tell()
        raw.clear()
        fields = next(reader, None)
        if fields is None:
            break
        if len(fields) != len(names):
            raise ValueError("Malformed source record")
        yield dict(zip(names, fields)), start, b"".join(raw)


def identities(path, cohort):
    published = json.loads((HERE / "duties.json").read_bytes())["coverage"]
    carrier = str(published["freight_forwarder"])
    original = frozenset(map(str, published["cohort_vehicle_ids"]))
    # Only the gated path may discover ranks; task columns never enter the ranking.
    with path.open("rb") as stream:
        ids = {row["vehicle_id"] for row, _, _ in csv_rows(stream) if row["freight_forwarder"] == carrier}
    if rank_slice(ids, "1-5") != original:
        raise ValueError("STOP: published rank self-check failed")
    return carrier, rank_slice(ids, cohort)


def presence(value):
    # Classify the source's missing/nonfinite markers without converting any magnitude.
    token = value.strip().lower().lstrip("+-")
    return None if token in {"", "nan", "inf", "infinity"} else 0.


def metadata(row):
    return Trip(row["track_id"], timestamp(row["start_time"]), timestamp(row["stop_time"]),
                presence(row[ENERGY]), flag(row["home_base"]), flag(row["industrial_area"]))


def witnesses(records):
    output = {}
    for vehicle, trips in records.items():
        before = [t for t in trips if t.start.date() < START]
        if before:
            t = before[-1]
            output.setdefault("before_selection", {})[vehicle] = dict(
                track_id=t.track_id, arrival=t.end.isoformat(), home_base=t.home, industrial_area=t.industrial)
        for label, edge in (("after_selection", CUT), ("after_evaluation", END)):
            t = next((t for t in trips if t.start.date() >= edge), None)
            if t:
                output.setdefault(label, {})[vehicle] = dict(track_id=t.track_id, departure=t.start.isoformat())
    return output


def index_source(path, cohort, registration=None, authorization=None):
    authorize(cohort, registration, authorization)
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != SHA256:
            raise ValueError("Pinned trip export required")
    carrier, vehicles = identities(path, cohort)
    counts, boundaries, indexes = project(path, carrier, vehicles)
    return counts, boundaries, indexes, sorted(vehicles, key=int)


def project(path, carrier, vehicles):
    records = {v: [] for v in vehicles}
    index = {name: dict(records=[], crossing={}, header=None) for name in BOUNDS}
    with path.open("rb") as stream:
        for row, offset, raw in csv_rows(stream):
            if row["freight_forwarder"] != carrier or row["vehicle_id"] not in vehicles:
                continue
            v = row["vehicle_id"]
            t = metadata(row)
            records[v].append(t)
            for name, (left, right) in BOUNDS.items():
                section = index[name]
                if section["header"] is None:
                    section["header"] = list(row)
                if left <= t.start.date() < right:
                    section["records"].append([offset, len(raw), digest(raw)])
                elif t.start.date() < left <= t.end.date():
                    for i in range((min(right-timedelta(days=1), t.end.date()) - left).days + 1):
                        section["crossing"].setdefault(str(left+timedelta(days=i)), []).append(v)
    for trips in records.values():
        trips.sort(key=lambda t: (t.start, int(t.track_id)))
    days = calendar(records, START, END)
    counts = []
    for i in range(0, len(days), 7):
        week = days[i:i+7]
        trucks = [v for day in week for v in day["vehicles"]]
        excluded = Counter(reason for day in week for reason in day["other_observed_vehicle_days_excluded"].values())
        counts.append(dict(week=week[0]["date"], complete=len(trucks), excluded=dict(sorted(excluded.items())),
                           mapped=sum(len(v["stops"]) for v in trucks),
                           unmapped=sum(len(v["unmapped_gaps"]) for v in trucks)))
    return counts, witnesses(records), index


def calendar(records, left, right, *, pads=None, crossing=None):
    pads = pads or {}
    crossing = crossing or {}
    tasks = defaultdict(list)
    exclusions = defaultdict(dict)
    for v in sorted(records, key=int):
        trips = records[v]
        good, bad = classify(trips)
        before, after = pads.get(v, (None, None))
        extended = ([before] if before else []) + trips + ([after] if after else [])
        for day, indices in good.items():
            if left <= day < right and v not in crossing.get(str(day), ()):
                shifted = [i + int(before is not None) for i in indices]
                tasks[day].append(duty(v, extended, shifted, day))
        for day, reason in bad.items():
            if left <= day < right:
                exclusions[day][v] = reason
    for ds, vehicles in crossing.items():
        for v in vehicles:
            exclusions[date.fromisoformat(ds)][v] = "trip_crosses_local_midnight"
    days = []
    for i in range((right-left).days):
        day = left + timedelta(days=i)
        start, end = day_bounds(day)
        trucks, bad = tasks[day], exclusions[day]
        absent = records.keys() - {v["vehicle_id"] for v in trucks} - bad.keys()
        days.append(dict(date=str(day), start=start.isoformat(), end=end.isoformat(),
                         split="holdout" if day < CUT else "second_holdout",
                         week_start=str(day-timedelta(days=day.weekday())),
                         availability="complete_tasks" if trucks else "observed_excluded_only" if bad else "no_recorded_tasks",
                         vehicles=trucks, other_observed_vehicle_days_excluded=bad,
                         unobserved_vehicle_ids=sorted(absent, key=int)))
    return days


def read_period(path, section, vehicles, left, right):
    records = {v: [] for v in (vehicles or ())}
    with path.open("rb") as stream:
        for offset, length, checksum in section["records"]:
            stream.seek(offset)
            raw = stream.read(length)
            if digest(raw) != checksum:
                raise ValueError("Indexed source record changed")
            fields, = csv.reader(io.StringIO(raw.decode("utf-8")), strict=True)
            row = dict(zip(section["header"], fields, strict=True))
            if ((vehicles is not None and row["vehicle_id"] not in vehicles)
                    or not left <= timestamp(row["start_time"]).date() < right):
                raise ValueError("Record outside its sealed projection")
            trip = metadata(row)
            value = float(row[ENERGY]) if trip.energy is not None else None
            records.setdefault(row["vehicle_id"], []).append(replace(trip, energy=value))
    for trips in records.values():
        trips.sort(key=lambda t: (t.start, int(t.track_id)))
    return records


def latest_selection(records):
    result = {}
    for v, trips in records.items():
        if trips:
            last = trips[-1]
            result[v] = dict(track_id=last.track_id, arrival=last.end.isoformat(),
                             home_base=last.home, industrial_area=last.industrial)
    return result


def period_days(records, name, section, boundaries, *, preceding=None, strict=False, truncate=False):
    left, right = BOUNDS[name]
    before = boundaries.get("before_selection", {}) if name == "selection" else preceding or {}
    after = boundaries.get("after_" + name, {})
    pads = {}
    for v in records:
        a = b = None
        if not strict and v in before:
            t = before[v]
            moment = timestamp(t["arrival"])
            a = Trip(t["track_id"], moment, moment, None, t["home_base"], t["industrial_area"])
        if not strict and v in after:
            t = after[v]
            moment = day_bounds(right)[0] if truncate else timestamp(t["departure"])
            b = Trip(t["track_id"], moment, moment, None, False, False)
        pads[v] = a, b
    return calendar(records, left, right, pads=pads, crossing=section["crossing"])


def effective_windows(days):
    # Compare complete effective intervals and source linkage; unclipped future
    # departure is retained separately in the published task for provenance.
    return [[day["date"], v["vehicle_id"], kind, {k: value for k, value in stop.items() if k != "next_departure"}]
            for day in days for v in day["vehicles"] for kind in ("stops", "unmapped_gaps") for stop in v[kind]]
