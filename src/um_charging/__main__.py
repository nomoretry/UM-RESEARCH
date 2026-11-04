"""Run a fixed-facility solve or the documented six-case suite into local-only Git."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

import numpy
import scipy

from .model import make_scenarios, solve, validate_input
from .validation import check_solution


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def checked_output(path, source):
    """Require a fresh directory below a separate ordinary Git repo with no remotes."""
    path = path.resolve()
    if path == source or source in path.parents or path.exists():
        raise ValueError("--output must be a new directory outside the source repository")
    ancestor = path.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    # Git emits UTF-8 paths on this Windows installation; text=True alone uses
    # cp936 and silently turns a real Chinese directory into a nonexistent one.
    run_root = Path(subprocess.check_output(["git", "-C", str(ancestor), "rev-parse", "--show-toplevel"], encoding="utf-8").strip()).resolve()
    if run_root == source or not (run_root / ".git").is_dir():
        raise ValueError("output must belong to an independent ordinary Git repository")
    if subprocess.check_output(["git", "-C", str(run_root), "remote"], encoding="utf-8").strip():
        raise ValueError("the local run repository must have no remotes")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--suite", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2]
    output = checked_output(args.output, source)
    config = json.loads(args.config.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)
    validate_input(config)
    cases = make_scenarios(config) if args.suite else {"single": config}
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], encoding="utf-8").strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], encoding="utf-8").strip())
    if dirty:
        raise ValueError("Commit the exact source before this canonical run; source repository is dirty")
    output.mkdir(parents=True)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "source_commit": commit,
        "source_dirty": dirty, "seed": None, "seed_note": "No random input generation or randomized scenarios",
        "config_sha256": digest(args.config),
        "source_sha256": {p.relative_to(source).as_posix(): digest(p) for p in sorted((source / "src" / "um_charging").glob("*.py"))},
        "environment": {"python": sys.version, "platform": platform.platform(), "numpy": numpy.__version__, "scipy": scipy.__version__},
        "solver": {"name": "HiGHS through scipy.optimize.milp", "version": None, "version_evidence": "Exact bundled HiGHS version is emitted in the captured solver banner", "time_limit_seconds": 60.0, "mip_rel_gap": 0.0},
        "command": [sys.executable, "-m", "um_charging", *sys.argv[1:]],
        "cost_scope": "Only weighted operating electricity cost; fixed sunk facilities; no annual claim when weight=1",
        "suite": args.suite,
    }
    write_json(output / "manifest.json", manifest)
    summaries = []
    failed_validation = False
    for name, data in cases.items():
        case_dir = output / name
        case_dir.mkdir()
        write_json(case_dir / "input.json", data)
        print(f"Solving {name}", flush=True)
        result = solve(data, display=True)
        validation = check_solution(data, result)
        write_json(case_dir / "result.json", result)
        write_json(case_dir / "validation.json", validation)
        summary = {"scenario": name, "input_sha256": digest(case_dir / "input.json"),
                   "status": result["status"], "has_solution": result["has_solution"],
                   "objective": result["objective"], "dual_bound": result["dual_bound"], "mip_gap": result["mip_gap"],
                   "validation_passed": validation["passed"], "validation_checks": validation.get("checks"),
                   "grid_energy_kwh": validation.get("grid_energy_kwh"), "site_peak_kw": validation.get("site_peak_kw")}
        summaries.append(summary)
        failed_validation |= (result["has_solution"] and validation["passed"] is not True) or result["status"] in {"unbounded", "solver_error"} or (result["status"] == "limit_reached" and not result["has_solution"])
        print(json.dumps(summary, allow_nan=False), flush=True)
    write_json(output / "suite_summary.json", summaries)
    return 1 if failed_validation else 0


if __name__ == "__main__":
    raise SystemExit(main())
