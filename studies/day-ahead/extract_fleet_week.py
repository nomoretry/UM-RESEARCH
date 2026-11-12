"""Reconstruct the historical DE-LU tariff used for the fleet weekday replay."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIRST = datetime(2025, 1, 6, tzinfo=timezone(timedelta(hours=1)))
PRICE_FILE = HERE / "fleet_week_prices.csv"


def hourly_points(raw, expected_sha256, first_ms, count):
    """Validate a pinned SMARD series against continuous UTC delivery hours."""
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Wrong SMARD weekly source bytes")
    points = json.loads(raw)["series"]
    if len(points) != count:
        raise ValueError("Missing or extra hourly delivery intervals")
    for i, (stamp, rate) in enumerate(points):
        if type(stamp) is not int or stamp != first_ms + i * 3_600_000:
            raise ValueError("Missing, duplicate or unordered UTC interval")
        if type(rate) not in (int, float) or not math.isfinite(rate):
            raise ValueError("Missing or non-finite market price")
    return points


def csv_from_source(raw):
    meta = json.loads((HERE / "january_2025_source.json").read_text(encoding="utf-8"))
    start_ms = int(FIRST.timestamp()) * 1000
    source, = [s for s in meta["sources"] if s["url"].endswith(f"_{start_ms}.json")]
    points = hourly_points(raw, source["sha256"], start_ms, 168)
    timestamps = [FIRST + timedelta(hours=i) for i in range(168)]
    with (HERE / "january_2025_prices.csv").open(encoding="utf-8", newline="") as source_file:
        subset = {row["start_berlin"]: float(row["eur_per_mwh"]) for row in csv.DictReader(source_file)}
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["start_berlin", "eur_per_mwh"])
    for t, (_, rate) in zip(timestamps, points, strict=True):
        if 8 <= t.hour < 12 and rate != subset[t.isoformat()]:
            raise ValueError("Existing four-hour price snapshot disagrees")
        writer.writerow([t.isoformat(), rate])
    return output.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path, help="SMARD series 4169 week starting 1736118000000")
    parser.add_argument("--output",type=Path,help="Write the derived UTF-8 CSV to a new file")
    args = parser.parse_args()
    rebuilt = csv_from_source(args.raw.read_bytes()).encode("utf-8")
    if args.output:
        with args.output.open("xb") as out:
            out.write(rebuilt)
    elif rebuilt != PRICE_FILE.read_bytes():
        raise ValueError("Published fleet prices differ from the pinned SMARD delivery week")
    print(f"Verified 168 hourly prices; SHA-256 {hashlib.sha256(rebuilt).hexdigest()}")
