"""Native certificates and independent replay for the locked holdout matrix."""
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from copy import copy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import random
from time import monotonic, perf_counter, process_time
from unittest.mock import patch

from . import holdout_service as registration
from . import m10_evidence as m10, site_sizing as ss
from .m10_policy_evidence import _equals, _meter_summary
from .m10_rolling import rolling_day_period


@dataclass(frozen=True)
class FinalRequest:
    scenario: str
    week: str
    design: ss.Design
    phase: str
    caps: tuple
    fixed: tuple = ()
    date: str | None = None
    locked: tuple = ()
    reference: tuple = ()

    def __post_init__(self):
        locked = self.locked.items() if isinstance(self.locked, dict) else self.locked
        object.__setattr__(self, "caps", tuple(self.caps))
        object.__setattr__(self, "fixed", tuple(sorted(map(tuple, self.fixed))))
        object.__setattr__(self, "locked", tuple(sorted((tuple(k), v) for k, v in locked)))
        object.__setattr__(self, "reference", tuple(sorted(map(tuple, self.reference))))

    def identifier(self, scope):
        return m10._hash([scope, asdict(self)])


def _shape(req, period):
    if req.phase == "rolling_energy":
        return rolling_day_period(period, req.date, set(req.fixed))
    if req.phase == "fixed_service":
        # The grouped model and B constraints stay the same. Its constant zero
        # objective establishes integer feasibility independently of procurement.
        service = copy(period)
        service.prices = {day: [0.] * len(prices) for day, prices in period.prices.items()}
        return service
    return period


def _legacy(req):
    return m10.Request(req.week, req.design, req.phase, req.caps, req.fixed, ())


def _solve(period, req, deadline):
    m10._admit(deadline)
    shaped = _shape(req, period)
    if req.phase in {"energy", "rolling_energy"}:
        return m10._solve(shaped, _legacy(req), deadline)
    start = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    began, cpu = perf_counter(), process_time()
    native_deadline = perf_counter() + deadline - monotonic()
    if req.phase == "registration":
        with patch.object(registration, "milp", m10._configured_milp):
            result = registration.solve_service_day(shaped, req.design, req.date, dict(req.locked),
                                                    req.reference, native_deadline, caps=req.caps)
    else:
        with patch.object(ss, "milp", m10._configured_milp):
            result = ss.solve(shaped, req.design, caps=req.caps, fixed=req.fixed, exact_energy=True,
                              deadline=native_deadline)
    result["stats"].update(started_utc=start, seconds=perf_counter() - began,
                           cpu_seconds=process_time() - cpu, worker_pid=os.getpid())
    return result


def _replay(period, req, raw):
    if req.phase == "registration":
        proof = registration.audit_service_certificate(period, req.date, dict(req.locked), req.reference, raw)
        if raw["audit"] is None:
            if raw["schedule"] or raw["states"]:
                raise ValueError("Daily registration has an unverified schedule")
        else:
            audit = ss.meter_replay(period, req.design.hardware(), ss.eb.DEFAULT_SPEC, req.caps, raw, physical=True)
            m10._assert_close(audit, raw["audit"])
        return proof
    shaped = _shape(req, period)
    m10.replay(shaped, _legacy(req), raw)
    if req.phase == "fixed_service":
        stats = raw["stats"]
        if (stats["status"] == "bounded" or
                any(stats[k] not in (None, 0.) for k in ("objective_lower", "objective_upper"))):
            raise ValueError("A fixed-service certificate must use the zero feasibility objective")
    return None


def _effective(period, req, raw):
    if req.phase in {"energy", "rolling_energy"}:
        return m10._admitted_result(_shape(req, period), _legacy(req), raw)
    return {**raw, "stats": {**raw["stats"], "original_status": raw["stats"]["status"],
                             "widened_interval": False}}


def _archive(period, req, deadline, directory, starts, scope):
    m10._admit(deadline)
    label = req.identifier(scope)
    start = dict(scope=scope, request=asdict(req),
                 started_utc=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                 worker_pid=os.getpid())
    m10._publish(starts / (label + ".json"), m10._encoded(dict(body=start, sha256=m10._hash(start))))
    raw = _solve(period, req, deadline)
    body = dict(scope=scope, request=asdict(req), result=raw, start_sha256=m10._hash(start))
    m10._publish(directory / (label + ".json.gz"),
                 gzip.compress(m10._encoded(dict(body=body, sha256=m10._hash(body))), compresslevel=1, mtime=0))
    return label


def _read_envelope(data):
    envelope = json.loads(data)
    if envelope["sha256"] != m10._hash(envelope["body"]):
        raise ValueError("Stored evidence body differs from its checksum")
    return envelope["body"]


