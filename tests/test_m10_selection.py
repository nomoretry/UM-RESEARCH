import json

import pytest

from um_charging import m10_selection as selection
from um_charging import m10_tables as tables
from um_charging import site_sizing as ss


def test_frozen_exports_replay_all_columns_and_detect_a_changed_bill(tmp_path):
    from um_charging.m10_costs import ANNUAL_COLUMNS, OPERATING_COLUMNS

    hardware = ss.Design(1, 20, 20)
    services = {hardware: dict(status="complete", same_service=True)}
    matrix = [dict(design=hardware.label, date="2021-11-26", vehicle_id="1",
                   status="completed", evidence_id="weekly-proof")]
    costs = dict(operating_points=[dict.fromkeys(OPERATING_COLUMNS)],
                 annual_costs=[dict.fromkeys(ANNUAL_COLUMNS)], winners=[])
    args = (tmp_path, services, matrix, {}, costs, [], {"certificates": 0})
    expected = tables.products(*args)
    assert tables.products(*args, verify=True) == expected
    bills = tmp_path / "annual_costs.csv"
    bills.write_bytes(bills.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="annual_costs.csv"):
        tables.products(*args, verify=True)


def test_source_and_settings_bound_on_resume(tmp_path, monkeypatch):
    folder = tmp_path / "formal"
    monkeypatch.setattr(selection, "frozen_inputs", lambda *_: {"weeks": 12})
    monkeypatch.setattr(selection, "checked_output", lambda path, _: path)
    monkeypatch.setattr(ss, "source_state", lambda: dict(commit="clean-snapshot", dirty=False))
    expected = selection.source_manifest(None, None, folder, "output")
    assert selection.source_manifest(None, None, folder, "resume") == expected
    monkeypatch.setattr(ss, "source_state", lambda: dict(commit="later-snapshot", dirty=False))
    with pytest.raises(ValueError, match="original source commit"):
        selection.source_manifest(None, None, folder, "resume")
    assert selection.source_manifest(None, None, folder, "verify") == expected
    manifest = folder / "run_manifest.json"
    manifest.write_text(json.dumps({**expected, "workers": 2}), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen run"):
        selection.source_manifest(None, None, folder, "verify")


def test_entry_routes_read_only_archive_replay(monkeypatch, tmp_path):
    calls = []

    def replay(study, path, previous):
        calls.append((study, path, previous))
        return {"solver_calls": 0}

    monkeypatch.setattr(selection, "verify_legacy", replay)
    assert selection.main(["--legacy", "m8", "--verify", str(tmp_path)]) == 0
    assert calls == [("m8", tmp_path, None)]
