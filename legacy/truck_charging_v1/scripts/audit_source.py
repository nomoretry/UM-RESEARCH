"""Read-only source-file audit; never treats a download error page as data.

Usage:
    python scripts/audit_source.py --source <actual source path>

Only aggregates and exact schema names are reported. No station or personal
record is printed. Exit status 2 means the file is not a readable source dataset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def audit(source: Path) -> dict:
    source = source.resolve(strict=True)
    payload = source.read_bytes()
    report = {
        "source_path": str(source),
        "file_size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "status": "not_audited",
        "format": None,
        "row_count": None,
        "schema": None,
        "missing_values_by_column": None,
        "duplicate_row_count": None,
        "coordinate_ranges": None,
        "heavy_truck_suitability": "not_verified",
        "source_provenance": "not_verified",
        "raw_record_samples_emitted": False,
        "findings": [],
    }
    stripped = payload.lstrip().lower()
    if stripped.startswith((b"<html", b"<!doctype html")):
        report.update(status="invalid_source", format="html_error_page")
        if b"403 forbidden" in stripped:
            report["findings"].append("The file contains an HTML 403 Forbidden response.")
        else:
            report["findings"].append("The file contains HTML, not the requested dataset.")
        report["findings"].append(
            "No dataset schema, records, coordinates, heavy-truck fields or source provenance can be audited."
        )
        report["findings"].append(
            "Exclude this file from all research-data ingestion. Preserve it unchanged as failed-download evidence."
        )
        return report
    if len(payload) < 12 or payload[:4] != b"PAR1" or payload[-4:] != b"PAR1":
        report.update(status="invalid_source", format="not_standard_parquet")
        report["findings"].append("The standard Parquet header/footer check failed; no schema is inferred.")
        return report
    report["format"] = "parquet"
    try:
        import pyarrow.parquet as pq
    except ImportError:
        report["status"] = "engine_unavailable"
        report["findings"].append("The Parquet header is present, but pyarrow is unavailable in this interpreter.")
        return report
    try:
        table = pq.read_table(source)
        frame = table.to_pandas()
        report.update(
            status="readable_requires_semantic_review",
            row_count=table.num_rows,
            schema=[{"name": field.name, "type": str(field.type)} for field in table.schema],
            missing_values_by_column={name: int(frame[name].isna().sum()) for name in frame.columns},
        )
        try:
            report["duplicate_row_count"] = int(frame.duplicated().sum())
        except TypeError:
            report["findings"].append("Full-row duplicate counting is unsupported for nested/unhashable columns.")
        report["findings"].append(
            "Coordinate, heavy-truck and provenance semantics must be verified from exact schema documentation; no field-name matching is guessed."
        )
    except Exception as error:
        report["status"] = "unreadable_parquet"
        report["findings"].append(f"Parquet read failed: {type(error).__name__}: {error}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[1] / "results" / "source_audit.json",
    )
    args = parser.parse_args()
    report = audit(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "readable_requires_semantic_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
