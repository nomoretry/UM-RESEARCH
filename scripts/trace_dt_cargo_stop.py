"""Trace one German fleet recording gap from DT-CARGO to the UM stop table."""

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path


DATASET = (Path(__file__).resolve().parents[1] / "reserach" / "truck optimaztion"
           / "Germany_Truck_Grid_Dataset_v1")
# First stop in the existing fleet-1 pilot week (source keys, not line numbers).
VEHICLE_ID, TRACK_ID = "1", "168"
FLEET = "raw/dt_cargo/fleet.csv"
TRACKS = "raw/dt_cargo/tracks.csv"
STOPS = "processed/stop_windows.csv"
AUDITED_VERSION = "805c534c73ed4d247babd053f60468b486f92519"


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        yield from csv.DictReader(source)


def unique(values, label):
    matches = list(values)
    if len(matches) != 1:
        raise ValueError(f"Expected one {label}, found {len(matches)}")
    return matches[0]


def utc(text):
    stamp = datetime.fromisoformat(text)
    if stamp.utcoffset() is None:
        raise ValueError("Recording timestamp requires an explicit UTC offset")
    return stamp.astimezone(timezone.utc)


def adjacent_recordings(tracks, vehicle_id, track_id):
    vehicle = sorted((r for r in tracks if r["vehicle_id"] == vehicle_id),
                     key=lambda r: (utc(r["start_time"]), int(r["track_id"])))
    ids = [r["track_id"] for r in vehicle]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate track_id in vehicle recordings")
    if track_id not in ids or ids[-1] == track_id:
        raise ValueError("Requested recording or its successor is missing")
    index = ids.index(track_id)
    return vehicle[index], vehicle[index + 1]


def check_gap(previous, following, stop, fleet_id, params):
    """Check the stored window against both consecutive raw recordings."""
    start, end = utc(previous["stop_time"]), utc(following["start_time"])
    seconds = (end - start).total_seconds()
    if seconds <= 0:
        raise ValueError("Nonpositive gap between recordings")
    if (following["vehicle_id"] != previous["vehicle_id"]
            or stop["vehicle_id"] != previous["vehicle_id"]
            or stop["fleet_test_id"] != fleet_id
            or stop["track_id"] != previous["track_id"]
            or stop["next_track_id"] != following["track_id"]
            or utc(stop["stop_utc"]) != start or utc(stop["next_start_utc"]) != end):
        raise ValueError("Stored stop does not match the adjacent recording keys and times")
    # build_dataset.py writes eight decimal places (hours).
    if not math.isclose(seconds / 3600, float(stop["inter_record_gap_h"]),
                        rel_tol=0, abs_tol=5.01e-9):
        raise ValueError("Stored duration disagrees with recording timestamps")
    gaps = [float(r["track_gap"]) for r in (previous, following)]
    if (not all(math.isfinite(g) for g in gaps)
            or not math.isclose(max(gaps), float(stop["boundary_gap_conservative_m"]),
                                rel_tol=0, abs_tol=5.01e-9)
            or max(gaps) > params["max_boundary_gap_m"]
            or not params["min_window_h"] <= seconds / 3600 <= params["max_window_h"]
            or previous["home_base"] != "True" or stop["home_base"] != "True"
            or stop["base_window_candidate"] != "True"
            or stop["evidence_class"] != "INFERRED_INTER_RECORD_WINDOW"):
        raise ValueError("Selected stop does not pass the stored base-window screen")
    return start, end


def whole_slots(start, end, minutes):
    step = timedelta(minutes=minutes)
    remainder = (start - datetime(1970, 1, 1, tzinfo=timezone.utc)) % step
    first = start + (step - remainder if remainder else timedelta())
    return max(0, (end - first) // step)


def trace():
    manifest = json.loads((DATASET / "source_manifest.json").read_text(encoding="utf-8"))
    sources = {r["path"]: r for r in manifest}
    # The pinned upstream files use LF; Windows Git may check out those bytes as CRLF.
    for name in (FLEET, TRACKS):
        data = (DATASET / name).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(data).hexdigest() != sources[name]["sha256"]:
            raise ValueError(f"Source hash mismatch for {name}")
    if any(sources[name]["git_commit"] != AUDITED_VERSION for name in (FLEET, TRACKS)):
        raise ValueError("Recheck the event fields for this different upstream version")
    fleet = unique((r for r in rows(DATASET / FLEET) if r["vehicle_id"] == VEHICLE_ID),
                   "vehicle registry row")
    previous, following = adjacent_recordings(rows(DATASET / TRACKS), VEHICLE_ID, TRACK_ID)
    stop = unique((r for r in rows(DATASET / STOPS)
                   if r["vehicle_id"] == VEHICLE_ID and r["track_id"] == TRACK_ID), "stop row")
    params = json.loads((DATASET / "scenario_parameters.json").read_text(encoding="utf-8"))
    start, end = check_gap(previous, following, stop, fleet["fleet_test_id"], params)
    seconds = (end - start).total_seconds()
    return {
        "source": {"dataset": "DT-CARGO, German truck fleet", "version": "V1.1",
                   "authors": ["Georg Balke", "Lennart Adenaw"],
                   "commit": sources[TRACKS]["git_commit"], "tracks_url": sources[TRACKS]["url"],
                   "codebook_url": sources["raw/dt_cargo/README.md"]["url"],
                   "database_license": "ODbL 1.0", "contents_license": "DbCL 1.0",
                   "lf_sha256": {name: sources[name]["sha256"] for name in (FLEET, TRACKS)}},
        "event_key": {key: int(stop[key]) for key in
                      ("fleet_test_id", "vehicle_id", "track_id", "next_track_id")},
        "recorded_endpoints": {"previous_stop_time": previous["stop_time"],
                               "next_start_time": following["start_time"]},
        "source_fields_reviewed": {"tracks": list(previous), "fleet": list(fleet)},
        "derived": {"recording_gap_seconds": seconds, "parking_upper_bound_minutes": seconds / 60,
                    "processed_table": STOPS, "stored_gap_hours": float(stop["inter_record_gap_h"]),
                    "base_window_screen_passed": True,
                    "max_adjacent_track_gap_m": float(stop["boundary_gap_conservative_m"])},
        "clock_grid_assumption": {"slot_minutes": params["slot_minutes"],
                                  "whole_slots_inside_gap": whole_slots(start, end, params["slot_minutes"])},
        "independent_event_times": {"site_arrival": None, "handling_release": None,
                                    "plug_connected": None, "power_delivery_started": None},
        "verified_charging_minutes": None,
        "matching_scope": ("Only the vehicle and adjacent track records match. The pinned fleet "
                           "registry and track summaries contain no independent stop or EVSE event "
                           "for these four times. The gap bounds possible charging between recordings."),
    }


if __name__ == "__main__":
    print(json.dumps(trace(), indent=2))
