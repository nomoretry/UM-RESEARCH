"""Verify publication tables. Run this file with the plotting interpreter to check the figure artists."""
from collections import Counter
import csv
import json
import math
from pathlib import Path
import struct
import sys


CASE = Path(__file__).resolve().parents[1] / "studies" / "fleet-service"
PAPER = CASE / "paper"


def load(name):
    return json.loads((CASE / name).read_bytes())


def csv_rows(name):
    with (PAPER / (name + ".csv")).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def interval(row):
    return " to ".join(f"{n:,.2f}" for n in row)


def test_paper_tables_reference_the_published_values():
    results = load("external_test.json")
    cohorts = load("external_designs.json")["cohorts"]
    segments = load("external_segments.json")["segments"]
    overview = csv_rows("table1_cohorts")
    assert [r["Ranks"] for r in overview] == [*cohorts, "16-18"]
    for row in overview:
        label = row["Ranks"]
        record = cohorts[label] if label in cohorts else results["cohorts"][label]
        assert row["Complete days"] == " / ".join(map(str, record["complete_days"]))
        if label in cohorts:
            assert row["Registered days"] == " / ".join(map(str, record["registered_days"]))
            counts = [sum(set(d[p].values()) == {"feasible"} for d in record["designs"].values())
                      for p in ("selection", "evaluation")]
            assert row["Feasible builds"] == " / ".join(map(str, counts))
            assert row["Outcome"] == "Failed"
        else:
            assert row["Outcome"] == "Not evaluable" and row["Feasible builds"] == row["Registered days"] == ""

    failures = csv_rows("table2_failures")
    for row, seg in zip(failures, segments, strict=True):
        assert [row["Ranks"], row["Failed segment"], row["Selected build"], row["Gap (kWh)"]] == [
            seg["cohort"], " to ".join(seg["dates"]), seg["selected"], f"{seg['deficit_kwh']:.3f}"]
        assert row["Bill (EUR/yr)"] == interval(cohorts[seg["cohort"]]["designs"][seg["selected"]]["selection_bill"]["new"])
        assert row["Constraint"] == ("Post-trip reserve" if seg["constraint"] == "single_truck_leg_boundary" else "Terminal energy")

    names = {"rule1": "Rule I", "rule2": "Rule II", "rule3": "Rule III",
             "rule4": "Rule IV", "weekly_union": "Weekly union"}
    expected = {(label, r["basis"].title(), names[r["method"]], r["design"], interval(r["premium"]),
                 {"未守住": "Failed", "守住": "Held"}[r["test"]])
                for label, c in cohorts.items() for r in c["comparisons"] if r["method"] in names}
    rule_rows = csv_rows("table3_rules")
    assert {tuple(r.values()) for r in rule_rows} == expected and len(rule_rows) == len(expected)
    operations = csv_rows("table5_operations")
    policies = load("second_holdout.json")["operating_policies"]
    assert len(operations) == 6
    for row in operations:
        source = policies["official_" + row["Connection"].lower()][row["Policy"].lower().replace(" ", "_")]
        assert row["Bill (EUR/yr)"] == interval(source["annual_cost_eur_2025"])
        assert row["Build"] == source["design"]
        assert row["Caps (kW)"] == " / ".join(map(str, source["caps_kw"]))
        surplus = source.get("terminal_surplus_eur_2025_per_year")
        assert row["Of which surplus (EUR/yr)"] == ("" if surplus is None else f"{surplus:,.2f}")


def test_print_fragments_and_raster_resolution():
    for path in PAPER.glob("table*.csv"):
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        tex = path.with_suffix(".tex").read_text(encoding="utf-8")
        assert all(tag in tex for tag in (r"\toprule", r"\midrule", r"\bottomrule"))
        for row in rows:
            assert " & ".join(cell or "---" for cell in row) + r" \\" in tex
    figures = sorted(PAPER.glob("figure*.png"))
    assert len(figures) == 6
    for path in figures:
        raw = path.read_bytes()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"
        offset = 8
        while raw[offset + 4:offset + 8] != b"pHYs":
            size, = struct.unpack_from(">I", raw, offset)
            offset += size + 12
            assert offset < len(raw)
        x, y, unit = struct.unpack_from(">IIB", raw, offset + 8)
        assert unit == 1 and x == y and round(x * .0254) == 300
        assert path.with_suffix(".pdf").read_bytes().startswith(b"%PDF-")


