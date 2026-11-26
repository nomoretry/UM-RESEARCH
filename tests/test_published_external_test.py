"""Check both language versions of the published external fleet results."""
import json
import math
from pathlib import Path
import re


CASE = Path(__file__).resolve().parents[1] / "studies" / "fleet-service"


def number(value):
    return "—" if value is None else f"{value:,.2f}"


def span(bounds):
    return "—" if not bounds else "–".join(number(v) for v in bounds)


def pair(values):
    return " / ".join("—" if x is None else str(x) for x in values)


def cells(text):
    return [line.strip("|").strip().split(" | ") for line in text.splitlines()
            if line.startswith("| ") and not line.startswith("| ---")]


def test_external_report_quantities_match_across_languages():
    text = (CASE / "external_test.md").read_text(encoding="utf-8")
    zh, en = text.split("# External test of sub-fleet charging facilities")
    numeric = r"[0-9]+(?:[.,][0-9]+)*"
    assert re.findall(numeric, zh) == re.findall(numeric, en)
    payload = json.loads((CASE / "external_test.json").read_bytes())
    # Check every rendered number against the numeric leaves or labels in the machine file.
    tokens = set()
    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                collect(key)
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, str):
            tokens.update(re.findall(numeric, value))
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            for fmt in ("{}", "{:,}", "{:,.2f}", "{:,.3f}"):
                tokens.update(re.findall(numeric, fmt.format(value)))
    collect(payload)
    collect(json.loads((CASE / "spec_check.json").read_bytes()))
    assert set(re.findall(numeric, zh)) <= tokens


def test_external_report_cells_match_cohort_evidence():
    doc = json.loads((CASE / "external_test.json").read_bytes())
    text = (CASE / "external_test.md").read_text(encoding="utf-8")
    zh, en = text.split("# External test of sub-fleet charging facilities")
    for lang in (zh, en):
        rows = cells(lang)
        for cid, cohort in doc["cohorts"].items():
            secondary = cohort["secondary"]
            selected = cohort["choices"].get("new", {})
            feasible = [cohort["selection_service"]["feasible"] if cohort["selection_service"] else None,
                        secondary["evaluation_service"]["feasible"] if secondary else None]
            primary = [cid, pair(cohort["complete_days"]), pair(cohort["registered_days"]), pair(feasible),
                       ", ".join(selected) or "—", " / ".join(span(v) for v in selected.values()) or "—"]
            verdict = cohort["primary"] if lang == zh else {
                "未守住": "Failed", "守住": "Held", "未定": "Undetermined", "不可评": "Not evaluable"
            }[cohort["primary"]]
            assert any(r[:-2] == primary and r[-2] == verdict for r in rows)
            if secondary is None:
                continue
            existing = cohort["choices"]["existing"]
            ratings = secondary["min_test_kw"]
            assert any(row[:3] == [cid, ", ".join(existing), " / ".join(span(v) for v in existing.values())]
                       and row[4:6] == [str(secondary["all_service"]["feasible"]),
                                         pair([ratings["PORT"], ratings["WAREHOUSE"]])] for row in rows)
            for phase, counts in secondary["site_classes"].items():
                phase_name = {"selection": "选型", "evaluation": "检验"}[phase] if lang == zh else phase.title()
                assert [cid, phase_name, *(str(counts.get(k, 0)) for k in
                                           ("port_only", "warehouse_only", "both", "neither"))] in rows
            strict = secondary["strict"]
            added, removed = strict["added_dates"], strict["removed_dates"]
            change_counts = [len(v) if v is not None else None for v in (added, removed)]
            assert any(row[:4] == [cid, str(strict["registered_days"]), pair(change_counts),
                                   ", ".join(strict["choices"]["new"])] for row in rows)
            for failure in secondary["failures"]:
                rated = secondary["training_max_kw"][failure["design"]]
                required = failure.get("required_kw", {})
                deficit = failure["deficit_kwh"]
                metrics = ["—" if deficit is None else f"{deficit:,.3f}",
                           pair([rated["PORT"], rated["WAREHOUSE"]]),
                           pair([required.get("PORT"), required.get("WAREHOUSE")])]
                assert any(r[:3] == [cid, failure["design"], failure["week"]] and r[5:8] == metrics for r in rows)
                expected = {
                    "single_truck_terminal_energy": ("段末电量", "Terminal energy"),
                    "single_truck_leg_boundary": ("行程储备", "Post-trip reserve"),
                }[failure["cause"]][lang == en]
                assert any(r[:3] == [cid, failure["design"], failure["week"]] and
                           r[-2:] == [expected, f"{failure['solo_high_kwh']:.3f}"] for r in rows)
            for label, bills in secondary["evaluation_bills"].items():
                assert [cid, label, span(bills["new"]), span(bills["existing"])] in rows
            for comparison in secondary["comparisons"]:
                assert any(r[0] == cid and r[3:6] == [comparison["design"] or "—", span(comparison["bill"]),
                                                      span(comparison["premium"])] for r in rows)
            for window in secondary["nested"]:
                for label in window["choices"]:
                    counts = window["new_demand"][label]
                    assert any(r[:4] == [cid, str(window["k"]), str(window["end"]), label] and
                               r[-2:] == [pair([counts["new_proven"], counts["denominator"]]), str(counts["unknown"])]
                               for r in rows)
        for digest in doc["registration"]["hashes"].values():
            assert digest in lang
        assert doc["registration"]["manifest_sha256"] in lang


