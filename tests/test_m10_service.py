import gzip
import json

import pytest

from um_charging import m10_service as study


def test_zero_warehouse_each_design_has_the_registered_strength_of_proof(monkeypatch):
    inputs = study.m10_inputs.load_inputs()
    period, = [p for p in inputs.periods if study.MISSING_DUTY in p.keys]
    fixed = inputs.registered & period.keys
    requested = [list(k) for k in sorted(fixed)]
    monkeypatch.setattr(study, "_m9_proof", lambda archive, p, keys: {"request": {"duties": requested}})
    grid = study.ss.design_grid(study.ss.COARSE_KW)
    proofs = study.no_warehouse_proofs(inputs, grid, None)
    excluded = proofs["exclusions"]
    assert set(excluded) == {d.label for d in grid if d.warehouse_kw == 0}
    for design in grid:
        if design.warehouse_kw == 0:
            row = excluded[design.label]
            assert row["fixed"] == requested
            assert row["caps_kw"] == list(design.caps)
            assert row["hardware"] == design.hardware()
            if design.port_plugs <= 1:
                assert row["method"] == "m9_fixed_R_infeasible_superset"
            else:
                assert row["method"] == "all_single_truck_segments_infeasible"
    relaxation = proofs["single_truck_relaxation"]
    assert (relaxation["date"], relaxation["vehicle_id"]) == study.MISSING_DUTY
    assert len(relaxation["segments"]) == 5
    assert all(not part["single_truck"]["feasible"] for part in relaxation["segments"])
    monkeypatch.setattr(study.hi, "diagnose_fixed",
                        lambda *args: {"single_truck_relaxation_feasible": True})
    fallback = study.no_warehouse_proofs(inputs, grid, None)["exclusions"]
    assert set(fallback) == {d.label for d in grid if d.warehouse_kw == 0 and d.port_plugs <= 1}


def test_archived_fixed_R_certificate_requires_exact_inputs_duties_and_solver_status(tmp_path, monkeypatch):
    inputs = study.m10_inputs.load_inputs()
    p, = [p for p in inputs.periods if study.MISSING_DUTY in p.keys]
    fixed = inputs.registered & p.keys
    request = dict(sample="fixed_R", week=study._week(p), design="p1-50-w0", caps=[50, 0],
                   phase="dispatch", day=None, duties=[list(k) for k in sorted(fixed)], locked=[])
    path = tmp_path / "0001.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as file:
        json.dump({"stats": {"status": "infeasible", "status_code": 2}, "audit": None}, file)
    ledger = tmp_path / "solves.jsonl"
    ledger.write_text(json.dumps(dict(request=request, file=path.name, sha256=study.digest(path),
                                      status="infeasible", audited=False)) + "\n", encoding="utf-8")
    hashes = {p.name: h for p, h in study.hi.INPUT_HASHES.items()}
    fields = dict(source_commit="test-source", input_hashes=hashes)
    (tmp_path / "manifest.json").write_text(json.dumps(fields), encoding="utf-8")
    published = tmp_path / "publication.json"
    published.write_text(json.dumps(dict(source_commit="test-source", inputs_sha256=hashes,
                                         ledger_sha256=study.digest(ledger))), encoding="utf-8")
    monkeypatch.setattr(study.m10_inputs, "M9_REGISTRATION", published)
    assert study._m9_proof(tmp_path, p, fixed)["certificate_sha256"] == study.digest(path)
    with pytest.raises(ValueError, match="exact M9"):
        study._m9_proof(tmp_path, p, fixed - {study.MISSING_DUTY})
    path.write_bytes(b"damaged")
    with pytest.raises(ValueError, match="infeasibility record"):
        study._m9_proof(tmp_path, p, fixed)


def test_failed_fixed_set_does_not_assign_every_omission_to_one_truck():
    inputs = study.m10_inputs.load_inputs()
    period, = [p for p in inputs.periods if study.MISSING_DUTY in p.keys]
    design = study.ss.Design(2, 100, 0)
    fixed = inputs.registered & period.keys
    witness = {("2021-11-22", "5")}
    row = study._weekly(period, fixed, "shortfall", witness, "fixed", "witness",
                        "rated_fixed_R", design, physical=True)
    proofs = {"single_truck_relaxation": {"single_truck_relaxation_feasible": False}}
    summary, matrix = study._summarize(design, [row], proofs)
    statuses = {(r["date"], r["vehicle_id"]): (r["status"], r["evidence_id"]) for r in matrix}
    assert not summary["same_service"]
    assert statuses[study.MISSING_DUTY] == ("not_completed", "single_truck_relaxation")
    assert statuses[("2021-11-22", "5")] == ("completed", "witness")
    assert all(status == ("unresolved", "fixed") for key, status in statuses.items()
               if key not in witness | {study.MISSING_DUTY})
