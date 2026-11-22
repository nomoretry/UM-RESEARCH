"""Screen the registered fine grid and reproduce its budget decision from frozen evidence."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from . import m10_inputs, site_sizing as ss
from .__main__ import checked_output, digest
from .m10_evidence import M10Evidence
from .m10_selection import run as replay_coarse
from .m10_tables import artifact, json_bytes
from .site_sizing_screen import without_solver


def read(path):
    return json.loads(path.read_bytes())


def now():
    return datetime.now(timezone.utc)


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_rows(path, rows, fields=None):
    """Stream large audit tables; nested proof identifiers retain their JSON types."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = None
        if fields is not None:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
        for row in rows:
            if writer is None:
                writer = csv.DictWriter(stream, fieldnames=list(row), lineterminator="\n")
                writer.writeheader()
            writer.writerow({k: compact(v) if isinstance(v, (list, tuple, dict)) else v for k, v in row.items()})


def registered_files(folder):
    """Identify the commit that first registered this round; reject subsequent edits."""
    def git(*args):
        return subprocess.check_output(["git", "-C", str(folder), *args])

    root = Path(git("rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()
    prefix = folder.relative_to(root).as_posix()
    names = ("registration.json", "PREREG_ADDENDUM_3.md")
    commit = git("log", "-1", "--diff-filter=A", "--format=%H", "--", "registration.json").decode().strip()
    if not commit:
        raise ValueError("Commit the refinement registration before screening")
    for name in names:
        if git("show", f"{commit}:{prefix}/{name}") != (folder / name).read_bytes():
            raise ValueError(f"Refinement registration differs from its first commit: {name}")
    scope = "SETTLEMENT_SCOPE.md"
    scope_commit = git("log", "-1", "--diff-filter=A", "--format=%H", "--", scope).decode().strip()
    if not scope_commit or git("show", f"{scope_commit}:{prefix}/{scope}") != (folder / scope).read_bytes():
        raise ValueError("Commit the unchanged quote settlement scope before screening")
    return read(folder / names[0]), dict(commit=commit, settlement_scope_commit=scope_commit,
                                        sha256={k: digest(folder / k) for k in (*names, scope)})


def filenames(folder):
    return {p.name: digest(p) for p in sorted(folder.iterdir()) if p.is_file() and p.name != "manifest.json"}


def evaluate(coarse, target, progress, registration, expected=None):
    from .m10_refine_bounds import RefinementBounds
    from .m10_refine_freeze import TABLE_FIELDS, freeze_coarse
    from .m10_refine_work import estimate_work

    def save(name, value):
        artifact(target / name, json_bytes(value))

    start = datetime.fromisoformat(registration["started_at"])
    duration = registration["wall_seconds"]
    if (start.utcoffset() is None or duration != 14400 or registration["reserve_seconds"] != 900
            or digest(coarse / "seal.json") != registration["coarse_seal_sha256"]
            or digest(coarse / "run_manifest.json") != registration["coarse_manifest_sha256"]):
        raise ValueError("Budget or source archive differs from the registered round")

    def time_check():
        if expected is None and (now() - start).total_seconds() >= duration:
            raise ss.fc.StudyLimit("four_hour_limit")

    time_check()
    previous = coarse.parent.parent / "20261121_holdout_weeks" / "formal"
    replay = replay_coarse(coarse, previous, mode="verify")
    if replay["status"] != "verified":
        raise ValueError("A sealed coarse archive is required")
    save("coarse_replay.json", replay)
    progress(f"粗网格原档通过独立回放，{replay['audit']['certificates']} 份证书。")
    inputs = m10_inputs.load_inputs()
    with M10Evidence(coarse, inputs, verify=True, parent_archive=coarse / "inherited") as evidence:
        calculation = RefinementBounds(inputs, coarse, evidence)
        checked = 0
        smallest = None
        first_failure = None

        def folds():
            nonlocal checked, smallest, first_failure
            for row in calculation.backtest():
                checked += 1
                lower = row["annual_lower_eur_2025"]
                margin = row["actual_eur_2025"] - lower if lower is not None else None
                if margin is None or not math.isfinite(margin) or not row["passed"] or margin < 0:
                    first_failure = row
                if margin is not None and math.isfinite(margin):
                    smallest = margin if smallest is None else min(smallest, margin)
                yield row
                if first_failure is not None:
                    return
                if checked % 144 == 0:
                    time_check()

        write_rows(target / "backtest.csv", folds())
        save("backtest_summary.json", dict(annual_comparisons=checked, smallest_margin_eur_2025=smallest,
                                            passed=first_failure is None, first_failure=first_failure))
        if first_failure is not None:
            progress(f"下界回测触发停止，首个超界/无效比较为第 {checked} 项。")
            return dict(status="stopped_backtest", solver_calls=0)
        if checked != read(coarse / "selection.json")["refinement_estimate"]["leave_one_week_out"]["annual_comparisons"]:
            raise ValueError("Incomplete leave-one-week-out coverage")
        progress(f"逐周留一通过 {checked} 项，最小余量 {smallest:.12g} 欧元/年。")
        time_check()
        points = []
        with (target / "screen_evidence.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
            for point in calculation.iter_screen(check=time_check):
                time_check()
                stream.write(compact(point) + "\n")
                points.append(point)
        earlier_estimate = read(coarse / "selection.json")["refinement_estimate"]
        points_expected = earlier_estimate["new_operating_points"]
        keys = {(p["design"], tuple(p["caps_kw"])) for p in points}
        if len(points) != points_expected or len(keys) != len(points):
            raise ValueError("Incomplete or repeated fine-grid points")
        write_rows(target / "screen_points.csv", (
            dict(design=p["design"], port_cap_kw=p["caps_kw"][0], warehouse_cap_kw=p["caps_kw"][1],
                 priced=p["priced"], decision=p["decision"], reason=p["reason"],
                 missing_weeks=p["missing_weeks"], service_weeks=p["service_weeks"]) for p in points))
        write_rows(target / "screen_tariffs.csv", (
            dict(design=p["design"], port_cap_kw=p["caps_kw"][0], warehouse_cap_kw=p["caps_kw"][1],
                 priced=p["priced"], **case) for p in points for case in p["tariffs"]))
        by_price = {label: dict(Counter(p["decision"] for p in points if p["priced"] == priced))
                    for label, priced in (("priced", True), ("unquoted", False))}
        save("screen_summary.json", dict(points=len(points), by_price=by_price,
                                         reasons=dict(Counter(p["reason"] for p in points)),
                                         prior_counts=earlier_estimate["point_counts"]))
        progress(f"筛选 {len(points)} 点，有价与无报价分别为 {by_price}。")
        time_check()
        gate = now() if expected is None else datetime.fromisoformat(expected["gate_utc"])
        elapsed = (gate - start).total_seconds()
        if not 0 <= elapsed < duration:
            raise ss.fc.StudyLimit("four_hour_limit")
        workload = estimate_work(points, evidence.records, elapsed_seconds=elapsed)
        save("workload.json", workload)
        decision = dict(branch=workload["budget"]["branch"], gate_utc=gate.isoformat(),
                        priced_seconds=workload["budget"]["priced_required_seconds"],
                        available_seconds=workload["budget"]["available_seconds"], solver_calls=0)
        save("decision.json", decision)
        progress(f"预算判断 {decision['branch']}，有价点需要 {decision['priced_seconds']:.1f} 秒，可用 {decision['available_seconds']:.1f} 秒。")
    if decision["branch"] == "B":
        builds = ((ss.Design(p["port_plugs"], p["port_kw"], p["warehouse_kw"]), tuple(p["caps_kw"])) for p in points)
        frozen = freeze_coarse(coarse, builds, screening=points)
        for name, fields in TABLE_FIELDS.items():
            write_rows(target / (name + ".csv"), frozen[name], fields)
        save("freeze_evidence.json", frozen["evidence"])
        progress(f"冻结 {len(frozen['frozen_facilities'])} 个口径，已结算缺价门槛 {len(frozen['quote_thresholds'])} 项。")
    time_check()
    return dict(status="frozen_coarse" if decision["branch"] == "B" else "admitted_refinement", **decision)


def run(coarse, folder, verify=False):
    coarse, folder = coarse.resolve(), folder.resolve()
    if folder.parent.is_relative_to(coarse.parent) or coarse.parent.is_relative_to(folder.parent):
        raise ValueError("Use a separate new refinement archive")
    registration, binding = registered_files(folder.parent)
    state = ss.source_state()
    if not verify and state["dirty"]:
        raise ValueError("Commit the research source before formal screening")

    def progress(line):
        if not verify:
            with (folder.parent / "PROGRESS.md").open("a", encoding="utf-8") as stream:
                stream.write(f"- {now().astimezone().isoformat()} {line}\n")
            print(line, flush=True)

    with without_solver():
        if verify:
            original = read(folder / "manifest.json")
            if (original["products"] != filenames(folder) or original["registration"] != binding
                    or digest(coarse / "seal.json") != registration["coarse_seal_sha256"]
                    or digest(coarse / "run_manifest.json") != registration["coarse_manifest_sha256"]):
                raise ValueError("Sealed results or registration differ")
            if original["result"]["status"] == "stopped_clock":
                return dict(status="verified_clock_checkpoint", products=len(original["products"]))
            if ("gate_utc" in original["result"] and
                    datetime.fromisoformat(original["result"]["gate_utc"]) > datetime.fromisoformat(original["sealed_utc"])):
                raise ValueError("Budget decision is dated after the archive seal")
            with TemporaryDirectory(prefix="um-refine-replay-") as temp:
                target = Path(temp)
                result = evaluate(coarse, target, progress, registration, expected=original["result"])
                if result != original["result"] or filenames(target) != original["products"]:
                    raise ValueError("Independent screened results differ")
            return dict(status="verified", result=result, products=len(original["products"]))
        checked_output(folder, ss.eb.ROOT)
        folder.mkdir()
        progress(f"正式无求解回测与筛选开跑，源码 {state['commit']}。")
        try:
            result = evaluate(coarse, folder, progress, registration)
        except ss.fc.StudyLimit as exc:
            result = dict(status="stopped_clock", reason=str(exc), solver_calls=0)
        artifact(folder / "manifest.json", json_bytes(dict(registration=binding, source_commit=state["commit"],
                 sealed_utc=now().isoformat(), result=result, products=filenames(folder))))
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coarse", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    result = run(args.coarse, args.verify or args.output, verify=args.verify is not None)
    print(compact(result))
    return 2 if result["status"].startswith("stopped") else 0


if __name__ == "__main__":
    raise SystemExit(main())