def test_rated_designs_posthoc_and_complete_days():
    doc = json.loads((CASE / "external_test.json").read_bytes())
    cohorts = json.loads((CASE / "external_designs.json").read_bytes())["cohorts"]
    details = doc["report_details"]
    reports = (CASE / "external_test.md").read_text(encoding="utf-8").split(
        "# External test of sub-fleet charging facilities")
    for label, cohort in cohorts.items():
        designs = cohort["designs"]
        assert len(designs) == doc["model"]["hardware_count"]
        for design in designs.values():
            assert [len(design[p]) for p in ("selection", "evaluation")] == doc["model"]["calendar_weeks"]
            selection_ok = all(s == "feasible" for s in design["selection"].values())
            assert selection_ok == bool(design["selection_bill"])
            if selection_ok:
                assert set(design["selection_bill"]) == {"new", "existing"}
        ranked = sorted((d["selection_bill"]["new"], name) for name, d in designs.items() if d["selection_bill"])
        survivors = {name for name, d in designs.items() if all(s == "feasible" for s in d["evaluation"].values())}
        rank, bill, name = next((i, b, n) for i, (b, n) in enumerate(ranked, 1) if n in survivors)
        p = details["posthoc"][label]
        assert (rank, bill, name, rank - 1) == (p["rank"], p["bill"], p["design"], p["cheaper_failed"])
        assert ranked[0] == (p["selected_bill"], cohort["selected"])
        assert all(b[1] < bill[0] for b, _ in ranked[:rank - 1])
        assert all(b[0] > bill[1] for b, _ in ranked[rank:])
        lo, hi = p["selected_bill"]
        assert p["premium_eur"] == [bill[0] - hi, bill[1] - lo]
        assert p["premium_percent"] == [100 * p["premium_eur"][0] / hi, 100 * p["premium_eur"][1] / lo]
        for report in reports:
            assert [label, name, str(rank), span(bill), span(p["premium_eur"]),
                    "–".join(f"{n:.3f}" for n in p["premium_percent"]), str(rank - 1)] in cells(report)
        if label in doc["cohorts"]:
            public = doc["cohorts"][label]
            assert len(ranked) == public["selection_service"]["feasible"]
            assert survivors == set(public["secondary"]["evaluation_feasible"])
    weekly = details["weekly_complete_days"]
    for label, weeks in weekly.items():
        counts = list(weeks.values())
        expected = cohorts[label] if label in cohorts else doc["cohorts"][label]
        assert [sum(counts[:12]), sum(counts[12:])] == expected["complete_days"]
    for report in reports:
        rows = cells(report)
        for week in weekly["1-5"]:
            assert [week, *(str(d[week]) for d in weekly.values())] in rows
        for seal in details["timeline"]["seals"]:
            assert [seal["cohort"], str(seal["stage"]), seal["timestamp"]] in rows


def test_failure_event_bounds_from_trip_energy_and_charging_windows():
    payload = json.loads((CASE / "external_segments.json").read_bytes())
    doc = json.loads((CASE / "external_test.json").read_bytes())
    assert [s["label"] for s in payload["segments"]] == ["Reference", "A", "B", "C"]
    for segment in payload["segments"]:
        assert set(segment) == {"label", "cohort", "dates", "selected", "baseline", "constraint",
                                "upper_kwh", "deficit_kwh", "events"}
        for name in ("selected", "baseline"):
            port, warehouse = re.fullmatch(r"p1-(\d+)-w(\d+)", segment[name]).groups()
            ratings = {"PORT": int(port), "WAREHOUSE": int(warehouse)}
            upper = payload["initial_kwh"]
            stopped = False
            previous_end = 0.0
            for event in segment["events"]:
                assert 0 <= previous_end <= event["start_h"] + 1e-8
                assert event["start_h"] <= event["end_h"]
                previous_end = event["end_h"]
                value = event[f"{name}_upper_kwh"]
                if stopped:
                    assert value is None
                    continue
                duration = event["end_h"] - event["start_h"]
                change = (duration * ratings[event["site"]] * payload["efficiency"]
                          if event["kind"] == "window" else -event["trip_kwh"])
                upper = min(payload["capacity_kwh"], upper + change)
                assert math.isclose(value, upper, abs_tol=1e-7)
                stopped = upper < payload["reserve_kwh"] - 1e-8
            if name == "baseline":
                assert not stopped and upper >= payload["initial_kwh"] - 1e-8
            else:
                assert math.isclose(upper, segment["upper_kwh"], abs_tol=1e-7)
                limit = payload["reserve_kwh"] if stopped else payload["initial_kwh"]
                assert math.isclose(limit - upper, segment["deficit_kwh"], abs_tol=1e-7)
        if segment["label"] == "Reference":
            assert math.isclose(segment["deficit_kwh"], doc["original_posthoc_reference"]["gap_kwh"])
        else:
            failure, = (r for r in doc["cohorts"][segment["cohort"]]["secondary"]["failures"]
                        if r["dates"] == segment["dates"])
            assert (failure["cause"], failure["solo_high_kwh"]) == (segment["constraint"], segment["upper_kwh"])
