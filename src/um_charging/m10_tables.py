"""Deterministic offline exports for the twelve-week coarse facility study."""
from collections import Counter
import csv
import io
import json
from pathlib import Path
from statistics import median, quantiles

from .__main__ import digest


SERVICE_COLUMNS = {
    "design": "Installed port plugs and port/warehouse kW, encoded by Design.label.",
    "date": "Berlin service date (YYYY-MM-DD) in the registered cohort.",
    "vehicle_id": "Vehicle identifier in that cohort.",
    "status": "completed, not_completed (omitted by the documented service witness), or unresolved.",
    "evidence_id": "Weekly proof or linked derivation in service_proofs.json.",
}
SOLVE_COLUMNS = {
    "id": "Stable weekly request identity.",
    "week": "Monday of the Berlin service week.",
    "design": "Hardware used in this optimization.",
    "phase": "Reason for the service or fixed-duty solve.",
    "port_cap_kw": "Port quarter-hour demand cap (kW).",
    "warehouse_cap_kw": "Warehouse quarter-hour demand cap (kW).",
    "started_utc": "Absolute start time in UTC.",
    "seconds": "Elapsed wall seconds for this request.",
    "cpu_seconds": "Worker process CPU seconds for this request.",
    "status": "Certified, bounded, infeasible or unresolved according to the proof.",
    "status_code": "Native SciPy optimization status code.",
    "message": "Native termination message.",
    "objective_unit": "2021 EUR for fixed service or negative weighted service score.",
    "objective_lower": "Solver lower objective bound in objective_unit.",
    "objective_upper": "Feasible objective upper bound in objective_unit.",
    "relative_gap": "Relative objective gap (fraction).",
    "absolute_gap": "Absolute objective gap in objective_unit.",
    "audited": "Whether a feasible schedule passed independent physical replay.",
    "worker_pid": "OS process identifier of the solving worker.",
    "certificate_sha256": "SHA-256 of archived certificate.",
}


def solve_columns(continuation):
    if not continuation:
        return SOLVE_COLUMNS
    return {**SOLVE_COLUMNS,
            "original_status": "Status under the earlier weekly timeout interval rule (EUR 0.05, 2021).",
            "certificate_origin": "parent for a byte-exact inherited certificate, current for a new solve.",
            "widened_interval": "True only if the new EUR 0.10 rule admits a formerly unresolved interval."}


def json_bytes(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            + "\n").encode("utf-8")


def csv_bytes(columns, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        if row.keys() != columns.keys():
            raise ValueError(f"CSV fields differ from dictionary: {row.keys() ^ columns.keys()}")
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def artifact(path, content, *, verify=False):
    """Compare frozen bytes or publish a complete file in the same directory."""
    path = Path(path)
    if verify:
        if path.read_bytes() != content:
            raise ValueError(f"Replayed product differs: {path.name}")
    else:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)


def table_dictionary(schemas):
    lines = ["# Twelve-week coarse selection tables", "",
             "The UTF-8 CSV files use one header row. Blank numerical cells mean no finite "
             "bound, certified value or applicable charge is available. The weekly scheduling "
             "model knows all fixed duties and DE-LU day-ahead prices within that week. "
             "Weekly purchase uses 2021 euros. Annual totals use 2025 euros per year, "
             "with energy repeated 52/12 times and each site's maximum measured demand billed once."]
    for name, columns in schemas.items():
        lines.extend(["", f"## {name}", "", "| Column | Definition |", "|---|---|"])
        lines.extend(f"| `{col}` | {meaning} |" for col, meaning in columns.items())
    return ("\n".join(lines) + "\n").encode("utf-8")


def solve_statistics(records):
    seconds = [r["seconds"] for r in records]
    return dict(unique_solves=len(records), status_counts=dict(Counter(r["status"] for r in records)),
                native_time_limits=sum(r["status_code"] == 1 and "time limit" in r["message"].lower()
                                       for r in records),
                first_solve_utc=min((r["started_utc"] for r in records), default=None),
                median_seconds=median(seconds) if seconds else None,
                p90_seconds=(quantiles(seconds, n=10, method="inclusive")[8]
                             if len(seconds) > 1 else next(iter(seconds), None)),
                max_seconds=max(seconds, default=None), sum_wall_seconds=sum(seconds))


def products(output, service, matrix, proofs, costs, records, audit, *, verify=False):
    from .m10_costs import OPERATING_COLUMNS, ANNUAL_COLUMNS

    continuation = bool(records and "certificate_origin" in records[0])
    schemas = {"service_matrix.csv": SERVICE_COLUMNS, "operating_points.csv": OPERATING_COLUMNS,
               "annual_costs.csv": ANNUAL_COLUMNS, "solves.csv": solve_columns(continuation)}
    tables = [matrix, costs["operating_points"], costs["annual_costs"], records]
    if continuation:
        from .m10_transparency import OLD_POINT_COLUMNS, TRANSPARENCY_COLUMNS
        schemas.update({"old_rule_transparency.csv": TRANSPARENCY_COLUMNS, "old_rule_points.csv": OLD_POINT_COLUMNS})
        tables.extend([costs["old_rule_transparency"], costs["old_rule_points"]])
    files = {name: csv_bytes(columns, rows) for (name, columns), rows in zip(schemas.items(), tables, strict=True)}
    files["TABLES_README.md"] = table_dictionary(schemas)
    files["service_proofs.json"] = json_bytes(proofs)
    files["service_summary.json"] = json_bytes({d.label: row for d, row in service.items()})
    files["selection.json"] = json_bytes({k: v for k, v in costs.items()
                                          if k not in ("annual_costs", "operating_points")})
    files["audit.json"] = json_bytes(audit)
    stats = solve_statistics(records)
    if continuation:
        stats["by_origin"] = {}
        for origin in ("parent", "current"):
            subset = [row for row in records if row["certificate_origin"] == origin]
            expanded = [row["absolute_gap"] for row in subset if row["widened_interval"]]
            stats["by_origin"][origin] = dict(**solve_statistics(subset),
                                              widened_intervals=len(expanded),
                                              maximum_widened_gap=max(expanded, default=None))
        files["old_rule_evidence.json"] = json_bytes(costs["old_rule_evidence"])
    files["compute_statistics.json"] = json_bytes(stats)
    for name, content in files.items():
        artifact(output / name, content, verify=verify)
    hashes = {name: digest(output / name) for name in files}
    artifact(output / "product_hashes.json", json_bytes(hashes), verify=verify)
    return hashes
