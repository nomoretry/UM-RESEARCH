import json
import os
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
