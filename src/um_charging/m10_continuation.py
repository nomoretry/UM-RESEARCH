"""Bind a resumed twelve-week selection to the byte-exact earlier checkpoint."""
import csv
import hashlib
import io
import json

from .__main__ import digest
from .m10_tables import artifact


def parent_identity(folder):
    return {name: digest(folder / name) for name in ("run_manifest.json", "checkpoint.json", "sessions.json")}


def checkpoint_files(folder, identity, inputs):
    if parent_identity(folder) != identity:
        raise ValueError("The continuation parent differs from its frozen identity")
    manifest = json.loads((folder / "run_manifest.json").read_bytes())
    if manifest["inputs"] != inputs or "parent_checkpoint" in manifest:
        raise ValueError("Expected the original checkpoint for the same twelve-week inputs")
    checkpoint = json.loads((folder / "checkpoint.json").read_bytes())
    expected = dict(identity)
    for name, checksum in checkpoint["files"].items():
        target = (folder / name).resolve()
        if not target.is_relative_to(folder.resolve()) or target == folder.resolve():
            raise ValueError("Parent product outside its archive")
        expected[name] = checksum
    ledger = (folder / "solves.csv").read_bytes()
    if hashlib.sha256(ledger).hexdigest() != expected["solves.csv"]:
        raise ValueError("Wrong parent solve ledger")
    records = list(csv.DictReader(io.StringIO(ledger.decode("utf-8"))))
    for row in records:
        label = row["id"]
        if len(label) != 64 or any(c not in "0123456789abcdef" for c in label):
            raise ValueError("Invalid parent certificate identifier")
        name = f"certificates/{label}.json.gz"
        if name in expected:
            raise ValueError("Duplicate parent certificate")
        expected[name] = row["certificate_sha256"]
    if len(records) != checkpoint["audit"]["certificates"]:
        raise ValueError("Incomplete parent solve inventory")
    return expected


def materialize_parent(source, destination, identity, inputs):
    """Keep the original immutable and make verification independent of its location."""
    for name, checksum in checkpoint_files(source, identity, inputs).items():
        content = (source / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != checksum:
            raise ValueError(f"Parent product failed its frozen checksum: {name}")
        file = destination / name
        if file.exists():
            if digest(file) != checksum:
                raise ValueError(f"Changed inherited file: {name}")
            continue
        file.parent.mkdir(parents=True, exist_ok=True)
        artifact(file, content)


def verify_parent_products(folder, identity, inputs):
    # M10Evidence independently authenticates all compressed certificates when it indexes them.
    files = checkpoint_files(folder, identity, inputs)
    if {p.relative_to(folder).as_posix() for p in (folder / "operating_batches").glob("*.csv")} != {
            n for n in files if n.startswith("operating_batches/")}:
        raise ValueError("Unexpected or missing inherited operating batch")
    for name, checksum in files.items():
        if not name.startswith("certificates/") and digest(folder / name) != checksum:
            raise ValueError(f"Inherited product differs from the original: {name}")


def compare_batch(prior, weekly):
    """Allow the new interval classification, preserving the original evidence and meters."""
    with prior.open(encoding="utf-8", newline="") as stream:
        saved = list(csv.DictReader(stream))
    if len(saved) != len(weekly):
        raise ValueError(f"Continuation changed the size of {prior.name}")
    changes = 0
    for old, new in zip(saved, weekly, strict=True):
        for field in old:
            value = "" if new[field] is None else str(new[field])
            if value == old[field]:
                continue
            if field in {"status", "point_status"} and old[field] == "unresolved" and value == "bounded":
                changes += field == "status"
                continue
            raise ValueError(f"Continuation changed {prior.name} {old['week']} {field}")
    return changes