def check_figure_artists():
    sys.path.insert(0, str(PAPER))
    import make_figures as figures

    report = load("external_test.json")
    cohorts = load("external_designs.json")["cohorts"]
    payload = load("external_segments.json")
    timeline = figures.design_timeline(report).axes[0]
    texts = {artist.get_text().replace("\n", " ") for artist in timeline.texts}
    assert all(" to ".join(report["model"][period]) in texts for period in ("selection_dates", "evaluation_dates"))
    assert all(figures.trucks(label) in texts for label in [*cohorts, "16-18"])
    assert [p.get_width() for p in timeline.patches] == [w / 19 - .006 for w in report["model"]["calendar_weeks"]]
    for ax, (label, cohort) in zip(figures.cost_outcomes(cohorts, report).axes, cohorts.items(), strict=True):
        assert [t.get_text().replace("\n", " ") for t in ax.get_yticklabels()] == ["Failed", "Held (completed all registered test duties)"]
        expected = {name: d for name, d in cohort["designs"].items() if d["selection_bill"]}
        assert len(ax.lines) == len(expected)
        for line in ax.lines:
            name = line.get_gid()
            build = expected[name]
            assert math.isclose(line.get_xdata()[0], sum(build["selection_bill"]["new"]) / 2000)
            assert (line.get_ydata()[0] > .5) == (set(build["evaluation"].values()) == {"feasible"})
            marker = ("s" if name == cohort["selected"] else "*" if name == report["report_details"]["posthoc"][label]["design"] else "o")
            assert line.get_marker() == marker
    bars = figures.feasible_counts(cohorts, report).axes[0].containers
    for group, phase in zip(bars, ("selection", "evaluation"), strict=True):
        assert [p.get_height() for p in group] == [
            sum(set(d[phase].values()) == {"feasible"} for d in c["designs"].values()) for c in cohorts.values()]
    for ax, seg in zip(figures.energy_segments(payload).axes, payload["segments"], strict=True):
        windows = [e for e in seg["events"] if e["kind"] == "window"]
        assert len(windows) == len(ax.patches)
        for patch, event in zip(ax.patches, windows, strict=True):
            assert math.isclose(patch.get_x(), event["start_h"])
            assert math.isclose(patch.get_width(), event["end_h"] - event["start_h"])
        for line in ax.lines:
            family = line.get_gid()
            if family in ("selected", "baseline"):
                points = list(zip(line.get_xdata(), line.get_ydata()))
                for event in seg["events"]:
                    value = event[family + "_upper_kwh"]
                    if value is not None:
                        assert (event["end_h"], value) in points
    axes = figures.segment_ratings(cohorts).axes
    for i, phase in enumerate(("selection", "evaluation")):
        for j, cohort in enumerate(cohorts.values()):
            ax = axes[i * len(cohorts) + j]
            levels = sorted({v for c in cohorts.values() for rows in c["required_ratings_kw"].values() for r in rows for v in r.values()})
            observed = {(levels[a.get_position()[0]], levels[a.get_position()[1]]): int(a.get_text()) for a in ax.texts}
            assert observed == Counter((r["PORT"], r["WAREHOUSE"]) for r in cohort["required_ratings_kw"][phase])
    spec_report = load("spec_check.json")
    grid = figures.specification_grid(spec_report).axes[0]
    assert len(grid.patches) == 24
    for row, artist in zip(spec_report["rows"], grid.texts, strict=True):
        expected = {"守住": "Held", "未守住": "Failed", "未定": "Undetermined",
                    "没做": "Not run", "不可评": "Not evaluable"}[row["verdict"]]
        assert artist.get_text().splitlines() == [expected, *(figures.ratings(n) for n in row.get("choices", {}).get("new", {}))]
    figures.plt.close("all")


if __name__ == "__main__":
    test_paper_tables_reference_the_published_values()
    test_print_fragments_and_raster_resolution()
    check_figure_artists()
    print("Six plotted figures and five table pairs match the published JSON.")
