"""Run, resume, or replay the preregistered twelve-week coarse facility selection."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from . import m10_inputs, site_sizing as ss
from .__main__ import checked_output, digest
from .m10_continuation import compare_batch, materialize_parent, parent_identity, verify_parent_products
from .m10_tables import (SERVICE_COLUMNS, artifact, csv_bytes, json_bytes, products, solve_columns,
                         solve_statistics)


WORKERS = 8
WALL_SECONDS = 4 * 3600
CLOSE_SECONDS = 15 * 60
REPEAT_SEED = 20261122


def utc_now():
    return datetime.now(timezone.utc)


def read(path):
    return json.loads(path.read_bytes())


def verify_legacy(study, path, previous=None):
    """Use the archive owners' no-solve replay paths for the original M8/M9 studies."""
    from .site_sizing_screen import without_solver

    with without_solver():
        if study == "m8":
            from .site_sizing_known_peak import run
            with TemporaryDirectory(prefix="um-m8-replay-") as target:
                work = Path(target)
                run(path.parent.parent, work)
                archived = read(path / "manifest.json")["output_sha256"]
                hashes = read(work / "manifest.json")["output_sha256"]
                if hashes != archived or any(digest(path / name) != value for name, value in hashes.items()):
                    raise ValueError("M8 replay differs from archived products")
                checks = read(work / "backtest.json")
                return dict(archive="m8", hashes=hashes, coarse_points=checks["coarse_points"],
                            annual_checks=checks["checks"], solver_calls=0)
        if study == "m9":
            from .holdout import run
            summary = run(path, replay=True)
        elif study == "m9-repair" and previous is not None:
            from .holdout_repair import run
            summary = run(path, previous, replay=True)
        else:
            raise ValueError("Supply the registered M9 archive with --previous for repair replay")
        return dict(archive=study, reason=summary["stop_reason"], certificates=summary["solve_count"],
                    ledger_sha256=summary["ledger_sha256"], solver_calls=0)


def frozen_inputs(inputs, previous):
    return dict(planning=inputs.source_sha256, fixed_service=sorted(inputs.main_reference),
                cost_sha256={p.name: digest(p) for p in (ss.COST_INPUT, ss.NETWORK_INPUT,
                    ss.CONNECTION_INPUT, ss.eb.WEEKS.with_name("site_sizing.json"))},
                previous_sha256={name: digest(previous / name)
                                 for name in ("solves.jsonl", "summary.json", "manifest.json")})


def source_manifest(inputs, previous, output, mode, *, parent=None):
    source = ss.source_state()
    if mode != "verify" and source["dirty"]:
        raise ValueError("Commit the research source before starting or resuming")
    binding = json.loads(json_bytes(frozen_inputs(inputs, previous)))
    settings = dict(workers=WORKERS, wall_seconds=WALL_SECONDS,
                    reserve_seconds=CLOSE_SECONDS, repeat_seed=REPEAT_SEED)
    name = output / "run_manifest.json"
    if mode == "output":
        if parent is not None and (output.parent.is_relative_to(parent.parent)
                                   or parent.parent.is_relative_to(output.parent)):
            raise ValueError("The continuation and its parent must use separate directories")
        checked_output(output, ss.eb.ROOT)
        manifest = dict(source_commit=source["commit"], inputs=binding, **settings,
                        first_started_utc=utc_now().isoformat())
        if parent is not None:
            manifest.update(parent_checkpoint=parent_identity(parent), timeout_interval_eur_2021=0.10)
            preflight_file = output.parent / "preflight.json"
            forecast = read(preflight_file)
            if (forecast["source_checkpoint_sha256"] != manifest["parent_checkpoint"]["checkpoint.json"]
                    or forecast["source_ledger_sha256"] != digest(parent / "solves.csv")
                    or forecast["budget_seconds"] != WALL_SECONDS or forecast["admit"] is not True
                    or not 0 < forecast["projected_wall_seconds"] <= WALL_SECONDS):
                raise ValueError("Preflight failed the registered four-hour admission gate")
            manifest["preflight_sha256"] = digest(preflight_file)
        # A visible run directory always contains its identity and original clock.
        with TemporaryDirectory(prefix="um-selection-start-", dir=output.parent) as temp:
            ready = Path(temp) / "prepared"
            ready.mkdir()
            artifact(ready / name.name, json_bytes(manifest))
            if parent is not None:
                artifact(ready / "preflight.json", preflight_file.read_bytes())
            ready.rename(output)
    else:
        manifest = read(name)
        if manifest["inputs"] != binding or any(manifest[k] != v for k, v in settings.items()):
            raise ValueError("Input or parent certificate archive differs from the frozen run")
        if mode == "resume" and manifest["source_commit"] != source["commit"]:
            raise ValueError("Resume requires the original source commit")
        if parent is not None and manifest.get("parent_checkpoint") != parent_identity(parent):
            raise ValueError("Cannot switch the parent of a continuation")
        if "parent_checkpoint" in manifest and manifest.get("timeout_interval_eur_2021") != 0.10:
            raise ValueError("Continuation timeout interval policy differs")
        if "parent_checkpoint" in manifest and digest(output / "preflight.json") != manifest["preflight_sha256"]:
            raise ValueError("Registered preflight differs")
    return manifest


