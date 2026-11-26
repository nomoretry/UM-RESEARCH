import json
import os
from collections import Counter
import csv
from pathlib import Path
from unittest.mock import patch

import pytest

from um_charging import m11_spec_check as check


CASE = Path(__file__).resolve().parents[1] / "studies/fleet-service"


def test_s0_rated_intervals_match_public_minimum():
    designs = json.loads((CASE / "external_designs.json").read_bytes())["cohorts"]["6-10"]["designs"]
    expected = json.loads((CASE / "external_test.json").read_bytes())["cohorts"]["6-10"]["choices"]
    for basis, published in expected.items():
        bounds = {k: v["selection_bill"][basis] for k, v in designs.items() if v["selection_bill"]}
        ceiling = min(hi for _, hi in bounds.values())
        assert {k: b for k, b in bounds.items() if b[0] <= ceiling + 1e-8} == published


def test_s0_native_selection_replay():
    archive = os.environ.get("UM_SPEC_SEALED_ARCHIVE")
    if not archive:
        pytest.skip("Offline native stage certificates required")
    expected = json.loads((CASE / "external_test.json").read_bytes())["cohorts"]["6-10"]["choices"]
    with patch.object(check.evidence, "_solve", side_effect=AssertionError("unexpected solve")):
        assert check.sealed_selection(Path(archive) / "formal/6-10") == expected


def test_published_spec_results_and_accounting():
    report = json.loads((CASE / "spec_check.json").read_bytes())
    old = json.loads((CASE / "external_test.json").read_bytes())
    rows = report["rows"]
    assert [(r["spec"], r["cohort"]) for r in rows] == [(s, c) for s in ("S0", *check.ORDER) for c in check.COHORTS]
    assert Counter({k:v for k,v in report["counts"].items() if v}) == Counter(r["verdict"] for r in rows)
    expected = {"守住":"Held", "未守住":"Failed", "未定":"Undetermined", "不可评":"Not evaluable", "没做":"Not run"}
    with (CASE / "paper/table4_specifications.csv").open(newline="", encoding="utf-8") as stream:
        table = list(csv.DictReader(stream))
    for r, printed in zip(rows, table, strict=True):
        assert [printed[k] for k in ("Spec", "Trucks", "Test")] == [r["spec"],r["cohort"],expected[r["verdict"]]]
        if r["verdict"] == "没做":
            assert printed["Least-cost build"] == printed["Feasible"] == ""
            continue
        assert printed["Least-cost build"] == ", ".join(r["choices"].get("new", {}))
        assert printed["Feasible"] == ("" if r["evaluation_feasible"] is None else str(r["evaluation_feasible"]))
        if r["spec"] == "S0":
            missed = r["registered"][1] - r["completed"]
            assert missed == sum(g["registered"] - g["completed_bounds"][0] for g in r["failed_weeks"])
            premium = old["report_details"]["posthoc"][r["cohort"]]["premium_eur"]
            assert r["eur_per_additional_duty"] == pytest.approx([p/(missed*52/7) for p in premium])
            if r["cohort"] in old["cohorts"]:
                original = old["cohorts"][r["cohort"]]
                assert r["choices"] == original["choices"] and r["verdict"] == original["primary"]
        else:
            for basis, selected in r["choices"].items():
                bills = {k:v[basis] for k,v in r["all_sizing_bills"].items()}
                upper = min((b[1] for b in bills.values() if b[1] is not None), default=float("inf"))
                assert {k:b for k,b in bills.items() if b[0] <= upper+1e-8} == selected