def _interrupted(start):
    return dict(stats=dict(status="unresolved", original_status="unresolved", status_code=None,
                           message="Started without a native certificate; this request is final unresolved",
                           objective=None, objective_lower=None, objective_upper=None, absolute_gap=None,
                           relative_gap=None, started_utc=start["started_utc"], seconds=0., cpu_seconds=0.,
                           worker_pid=start["worker_pid"], widened_interval=False),
                audit=None, states=[], schedule=[])


class FinalEvidence:
    """Record each request before solving, and recover incomplete requests without retrying."""
    def __init__(self, output, scenarios, *, deadline=math.inf, verify=False, workers=m10.WORKERS, scope=None):
        if not isinstance(workers, int) or not 1 <= workers <= m10.WORKERS:
            raise ValueError("Use between one and eight workers")
        self.directory = Path(output) / "certificates"
        self.starts = Path(output) / "native_starts"
        self.periods = {(scenario, p.days[0]["week_start"]): p for scenario, periods in scenarios.items() for p in periods}
        if sum(map(len, scenarios.values())) != len(self.periods):
            raise ValueError("More than one period per scenario and week")
        self.scope = m10._hash(dict(policy="second_holdout_native_v1", solver=m10.POLICY, binding=scope,
                                    periods={f"{s}/{w}": m10._hash([p.days, p.prices, p.cases, p.chains])
                                             for (s, w), p in self.periods.items()}))
        self.deadline, self.verify, self.workers = deadline, verify, workers
        self._pool = self._environment = None
        self._rows, self._requests = {}, {}
        self.unresolved = set()
        self._cached = lru_cache(maxsize=32)(self._read)

    def __enter__(self):
        if not self.verify:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.starts.mkdir(parents=True, exist_ok=True)
        if not self.directory.is_dir() or not self.starts.is_dir():
            raise ValueError("Missing sealed native ledger")
        started = {p.stem for p in self.starts.glob("*.json")}
        completed = {p.name.removesuffix(".json.gz") for p in self.directory.glob("*.json.gz")}
        if not completed <= started:
            raise ValueError("A native certificate has no started request")
        for label in sorted(started):
            self._index(label)
        if not self.verify:
            self._environment = patch.dict(os.environ, m10.WORKER_ENV)
            self._environment.__enter__()
        return self

    def __exit__(self, *exc):
        try:
            if self._pool is not None:
                self._pool.shutdown(wait=True, cancel_futures=True)
        finally:
            self._cached.cache_clear()
            if self._environment is not None:
                self._environment.__exit__(*exc)

    def _validate(self, req):
        period = self.periods.get((req.scenario, req.week))
        if period is None:
            raise ValueError("Unknown scenario or calendar week")
        if len(req.caps) != 2 or any(not 0 <= v <= k for v, k in zip(req.caps, req.design.caps, strict=True)):
            raise ValueError("Operating limits exceed rated hardware")
        if any(len(r) != len(set(r)) or not set(r) <= period.keys for r in (req.fixed, req.reference)):
            raise ValueError("Request references repeated or unknown duties")
        if req.phase == "registration":
            before = {k for k in period.keys if req.date is not None and k[0] < req.date}
            if (req.fixed or req.date not in period.cases or set(dict(req.locked)) != before
                    or len(dict(req.locked)) != len(req.locked)
                    or any(type(v) is not bool for _, v in req.locked)):
                raise ValueError("Daily registration must freeze all earlier eligible choices")
        elif req.phase in {"energy", "fixed_service", "rolling_energy"}:
            if req.locked or req.reference or not req.fixed:
                raise ValueError("A fixed-service request needs an exact nonempty register only")
            if req.phase == "rolling_energy":
                if req.date not in period.cases or any(k[0] != req.date for k in req.fixed):
                    raise ValueError("A rolling request is limited to its exact calendar day")
            elif req.date is not None:
                raise ValueError("A weekly request cannot specify a single calendar day")
        else:
            raise ValueError(f"Unknown request phase: {req.phase}")
        return period

    def _read(self, label):
        start_bytes = (self.starts / (label + ".json")).read_bytes()
        start = _read_envelope(start_bytes)
        req = FinalRequest(**{**start["request"], "design": ss.Design(**start["request"]["design"])})
        period = self._validate(req)
        if start["scope"] != self.scope or req.identifier(self.scope) != label:
            raise ValueError("Started request differs from the scope")
        file = self.directory / (label + ".json.gz")
        if not file.is_file():
            return req, _interrupted(start), None, hashlib.sha256(start_bytes).hexdigest()
        content = file.read_bytes()
        body = _read_envelope(gzip.decompress(content))
        if (body["scope"] != self.scope or body["request"] != start["request"]
                or body["start_sha256"] != m10._hash(start)):
            raise ValueError(f"Certificate does not match the started request: {label}")
        raw = body["result"]
        _replay(period, req, raw)
        return req, _effective(period, req, raw), hashlib.sha256(content).hexdigest(), hashlib.sha256(start_bytes).hexdigest()

    def _index(self, label):
        req, result, checksum, start_sha = self._cached(label)
        stats = result["stats"]
        fields = ("status", "original_status", "status_code", "message", "started_utc", "seconds", "cpu_seconds",
                  "worker_pid", "objective_lower", "objective_upper", "absolute_gap")
        self._rows[label] = dict(id=label, scenario=req.scenario, week=req.week, date=req.date,
                                 phase=req.phase, design=req.design.label, port_cap_kw=req.caps[0],
                                 warehouse_cap_kw=req.caps[1], started_sha256=start_sha, certificate_sha256=checksum,
                                 audited=result["audit"] is not None, **{key: stats[key] for key in fields})
        self._requests[label] = req

    @property
    def records(self):
        return [self._rows[k] for k in sorted(self._rows)]

    @property
    def new_records(self):
        return self.records

    def request_for(self, label):
        return self._requests[label]

    def get(self, label):
        if label not in self._rows:
            raise KeyError(label)
        return self._cached(label)[1]

    def is_new(self, request):
        return request.identifier(self.scope) not in self._rows

    def record_unresolved(self, request, *, group=None):
        policy = "rolling" if request.phase == "rolling_energy" else "full_information"
        self.unresolved.add(group if group is not None else
                            (request.scenario, request.week, request.design.label, request.caps, policy))

    def check(self, limit_unresolved=True):
        if limit_unresolved and len(self.unresolved) > ss.fc.MAX_UNRESOLVED:
            raise ss.fc.StudyLimit("More than three unresolved weekly groups")
        if not self.verify and monotonic() >= self.deadline:
            raise ss.fc.StudyLimit("Formal computation reached its closing reserve")

    def batch(self, requests):
        requests = list(requests)
        periods = [self._validate(req) for req in requests]
        labels = [req.identifier(self.scope) for req in requests]
        missing = {label: (period, req) for label, period, req in zip(labels, periods, requests, strict=True)
                   if label not in self._rows}
        if missing:
            if self.verify:
                raise ValueError(f"Missing sealed certificate {next(iter(missing))}")
            self._run(missing.values())
        return [(label, self.get(label)) for label in labels]

    def _run(self, requests):
        self.check(limit_unresolved=False)
        m10._admit(self.deadline)
        if self._pool is None:
            self._pool = ProcessPoolExecutor(self.workers, mp_context=multiprocessing.get_context("spawn"))
        todo, running, error = iter(requests), set(), None
        while True:
            while error is None and len(running) < self.workers:
                pair = next(todo, None)
                if pair is None:
                    break
                try:
                    m10._admit(self.deadline)
                    period, req = pair
                    running.add(self._pool.submit(_archive, period, req, self.deadline,
                                                  self.directory, self.starts, self.scope))
                except Exception as exc:
                    error = exc
            if not running:
                break
            done, running = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                try:
                    self._index(future.result())
                except Exception as exc:
                    if error is None:
                        error = exc
        if error is not None:
            # Even if a worker died, its published started marker makes the
            # interrupted request permanently distinct from one never started.
            for p in sorted(self.starts.glob("*.json")):
                if p.stem not in self._rows:
                    self._index(p.stem)
            raise error

    def verify_all(self):
        self._cached.cache_clear()
        for label, row in self._rows.items():
            _, _, checksum, start_sha = self._cached(label)
            if (checksum, start_sha) != (row["certificate_sha256"], row["started_sha256"]):
                raise ValueError(f"Certificate changed during audit: {label}")
        rows = self.records
        return dict(certificates=sum(r["certificate_sha256"] is not None for r in rows),
                    final_interrupted=sum(r["certificate_sha256"] is None for r in rows),
                    feasible_replayed=sum(r["audited"] for r in rows),
                    status_counts=dict(Counter(r["status"] for r in rows)),
                    unresolved_weekly_groups=len(self.unresolved))

    def repeat_spec(self, label):
        req = self.request_for(label)
        return "final", self.periods[req.scenario, req.week], req

    def determinism(self, seed=m10.AUDIT_SEED, count=20):
        return determinism_all([self], self.directory.parent, self.deadline,
                               seed=seed, count=count, verify=self.verify, workers=self.workers)


