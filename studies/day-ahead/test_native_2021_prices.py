import csv
from datetime import datetime, timedelta
import hashlib
import json

import pytest

from extract_fleet_week import hourly_points
from extract_native_2021 import PRICES, SOURCE, selected_dates


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
