import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from extract_fleet_week import hourly_points
from extract_native_2021 import (
    HOLDOUT_PRICES, HOLDOUT_SOURCE, PRICES, SOURCE, SECOND_HOLDOUT_PRICES,
    SECOND_HOLDOUT_SOURCE, extract, selected_dates,
)


def test_delivery_hours_and_offsets():
    raw = PRICES.read_bytes()
    meta = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert hashlib.sha256(raw).hexdigest() == meta["price_csv_sha256"] == (
        "8afde0563af37e3433158b04a7cad1fb394a609714279c68c9b1fa9ec1ee31bf"
    )
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


@pytest.mark.parametrize("price_file,source_file,first,end,weeks,price_range,negative,checksum", [
    (HOLDOUT_PRICES, HOLDOUT_SOURCE, "2021-11-08", "2021-12-20", 6, [21.83, 425.0], 0,
     "28e3f8a242625ddd59338ec340e756d49c07d0d7ca8b6bbfb627906ee0c908dc"),
    (SECOND_HOLDOUT_PRICES, SECOND_HOLDOUT_SOURCE, "2021-12-20", "2022-02-07", 7, [-1.05, 620.0], 9,
     "bb6ce2edd4482c4c36f0e58a70b3ceef2db71ea264e8e2e7438b23d5035bd704"),
], ids=["first-holdout", "second-holdout"])
def test_holdout_delivery_hours_and_source_weeks(price_file, source_file, first, end, weeks, price_range, negative, checksum):
    raw = price_file.read_bytes()
    meta = json.loads(source_file.read_bytes())
    assert hashlib.sha256(raw).hexdigest() == meta["price_csv_sha256"] == checksum
    assert (meta["series"], meta["market_area"], meta["native_interval_minutes"], meta["currency_unit"]) == (
        4169, "DE-LU", 60, "EUR/MWh"
    )
    assert meta["timezone"] == "Europe/Berlin"
    berlin = ZoneInfo(meta["timezone"])
    start = datetime.fromisoformat(first).replace(tzinfo=berlin).astimezone(timezone.utc)
    last = datetime.fromisoformat(end).replace(tzinfo=berlin).astimezone(timezone.utc)
    hours = (last - start) // timedelta(hours=1)
    assert hours == meta["native_intervals"] == 168 * weeks
    expected = [(start + timedelta(hours=i)).astimezone(berlin).isoformat() for i in range(hours)]
    rows = list(csv.DictReader(raw.decode().splitlines()))
    assert [row["start_berlin"] for row in rows] == expected
    dates = {datetime.fromisoformat(stamp).date() for stamp in expected}
    assert len(dates) == meta["selected_days"] == 7 * weeks
    assert dates == selected_dates(meta)
    rates = [float(row["eur_per_mwh"]) for row in rows]
    assert [min(rates), max(rates)] == meta["price_range_eur_per_mwh"] == price_range
    assert sum(value < 0 for value in rates) == meta["negative_price_intervals"] == negative
    assert [w["first_utc_ms"] for w in meta["sources"]] == [
        int((start + timedelta(weeks=i)).timestamp()) * 1000 for i in range(weeks)
    ]
    assert all(w["hour_count"] == 168 for w in meta["sources"])


@pytest.mark.parametrize("env_name,source_file,price_file", [
    ("UM_SMARD_HOLDOUT", HOLDOUT_SOURCE, HOLDOUT_PRICES),
    ("UM_SMARD_SECOND_HOLDOUT", SECOND_HOLDOUT_SOURCE, SECOND_HOLDOUT_PRICES),
], ids=["first-holdout", "second-holdout"])
def test_rebuild_holdout_from_archived_smard_weeks(env_name, source_file, price_file):
    cache = os.getenv(env_name)
    if not cache:
        pytest.skip(f"Set {env_name} to verify the archived source responses")
    directory = Path(cache)
    meta = json.loads(source_file.read_bytes())
    index = (directory / "index_hour.json").read_bytes()
    assert hashlib.sha256(index).hexdigest() == meta["index_sha256"]
    starts = set(json.loads(index)["timestamps"])
    assert all(week["first_utc_ms"] in starts for week in meta["sources"])
    assert extract(meta, directory) == price_file.read_bytes()
