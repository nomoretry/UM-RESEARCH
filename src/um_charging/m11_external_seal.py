"""Immutable stage artifacts and the external-cohort opening gate."""
import hashlib
import json
from pathlib import Path
import subprocess

from .m10_evidence import _encoded, _publish


FROZEN_SHA256 = "5bc8060e64be82a1493e4252e53b37fed97365023c905407a4df0d327c086161"
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


def authorize(cohort, registration, authorization=None):
    if cohort not in RANKS:
        raise ValueError("Unknown rank interval")
    if cohort == "1-5" and registration is None:
        return
    if not FROZEN_SHA256 or registration is None or registration.name != "PREREG_M11_EXTERNAL.md":
        raise PermissionError("External cohorts are sealed")
    if digest(registration.read_bytes()) != FROZEN_SHA256:
        raise PermissionError("External registration digest differs")
    root = committed(registration)
    if cohort != "1-5":
        if authorization is None or authorization.name != "OPENING_AUTHORIZATION.md":
            raise PermissionError("Committed opening authorization required")
        if committed(authorization) != root or FROZEN_SHA256 not in authorization.read_text(encoding="utf-8").split():
            raise PermissionError("Opening authorization does not bind this registration")


def execution_binding(registration, head, study):
    import re
    body = registration.read_text(encoding="utf-8")
    match = re.findall(r"^执行代码 P = ([a-f0-9]{40})$", body, flags=re.MULTILINE)
    parents = git(study,"rev-list","--parents","-n","1",head).decode().split()
    if len(match)!=1 or parents != [head,match[0]]:
        raise ValueError("Execution commit must be the registered direct child")
    path="src/um_charging/m11_external_seal.py"
    if git(study,"diff","--name-only",match[0],head).decode().splitlines()!=[path]:
        raise ValueError("Unexpected execution changes")
    before=git(study,"show",match[0]+":"+path)
    after=git(study,"show",head+":"+path)
    marker=b'FROZEN_SHA256' + b' = ""'
    if before.count(marker)!=1 or before.replace(marker,b'FROZEN_SHA256 = "'+FROZEN_SHA256.encode()+b'"')!=after:
        raise ValueError("Frozen commit must change only the digest line")


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
