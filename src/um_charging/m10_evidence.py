"""Hash-bound weekly M10 certificates, budgeted workers and solver-free replay."""

from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import io
import json
import math
import multiprocessing
import os
from pathlib import Path
import random
from tempfile import NamedTemporaryFile
from time import monotonic, perf_counter, process_time
from unittest.mock import patch

from scipy.optimize import milp

from . import site_sizing as ss


WORKERS = 8
AUDIT_SEED = 20261122
CONTINUATION_TIMEOUT_GAP_EUR = 0.10
WORKER_ENV = {"PYTHONHASHSEED": "0", "OPENBLAS_NUM_THREADS": "1",
              "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
SOLVER_OPTIONS = {"threads": 1, "random_seed": 0}
POLICY = {"model": "grouped", "delay_min": 0, "time_limit_s": ss.fc.SOLVE_SECONDS,
          "energy_rel_gap": ss.fc.RELATIVE_COST_GAP, "energy_abs_gap": ss.fc.ABSOLUTE_COST_GAP,
          "timeout_abs_gap": ss.TIMEOUT_COST_GAP_EUR, "service_rel_gap": 0, "service_abs_gap": 0,
          "primal_feasibility_tolerance": 1e-9, "mip_feasibility_tolerance": 1e-9,
          **SOLVER_OPTIONS}


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _hash(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


@dataclass(frozen=True)
class Request:
    week: str
    design: ss.Design
    phase: str
    caps: tuple
    fixed: tuple | None
    prefer: tuple

    @classmethod
    def make(cls, period, design, phase, caps, *, fixed=None, prefer=()):
        return cls(period.days[0]["week_start"], design, phase, tuple(caps),
                   None if fixed is None else tuple(sorted(fixed)), tuple(sorted(prefer)))

    @classmethod
    def from_json(cls, data):
        fixed = data["fixed"]
        return cls(data["week"], ss.Design(**data["design"]), data["phase"], tuple(data["caps"]),
                   None if fixed is None else tuple(map(tuple, fixed)), tuple(map(tuple, data["prefer"])))

    def identifier(self, scope):
        return _hash([scope, asdict(self)])


def _configured_milp(*args, options, **kwargs):
    return milp(*args, options={**options, **SOLVER_OPTIONS}, **kwargs)


def _admit(deadline):
    if monotonic() + ss.fc.SOLVE_SECONDS > deadline:
        raise ss.fc.StudyLimit("A full 300-second weekly solve no longer fits before the closing reserve")


def _solve(period, request, deadline):
    _admit(deadline)
    started = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    clock, cpu = perf_counter(), process_time()
    # Each worker runs one request at a time. M8's validated solve path builds
    # the model and sets its tolerances. The M10 worker freezes thread and seed.
    with patch.object(ss, "milp", _configured_milp):
        result = ss.solve(period, request.design, caps=request.caps, fixed=request.fixed,
                          prefer=request.prefer, deadline=perf_counter() + deadline - monotonic())
    stats = result["stats"]
    stats.update(started_utc=started, seconds=perf_counter() - clock,
                 cpu_seconds=process_time() - cpu, worker_pid=os.getpid())
    timed_out = stats["status_code"] == 1 and "time limit" in stats["message"].lower()
    if (timed_out and request.fixed is not None and result["audit"] is not None
            and stats["absolute_gap"] is not None and stats["absolute_gap"] <= ss.TIMEOUT_COST_GAP_EUR + 1e-9):
        stats["status"] = "bounded"
    return result


def _publish(path, content):
    """Atomically create without replacing an earlier completed request."""
    with NamedTemporaryFile(dir=path.parent, suffix=".partial", delete=False) as fp:
        tmp = Path(fp.name)
        try:
            fp.write(content)
            fp.flush()
            os.fsync(fp.fileno())
        except BaseException:
            fp.close()
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.link(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _archive(period, request, deadline, directory, scope):
    result = _solve(period, request, deadline)
    label = request.identifier(scope)
    body = {"scope": scope, "request": asdict(request), "result": result}
    envelope = {"body": body, "sha256": _hash(body)}
    compressed = gzip.compress(_encoded(envelope), compresslevel=1, mtime=0)
    _publish(directory / (label + ".json.gz"), compressed)
    return label


def _assert_close(actual, expected):
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError("Archived replay fields differ")
        for key in expected:
            _assert_close(actual[key], expected[key])
    elif isinstance(expected, (list, tuple)):
        for a, b in zip(actual, expected, strict=True):
            _assert_close(a, b)
    elif isinstance(expected, float):
        ss.close(actual, expected, "archived physical replay")
    elif actual != expected:
        raise ValueError(("Archived replay differs", actual, expected))


def replay(period, req, result):
    stats = result["stats"]
    lower, upper = stats["objective_lower"], stats["objective_upper"]
    absolute, relative = stats["absolute_gap"], stats["relative_gap"]
    if lower is not None and upper is not None:
        if lower > upper + ss.EPS or not math.isclose(absolute, max(0., upper-lower), rel_tol=0, abs_tol=1e-9):
            raise ValueError("Inconsistent archived objective bounds")
    status = stats["status"]
    if status == "certified":
        absolute_target = ss.fc.ABSOLUTE_COST_GAP if req.fixed is not None else 0
        relative_target = ss.fc.RELATIVE_COST_GAP if req.fixed is not None else 0
        if not (stats["status_code"] == 0 and result["audit"] is not None and absolute is not None
                and (absolute <= absolute_target + 1e-9
                     or relative is not None and relative <= relative_target + 1e-12)):
            raise ValueError("Archived certification does not satisfy its registered gap")
    elif status == "bounded":
        if not (req.fixed is not None and stats["status_code"] == 1 and "time limit" in stats["message"].lower()
                and result["audit"] is not None and absolute is not None and absolute <= ss.TIMEOUT_COST_GAP_EUR + 1e-9):
            raise ValueError("Invalid bounded weekly certificate")
    elif status == "infeasible":
        if stats["status_code"] != 2 or result["audit"] is not None:
            raise ValueError("Invalid native infeasibility evidence")
    elif status != "unresolved":
        raise ValueError(f"Unknown M10 solve status {status}")
    if result["audit"] is None:
        if result["schedule"] or result["states"] or upper is not None:
            raise ValueError("Missing replay for a returned incumbent")
        return
    states = {(r["date"], r["vehicle_id"]) for r in result["states"]}
    selected = ss.eb.selected(result)
    active = period.keys if req.fixed is None else set(req.fixed)
    if states != active or len(states) != len(result["states"]):
        raise ValueError("Archived state inventory differs from the requested duties")
    if req.fixed is not None and selected != active:
        raise ValueError("The fixed-service witness omits a requested duty")
    if req.fixed is None:
        weight = len(req.prefer) + 1
        score = -weight * len(selected) - len(selected & set(req.prefer))
        ss.close(upper, score, "service score")
        bound = len(period.keys) if lower is None else min(len(period.keys), math.floor((-lower+ss.EPS)/weight))
        if stats["completed_bounds"] != [len(selected), bound] or (status == "certified" and len(selected) != bound):
            raise ValueError("Invalid whole-duty integer service bounds")
    checked = ss.meter_replay(period, req.design.hardware(), ss.eb.DEFAULT_SPEC, req.caps, result,
                              physical=req.fixed is None)
    _assert_close(checked, result["audit"])
    if req.fixed is not None:
        ss.close(upper, checked["purchase_eur"], "fixed-service incumbent")


def _admitted_result(period, req, original):
    """Apply the continuation's analytical rule to the original native evidence."""
    stats = original["stats"]
    status = stats["status"]
    lower, upper = stats["objective_lower"], stats["objective_upper"]
    widened = (status == "unresolved" and req.fixed is not None and original["audit"] is not None
               and stats["status_code"] == 1 and "time limit" in stats["message"].lower()
               and lower is not None and upper is not None and math.isfinite(lower) and math.isfinite(upper)
               and 0 <= upper - lower <= CONTINUATION_TIMEOUT_GAP_EUR)
    if widened:
        # A recorded gap is insufficient on its own. Independently validate the
        # fixed duties, physical schedule, price replay and both bounds.
        replay(period, req, original)
    return {**original, "stats": {**stats, "original_status": status, "widened_interval": widened,
                                  "status": "bounded" if widened else status}}


def _schedule_digest(result):
    def normalized(row):
        return {key: round(value, 9) if isinstance(value, float) else value for key, value in row.items()}
    return _hash({key: sorted((normalized(row) for row in result[key]), key=_encoded)
                  for key in ("schedule", "states")})


def _summary(result):
    stats = result["stats"]
    fields = ("status", "status_code", "message", "objective_lower", "objective_upper", "relative_gap",
              "absolute_gap", "worker_pid", "started_utc", "seconds", "cpu_seconds")
    if "original_status" in stats:
        fields += ("original_status", "widened_interval")
    return {**{key: stats[key] for key in fields}, "objective": stats["objective_upper"],
            "schedule_sha256": _schedule_digest(result)}


def _repeat(period, request, deadline, path, original_checksum, sample_hash, continuation):
    result = _solve(period, request, deadline)
    replay(period, request, result)
    if continuation:
        result = _admitted_result(period, request, result)
    body = {"sample_sha256": sample_hash, "certificate_sha256": original_checksum,
            "repeated": _summary(result)}
    _publish(path, _encoded({"body": body, "sha256": _hash(body)}))


class M10Evidence:
    def __init__(self, output, inputs, *, workers=WORKERS, deadline=math.inf, verify=False, parent_archive=None):
        if not isinstance(workers, int) or workers < 1:
            raise ValueError("Expected a positive number of worker processes")
        self.periods = {p.days[0]["week_start"]: p for p in inputs.periods}
        self.directory = Path(output) / "certificates"
        self.parent_archive = Path(parent_archive).resolve() if parent_archive is not None else None
        if self.parent_archive is not None and self.directory.resolve().is_relative_to(self.parent_archive):
            raise ValueError("The continuation must use its own certificate directory")
        self._parent_hashes = {}
        self.workers = workers
        self.deadline = deadline
        self.verify = verify
        self.scope = _hash({"policy": POLICY, "inputs": inputs.source_sha256,
                            "reference": sorted(inputs.main_reference),
                            "weeks": list(self.periods)})
        self._pool = None
        self._environment = None
        self._rows = {}
        self._requests = {}
        self.unresolved = set()
        self._read_cached = lru_cache(maxsize=32)(self._read)
        self.trial = False

    def __enter__(self):
        if self.verify and not self.directory.is_dir():
            raise ValueError("The M10 certificate directory is absent")
        if not self.verify:
            self.directory.mkdir(exist_ok=True, parents=True)
        if self.parent_archive is not None:
            checkpoint = json.loads((self.parent_archive / "checkpoint.json").read_bytes())
            ledger = (self.parent_archive / "solves.csv").read_bytes()
            if hashlib.sha256(ledger).hexdigest() != checkpoint["files"]["solves.csv"]:
                raise ValueError("The parent solve ledger differs from its checkpoint")
            for row in csv.DictReader(io.StringIO(ledger.decode("utf-8"))):
                label = row["id"]
                if label in self._parent_hashes:
                    raise ValueError(f"Duplicate parent request {label}")
                self._parent_hashes[label] = row["certificate_sha256"]
            discovered = {p.name.removesuffix(".json.gz")
                          for p in (self.parent_archive / "certificates").glob("*.json.gz")}
            if (discovered != self._parent_hashes.keys()
                    or len(discovered) != checkpoint["audit"]["certificates"]):
                raise ValueError("Parent certificate inventory does not match the checkpoint")
            for label in sorted(self._parent_hashes):
                self._index(label)
        for path in sorted(self.directory.glob("*.json.gz")):
            label = path.name.removesuffix(".json.gz")
            if label in self._parent_hashes:
                raise ValueError(f"Current directory duplicates a parent certificate {label}")
            self._index(label)
        if not self.verify:
            self._environment = patch.dict(os.environ, WORKER_ENV)
            self._environment.__enter__()
        return self

    def __exit__(self, *exc):
        try:
            if self._pool is not None:
                self._pool.shutdown(wait=True, cancel_futures=True)
        finally:
            self._read_cached.cache_clear()
            if self._environment is not None:
                self._environment.__exit__(*exc)

    def _read(self, label):
        directory = self.parent_archive / "certificates" if label in self._parent_hashes else self.directory
        content = (directory / (label + ".json.gz")).read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        if label in self._parent_hashes and checksum != self._parent_hashes[label]:
            raise ValueError(f"Certificate differs from parent solve ledger: {label}")
        envelope = json.loads(gzip.decompress(content))
        body = envelope["body"]
        req = Request.from_json(body["request"])
        if (envelope["sha256"] != _hash(body) or body["scope"] != self.scope
                or req.identifier(self.scope) != label):
            raise ValueError(f"Certificate hash or input scope differs: {label}")
        result = body["result"]
        if self.parent_archive is not None:
            result = _admitted_result(self.periods[req.week], req, result)
        return req, result, checksum

    def _index(self, label):
        req, result, sha256 = self._read_cached(label)
        stats = result["stats"]
        fields = ("started_utc", "seconds", "cpu_seconds", "status", "status_code", "message", "worker_pid",
                  "objective_lower", "objective_upper", "relative_gap", "absolute_gap")
        self._rows[label] = {"id": label, "week": req.week, "design": req.design.label, "phase": req.phase,
                             "port_cap_kw": req.caps[0], "warehouse_cap_kw": req.caps[1],
                             "objective_unit": "EUR_2021" if req.fixed is not None else "negative_weighted_service_score",
                             **{key: stats[key] for key in fields}, "audited": result["audit"] is not None,
                             "certificate_sha256": sha256}
        if self.parent_archive is not None:
            self._rows[label].update(original_status=stats["original_status"],
                                     widened_interval=stats["widened_interval"],
                                     certificate_origin="parent" if label in self._parent_hashes else "current")
        self._requests[label] = req
        if stats["status"] == "unresolved":
            self.unresolved.add((req.week, req.design, req.caps))

    @property
    def records(self):
        return [self._rows[label] for label in sorted(self._rows)]

    def get(self, label):
        if label not in self._rows:
            raise KeyError(label)
        return self._read_cached(label)[1]

    def request_for(self, label):
        return self._requests[label]

    def check(self):
        if len(self.unresolved) > ss.fc.MAX_UNRESOLVED:
            raise ss.fc.StudyLimit("More than three unresolved weekly groups")
        if monotonic() >= self.deadline:
            raise ss.fc.StudyLimit("Formal computation reached its closing reserve")

    def call(self, period, design, phase, caps, fixed=None, prefer=()):
        request = Request.make(period, design, phase, caps, fixed=fixed, prefer=prefer)
        return self.batch([request])[0]

    def batch(self, requests):
        requests = list(requests)
        labels = [r.identifier(self.scope) for r in requests]
        missing = dict((label, req) for label, req in zip(labels, requests, strict=True) if label not in self._rows)
        if missing:
            if self.verify:
                raise ValueError(f"Missing sealed certificate {next(iter(missing))}")
            self.check()
            _admit(self.deadline)
            if self._pool is None:
                self._pool = ProcessPoolExecutor(self.workers, mp_context=multiprocessing.get_context("spawn"))
            # At most eight groups can be in flight. Once a limit is reached,
            # drain the already running workers; each publishes its own proof.
            todo = iter(missing.values())
            running = set()
            error = None
            while True:
                while error is None and len(running) < self.workers:
                    req = next(todo, None)
                    if req is None:
                        break
                    try:
                        self.check()
                        _admit(self.deadline)
                        running.add(self._pool.submit(_archive, self.periods[req.week], req,
                                                      self.deadline, self.directory, self.scope))
                    except Exception as exc:
                        error = exc
                if not running:
                    break
                done, running = wait(running, return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        self._index(future.result())
                        self.check()
                    except Exception as exc:
                        if error is None:
                            error = exc
            if error is not None:
                raise error
        return [(label, self.get(label)) for label in labels]

    def verify_all(self):
        self._read_cached.cache_clear()
        for label in sorted(self._rows):
            req, result, checksum = self._read_cached(label)
            if checksum != self._rows[label]["certificate_sha256"]:
                raise ValueError(f"Changed certificate {label}")
            # Validate the unaltered status against the policy under which the
            # proof was produced. _read replays every newly admitted interval.
            if self.parent_archive is not None:
                result = {**result, "stats": {**result["stats"], "status": result["stats"]["original_status"]}}
            replay(self.periods[req.week], req, result)
        rows = self._rows.values()
        audit = {"certificates": len(self._rows), "feasible_replayed": sum(r["audited"] for r in rows),
                 "status_counts": dict(Counter(r["status"] for r in rows)),
                 "unresolved_weekly_groups": len(self.unresolved)}
        if self.parent_archive is not None:
            audit.update(original_status_counts=dict(Counter(r["original_status"] for r in rows)),
                         certificate_origins=dict(Counter(r["certificate_origin"] for r in rows)),
                         widened_intervals=sum(r["widened_interval"] for r in rows))
        return audit

    def determinism(self, seed=AUDIT_SEED, count=20):
        self.check()
        labels = random.Random(seed).sample(sorted(self._rows), count)
        sample = {"seed": seed, "scope": self.scope, "labels": labels}
        if self.parent_archive is not None:
            sample["timeout_interval_eur"] = CONTINUATION_TIMEOUT_GAP_EUR
        sample_hash = _hash(sample)
        directory = self.directory.parent / "determinism" / sample_hash
        if not self.verify:
            directory.mkdir(parents=True, exist_ok=True)
        if self._pool is not None:
            self._pool.shutdown(wait=True)
            self._pool = None
        comparisons = []
        # A separate one-shot pool per batch ensures one fresh interpreter per
        # selected request, including when a worker finishes before its peers.
        pending = [key for key in labels if not (directory / (key + ".json")).is_file()]
        if self.verify and pending:
            raise ValueError(f"Missing sealed repeat for {pending[0]}")
        for start in range(0, len(pending), self.workers):
            _admit(self.deadline)
            batch = pending[start:start+self.workers]
            with ProcessPoolExecutor(len(batch), mp_context=multiprocessing.get_context("spawn"),
                                     max_tasks_per_child=1) as pool:
                futures = [pool.submit(_repeat, self.periods[self._requests[key].week],
                                       self._requests[key], self.deadline, directory / (key + ".json"),
                                       self._rows[key]["certificate_sha256"], sample_hash,
                                       self.parent_archive is not None) for key in batch]
                for future in futures:
                    future.result()
        for label in labels:
            envelope = json.loads((directory / (label + ".json")).read_bytes())
            body = envelope["body"]
            if (envelope["sha256"] != _hash(body) or body["sample_sha256"] != sample_hash
                    or body["certificate_sha256"] != self._rows[label]["certificate_sha256"]):
                raise ValueError(f"Determinism checkpoint differs for {label}")
            prior, repeated = _summary(self.get(label)), body["repeated"]
            a, b = prior["objective"], repeated["objective"]
            objective_equal = a == b if a is None or b is None else math.isclose(a, b, rel_tol=0, abs_tol=ss.EPS)
            status_equal = prior["status"] == repeated["status"]
            schedule_equal = prior["schedule_sha256"] == repeated["schedule_sha256"]
            comparisons.append({"id": label, "status_equal": status_equal, "objective_equal": objective_equal,
                                "schedule_equal": schedule_equal, "match": status_equal and objective_equal and schedule_equal,
                                "original": prior, "repeated": repeated})
            if self.parent_archive is not None:
                comparisons[-1]["original_status_equal"] = prior["original_status"] == repeated["original_status"]
        matched = sum(row["match"] for row in comparisons)
        return {"seed": seed, "requested": count, "comparisons": comparisons, "matched": matched,
                "all_match": matched == count}
