"""Run the archived, screened operating grid under the registered study limits."""

from argparse import ArgumentParser
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from multiprocessing import get_context
from multiprocessing.connection import wait
from pathlib import Path
from time import perf_counter
import traceback

from . import site_sizing as ss
from .__main__ import checked_output, digest, write_json
from .site_sizing_bounds import AnnualBillBounds
from .site_sizing_screen import COST_MARGIN_EUR, WORKERS, verify_solver_source
from .site_sizing_screen_evidence import _annual_point, _ledgers, _load_week, load_evidence


WALL_SECONDS = 2.5 * 3600
PROGRESS_SECONDS = 15 * 60


def _atomic_json(path, data):
    pending = path.with_suffix(".tmp")
    write_json(pending, data)
    pending.replace(path)


def _dominates_caps(larger, smaller):
    return all(a >= b for a, b in zip(larger, smaller, strict=True))


def _scope_data(scope):
    week, design, caps = scope
    return {"week": week, "design": design.label, "caps_kw": caps}


def _proof_data(proof):
    return {**_scope_data(proof.scope), "status": proof.status, "proof": proof.proof,
            "proof_sha256": proof.proof_sha256, "lower_eur_2021": proof.lower_eur,
            "upper_eur_2021": proof.upper_eur, "audited": proof.audit is not None}


def _all_above(lower, incumbent):
    return all(lower[scenario][basis] > total + COST_MARGIN_EUR
               for (scenario, basis), total in incumbent.items())


@dataclass
class OperatingPoint:
    design: ss.Design
    caps: tuple
    kind: str
    status: str = "pending"
    missing: tuple = ()
    weeks: tuple = ()
    failed: tuple = ()
    infeasible_proof: object = None
    settlement: object = None
    interval: dict = field(default_factory=dict)

    def serialize(self):
        value = {
            "design": self.design.label, "caps_kw": self.caps, "kind": self.kind,
            "status": self.status, "weeks": [_proof_data(proof) for proof in self.weeks],
            "failed_weeks": [_proof_data(proof) for proof in self.failed],
            "missing_weeks": [_scope_data(scope) for scope in self.missing],
        }
        if self.infeasible_proof is not None:
            value["infeasible_proof"] = _proof_data(self.infeasible_proof)
        if self.settlement is not None:
            value.update(totals_eur=self.settlement.totals, dispatch=self.settlement.dispatch)
        return {**value, **self.interval}


def _registered_points(screening, threshold_points, evidence):
    actual = {(row["design"], tuple(row["caps_kw"])) for row in evidence.prescan_points}
    screen_rows = {(row["design"], tuple(row["caps_kw"])): row for row in screening["points"]}
    if screen_rows.keys() != actual or len(screening["points"]) != len(actual):
        raise ValueError("The screening output differs from the registered priced operating points")
    if len(threshold_points) > 10:
        raise ValueError("At most ten quote-threshold points may be selected")
    threshold_keys = {(row["design"], tuple(row["caps_kw"])) for row in threshold_points}
    if len(threshold_points) != len(threshold_keys) or not threshold_keys <= actual:
        raise ValueError("Invalid or repeated quote-threshold point")

    ranking = []
    thresholds = []
    excluded = Counter()
    for key, row in screen_rows.items():
        name, caps = key
        absent_split = all(part["no_relaxed_load_split"] for part in row["annual_comparison"])
        if row["status"] == "needs_solves":
            ranking.append(OperatingPoint(evidence.cases[name], caps, "ranking"))
        else:
            status = row["status"]
            if status == "excluded_by_annual_lower_bound" and absent_split:
                status = "relaxed_infeasible"
            excluded[status] += 1
        if key in threshold_keys:
            if row["status"] != "excluded_by_annual_lower_bound" or absent_split:
                raise ValueError(f"Invalid quote-only scope: {key}")
            thresholds.append(OperatingPoint(evidence.cases[name], caps, "threshold"))
    if excluded["relaxed_infeasible"] != screening["no_relaxed_load_split_count"]:
        raise ValueError("The capacity-relaxation exclusions do not reconcile")
    return ranking + thresholds, excluded