def run(output, previous, *, mode="output", new_round=False, from_checkpoint=None):
    from .m10_costs import OPERATING_COLUMNS, cost_results
    from .m10_evidence import M10Evidence
    from .m10_service import service_grid
    from .site_sizing_screen import without_solver
    from contextlib import nullcontext

    verify = mode == "verify"
    output = output.resolve()
    inputs = m10_inputs.load_inputs()
    if from_checkpoint is not None:
        from_checkpoint = from_checkpoint.resolve()
        if mode != "resume" or (not output.exists() and not new_round):
            raise ValueError("Import a checkpoint with --resume and an explicit new round")
    create = mode == "output" or (from_checkpoint is not None and not output.exists())
    manifest = source_manifest(inputs, previous, output, "output" if create else mode, parent=from_checkpoint)
    if mode == "resume" and (output / "seal.json").exists():
        return run(output, previous, mode="verify")
    opened = utc_now()
    clock_file = output / "sessions.json"
    sessions = read(clock_file) if clock_file.exists() else []
    if not sessions and verify:
        raise ValueError("Missing run session clock")
    if not sessions or (new_round and not create and "parent_checkpoint" not in manifest):
        sessions.append(dict(started_utc=manifest["first_started_utc"] if not sessions else opened.isoformat()))
        artifact(clock_file, json_bytes(sessions))
    start = datetime.fromisoformat(sessions[-1]["started_utc"])
    hard_end = start + timedelta(seconds=WALL_SECONDS)
    cutoff = math.inf if verify else monotonic() + (hard_end - opened).total_seconds() - CLOSE_SECONDS
    parent = None
    if "parent_checkpoint" in manifest:
        parent = output / "inherited"
        if from_checkpoint is not None:
            materialize_parent(from_checkpoint, parent, manifest["parent_checkpoint"], manifest["inputs"])
        verify_parent_products(parent, manifest["parent_checkpoint"], manifest["inputs"])

    def progress(message):
        if not verify:
            with (output.parent / "PROGRESS.md").open("a", encoding="utf-8") as file:
                file.write(f"- {utc_now().astimezone().isoformat()} {message}\n")
            print(message, flush=True)

    def save(name, value):
        artifact(output / name, json_bytes(value), verify=verify)

    def batch_checkpoint(design, weekly):
        batches = output / "operating_batches"
        if parent is not None:
            prior = parent / "operating_batches" / (design.label + ".csv")
            if prior.exists():
                compare_batch(prior, weekly)
        if not verify:
            batches.mkdir(exist_ok=True)
        artifact(batches / (design.label + ".csv"), csv_bytes(OPERATING_COLUMNS, weekly), verify=verify)

    stopped = (read(output / "checkpoint.json") if verify and not (output / "seal.json").exists() else None)
    progress(f"正式{('开跑' if mode == 'output' else '续算')}，源码 {manifest['source_commit']}，"
             f"{len(inputs.periods)} 周、{len(inputs.main_reference)} 个登记车日、{WORKERS} 进程。")
    with (without_solver() if verify else nullcontext()), M10Evidence(
            output, inputs, workers=WORKERS, deadline=cutoff, verify=verify, parent_archive=parent) as evidence:
        if stopped:
            audit = evidence.verify_all()
            counts = solve_statistics(evidence.records)
            artifact(output / "solves.csv", csv_bytes(solve_columns(parent is not None), evidence.records), verify=True)
            if counts != stopped["solve_statistics"] or audit != stopped["audit"]:
                raise ValueError("Partial certificate archive differs from its checkpoint")
            for name, expected in stopped["files"].items():
                if digest(output / name) != expected:
                    raise ValueError(f"Checkpoint product differs: {name}")
            return dict(status="verified_checkpoint", reason=stopped["reason"], audit=audit)
        try:
            service, matrix, proofs = service_grid(inputs, evidence, m9_archive=previous, progress=progress)
            save("service_summary.json", {d.label: row for d, row in service.items()})
            save("service_proofs.json", proofs)
            artifact(output / "service_matrix.csv", csv_bytes(SERVICE_COLUMNS, matrix), verify=verify)
            if parent is not None:
                for name in ("service_summary.json", "service_proofs.json", "service_matrix.csv"):
                    if digest(output / name) != digest(parent / name):
                        raise ValueError(f"Continuation changed the inherited service results: {name}")
            progress(f"服务网格完成，35 套硬件，逐设计状态 {dict(Counter(r['status'] for r in service.values()))}。")
            costs = cost_results(inputs, service, evidence, progress=progress, checkpoint=batch_checkpoint)
            audit = evidence.verify_all()
            hashes = products(output, service, matrix, proofs, costs, evidence.records, audit, verify=verify)
            progress(f"全部正式证书和账单已回放，冻结 {len(hashes)} 项产品，证书 {len(evidence.records)} 份。")
            if verify:
                seal = read(output / "seal.json")
                save("determinism.json", evidence.determinism(seed=REPEAT_SEED, count=20))
                if (seal["products"] != hashes or seal["determinism_sha256"] != digest(output / "determinism.json")
                        or seal["report_sha256"] != digest(output / "DETERMINISM.md")):
                    raise ValueError("Archive seal differs")
                return dict(status="verified", audit=audit, product_count=len(hashes))
            checks = evidence.determinism(seed=REPEAT_SEED, count=20)
            save("determinism.json", checks)
            progress(f"新进程确定性抽查 {checks['requested']} 次，一致 {checks['matched']} 次。")
            details = ["# 新进程确定性复核", "",
                       f"固定抽样种子 {REPEAT_SEED}。共比较 {len(checks['comparisons'])} 次，"
                       f"状态、目标与排程摘要均相符 {checks['matched']} 次。", "",
                       "| 请求 | 状态一致 | 目标一致 | 排程摘要一致 |", "|---|---|---|---|"]
            for row in checks["comparisons"]:
                details.append(f"| {row['id']} | {row['status_equal']} | {row['objective_equal']} | {row['schedule_equal']} |")
            artifact(output / "DETERMINISM.md", ("\n".join(details) + "\n").encode())
            if utc_now() >= hard_end:
                raise ss.fc.StudyLimit("Formal four-hour limit reached before sealing")
            save("seal.json", dict(products=hashes, determinism_sha256=digest(output / "determinism.json"),
                                   report_sha256=digest(output / "DETERMINISM.md"), sealed_utc=utc_now().isoformat(),
                                   elapsed_seconds=(utc_now()-start).total_seconds()))
            progress("粗网格和确定性抽查已封存。")
            return dict(status="complete", audit=audit, product_count=len(hashes))
        except ss.fc.StudyLimit as exc:
            if verify:
                raise
            records = evidence.records
            audit = evidence.verify_all()
            artifact(output / "solves.csv", csv_bytes(solve_columns(parent is not None), records))
            names = ["solves.csv", "service_summary.json", "service_proofs.json", "service_matrix.csv"]
            names.extend(p.relative_to(output).as_posix() for p in (output / "operating_batches").glob("*.csv"))
            if (output / "product_hashes.json").is_file():
                names.extend(["product_hashes.json", *read(output / "product_hashes.json")])
            checkpoint = dict(reason=str(exc), stopped_utc=utc_now().isoformat(),
                              elapsed_seconds=(utc_now()-start).total_seconds(), audit=audit,
                              solve_statistics=solve_statistics(records),
                              files={n: digest(output/n) for n in names if (output/n).is_file()})
            save("checkpoint.json", checkpoint)
            progress(f"触发停止条件，已保存断点。{exc}；正式求解 {len(records)} 次。")
            return dict(status="stopped", **checkpoint)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    for mode in ("output", "resume", "verify"):
        group.add_argument(f"--{mode}", type=Path)
    parser.add_argument("--previous", type=Path, help="Original M9 registration archive")
    parser.add_argument("--legacy", choices=["m8", "m9", "m9-repair"], help="Study to replay with --verify")
    parser.add_argument("--new-round", action="store_true", help="Record a fresh four-hour budget on explicit resumption")
    parser.add_argument("--from-checkpoint", type=Path, help="Import the earlier checked archive under the M10 0.10 EUR policy")
    args = parser.parse_args(argv)
    if args.legacy:
        if args.verify is None or args.new_round or args.from_checkpoint is not None:
            parser.error("--legacy requires --verify")
        result = verify_legacy(args.legacy, args.verify.resolve(), args.previous)
    else:
        if args.new_round and args.resume is None:
            parser.error("--new-round requires --resume")
        mode = next(m for m in ("output", "resume", "verify") if getattr(args, m) is not None)
        target = getattr(args, mode).resolve()
        previous = args.previous or target.parent.parent / "20261121_holdout_weeks" / "formal"
        result = run(target, previous, mode=mode, new_round=args.new_round, from_checkpoint=args.from_checkpoint)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
    return 2 if result.get("status") == "stopped" else 0


if __name__ == "__main__":
    raise SystemExit(main())
