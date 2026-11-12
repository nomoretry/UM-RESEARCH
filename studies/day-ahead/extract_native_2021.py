"""Rebuild the native DE-LU delivery hours for the UM port connector comparison."""
import argparse
import csv
from datetime import date, datetime, time, timedelta
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from extract_fleet_week import hourly_points


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "native_2021_source.json"
PRICES = HERE / "native_2021_prices.csv"


def selected_dates(meta):
    days = set()
    for scope in meta["service_date_ranges_inclusive"]:
        first, last = map(date.fromisoformat, scope)
        if first > last:
            raise ValueError("Reversed delivery date range")
        days.update(first + timedelta(days=i) for i in range((last - first).days + 1))
    return days


def extract(meta, raw_dir):
    zone = ZoneInfo(meta["timezone"])
    days = selected_dates(meta)
    expected = set()
    for d in days:
        start = datetime.combine(d, time(), zone)
        end = datetime.combine(d + timedelta(days=1), time(), zone)
        expected.update(range(int(start.timestamp()) * 1000, int(end.timestamp()) * 1000, 3_600_000))
    by_time = {}
    for week in meta["sources"]:
        raw = (raw_dir / week["url"].rsplit("/", 1)[1]).read_bytes()
        points = hourly_points(raw, week["sha256"], week["first_utc_ms"], week["hour_count"])
        for stamp, value in points:
            if stamp in expected:
                if stamp in by_time:
                    raise ValueError("Overlapping source weeks")
                by_time[stamp] = value
    if by_time.keys() != expected:
        raise ValueError("Incomplete selected delivery dates")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["start_berlin", "eur_per_mwh"])
    for stamp, price in sorted(by_time.items()):
        local = datetime.fromtimestamp(stamp / 1000, zone)
        writer.writerow([local.isoformat(), price])
    return buffer.getvalue().encode("utf-8")


def fetch_missing(meta, directory):
    directory = directory.resolve()
    if directory.is_relative_to(HERE.parents[1]):
        raise ValueError("Use an external raw-data cache")
    directory.mkdir(parents=True, exist_ok=True)
    for week in meta["sources"]:
        path = directory / week["url"].rsplit("/", 1)[1]
        if path.exists():
            continue
        with urlopen(week["url"], timeout=60) as response:
            raw = response.read()
        hourly_points(raw, week["sha256"], week["first_utc_ms"], week["hour_count"])
        with path.open("xb") as f:
            f.write(raw)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_dir", type=Path, help="External directory holding the seven source weeks")
    parser.add_argument("--fetch", action="store_true", help="Download missing files from the pinned official URLs")
    parser.add_argument("--output", type=Path, help="Save rebuilt CSV to a new file")
    args = parser.parse_args()
    metadata = json.loads(SOURCE.read_text(encoding="utf-8"))
    if args.fetch:
        fetch_missing(metadata, args.raw_dir)
    rebuilt = extract(metadata, args.raw_dir)
    checksum = hashlib.sha256(rebuilt).hexdigest()
    if metadata["price_csv_sha256"] != checksum or PRICES.read_bytes() != rebuilt:
        raise ValueError("The published CSV and source reconstruction differ")
    if args.output:
        with args.output.open("xb") as out:
            out.write(rebuilt)
    print(f"Verified {len(rebuilt.splitlines())-1} native delivery hours; SHA-256 {checksum}")
