"""Check both language versions of the published external fleet results."""
import json
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
            for fmt in ("{}", "{:,.2f}", "{:,.3f}"):
                tokens.update(re.findall(numeric, fmt.format(value)))
    collect(payload)
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
