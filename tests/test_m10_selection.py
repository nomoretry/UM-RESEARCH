import json
import csv

import pytest

from um_charging import m10_selection as selection
from um_charging import m10_continuation as continuation
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


def test_continuation_binds_forecast_before_creating_output(tmp_path, monkeypatch):
    parent, output = tmp_path / "old" / "formal", tmp_path / "new" / "formal"
    parent.mkdir(parents=True)
    output.parent.mkdir()
    for name in ("run_manifest.json", "sessions.json", "checkpoint.json", "solves.csv"):
        (parent / name).write_bytes(b"frozen")
    monkeypatch.setattr(selection, "frozen_inputs", lambda *_: {"weeks": 12})
    monkeypatch.setattr(selection, "checked_output", lambda *_: None)
    monkeypatch.setattr(ss, "source_state", lambda: dict(commit="clean-snapshot", dirty=False))
    forecast = dict(source_checkpoint_sha256=selection.digest(parent / "checkpoint.json"),
                    source_ledger_sha256=selection.digest(parent / "solves.csv"), admit=True,
                    budget_seconds=selection.WALL_SECONDS, projected_wall_seconds=selection.WALL_SECONDS + 1)
    preflight = output.parent / "preflight.json"
    preflight.write_text(json.dumps(forecast))
    with pytest.raises(ValueError, match="admission gate"):
        selection.source_manifest(None, None, output, "output", parent=parent)
    assert not output.exists()
    preflight.write_text(json.dumps({**forecast, "projected_wall_seconds": selection.WALL_SECONDS}))
    manifest = selection.source_manifest(None, None, output, "output", parent=parent)
    assert selection.digest(output / "preflight.json") == manifest["preflight_sha256"]
    assert selection.source_manifest(None, None, output, "resume", parent=parent) == manifest
    with pytest.raises(ValueError, match="separate directories"):
        selection.source_manifest(None, None, parent, "output", parent=parent)


def test_parent_snapshot_is_independent_and_rejects_changed_products(tmp_path):
    parent, copied = tmp_path / "old", tmp_path / "new"
    parent.mkdir()
    (parent / "certificates").mkdir()
    (parent / "run_manifest.json").write_text(json.dumps({"inputs": {"weeks": 12}}))
    (parent / "sessions.json").write_text("[]")
    label = "a" * 64
    cert = parent / "certificates" / (label + ".json.gz")
    cert.write_bytes(b"frozen compressed evidence")
    (parent / "solves.csv").write_text("id,certificate_sha256\n" + label + "," + selection.digest(cert) + "\n")
    products = {"solves.csv": selection.digest(parent / "solves.csv")}
    (parent / "checkpoint.json").write_text(json.dumps({"audit": {"certificates": 1}, "files": products}))
    identity = continuation.parent_identity(parent)
    continuation.materialize_parent(parent, copied, identity, {"weeks": 12})
    continuation.verify_parent_products(copied, identity, {"weeks": 12})
    copy = copied / "certificates" / cert.name
    assert copy.read_bytes() == cert.read_bytes() and not copy.samefile(cert)
    copy.write_bytes(b"damaged")
    with pytest.raises(ValueError, match="Changed inherited file"):
        continuation.materialize_parent(parent, copied, identity, {"weeks": 12})
    assert cert.read_bytes() == b"frozen compressed evidence"
    (copied / "solves.csv").write_bytes(b"altered exported bound")
    with pytest.raises(ValueError, match="ledger"):
        continuation.verify_parent_products(copied, identity, {"weeks": 12})


def test_completed_week_can_change_admission_only(tmp_path):
    prior = tmp_path / "prior.csv"
    old = {"week": "2021-11-15", "status": "unresolved", "point_status": "unresolved",
           "evidence_id": "original", "purchase_upper": "238.25"}
    with prior.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=old)
        writer.writeheader()
        writer.writerow(old)
    current = {**old, "status": "bounded", "point_status": "bounded"}
    assert continuation.compare_batch(prior, [current]) == 1
    with pytest.raises(ValueError, match="purchase_upper"):
        continuation.compare_batch(prior, [{**current, "purchase_upper": 238.0}])