class FormalGrid:
    def __init__(self, evidence, screening, threshold_points):
        self.evidence = evidence
        self.points, self.initial_counts = _registered_points(screening, threshold_points, evidence)
        self.bounds = AnnualBillBounds(tuple(evidence.periods.values()), evidence.reference,
                                       evidence.network, evidence.materials)
        self.attempts = {}
        self.results = []
        self.monotone_weekly_checks = 0
        self.incumbent = {(row["scenario"], row["connection_basis"]): row["annual_total_eur"]
                          for row in evidence.publication["winners"]}
        self.archive_records = {week: list(rows) for week, rows in evidence.records_by_week.items()}
        self.quote_records = {week: list(rows) for week, rows in evidence.records_by_week.items()}
        at_caps, infeasible = evidence.combined_index
        self.quote_evidence = replace(evidence, combined_index=(
            {key: dict(proofs) for key, proofs in at_caps.items()}, infeasible))
        self.by_hardware = defaultdict(list)
        for week, rows in self.archive_records.items():
            for proof in rows:
                self.by_hardware[week, proof.design].append(proof)
        scopes = {scope for point in self.points if point.kind == "ranking"
                  for scope in evidence.point_plan(point.design, point.caps).missing}
        registered = {(row["week"], evidence.cases[row["design"]], tuple(row["caps_kw"]))
                      for row in screening["unique_weekly_groups_to_solve"]}
        if scopes != registered:
            raise ValueError("The pending groups differ from the archived screening output")
        self.ranking_scopes = scopes
        self.initial_ranking_groups = len(scopes)
        self.initial_threshold_groups = len({scope for point in self.points if point.kind == "threshold"
                                             for scope in evidence.point_plan(point.design, point.caps).missing})

    def add_proof(self, proof, seconds):
        if proof.scope in self.attempts:
            raise ValueError(f"Repeated solver group in the formal archive: {proof.scope}")
        self._audit_monotonicity(proof)
        self.attempts[proof.scope] = proof
        self.by_hardware[proof.week, proof.design].append(proof)
        ranking = proof.scope in self.ranking_scopes
        self.results.append({**_proof_data(proof), "solve_seconds": seconds,
                             "kind": "ranking" if ranking else "threshold"})
        self.quote_records[proof.week].append(proof)
        self._index_proof(self.quote_evidence, proof)
        if ranking:
            self.archive_records[proof.week].append(proof)
            self._index_proof(self.evidence, proof)

    @staticmethod
    def _index_proof(evidence, proof):
        at_caps, infeasible = evidence.combined_index
        if proof.status in ss.ENERGY_ACCEPTED:
            at_caps.setdefault((proof.week, proof.caps), {})[proof.design] = proof
        elif proof.status == "infeasible":
            evidence.combined_index = at_caps, (*infeasible, proof)

    def _audit_monotonicity(self, proof):
        for previous in self.by_hardware[proof.week, proof.design]:
            for larger, smaller in ((proof, previous), (previous, proof)):
                if not _dominates_caps(larger.caps, smaller.caps):
                    continue
                if larger.status == "infeasible" and smaller.audit is not None:
                    raise ValueError(f"Infeasible proof contradicts a tighter feasible schedule: "
                                     f"{larger.proof}, {smaller.proof}")
                if larger.lower_eur is None or smaller.audit is None:
                    continue
                self.monotone_weekly_checks += 1
                if larger.lower_eur > smaller.audit["purchase_eur"] + ss.EPS:
                    raise ValueError(f"Weekly wholesale monotonicity fails: {larger.proof}, {smaller.proof}")

    def refresh(self, *, collect_intervals=False):
        for point in self.points:
            if point.status in {"settled", "infeasible_solve", "infeasible_monotonicity"}:
                continue
            if point.status == "excluded_by_interval" and not collect_intervals:
                continue
            self._classify(point, collect_intervals)

    def _classify(self, point, collect_intervals):
        evidence = self.evidence if point.kind == "ranking" else self.quote_evidence
        records = self.archive_records if point.kind == "ranking" else self.quote_records
        plan = evidence.point_plan(point.design, point.caps)
        point.infeasible_proof = plan.proof
        point.weeks = plan.weeks
        point.missing = tuple(scope for scope in plan.missing if scope not in self.attempts)
        point.failed = tuple(self.attempts[scope] for scope in plan.missing if scope in self.attempts)
        if plan.status == "settled":
            point.settlement = _annual_point(evidence, point.design, point.caps, plan.weeks)
            point.interval = {}
            point.status = plan.status
            return
        if plan.status.startswith("infeasible"):
            point.status = plan.status
            point.interval = {}
            return
        if point.failed:
            lower = self.bounds.annual_lower_bounds(point.design, point.caps, records)
            point.interval = {
                "annual_lower_totals_eur": lower["total_eur"],
                "annual_upper_totals_eur": None,
                "wholesale_weekly_lower_proofs": [
                    {"week": week, "proof": proof.proof, "lower_eur_2021": proof.lower_eur}
                    for week, proof in lower["weekly"].items()
                ],
            }
            if collect_intervals and not point.missing and all(proof.audit is not None for proof in point.failed):
                feasible = tuple(replace(proof, lower_eur=lower["weekly"][proof.week].lower_eur)
                                 for proof in point.weeks + point.failed)
                upper = _annual_point(evidence, point.design, point.caps, feasible).totals
                for scenario, tariffs in lower["total_eur"].items():
                    for basis, bound in tariffs.items():
                        if bound > upper[scenario][basis] + ss.EPS:
                            raise ValueError("The annual lower bound exceeds an independent settlement")
                point.interval["annual_upper_totals_eur"] = upper
            if point.kind == "ranking" and _all_above(lower["total_eur"], self.incumbent):
                point.status = "excluded_by_interval"
                return
            if not point.missing:
                point.status = "unresolved" if point.kind == "ranking" else "threshold_interval"
                return
        point.status = "pending"

    def next_scope(self, active):
        free = {}
        busy = {(week, caps) for week, _, caps in active}
        for point in self.points:
            if point.status != "pending":
                continue
            for week, design, caps in point.missing:
                group = week, caps
                if group in busy:
                    continue
                order = (point.kind != "threshold", caps[1] != 0, -caps[0], -caps[1],
                         week, -design.port_plugs, -design.port_kw, -design.warehouse_kw)
                scope = week, design, caps
                if group not in free or order < free[group][0]:
                    free[group] = order, scope
        return min(free.values())[1] if free else None

    def unresolved_count(self):
        return sum(point.kind == "ranking" and point.status == "unresolved" for point in self.points)

    def counts(self):
        return self.initial_counts + Counter(point.status for point in self.points if point.kind == "ranking")

    def annual_tables(self):
        operations = defaultdict(list)
        for previous in self.evidence.annual_points:
            operations[previous.design].append(previous.dispatch)
        for point in self.points:
            if point.kind == "ranking" and point.settlement is not None:
                operations[point.design].append(point.settlement.dispatch)
        grid = ss.DispatchGrid([], None, None, None)
        grid.check_order(operations)
        costs, winners = ss.annual_tables(operations, self.evidence.materials, self.evidence.scenarios)
        return {
            "monotone_annual_checks": grid.energy_checks,
            "winners": [dict(scenario=scenario, connection_basis=basis, **value)
                        for (scenario, basis), value in winners.items()],
            "cost_rows": [dict(design=design, scenario=scenario, **value)
                          for (design, scenario), value in costs.items()],
        }


