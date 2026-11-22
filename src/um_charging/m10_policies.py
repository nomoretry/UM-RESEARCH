"""Run or independently replay the registered twelve-week charging-policy comparison."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from time import monotonic

from . import m10_inputs, site_sizing as ss
from .__main__ import checked_output, digest
from .m10_policy_evidence import PolicyEvidence
from .m10_refine import compact
from .m10_refine_work import CLOSING_SECONDS, ROUND_SECONDS, WORKERS, estimate_work
from .m10_warehouse_price import screened_points, warehouse_prices
from .m10_weekly_union import exact_no_warehouse, weekly_union
from .site_sizing_screen import without_solver


def registration(folder):
    name = "PREREG_POLICIES.md"
    def git(*args):
        return subprocess.check_output(["git", "-C", str(folder), *args])
    root = Path(git("rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()
    rel = (folder / name).resolve().relative_to(root).as_posix()
    if subprocess.run(["git", "-C", str(folder), "rev-parse", "--quiet", "--verify", "HEAD"],
                      stdout=subprocess.DEVNULL, check=False).returncode:
        raise ValueError("Commit the policy preregistration before computing the comparison")
    commit = git("log", "-1", "--diff-filter=A", "--format=%H", "--", name).decode().strip()
    if not commit or git("show", f"{commit}:{rel}") != (folder / name).read_bytes():
        raise ValueError("Commit the policy preregistration before computing the comparison")
    return dict(commit=commit, sha256=digest(folder / name))


def elapsed(started):
    if started is None or started.tzinfo is None:
        raise ValueError("The round start requires its UTC offset")
    value = (datetime.now(timezone.utc) - started).total_seconds()
    if value < 0:
        raise ValueError("The round start lies in the future")
    return value


def planning_budget(coarse, refinement, started):
    """Time the actual warehouse requests against the sealed coarse timings, without optimization."""
    plan = [dict(p, service_weeks=[]) for p in screened_points(refinement)]
    source = coarse / "solves.csv"
    if digest(source) != json.loads((coarse / "seal.json").read_bytes())["products"][source.name]:
        raise ValueError("Historical timings differ from the sealed coarse ledger")
    with source.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result = estimate_work(plan, rows, elapsed_seconds=elapsed(started), workers=WORKERS)
    budget = result["budget"]
    return dict(scope="Warehouse 15 kW only. Rolling dispatch and the weekly design union are additional.",
                evaluated_utc=datetime.now(timezone.utc).isoformat(), round_started=started.isoformat(),
                source_ledger_sha256=digest(source), registered_warehouse_points=len(plan),
                retained_warehouse_points=sum(p["decision"] == "retain" for p in plan),
                projected_wall_seconds=result["combined"]["projected_wall_seconds"],
                weekly_requests=result["combined"]["unique_weekly_requests"],
                fits_warehouse=budget["all_required_seconds"] <= budget["available_seconds"],
                estimate=result)


def _write(path, data):
    """Replace only a completed derived file. Published native certificates are immutable."""
    with NamedTemporaryFile(dir=path.parent, delete=False) as fp:
        tmp = Path(fp.name)
    try:
        with tmp.open("w", encoding="utf-8", newline="") as stream:
            if path.suffix == ".csv":
                fields = list(dict.fromkeys(k for row in data for k in row))
                if not fields and path.name == "new_solves.csv":
                    fields = ["id", "week", "calendar_week", "phase", "design", "port_cap_kw",
                              "warehouse_cap_kw", "original_status", "status", "started_utc",
                              "seconds", "cpu_seconds", "objective_lower", "objective_upper",
                              "certificate_sha256"]
                if not fields and path.name == "warehouse_bills.csv":
                    fields = ["design", "port_cap_kw", "warehouse_cap_kw", "scenario", "connection_basis",
                              "known_lower", "known_upper", "missing_ratings_kw", "total_lower", "total_upper"]
                writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
                if fields:
                    writer.writeheader()
                for row in data:
                    writer.writerow({k: compact(v) if isinstance(v, (list, tuple, dict)) else v
                                     for k, v in row.items()})
            elif path.suffix == ".jsonl":
                for row in data:
                    stream.write(compact(row) + "\n")
            else:
                stream.write(compact(data) + "\n")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _statistics(rows):
    return dict(new_requests=len(rows), phase_counts=dict(Counter(r["phase"] for r in rows)),
                status_counts=dict(Counter(r["status"] for r in rows)),
                native_status_counts=dict(Counter(r["original_status"] for r in rows)),
                first_native_start_utc=min((r["started_utc"] for r in rows), default=None),
                solver_seconds=math.fsum(r["seconds"] for r in rows),
                worker_cpu_seconds=math.fsum(r["cpu_seconds"] for r in rows),
                longest_solve_seconds=max((r["seconds"] for r in rows), default=0.))


def _record_schedule(stream, table, row):
    """Rebuild the old prefix in order. Complete an interrupted last line before appending."""
    if table != "policy_schedules":
        raise ValueError(f"Unknown policy schedule table {table}")
    expected = (compact(row) + "\n").encode("utf-8")
    previous = stream.readline()
    if previous != expected:
        if previous.endswith(b"\n") or not expected.startswith(previous):
            raise ValueError("Archived policy schedule differs from the deterministic replay")
        stream.write(expected[len(previous):])
        stream.flush()


def _build(inputs, coarse, refinement, target, ledger, progress):
    from .m10_policy_grid import policy_grid

    products = {}
    def store(name, value):
        ledger.check()
        path = target / name
        _write(path, value)
        products[name] = _file_hash(path)

    def tables(collection):
        for name, rows in collection.items():
            ext = ".jsonl" if name == "policy_schedules" else ".csv"
            store(name + ext, rows)

    store("exact_no_warehouse.json", exact_no_warehouse(inputs))
    schedule_path = target / "policy_schedules.jsonl"
    with schedule_path.open("r+b" if schedule_path.exists() else "w+b") as journal:
        policy = policy_grid(inputs, ledger, progress=progress,
                             checkpoint=lambda name, row: _record_schedule(journal, name, row))
        if journal.read(1):
            raise ValueError("Archived policy schedule contains unexpected trailing weeks")
    del policy["policy_schedules"]
    products[schedule_path.name] = _file_hash(schedule_path)
    tables(policy)
    tables(weekly_union(inputs, coarse, ledger, progress=progress))
    tables(warehouse_prices(inputs, coarse, refinement, ledger, progress=progress))
    solves = sorted(ledger.new_records, key=lambda row: row["id"])
    store("new_solves.csv", solves)
    store("compute_statistics.json", _statistics(solves))
    store("replay.json", ledger.verify_all())
    audit = ledger.determinism(seed=20261122, count=20)
    store("determinism.json", audit)
    return products, dict(status="complete" if audit["all_match"] else "stopped_determinism",
                          new_solves=len(ledger.new_records), repeats=audit["sampled"], matched=audit["matched"])


def _session(folder, origin, started, new_round):
    session_file = folder / "rounds.json"
    sessions = (json.loads(session_file.read_bytes()) if session_file.exists()
                else [origin["round_start_utc"]])
    start = started.astimezone(timezone.utc).isoformat()
    if sessions[0] != origin["round_start_utc"]:
        raise ValueError("The initial formal round start differs from the archive origin")
    if new_round:
        checkpoint = json.loads((folder / "checkpoint.json").read_bytes())
        if (checkpoint["unresolved_weekly_groups"] > ss.fc.MAX_UNRESOLVED
                or datetime.fromisoformat(start) <= datetime.fromisoformat(sessions[-1])):
            raise ValueError("A fresh clock cannot waive a substantive stop or move backwards")
        sessions.append(start)
    if start != sessions[-1]:
        raise ValueError("Resume requires the recorded round start")
    if new_round or not session_file.exists():
        _write(session_file, sessions)
    return sessions


def run(coarse, refinement, folder, *, mode, started=None, new_round=False, prereg_folder=None):
    coarse, refinement, folder = (Path(p).resolve() for p in (coarse, refinement, folder))
    if any(folder.parent.is_relative_to(old.parent) or old.parent.is_relative_to(folder.parent)
           for old in (coarse, refinement)):
        raise ValueError("Use a separate policy run folder outside both source archives")
    prereg = registration(Path(prereg_folder).resolve() if prereg_folder is not None else folder.parent)
    inputs = m10_inputs.load_inputs()
    _check_input_bindings(coarse, refinement, inputs)
    binding = dict(registration=prereg, planning_sha256=inputs.source_sha256,
                   fixed_service=sorted([list(key) for key in inputs.registered]),
                   coarse_seal_sha256=digest(coarse / "seal.json"),
                   refinement_manifest_sha256=digest(refinement / "manifest.json"))
    verify = mode == "verify"
    if mode not in {"output", "resume", "verify"}:
        raise ValueError("Unknown policy archive mode")
    if new_round and mode != "resume":
        raise ValueError("A new clock requires explicit resumption of a prior checkpoint")
    state = ss.source_state()
    if verify:
        if (folder / "manifest.json").is_file():
            seal = json.loads((folder / "manifest.json").read_bytes())
            origin = json.loads((folder / "binding.json").read_bytes())
            if (seal["binding"] != binding or origin != seal["origin"]
                    or seal["rounds"] != json.loads((folder / "rounds.json").read_bytes())
                    or origin["binding"] != binding or any(_file_hash(folder / k) != v
                                                           for k, v in seal["products"].items())):
                raise ValueError("Policy archive binding or sealed products differ")
        else:
            raise ValueError("A completed policy archive is required for verification")
        deadline = (math.inf if started is None else monotonic() + ROUND_SECONDS - elapsed(started))
    else:
        if state["dirty"]:
            raise ValueError("Commit the policy source before the formal twelve-week run")
        deadline = monotonic() + ROUND_SECONDS - CLOSING_SECONDS - elapsed(started)
        if deadline <= monotonic():
            raise ss.fc.StudyLimit("The four-hour round reached the closing reserve")
        if mode == "output":
            checked_output(folder, ss.eb.ROOT)
            folder.mkdir()
            _write(folder / "binding.json", dict(binding=binding, source_commit=state["commit"],
                   round_start_utc=started.astimezone(timezone.utc).isoformat()))
        origin = json.loads((folder / "binding.json").read_bytes())
        if (origin["binding"] != binding or origin["source_commit"] != state["commit"]
                or (folder / "manifest.json").exists()):
            raise ValueError("Resume requires the same source, inputs and unsealed archive")
        sessions = _session(folder, origin, started, new_round)

    def progress(line):
        if verify:
            return
        stamp = datetime.now().astimezone().isoformat()
        with (folder.parent / "PROGRESS.md").open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"- {stamp} {line}\n")
        if monotonic() >= deadline:
            raise ss.fc.StudyLimit("The round reached its closing reserve")

    with PolicyEvidence(folder, inputs, coarse, deadline=deadline, verify=verify) as ledger:
        if verify:
            with without_solver(), TemporaryDirectory(prefix="um-policy-replay-") as work:
                products, result = _build(inputs, coarse, refinement, Path(work), ledger, progress)
            if products != seal["products"] or result != seal["result"]:
                raise ValueError("Independent policy reconstruction differs")
            ledger.check()
            return dict(status="verified", result=result, products=len(products))
        try:
            progress("开始 12 周运营方式、并集与 15 kW 核算")
            products, result = _build(inputs, coarse, refinement, folder, ledger, progress)
            ledger.check()
        except ss.fc.StudyLimit as exc:
            _write(folder / "new_solves.csv", sorted(ledger.new_records, key=lambda row: row["id"]))
            result = dict(status="stopped", reason=str(exc), statistics=_statistics(ledger.new_records),
                          unresolved_weekly_groups=len(ledger.unresolved))
            _write(folder / "checkpoint.json", result)
            return result
        _write(folder / "manifest.json", dict(binding=binding, origin=origin, rounds=sessions,
                                              products=products, result=result))
        return result


def _check_input_bindings(coarse, refinement, inputs):
    manifest = json.loads((coarse / "run_manifest.json").read_bytes())
    ref = json.loads((refinement / "manifest.json").read_bytes())
    if (manifest["inputs"]["planning"] != inputs.source_sha256
            or list(map(tuple, manifest["inputs"]["fixed_service"])) != sorted(inputs.registered)
            or manifest["timeout_interval_eur_2021"] != .10):
        raise ValueError("Planning inputs differ from the frozen service or interval rule")
    for path in (ss.eb.WEEKS.with_name("site_sizing.json"), ss.CONNECTION_INPUT, ss.NETWORK_INPUT, ss.COST_INPUT):
        if digest(path) != manifest["inputs"]["cost_sha256"][path.name]:
            raise ValueError(f"Cost input differs from sealed coarse registration: {path.name}")
    if digest(refinement / "frozen_facilities.csv") != ref["products"]["frozen_facilities.csv"]:
        raise ValueError("Frozen full-information facilities differ")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coarse", required=True, type=Path)
    parser.add_argument("--refinement", required=True, type=Path)
    parser.add_argument("--prereg-folder", type=Path,
                        help="Directory holding the original committed PREREG_POLICIES.md")
    action = parser.add_mutually_exclusive_group(required=True)
    for mode in ("output", "resume", "verify"):
        action.add_argument("--" + mode, type=Path)
    action.add_argument("--preflight", action="store_true")
    parser.add_argument("--new-round", action="store_true",
                        help="Start a separately authorized round from a timed checkpoint")
    parser.add_argument("--started", type=datetime.fromisoformat, help="Offset-aware round start")
    args = parser.parse_args(argv)
    if args.verify is None and args.started is None:
        parser.error("Computing or estimating a round requires --started")
    if args.new_round and args.resume is None:
        parser.error("--new-round requires --resume")
    if args.preflight:
        result = planning_budget(args.coarse, args.refinement, args.started)
    else:
        mode = next(m for m in ("output", "resume", "verify") if getattr(args, m) is not None)
        result = run(args.coarse, args.refinement, getattr(args, mode), mode=mode, started=args.started,
                     new_round=args.new_round, prereg_folder=args.prereg_folder)
    print(compact(result), flush=True)
    return 2 if result.get("status", "").startswith("stopped") else 0


if __name__ == "__main__":
    raise SystemExit(main())
