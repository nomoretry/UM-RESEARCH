"""Verify an immutable dataset snapshot in a fresh, external local-run directory.

Git normalized 16 SimBench CSV files to LF before the original baseline commit.
The committed, checksum-verified ZIP retains their original CRLF bytes. This
entry point recovers those exact bytes, preserves the original manifests, and
runs the unchanged verifier. It never rebuilds data or modifies the checkout.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

DATASET_PATH = "reserach/truck optimaztion/Germany_Truck_Grid_Dataset_v1"
ZIP_PATH = "raw/simbench/1-MV-urban--0-sw.zip"
ZIP_PREFIX = "1-MV-urban--0-sw/"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def csv_rows(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file, delimiter=delimiter))


def check_manifests(dataset: Path) -> list[dict[str, object]]:
    """Check existing SHA-256 and byte counts without rewriting a manifest."""
    checks = []
    entries = json.loads((dataset / "source_manifest.json").read_text(encoding="utf-8"))
    entries += csv_rows(dataset / "file_manifest.csv")
    for entry in entries:
        path = dataset / entry["path"]
        if not path.resolve().is_relative_to(dataset.resolve()):
            raise ValueError("Manifest path escapes snapshot")
        data = path.read_bytes()
        actual = sha256(data)
        passed = actual == entry["sha256"] and len(data) == int(entry["bytes"])
        checks.append(dict(path=entry["path"], sha256=actual, bytes=len(data), passed=passed))
        if not passed:
            raise ValueError("Original manifest mismatch: " + entry["path"])
    return checks


def independent_summary(dataset: Path) -> dict[str, object]:
    """Recount stored tables; this does not claim a build_dataset.py rerun."""
    cycles = csv_rows(dataset / "processed/duty_cycle_scenarios.csv")
    for row in cycles:
        for key in ("scenario_eligible", "baseline_profile_eligible"):
            if row[key] not in ("True", "False"):
                raise ValueError("Unexpected boolean encoding in " + key)
    eligible = [r for r in cycles if r["scenario_eligible"] == "True"]
    selected = [r for r in cycles if r["baseline_profile_eligible"] == "True"]
    eligible_kwh = sum(float(r["energy_grid_kwh"]) for r in eligible)
    selected_kwh = sum(float(r["energy_grid_kwh"]) for r in selected)
    grid = csv_rows(dataset / "raw/simbench/csv/LoadProfile.csv", ";")
    complete = len(grid) == 366 * 96 and all(
        value is not None and value != "" for row in grid for value in row.values()
    )
    if not complete:
        raise ValueError("Independent raw LoadProfile completeness check failed")
    fleet = csv_rows(dataset / "raw/dt_cargo/fleet.csv")
    return dict(
        raw_vehicles=len(fleet), fleets=len({r["fleet_test_id"] for r in fleet}),
        raw_tracks=len(csv_rows(dataset / "raw/dt_cargo/tracks.csv")),
        observed_vehicle_days=len(csv_rows(dataset / "processed/vehicle_days.csv")),
        stored_cycles=len(cycles), quality_eligible_cycles=len(eligible),
        profile_cycles=len(selected), profile_vehicles=len({r["vehicle_id"] for r in selected}),
        quality_eligible_grid_energy_kwh=eligible_kwh,
        profile_grid_energy_kwh=selected_kwh,
        profile_energy_coverage=selected_kwh / eligible_kwh,
        raw_load_profile_rows=len(grid), raw_load_profile_complete=complete,
        scope="Recount and consistency validation of stored data; no data reconstruction, SOC optimization or power flow",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True, help="Exact dataset source commit")
    parser.add_argument("--output", required=True, type=Path, help="New directory inside an external Git repository without remotes")
    parser.add_argument("--python-executable", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    python_executable = args.python_executable.resolve()
    if not python_executable.is_file():
        raise ValueError("Python executable does not exist")
    child_environment = os.environ.copy()
    child_environment.pop("PYTHONOPTIMIZE", None)
    child_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(repo) or repo.is_relative_to(output):
        raise ValueError("Output must be a new directory outside the research checkout")
    if not output.parent.is_dir():
        raise ValueError("Output parent must be the existing local run repository")
    local_root = Path(git(output.parent, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if local_root == repo or repo.is_relative_to(local_root) or not output.is_relative_to(local_root) or git(local_root, "remote").strip():
        raise ValueError("Run storage must be a separate Git repository without remotes")
    if (local_root / ".git").is_file():
        raise ValueError("Run storage cannot be a linked worktree or submodule")
    commit = git(repo, "rev-parse", args.source_commit + "^{commit}").decode().strip()
    if commit != args.source_commit:
        raise ValueError("Use the full immutable source commit SHA")
    output.mkdir()
    dataset = output / "dataset"
    dataset.mkdir()
    save_json(output / "command.json", dict(argv=[sys.executable, *sys.argv], cwd=str(Path.cwd())))
    (output / "runner_source.py").write_bytes(Path(__file__).read_bytes())
    manifest = dict(
        run_id=output.name, started_utc=datetime.now(timezone.utc).isoformat(),
        dataset_source_commit=commit, dataset_source_path=DATASET_PATH,
        runner_source_commit=git(repo, "rev-parse", "HEAD").decode().strip(),
        checkout_status_porcelain=git(repo, "status", "--porcelain=v1").decode("utf-8"),
        runner_sha256=sha256(Path(__file__).read_bytes()),
        source_scope="Committed dataset subtree, plus original bytes from its versioned and verified ZIP; unrelated checkout changes excluded",
        seed=None, solver=None, objective=None, bound=None, gap=None,
    )
    save_json(output / "manifest.json", manifest)
    try:
        archive = git(repo, "archive", commit, DATASET_PATH)
        manifest["git_archive_sha256"] = sha256(archive)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            for member in stream.getmembers():
                if not member.isfile():
                    continue
                if not member.name.startswith(DATASET_PATH + "/"):
                    raise ValueError("Unexpected archive path")
                relative = member.name[len(DATASET_PATH) + 1:]
                target = dataset / relative
                if not target.resolve().is_relative_to(dataset.resolve()):
                    raise ValueError("Archive path escapes snapshot")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(stream.extractfile(member).read())
        source_items = json.loads((dataset / "source_manifest.json").read_text(encoding="utf-8"))
        zip_item = next(item for item in source_items if item["path"] == ZIP_PATH)
        archive_bytes = (dataset / ZIP_PATH).read_bytes()
        if sha256(archive_bytes) != zip_item["sha256"] or len(archive_bytes) != zip_item["bytes"]:
            raise ValueError("Original SimBench ZIP checksum mismatch")
        expected = {item["path"]: item["sha256"] for item in csv_rows(dataset / "file_manifest.csv")}
        restorations = []
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as stream:
            for member in stream.infolist():
                if member.is_dir():
                    continue
                if not member.filename.startswith(ZIP_PREFIX):
                    raise ValueError("Unexpected SimBench archive member")
                relative = "raw/simbench/csv/" + member.filename[len(ZIP_PREFIX):]
                target = dataset / relative
                if not target.resolve().is_relative_to(dataset.resolve()):
                    raise ValueError("ZIP member escapes snapshot")
                original = stream.read(member.filename)
                if sha256(original) != expected[relative]:
                    raise ValueError("ZIP member does not match original manifest: " + relative)
                restorations.append(dict(path=relative, archive_member=member.filename,
                    git_blob_sha256=sha256(target.read_bytes()), restored_sha256=sha256(original)))
                target.write_bytes(original)
        save_json(output / "byte_restoration.json", restorations)
        hash_checks = check_manifests(dataset)
        save_json(output / "hash_checks.json", hash_checks)
        inventory = [dict(path=p.relative_to(dataset).as_posix(), bytes=p.stat().st_size,
                          sha256=sha256(p.read_bytes())) for p in sorted(dataset.rglob("*")) if p.is_file()]
        save_json(output / "input_inventory.json", inventory)
        manifest["input_inventory_sha256"] = sha256((output / "input_inventory.json").read_bytes())
        environment_command = [str(python_executable), "-c", "import sys,platform,numpy,pandas,json; print(json.dumps(dict(python=sys.version,executable=sys.executable,platform=platform.platform(),numpy=numpy.__version__,pandas=pandas.__version__,optimize=sys.flags.optimize)))"]
        environment_result = subprocess.run(environment_command, capture_output=True, timeout=180, env=child_environment)
        (output / "environment_stdout.txt").write_bytes(environment_result.stdout)
        (output / "environment_stderr.txt").write_bytes(environment_result.stderr)
        environment_result.check_returncode()
        environment = json.loads(environment_result.stdout)
        manifest["environment"] = environment
        if environment["optimize"] != 0:
            raise ValueError("Dataset verifier must run with Python assertions enabled")
        manifest["pandas_declared_range_satisfied"] = environment["pandas"].split(".")[0] == "2"
        manifest["dependency_note"] = "Original requirement: pandas>=2.0,<3.0 and numpy>=1.24. A successful run outside this range is recorded as an environment deviation, not a supported-range reproduction."
        command = [str(python_executable), str(dataset / "verify_dataset.py")]
        save_json(output / "verifier_command.json", dict(argv=command, cwd=str(dataset), optimization=False))
        started = datetime.now(timezone.utc).isoformat()
        result = subprocess.run(command, cwd=dataset, capture_output=True, timeout=180, env=child_environment)
        (output / "stdout.txt").write_bytes(result.stdout)
        (output / "stderr.txt").write_bytes(result.stderr)
        manifest.update(verifier_started_utc=started, verifier_exit_code=result.returncode)
        if result.returncode != 0:
            save_json(output / "exit.json", dict(exit_code=result.returncode))
            return result.returncode
        verification = json.loads(result.stdout)
        summary = independent_summary(dataset)
        save_json(output / "validation.json", dict(original_verifier=verification,
            original_manifest_entries_checked=len(hash_checks), restored_csv_count=len(restorations),
            independent_summary=summary, solver=None, objective=None, bound=None, gap=None))
        save_json(output / "exit.json", dict(exit_code=0))
        print(json.dumps(dict(run_id=output.name, verified=True, **summary), ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        save_json(output / "failure.json", dict(type=type(error).__name__, message=str(error)))
        save_json(output / "exit.json", dict(exit_code=1))
        raise
    finally:
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save_json(output / "manifest.json", manifest)


if __name__ == "__main__":
    raise SystemExit(main())
