"""Verify the publication copies as byte streams, independent of line endings."""
import hashlib
import json
from pathlib import Path
import re


CASE = Path(__file__).resolve().parents[1] / "studies" / "fleet-service"
PACKAGE = CASE / "preregistration"


def test_registration_digests_and_manifest():
    registration = json.loads((CASE / "external_test.json").read_bytes())["registration"]
    manifest = (PACKAGE / "prereg_manifest_v4.txt").read_bytes()
    assert hashlib.sha256(manifest).hexdigest() == registration["manifest_sha256"]
    local_entries = {}
    lines = manifest.decode("utf-8").splitlines()
    for line in lines:
        entry = re.fullmatch(r"([0-9a-f]{64})  (\S+)", line)
        if entry is None:
            continue
        digest, path = entry.groups()
        relative = path.removeprefix("runs/20261125_m11_external_open/")
        local = PACKAGE / relative
        if local.is_file():
            assert hashlib.sha256(local.read_bytes()).hexdigest() == digest
            local_entries[relative] = digest
    expected = registration["hashes"]
    assert set(local_entries) == set(expected) | {"REFREEZE_NOTE.md"}
    assert {name: local_entries[name] for name in expected} == expected
    gate = (PACKAGE / "GATE_OUTPUT.txt").read_text(encoding="utf-8")
    assert f"block {registration['block_height']}:" in gate
    assert registration["block_time_utc"] in gate and gate.rstrip().endswith("GATE: PASS")
    assert bytes.fromhex(registration["manifest_sha256"]) in (PACKAGE / "prereg_manifest_v4.txt.ots").read_bytes()
