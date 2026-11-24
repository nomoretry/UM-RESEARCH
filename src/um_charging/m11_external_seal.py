"""Immutable stage artifacts and the external-cohort opening gate."""
import hashlib
import json
from pathlib import Path
import subprocess

from .m10_evidence import _encoded, _publish


FROZEN_SHA256 = ""
RANKS = {"1-5": (0, 5), "6-10": (5, 10), "11-15": (10, 15), "16+": (15, 20)}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], stderr=subprocess.DEVNULL)


def committed(path):
    path = path.resolve()
    root = Path(git(path.parent, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    rel = path.relative_to(root).as_posix()
    if git(root, "remote").strip() or git(root, "show", "HEAD:" + rel) != path.read_bytes():
        raise ValueError("Expected the identical committed file in the offline archive")
    return root


def authorize(cohort, registration):
    if cohort not in RANKS:
        raise ValueError("Unknown rank interval")
    if cohort == "1-5" and registration is None:
        return
    if not FROZEN_SHA256 or registration is None or registration.name != "PREREG_M11_EXTERNAL.md":
        raise PermissionError("External cohorts are sealed")
    if digest(registration.read_bytes()) != FROZEN_SHA256:
        raise PermissionError("External registration digest differs")
    committed(registration)


def put(folder, name, data):
    raw = _encoded(data) + b"\n"
    path = folder / name
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("Refusing to overwrite an existing stage artifact")
    else:
        _publish(path, raw)
    return digest(raw)


def seal(folder, cohort, stage, names, previous):
    files = {name: digest((folder / name).read_bytes()) for name in sorted(names)}
    return put(folder, "manifest.json", dict(cohort=cohort, stage=stage, previous=previous, files=files))


def check(folder, cohort, stage):
    path = folder / "manifest.json"
    committed(path)
    body = path.read_bytes()
    doc = json.loads(body)
    if doc["cohort"] != cohort or doc["stage"] != stage:
        raise ValueError("Wrong stage or cohort")
    for name, checksum in doc["files"].items():
        if Path(name).name != name or digest((folder / name).read_bytes()) != checksum:
            raise ValueError("Stage artifact differs from its manifest")
    return digest(body)
