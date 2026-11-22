import csv
from datetime import datetime, timedelta, timezone
import io
import json
import subprocess
from types import SimpleNamespace

import pytest

from um_charging import m10_policies as policies


def test_registration_precedes_computation_and_freezes_exact_bytes(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Study test",
                        "-c", "user.email=synthetic", *args], check=True, capture_output=True)
    git("init")
    file = tmp_path / "PREREG_POLICIES.md"
    file.write_bytes(b"synthetic policy\n")
    with pytest.raises(ValueError, match="Commit"):
        policies.registration(tmp_path)
    git("add", "--", file.name)
    git("commit", "-m", "Register synthetic methods")
    frozen = policies.registration(tmp_path)
    assert len(frozen["commit"]) == 40
    file.write_bytes(b"changed after registration\n")
    with pytest.raises(ValueError, match="preregistration"):
        policies.registration(tmp_path)


def test_resume_preserves_round_start_and_only_extends_clock_explicitly(tmp_path):
    start = datetime.now(timezone.utc) - timedelta(hours=5)
    origin = {"round_start_utc": start.isoformat()}
    assert policies._session(tmp_path, origin, start, False) == [start.isoformat()]
    later = start + timedelta(hours=5)
    with pytest.raises(ValueError, match="recorded round start"):
        policies._session(tmp_path, origin, later, False)
    policies._write(tmp_path / "checkpoint.json", {"unresolved_weekly_groups": 4})
    with pytest.raises(ValueError, match="substantive stop"):
        policies._session(tmp_path, origin, later, True)
    policies._write(tmp_path / "checkpoint.json", {"unresolved_weekly_groups": 0})
    assert policies._session(tmp_path, origin, later, True) == [start.isoformat(), later.isoformat()]


def test_week_journal_finishes_truncated_line_and_refuses_different_replay():
    rows = [{"week": "2021-01-04", "days": [{"completed": True}]},
            {"week": "2021-01-11", "days": [{"completed": False}]}]
    stream = io.BytesIO()
    for r in rows:
        policies._record_schedule(stream, "policy_schedules", r)
    expected = stream.getvalue()
    resumed = io.BytesIO(expected[:-8])
    for r in rows:
        policies._record_schedule(resumed, "policy_schedules", r)
    assert resumed.getvalue() == expected
    resumed.seek(0)
    with pytest.raises(ValueError, match="differs"):
        policies._record_schedule(resumed, "policy_schedules", rows[1])


def test_products_rebuild_identically_and_link_to_native_records(tmp_path, monkeypatch):
    from um_charging import m10_policy_grid as grid

    sample = dict(week="2021-01-04", days=[{"completed": True}], schedule=[])
    def simulate(inputs, ledger, *, progress, checkpoint):
        checkpoint("policy_schedules", sample)
        return dict(policy_schedules=[sample], policy_comparison=[
            dict(item="whole_invoice", total=12.5),
            dict(item="terminal_surplus_included", included=1.5)])
    monkeypatch.setattr(grid, "policy_grid", simulate)
    monkeypatch.setattr(policies, "exact_no_warehouse", lambda inputs: dict(deficit_kwh="3/2"))
    monkeypatch.setattr(policies, "weekly_union", lambda *a, **k: {"weekly_minima": []})
    monkeypatch.setattr(policies, "warehouse_prices", lambda *a, **k: {"warehouse_thresholds": []})
    ledger = SimpleNamespace(check=lambda: None, new_records=[], verify_all=lambda: dict(new_certificates=0),
        determinism=lambda seed, count: dict(all_match=True, sampled=0, matched=0, seed=seed, requested=count))
    args = (None, None, None, tmp_path, ledger, lambda line: None)
    products, result = policies._build(*args)
    assert policies._build(*args) == (products, result)
    assert json.loads((tmp_path / "policy_schedules.jsonl").read_bytes()) == sample
    with (tmp_path / "policy_comparison.csv").open(newline="", encoding="utf-8") as stream:
        bills = list(csv.DictReader(stream))
    assert bills[0]["total"] == "12.5" and bills[1]["total"] == "" and bills[1]["included"] == "1.5"
    assert result["new_solves"] == result["repeats"] == 0
