import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from extract_fleet_week import hourly_points
from extract_native_2021 import HOLDOUT_PRICES, HOLDOUT_SOURCE, PRICES, SOURCE, extract, selected_dates


def test_delivery_hours_and_offsets():
    raw = PRICES.read_bytes()
    meta = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert hashlib.sha256(raw).hexdigest() == meta["price_csv_sha256"]
    rows = list(csv.DictReader(raw.decode().splitlines()))
    stamps = [datetime.fromisoformat(row["start_berlin"]) for row in rows]
    assert {s.date() for s in stamps} == selected_dates(meta)
    assert len(stamps) == len({s.timestamp() for s in stamps}) == 1081
    assert stamps == sorted(stamps)
    assert sum(float(r["eur_per_mwh"]) < 0 for r in rows) == 7
    repeated = [(s.utcoffset(), r["eur_per_mwh"]) for s, r in zip(stamps, rows)
                if s.date().isoformat() == "2021-10-31" and s.hour == 2]
    assert repeated == [(timedelta(hours=2), "69.03"), (timedelta(hours=1), "64.49")]


@pytest.mark.parametrize("series", [
    [[0, -0.1], [0, 2]],
    [[0, None], [3600000, 2]],
    [[0, 1]],
])
def test_reject_incomplete_quotes_even_with_correct_hash(series):
    raw = json.dumps({"series": series}).encode()
    with pytest.raises(ValueError):
        hourly_points(raw, hashlib.sha256(raw).hexdigest(), 0, 2)


def test_holdout_delivery_hours_and_source_weeks():
    raw = HOLDOUT_PRICES.read_bytes()
    meta = json.loads(HOLDOUT_SOURCE.read_bytes())
    assert hashlib.sha256(raw).hexdigest() == meta["price_csv_sha256"]
    assert (meta["series"], meta["market_area"], meta["native_interval_minutes"], meta["currency_unit"]) == (
        4169, "DE-LU", 60, "EUR/MWh"
    )
    assert meta["timezone"] == "Europe/Berlin"
    berlin = ZoneInfo(meta["timezone"])
    start = datetime(2021, 11, 8, tzinfo=berlin).astimezone(timezone.utc)
    last = datetime(2021, 12, 20, tzinfo=berlin).astimezone(timezone.utc)
    hours = (last - start) // timedelta(hours=1)
    assert hours == meta["native_intervals"] == 1008
    expected = [(start + timedelta(hours=i)).astimezone(berlin).isoformat() for i in range(hours)]
    rows = list(csv.DictReader(raw.decode().splitlines()))
    assert [row["start_berlin"] for row in rows] == expected
    dates = {datetime.fromisoformat(stamp).date() for stamp in expected}
    assert len(dates) == meta["selected_days"] == 42
    assert dates == selected_dates(meta)
    rates = [float(row["eur_per_mwh"]) for row in rows]
    assert [min(rates), max(rates)] == meta["price_range_eur_per_mwh"] == [21.83, 425.0]
    assert sum(value < 0 for value in rates) == meta["negative_price_intervals"] == 0
    weeks = meta["sources"]
    assert [w["first_utc_ms"] for w in weeks] == [
        int((start + timedelta(weeks=i)).timestamp()) * 1000 for i in range(6)
    ]
    assert all(w["hour_count"] == 168 for w in weeks)


def test_rebuild_holdout_from_archived_smard_weeks():
    cache = os.getenv("UM_SMARD_HOLDOUT")
    if not cache:
        pytest.skip("Set UM_SMARD_HOLDOUT to verify the archived source responses")
    directory = Path(cache)
    meta = json.loads(HOLDOUT_SOURCE.read_bytes())
    index = (directory / "index_hour.json").read_bytes()
    assert hashlib.sha256(index).hexdigest() == meta["index_sha256"]
    starts = set(json.loads(index)["timestamps"])
    assert all(week["first_utc_ms"] in starts for week in meta["sources"])
    assert extract(meta, directory) == HOLDOUT_PRICES.read_bytes()
