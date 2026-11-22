"""A read-only coarse archive and a separate, resumable ledger for policy-day and full-week requests."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import csv
import hashlib
import json
import math
import multiprocessing
from pathlib import Path
import random

from . import m10_evidence as m10, site_sizing as ss
from .m10_rolling import rolling_day_period

Request = m10.Request


def _meter_summary(result):
    audit = result["audit"]
    return {**m10._summary(result), "meter": None if audit is None else {
        key: audit[key] for key in ("purchase_eur", "site_grid_kwh", "site_quarter_peak_kw")}}


def _repeat(period, req, deadline, path, original_checksum, sample_hash):
    raw = m10._solve(period, req, deadline)
    m10.replay(period, req, raw)
    effective = m10._admitted_result(period, req, raw)
    body = dict(sample_sha256=sample_hash, certificate_sha256=original_checksum, repeated=_meter_summary(effective))
    m10._publish(path, m10._encoded(dict(body=body, sha256=m10._hash(body))))


def _equals(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equals(v, b[k]) for k, v in a.items())
    if a is None or b is None:
        return a is b
    return math.isclose(a, b, rel_tol=0, abs_tol=ss.EPS)


class PolicyEvidence(m10.M10Evidence):
    def __init__(self, output, inputs, coarse_archive, *, deadline=math.inf, verify=False, workers=m10.WORKERS):
        super().__init__(output, inputs, workers=workers, deadline=deadline, verify=verify)
        if workers > m10.WORKERS:
            raise ValueError("The policy study permits at most eight solver workers")
        self._reference = inputs.registered
        self._parent = None
        self._inherited_ids = set()
        self._day_to_week = {}
        self._active_days_by_week = {}
        self._calendar_week = set(self.periods)
        for week, period in list(self.periods.items()):
            self._active_days_by_week[week] = set()
            for day in period.cases:
                if any(d == day for d, _ in period.keys & self._reference):
                    key = "day:" + day
                    self._day_to_week[key] = week
                    self._active_days_by_week[week].add(key)
                    self.periods[key] = rolling_day_period(period, day, self._reference)
        seal_sha = None
        if coarse_archive is not None:
            coarse = Path(coarse_archive).resolve()
            if self.directory.resolve().is_relative_to(coarse):
                raise ValueError("The policy ledger must be outside the coarse archive")
            seal_bytes = (coarse / "seal.json").read_bytes()
            sealed_ledger = json.loads(seal_bytes)["products"]["solves.csv"]
            if hashlib.sha256((coarse / "solves.csv").read_bytes()).hexdigest() != sealed_ledger:
                raise ValueError("Coarse source ledger differs from its seal")
            seal_sha = hashlib.sha256(seal_bytes).hexdigest()
            self._parent = m10.M10Evidence(coarse, inputs, verify=True, parent_archive=coarse / "inherited")
        self.scope = m10._hash(dict(source_scope=self.scope, coarse_seal=seal_sha, daily_terminal_kwh=150,
                                    fixed_service="registered_only", timeout_eur_per_week=.10,
                                    dispatch="current_day_released_windows_v1"))
        self._new_group_status = {}

    def __enter__(self):
        if self._parent is not None:
            self._parent.__enter__()
            self._inherited_ids = {row["id"] for row in self._parent.records}
            with (self._parent.directory.parent / "solves.csv").open(encoding="utf-8", newline="") as stream:
                sealed = {row["id"]: row["certificate_sha256"] for row in csv.DictReader(stream)}
            if sealed != {row["id"]: row["certificate_sha256"] for row in self._parent.records}:
                raise ValueError("Inherited certificate bytes differ from the sealed coarse ledger")
        super().__enter__()
        return self

    def __exit__(self, *exc):
        try:
            super().__exit__(*exc)
        finally:
            if self._parent is not None:
                self._parent.__exit__(*exc)

    def _read(self, label):
        req, raw, checksum = super()._read(label)
        self._validate(req)
        return req, m10._admitted_result(self.periods[req.week], req, raw), checksum

    def _validate(self, req):
        daily = req.phase == "rolling_energy" and req.week in self._day_to_week
        weekly = req.phase == "energy" and req.week in self._calendar_week
        if not (daily or weekly):
            raise ValueError("Unknown formal policy request or calendar day")
        period = self.periods[req.week]
        if (req.fixed != tuple(sorted(period.keys & self._reference)) or req.prefer
                or len(req.caps) != 2 or any(c < 0 or c > h for c, h in zip(req.caps, req.design.caps, strict=True))):
            raise ValueError("Formal policy request differs from the frozen service or limits")

    def _index(self, label):
        super()._index(label)
        req = self._requests[label]
        data = self._rows[label]
        data["source_round"] = "R014"
        data["calendar_week"] = self._day_to_week.get(req.week, req.week)
        data.update(original_status=self.get(label)["stats"]["original_status"], certificate_origin="current")
        self.unresolved.discard((req.week, req.design, req.caps))
        group = (data["calendar_week"], req.design.label, req.caps, req.phase)
        members = self._new_group_status.setdefault(group, {})
        members[req.week] = (data["status"], data["absolute_gap"])
        statuses = {s for s, _ in members.values()}
        full_rolling = req.phase == "rolling_energy" and members.keys() == self._active_days_by_week[group[0]]
        aggregate_wide = full_rolling and "bounded" in statuses and all(g is not None for _, g in members.values()) and (
            math.fsum(g for _, g in members.values()) > m10.CONTINUATION_TIMEOUT_GAP_EUR)
        # A partial batch can end before another date proves the complete
        # weekly task list infeasible. Count only adjudicated weekly groups.
        completed_group = req.phase != "rolling_energy" or full_rolling
        if completed_group and ("unresolved" in statuses or aggregate_wide) and "infeasible" not in statuses:
            self.unresolved.add(group)
        elif completed_group:
            self.unresolved.discard(group)

    def record_rolling_week(self, result):
        group = (result["week"], result["design"], tuple(result["caps_kw"]), "rolling_energy")
        if result["status"] == "unresolved":
            self.unresolved.add(group)
        else:
            self.unresolved.discard(group)
        self.check()

    @property
    def new_records(self):
        return super().records

    @property
    def records(self):
        old = [] if self._parent is None else [{**r, "source_round": "R012", "calendar_week": r["week"]}
                                                for r in self._parent.records]
        return old + self.new_records

    def request_for(self, label):
        return self._parent.request_for(label) if label in self._inherited_ids else super().request_for(label)

    def get(self, label):
        return self._parent.get(label) if label in self._inherited_ids else super().get(label)

    def batch(self, requests):
        requests = list(requests)
        pending, ids = [], []
        for req in requests:
            self._validate(req)
            parent_id = req.identifier(self._parent.scope) if self._parent is not None else None
            if parent_id in self._inherited_ids:
                ids.append(parent_id)
            else:
                ids.append(req.identifier(self.scope))
                pending.append(req)
        super().batch(pending)
        return [(label, self.get(label)) for label in ids]

    def verify_all(self):
        old = self._parent.verify_all() if self._parent is not None else {}
        self._read_cached.cache_clear()
        for label, row in self._rows.items():
            req, raw, checksum = m10.M10Evidence._read(self, label)
            if row["certificate_sha256"] != checksum:
                raise ValueError("Changed policy certificate")
            m10.replay(self.periods[req.week], req, raw)
            self._read_cached(label)
        counts = Counter(r["status"] for r in self.new_records)
        total = counts + Counter(old.get("status_counts", {}))
        new_feasible = sum(r["audited"] for r in self.new_records)
        return dict(certificates=sum(total.values()), new_certificates=len(self._rows),
                    inherited_certificates=len(self._inherited_ids), new_feasible_replayed=new_feasible,
                    feasible_replayed=new_feasible+old.get("feasible_replayed", 0),
                    status_counts=dict(total), new_status_counts=dict(counts),
                    unresolved_weekly_groups=len(self.unresolved))

    def determinism(self, seed=m10.AUDIT_SEED, count=20):
        self.check()
        labels = random.Random(seed).sample(sorted(self._rows), min(count, len(self._rows)))
        binding = m10._hash(dict(scope=self.scope, seed=seed, labels=labels))
        directory = self.directory.parent / "determinism" / binding
        if not self.verify:
            directory.mkdir(parents=True, exist_ok=True)
        if self._pool is not None:
            self._pool.shutdown(wait=True)
            self._pool = None
        pending = [label for label in labels if not (directory / (label + ".json")).is_file()]
        if self.verify and pending:
            raise ValueError("A sealed policy repeat is missing")
        for i in range(0, len(pending), self.workers):
            m10._admit(self.deadline)
            group = pending[i:i + self.workers]
            with ProcessPoolExecutor(len(group), mp_context=multiprocessing.get_context("spawn"),
                                     max_tasks_per_child=1) as pool:
                tasks = [pool.submit(_repeat, self.periods[self._requests[k].week], self._requests[k],
                                     self.deadline, directory / (k + ".json"), self._rows[k]["certificate_sha256"],
                                     binding) for k in group]
                for task in tasks:
                    task.result()
        comparisons = []
        for label in labels:
            envelope = json.loads((directory / (label + ".json")).read_bytes())
            body = envelope["body"]
            if (m10._hash(body) != envelope["sha256"] or body["sample_sha256"] != binding
                    or body["certificate_sha256"] != self._rows[label]["certificate_sha256"]):
                raise ValueError("Policy repetition certificate does not match its original")
            original, repeated = _meter_summary(self.get(label)), body["repeated"]
            checks = dict(status_equal=original["status"] == repeated["status"],
                          original_status_equal=original["original_status"] == repeated["original_status"],
                          objective_equal=_equals(original["objective"], repeated["objective"]),
                          bounds_equal=all(_equals(original[k], repeated[k]) for k in ("objective_lower","objective_upper")),
                          schedule_equal=original["schedule_sha256"] == repeated["schedule_sha256"],
                          meter_equal=_equals(original["meter"], repeated["meter"]))
            comparisons.append(dict(id=label, **checks, match=all(checks.values()), original=original, repeated=repeated))
        matched = sum(r["match"] for r in comparisons)
        return dict(seed=seed, requested=count, available=len(self._rows), sampled=len(labels), matched=matched,
                    all_match=matched == len(labels), comparisons=comparisons)