def _repeat(kind, period, request, deadline, destination, binding, checksum):
    if kind == "breakpoint":
        from .m10_breakpoint import repeat_certificate
        repeated = repeat_certificate(request, deadline)
        if (repeated["certificate_sha256"] != checksum
                or repeated["id"] != request.name.removesuffix(".json.gz")
                or type(repeated["match"]) is not bool):
            raise ValueError("Breakpoint repeat belongs to another native certificate")
        body = dict(binding=binding, certificate_sha256=checksum, breakpoint_comparison=repeated)
        m10._publish(destination, m10._encoded(dict(body=body, sha256=m10._hash(body))))
        return
    if kind == "final":
        raw = _solve(period, request, deadline)
        _replay(period, request, raw)
        result = _effective(period, request, raw)
    else:
        raw = m10._solve(period, request, deadline)
        m10.replay(period, request, raw)
        result = m10._admitted_result(period, request, raw) if kind == "legacy_wide" else raw
    body = dict(binding=binding, certificate_sha256=checksum, repeated=_meter_summary(result))
    m10._publish(destination, m10._encoded(dict(body=body, sha256=m10._hash(body))))


def determinism_all(ledgers, output, deadline, *, breakpoint_dir=None, seed=m10.AUDIT_SEED,
                    count=20, verify=False, workers=m10.WORKERS):
    """Draw one seed-locked sample across multiple native ledgers using fresh worker interpreters."""
    if not 1 <= workers <= m10.WORKERS or count < 0:
        raise ValueError("Invalid repeat worker or sample count")
    sources = {}
    for evidence in ledgers:
        for record in evidence.new_records if hasattr(evidence, "new_records") else evidence.records:
            label, checksum = record["id"], record["certificate_sha256"]
            if checksum is None:
                continue
            if label in sources:
                raise ValueError("Repeated native certificate identifier across ledgers")
            sources[label] = evidence, checksum, None
    if breakpoint_dir is not None:
        archive = Path(breakpoint_dir)
        if not archive.is_dir():
            raise ValueError("The completed breakpoint certificate directory is absent")
        for file in sorted(archive.glob("*.json.gz")):
            label = file.name.removesuffix(".json.gz")
            if label in sources:
                raise ValueError("Repeated breakpoint certificate identifier")
            sources[label] = None, hashlib.sha256(file.read_bytes()).hexdigest(), file
    labels = random.Random(seed).sample(sorted(sources), min(count, len(sources)))
    binding = m10._hash(dict(seed=seed, labels=[(label, sources[label][1]) for label in labels]))
    folder = Path(output) / "determinism" / binding
    if not verify:
        folder.mkdir(parents=True, exist_ok=True)
    pending = [label for label in labels if not (folder / (label + ".json")).is_file()]
    if verify and pending:
        raise ValueError("A registered repeat certificate is absent")
    for i in range(0, len(pending), workers):
        m10._admit(deadline)
        jobs = pending[i:i + workers]
        with patch.dict(os.environ, m10.WORKER_ENV), ProcessPoolExecutor(
                len(jobs), mp_context=multiprocessing.get_context("spawn"), max_tasks_per_child=1) as pool:
            futures = []
            for label in jobs:
                evidence, checksum, file = sources[label]
                if file is not None:
                    kind, period, request = "breakpoint", None, file
                elif hasattr(evidence, "repeat_spec"):
                    kind, period, request = evidence.repeat_spec(label)
                else:
                    request = evidence.request_for(label)
                    kind = "legacy_wide" if "original_status" in evidence.get(label)["stats"] else "legacy"
                    period = evidence.periods[request.week]
                futures.append(pool.submit(_repeat, kind, period, request, deadline,
                                           folder / (label + ".json"), binding, checksum))
            for future in futures:
                future.result()
    comparisons = []
    for label in labels:
        evidence, checksum, file = sources[label]
        body = _read_envelope((folder / (label + ".json")).read_bytes())
        if body["binding"] != binding or body["certificate_sha256"] != checksum:
            raise ValueError("Repeat record belongs to another request or source certificate")
        if file is not None:
            comparisons.append(body["breakpoint_comparison"])
            continue
        original, repeated = _meter_summary(evidence.get(label)), body["repeated"]
        fields = ("status", "original_status", "status_code", "schedule_sha256")
        checks = {key: original.get(key) == repeated.get(key) for key in fields}
        checks.update({key: _equals(original[key], repeated[key])
                       for key in ("objective_lower", "objective_upper", "meter")})
        comparisons.append(dict(id=label, original=original, repeated=repeated, checks=checks,
                                match=all(checks.values())))
    matched = sum(r["match"] for r in comparisons)
    return dict(seed=seed, requested=count, available=len(sources), sampled=len(labels), matched=matched,
                all_match=matched == len(labels), comparisons=comparisons)