def _worker(connection, directory, reference, deadline):
    try:
        periods = {p.days[0]["week_start"]: p for p in ss.fc._periods("full")}
        evidence = ss.Evidence(directory, perf_counter(), trial=False)
        evidence.deadline = deadline
        for week, design, caps in iter(connection.recv, None):
            # This run's stopping threshold counts unresolved operating points
            # across workers, after applying the annual interval rule.
            evidence.unresolved.clear()
            period = periods[week]
            label, _ = evidence.call(period, design, "energy", caps, fixed=reference & period.keys)
            checksum = digest(directory / f"{label}.json.gz")
            connection.send(("proof", evidence.calls[-1], checksum))
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        try:
            connection.send(("error", traceback.format_exc(), None))
        except OSError:
            pass
    finally:
        connection.close()


def _audit_record(grid, directory, source, row, checksum):
    evidence = grid.evidence
    prefix = f"formal/{directory.name}"
    # The subprocess's ordinary Python record has a tuple. Its gzip and
    # ledger are JSON arrays, which the proof validator compares literally.
    persisted = {**row, "caps_kw": list(row["caps_kw"])}
    proof = _load_week(directory, persisted, source, prefix, evidence.cases,
                       evidence.periods, evidence.reference, expected_sha=checksum)
    grid.add_proof(proof, row["seconds"])


