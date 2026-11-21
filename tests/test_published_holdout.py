"""Reconcile the published bilingual tables with the versioned holdout results."""
from decimal import Decimal
from itertools import groupby
import json
from pathlib import Path
import re

from um_charging.holdout_report import BASE, BASIS, PORT20, PORT40, TARIFF


STUDY = Path(__file__).resolve().parents[1] / "studies/fleet-service"
REPORT = (STUDY / "holdout_test.md").read_text(encoding="utf-8")
RESULT = json.loads((STUDY / "holdout_test.json").read_text(encoding="utf-8"))
REPAIRS = ("p1-20-w20", "p1-40-w20")


def table(header_cell):
    """Select a Markdown table by a semantic column label, ignoring surrounding prose."""
    matches = []
    for in_table, lines in groupby(REPORT.splitlines(), lambda line: line.strip().startswith("|")):
        if in_table:
            rows = [[s.strip() for s in line.strip().strip("|").split("|")] for line in lines]
            if header_cell in rows[0]:
                assert all(len(row) == len(rows[0]) for row in rows)
                matches.append(rows[2:])
    match, = matches
    return match


def duties(cell):
    if cell == "∅":
        return []
    pairs = []
    for item in cell.split(","):
        match = re.fullmatch(r"\s*(\d{4}-\d{2}-\d{2})\s*\((\d+)\)\s*", item)
        assert match, cell
        pairs.append(list(match.groups()))
    return sorted(pairs)


def vehicle_ids(cell):
    return [] if cell == "∅" else sorted(cell.replace(" ", "").split(","), key=int)


def bill_interval(cell):
    # A range that collapses at published cent precision is displayed as a single number.
    numeric = cell.split(" (")[0].replace(",", "")
    endpoints = [Decimal(x) for x in numeric.split("–")]
    assert 1 <= len(endpoints) <= 2
    return [endpoints[0], endpoints[-1]]


def rank_bounds(cell):
    return [None if rank == "—" else [int(rank.split("–")[0]), int(rank.split("–")[-1])]
            for rank in (part.strip() for part in cell.split(","))]


def annual_rows(header, evidence):
    rows = table(header)
    indexed = {(r[0], r[1]): r[2:] for r in rows}
    expected = {(TARIFF[r["scenario"]], BASIS[r["connection_basis"]]): r for r in evidence}
    assert len(rows) == len(indexed) == len(expected) == 12
    assert indexed.keys() == expected.keys()
    return [(cells, expected[key]) for key, cells in indexed.items()]


def expected_bill(bill):
    return [Decimal(f"{x:.2f}") for x in bill["annual_total_eur_bounds"]]


def test_published_main_register_and_missing_vehicle_days():
    main = RESULT["main"]
    dates = {r["date"]: r for r in main["daily"]}
    rows = table("登记 / Baseline register")
    assert len(rows) == len(dates) and {r[0] for r in rows} == dates.keys()
    for day, eligible, registered, twenty, forty in rows:
        r = dates[day]
        assert [vehicle_ids(c) for c in (eligible, registered, twenty, forty)] == [
            r["eligible"], r["registered"], r["facilities"][PORT20], r["facilities"][PORT40]]
    n = sum(len(r["registered"]) for r in dates.values())
    eligible = sum(len(r["eligible"]) for r in dates.values())
    assert f"{n}/{eligible}" in REPORT.split("\n## ", 1)[0]
    for field in ("annual_grid_kwh", "m8_annual_grid_kwh"):
        assert f'{main[field]:,.2f}' in REPORT.split("\n## ", 1)[0]
    gaps = table("登记外完成 (ID) / Added")
    assert [r[0] for r in gaps] == [PORT20, PORT40]
    for design, _, missing, added in gaps:
        assert duties(missing) == main["missing"][design]
        assert duties(added) == main["added"][design]


def test_published_fixed_facility_annual_bills_and_ranks():
    designs = (PORT20, PORT40, BASE)
    for cells, case in annual_rows("名次 / Ranks (20, 40, B)", RESULT["billing"]["cases"]):
        for cell, design in zip(cells[:3], designs, strict=True):
            bill = case["bills"][design]
            if bill["status"] == "service_gap":
                assert "gap" in cell and "annual_total_eur_bounds" not in bill
            else:
                assert bill_interval(cell) == expected_bill(bill)
        assert rank_bounds(cells[3]) == [case["rank_bounds"].get(d) for d in designs]
        assert cells[4] == {PORT20: "20", PORT40: "40"}[case["m8_winner"]]


def test_published_repair_bills_ranks_and_operating_policies():
    for cells, case in annual_rows("名次 / Ranks (B, 20/20, 40/20)", RESULT["repair_billing"]["cases"]):
        primary = [case["repairs"][d]["main"] for d in REPAIRS]
        references = [case["repairs"][d]["reference"] for d in REPAIRS]
        assert [bill_interval(c) for c in cells[:5]] == [
            expected_bill(b) for b in [case["baseline"], *primary, *references]]
        for cell, bill in zip(cells[1:3], primary, strict=True):
            assert {"rated_fallback": "fallback", "frozen": "frozen"}[bill["policy"]] in cell
        assert rank_bounds(cells[-1]) == [case["rank_bounds"][d] for d in (BASE, *REPAIRS)]


def test_published_sensitivity_register_and_six_service_outcomes():
    result = RESULT["sensitivity"]
    register_line, = [line for line in REPORT.splitlines() if line.startswith("重新登记 / Reregistered")]
    count, delta = register_line.split("个车日 / vehicle-days.")
    assert int(re.search(r"(\d+)\s*$", count).group(1)) == result["registered_count"]
    removed, added = delta.strip().removeprefix("移出 / Removed — ").split(". 新增 / Added — ")
    assert duties(removed) == result["registration_lost"]
    assert duties(added.rstrip(".")) == result["registration_gained"]
    rows = table("港/仓限峰 / Meter kW")
    records = {(r["design"], tuple(r["caps_kw"])): r for r in result["configs"]}
    found = set()
    for name, limits, n, status, missing, lost, gained, outcome in rows:
        key = name, tuple(map(int, limits.split("/")))
        found.add(key)
        r = records[key]
        assert int(n) == r["served_count"]
        assert status.split("/")[-1].strip() == {"matched": "retained", "service_gap": "gap"}[r["status"]]
        assert [duties(c) for c in (missing, lost, gained)] == [
            r["missing"], r["lost_vs_main"], r["gained_vs_main"]]
        assert outcome.split("/")[-1].strip() == result["target_gap"]["by_config"][r["id"]]
    assert len(rows) == len(found) == 6 and found == records.keys()
