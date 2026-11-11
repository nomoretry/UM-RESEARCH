"""Protect the distinction between a recording gap and a verified charging window."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from trace_dt_cargo_stop import adjacent_recordings, check_gap, trace, utc, whole_slots


def test_pilot_event_tracks_bound_the_interval_but_do_not_supply_plug_times():
    event = trace()
    assert event["event_key"] == {"vehicle_id": 1, "fleet_test_id": 1,
                                  "track_id": 168, "next_track_id": 169}
    assert event["derived"]["recording_gap_seconds"] == 1230.765
    assert event["clock_grid_assumption"]["whole_slots_inside_gap"] == 0
    assert event["verified_charging_minutes"] is None
    assert all(stamp is None for stamp in event["independent_event_times"].values())


def test_pair_uses_vehicle_and_utc_chronology_across_clock_change():
    tracks = [
        {"vehicle_id": "3", "track_id": "2", "start_time": "2021-10-31 02:10:00+01:00"},
        {"vehicle_id": "9", "track_id": "4", "start_time": "2021-10-31 02:58:00+02:00"},
        {"vehicle_id": "3", "track_id": "7", "start_time": "2021-10-31 02:55:00+02:00"},
    ]
    first, second = adjacent_recordings(tracks, "3", "7")
    assert (first["track_id"], second["track_id"]) == ("7", "2")
    with pytest.raises(ValueError, match="successor"):
        adjacent_recordings(tracks, "3", "2")
    with pytest.raises(ValueError, match="Duplicate"):
        adjacent_recordings(tracks + [tracks[0]], "3", "7")
    with pytest.raises(ValueError, match="UTC offset"):
        utc("2021-10-31 02:10:00")


def test_quarter_hour_grid_uses_complete_aligned_slots_only():
    end = utc("2021-10-11 00:30:00+02:00")
    assert whole_slots(utc("2021-10-11 00:15:00+02:00"), end, 15) == 1
    assert whole_slots(utc("2021-10-11 00:15:00.001+02:00"), end, 15) == 0


def test_processed_row_cannot_link_a_different_next_track():
    start, end = "2021-10-11 00:00:00+02:00", "2021-10-11 00:30:00+02:00"
    previous = {"vehicle_id": "3", "track_id": "9", "stop_time": start}
    following = {"vehicle_id": "3", "track_id": "11", "start_time": end}
    stop = {"vehicle_id": "3", "track_id": "9", "next_track_id": "10", "fleet_test_id": "1"}
    with pytest.raises(ValueError, match="keys and times"):
        check_gap(previous, following, stop, "1", {})