def _launch(grid, output, progress, source, deadline, elapsed):
    ctx = get_context("spawn")
    workers = {}
    active = {}
    next_tick = perf_counter() + PROGRESS_SECONDS - (elapsed() % PROGRESS_SECONDS)
    stop = None
    last_folder = max((int(path.name.removeprefix("worker-"))
                       for path in output.glob("worker-*") if path.is_dir()), default=0)
    try:
        grid.refresh()
        while perf_counter() < deadline:
            if grid.unresolved_count() > ss.fc.MAX_UNRESOLVED:
                stop = "more than three unresolved priced operating points"
                break
            for connection in tuple(workers):
                if connection in active:
                    continue
                scope = grid.next_scope(active.values())
                if scope is None:
                    break
                active[connection] = scope
                connection.send(scope)
            while len(workers) < WORKERS and perf_counter() < deadline:
                scope = grid.next_scope(active.values())
                if scope is None:
                    break
                last_folder += 1
                directory = output / f"worker-{last_folder:02d}"
                directory.mkdir()
                parent, child = ctx.Pipe()
                process = ctx.Process(target=_worker, args=(child, directory, grid.evidence.reference, deadline))
                process.start()
                child.close()
                workers[parent] = directory, process
                active[parent] = scope
                parent.send(scope)
            if not active:
                break
            timeout = max(0., min(next_tick, deadline) - perf_counter())
            for connection in wait(active, timeout=timeout):
                if perf_counter() >= deadline:
                    break
                kind, row, checksum = connection.recv()
                if kind == "error":
                    raise ValueError(row)
                scope = active.pop(connection)
                if _scope_data(scope) != {key: row[key] for key in ("week", "design", "caps_kw")}:
                    raise ValueError(f"A worker reported another scope: {row}")
                _audit_record(grid, workers[connection][0], source, row, checksum)
                grid.refresh()
                if grid.unresolved_count() > ss.fc.MAX_UNRESOLVED:
                    stop = "more than three unresolved priced operating points"
                    break
            if stop:
                break
            if perf_counter() >= next_tick:
                ss._progress(progress, f"正式运行进度。新完成周组 {len(grid.results)}，"
                                       f"墙钟 {elapsed():.1f} 秒，未判定点 {grid.unresolved_count()}。")
                next_tick += PROGRESS_SECONDS
        if stop is None and perf_counter() >= deadline:
            stop = "formal wall-clock budget exhausted"
    except KeyboardInterrupt:
        stop = "interrupted"
    except Exception:
        stop = traceback.format_exc()
    finally:
        for connection, (_, process) in workers.items():
            if connection in active:
                if process.is_alive():
                    process.terminate()
            elif process.is_alive():
                try:
                    connection.send(None)
                except OSError:
                    pass
            connection.close()
            process.join(5.)
            if process.is_alive():
                process.terminate()
                process.join()
    return stop, [_scope_data(scope) for scope in active.values()]


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--coarse-archive", type=Path, required=True)
    parser.add_argument("--pilot-archive", type=Path, required=True)
    parser.add_argument("--published-baseline", type=Path)
    parser.add_argument("--screening", type=Path, required=True)
    parser.add_argument("--threshold-points", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    source = ss.source_state()
    if source["dirty"]:
        raise ValueError("The formal solver requires a clean source commit")
    screening = ss.eb.read_json(args.screening)
    evidence = load_evidence(args.coarse_archive, args.pilot_archive,
                             publication_path=args.published_baseline)
    if (screening["solver_calls"] != 0 or screening["source"]["dirty"]
            or screening["inputs_sha256"] != evidence.publication["inputs_sha256"]
            or screening["archive_sha256"] != evidence.archive_sha256
            or screening["backtest_sha256"] != digest(args.screening.with_name("backtest.json"))
            or ss.eb.read_json(args.screening.with_name("backtest.json"))["status"] != "passed"):
        raise ValueError("The screening and audited model inputs do not match")
    verify_solver_source(evidence.pilot_summary["source"])
    threshold_points = ss.eb.read_json(args.threshold_points)
    grid = FormalGrid(evidence, screening, threshold_points)
    output = args.output.resolve()
    if output.name != "formal" or output.parent != args.screening.resolve().parent:
        raise ValueError("The formal output must be next to the screener evidence")

    metadata = {
        "source": source, "inputs_sha256": screening["inputs_sha256"],
        "published_baseline_sha256": digest(args.published_baseline or
                                           ss.eb.WEEKS.with_name("site_sizing.json")),
        "screening_sha256": digest(args.screening), "threshold_points_sha256": digest(args.threshold_points),
        "maximum_wall_seconds": WALL_SECONDS, "per_solve_seconds": ss.fc.SOLVE_SECONDS, "workers": WORKERS,
    }
    if args.resume:
        old = ss.eb.read_json(output / "run.json")
        for key, actual in metadata.items():
            if old[key] != actual:
                raise ValueError(f"The resumed run's provenance changed: {key}")
        started = datetime.fromisoformat(old["started_at"])
        if (output / "summary.json").exists():
            prior = ss.eb.read_json(output / "summary.json")
            if prior["stop_reason"] != "interrupted":
                raise ValueError("Only an interrupted run can be resumed")
        for ledger in sorted(output.glob("worker-*/solves.jsonl")):
            for row in _ledgers(ledger):
                proof_file = ledger.parent / (row["id"] + ".json.gz")
                _audit_record(grid, ledger.parent, source["commit"], row, digest(proof_file))
    else:
        output = checked_output(output, ss.eb.ROOT)
        output.mkdir()
        started = datetime.now(timezone.utc)
        _atomic_json(output / "run.json", dict(metadata, started_at=started.isoformat()))
    elapsed = lambda: (datetime.now(timezone.utc) - started).total_seconds()
    deadline = perf_counter() + max(0., WALL_SECONDS - elapsed())
    ss._progress(args.progress, f"正式运行{'续算' if args.resume else '开始'}。源码 {source['commit']}，"
                               f"有价待算 {grid.initial_ranking_groups} 周组，报价见证 {grid.initial_threshold_groups} 周组，"
                               f"{WORKERS} 进程，{WALL_SECONDS / 3600:g} 小时墙钟上限。")
    stop, unfinished = _launch(grid, output, args.progress, source["commit"], deadline, elapsed)
    solver_wall = elapsed()
    annual = {}
    try:
        grid.refresh(collect_intervals=True)
        if stop is None:
            if any(point.status in {"pending", "unresolved"} for point in grid.points):
                stop = "some priced operating points still have no accepted outcome"
            else:
                annual = grid.annual_tables()
    except Exception:
        if stop is None:
            stop = traceback.format_exc()
    summary = {
        **metadata, "started_at": started.isoformat(), "wall_seconds": solver_wall,
        "status": "stopped" if stop else "complete", "stop_reason": stop,
        "initial_ranking_week_groups": grid.initial_ranking_groups,
        "initial_threshold_week_groups": grid.initial_threshold_groups,
        "solver_calls": len(grid.results), "solver_status": dict(Counter(r["status"] for r in grid.results)),
        "audited_schedules": sum(row["audited"] for row in grid.results),
        "monotone_weekly_checks": grid.monotone_weekly_checks,
        "unfinished_attempts": unfinished, "unresolved_priced_points": grid.unresolved_count(),
        "point_counts": dict(grid.counts()),
        "points": [point.serialize() for point in grid.points],
        "results": grid.results,
        **annual,
    }
    _atomic_json(output / "summary.json", summary)
    ss._progress(args.progress, f"正式运行{'停止' if stop else '结束'}。新完成周组 {len(grid.results)}，"
                               f"墙钟 {solver_wall:.1f} 秒，未判定点 {grid.unresolved_count()}。")
    if stop:
        raise SystemExit(stop)


if __name__ == "__main__":
    main()
