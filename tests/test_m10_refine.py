import csv
from datetime import datetime, timezone
import json

import pytest

from um_charging import m10_refine as refine
from um_charging import m10_refine_bounds as bounds


@pytest.mark.parametrize("lower", [None, 10.00000000001])
def test_invalid_fold_keeps_witness_and_blocks_screening(tmp_path, monkeypatch, lower):
    source, output = tmp_path / "coarse", tmp_path / "refine"
    source.mkdir()
    output.mkdir()
    for name in ("seal.json", "run_manifest.json"):
        (source / name).write_bytes(b"{}")
    registration = dict(started_at=datetime.now(timezone.utc).isoformat(), wall_seconds=14400,
                        reserve_seconds=900, coarse_seal_sha256=refine.digest(source / "seal.json"),
                        coarse_manifest_sha256=refine.digest(source / "run_manifest.json"))
    monkeypatch.setattr(refine, "replay_coarse", lambda *args, **kwargs: {"status": "verified", "audit": {"certificates": 1}})
    monkeypatch.setattr(refine.m10_inputs, "load_inputs", lambda: None)
    from contextlib import nullcontext
    monkeypatch.setattr(refine, "M10Evidence", lambda *args, **kwargs: nullcontext())

    class FailedFold:
        def __init__(self, *args):
            pass

        def backtest(self):
            yield dict(design="p1-20-w20", actual_eur_2025=10., annual_lower_eur_2025=lower,
                       passed=False, frozen_proof_ids=["proof"])
            pytest.fail("A failed fold must stop the run immediately")

    monkeypatch.setattr(bounds, "RefinementBounds", FailedFold)
    result = refine.evaluate(source, output, lambda _: None, registration)
    assert result == {"status": "stopped_backtest", "solver_calls": 0}
    report = refine.read(output / "backtest_summary.json")
    assert report["annual_comparisons"] == 1 and not report["passed"]
    assert report["first_failure"]["annual_lower_eur_2025"] == lower
    with (output / "backtest.csv").open(newline="", encoding="utf-8") as file:
        row, = csv.DictReader(file)
    assert json.loads(row["frozen_proof_ids"]) == ["proof"]
    assert not (output / "decision.json").exists()
