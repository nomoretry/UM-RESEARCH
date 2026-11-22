"""Twelve-week 23-window sensitivity with a freshly registered comparison cohort."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import json
import math
import multiprocessing
import os
from pathlib import Path
from time import monotonic, perf_counter, process_time
from unittest.mock import patch
import warnings

from scipy.optimize import Bounds, LinearConstraint, OptimizeResult
from scipy.sparse import coo_matrix

from . import holdout_service, m10_evidence as evidence, m10_inputs, site_sizing as ss
from .__main__ import checked_output, digest
from .m10_costs import _parameters
from .m10_policies import _write, elapsed
from .m10_policy_costs import invoices, point_key
from .m10_refine_work import CLOSING_SECONDS, ROUND_SECONDS
from .site_sizing_bounds import AnnualBillBounds, WholesaleRecord
from .site_sizing_screen import COST_MARGIN_EUR


MAIN_POINTS = (ss.Design(1, 40, 20), ss.Design(1, 20, 20))
BASES = ("new", "existing")
SPEC = ss.eb.DEFAULT_SPEC
METHOD = "12_week_23_window_sensitivity_v1"


def _week(period):
    return period.days[0]["week_start"]


def _m8_hardware():
    return ss.eb.read_json(ss.eb.REFERENCE)["hardware"]["one"]


def _scope(inputs):
    return evidence._hash(dict(method=METHOD, source=inputs.source_sha256,
                              original=sorted(inputs.main_reference), intervals=inputs.excluded_intervals,
                              m8_hardware=_m8_hardware(), policy=evidence.POLICY))


def _weights(period, preferred):
    """One integer score gives whole-week count, overlap, then ordered duty bits."""
    keys = sorted(period.keys, key=lambda key: (key[0], int(key[1])))
    if len(keys) > 38 or len({(d, int(v)) for d, v in keys}) != len(keys):
        raise ValueError("Weekly registration score exceeds its exact numerical domain")
    bits = 1 << len(keys)
    count = (len(preferred) + 1) * bits
    return {key: count + bits * (key in preferred) + (1 << (len(keys)-1-i))
            for i, key in enumerate(keys)}


def _week_score(period, preferred, result):
    stats = result["stats"]
    chosen = ss.eb.selected(result)
    weights = _weights(period, preferred)
    score = sum(weights[k] for k in chosen) if result["audit"] is not None else None
    bounds = holdout_service._integer_certificate(stats["native_mip_dual_bound"], score)
    if score is not None:
        ss.close(float(score), -stats["objective_upper"], "weighted M8 weekly service score")
    return bounds


class _LegacyWeekUnresolved(Exception):
    pass


def _m8_week(period, preferred, deadline):
    """Keep the original M8 model and extraction; replace only its objective and budget."""
    original_matrix = ss.eb.Matrix
    weights = _weights(period, preferred)
    begin = perf_counter()
    native = None

    class WeightedMatrix(original_matrix):
        def solve(self):
            nonlocal native
            # The legacy model declares one served variable and two SOC
            # variables per sorted duty before it adds any charging variables.
            columns = [3*i for i in range(len(period.keys))]
            if [i for i, cost in enumerate(self.cost) if cost == -1] != columns:
                raise ValueError("Legacy M8 served columns no longer match their declaration")
            for i, key in zip(columns, sorted(period.keys), strict=True):
                self.cost[i] = -weights[key]
            matrix = coo_matrix((self.data, (self.row, self.col)),
                                shape=(len(self.lb), len(self.cost))).tocsr()
            remaining = min(deadline, begin + ss.fc.SOLVE_SECONDS) - perf_counter()
            if remaining <= 0:
                raise ss.fc.StudyLimit("Sensitivity registration reached the wall deadline")
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Unrecognized options detected.*", category=RuntimeWarning)
                native = evidence._configured_milp(
                    self.cost, integrality=self.integer, bounds=Bounds(self.lower, self.upper),
                    constraints=LinearConstraint(matrix, self.lb, self.ub),
                    options=dict(time_limit=remaining, mip_rel_gap=0., mip_abs_gap=0.,
                                 mip_feasibility_tolerance=1e-9, primal_feasibility_tolerance=1e-9))
            if native.status != 0:
                raise _LegacyWeekUnresolved
            # The legacy physical replay's objective field is the served count.
            # Retain the native weighted objective separately below.
            return OptimizeResult(**{**native, "fun": -sum(native.x[i] > .5 for i in columns)})

    try:
        with patch.object(ss.eb, "Matrix", WeightedMatrix):
            result = ss.eb.solve(period, _m8_hardware(), SPEC, ss.eb.B)
    except _LegacyWeekUnresolved:
        result = dict(states=[], schedule=[], audit=None)
    stats = ss.fc._solve_stats(native, False, len(period.keys), perf_counter()-begin, 0., 0.)
    if result["audit"] is None:
        stats.update(objective_upper=None, objective=None, absolute_gap=None, relative_gap=None)
    else:
        stats["objective"] = -len(ss.eb.selected(result))
    result["stats"] = stats
    stats["integer_score_bounds"] = _week_score(period, preferred, result)
    if result["audit"] is not None and (stats["integer_score_bounds"][0] is None or
                                        len(set(stats["integer_score_bounds"])) != 1):
        raise ValueError("The weighted M8 registration is not uniquely certified")
    return result


def _request(phase, period, *, preferred=(), design=None, day=None, locked=None, fixed=None):
    return dict(phase=phase, week=_week(period), preferred=[list(k) for k in sorted(preferred)],
                design=asdict(design) if design is not None else None, day=day,
                locked=[[d, v, value] for (d, v), value in sorted((locked or {}).items())],
                fixed=None if fixed is None else [list(k) for k in sorted(fixed)])


def _energy_request(period, request):
    design = ss.Design(**request["design"])
    return evidence.Request.make(period, design, "breakpoint_energy", design.caps,
                                 fixed=set(map(tuple, request["fixed"])))


def _audit(period, request, result):
    stats, phase = result["stats"], request["phase"]
    if phase == "breakpoint_energy":
        evidence.replay(period, _energy_request(period, request), result)
        return
    if phase not in ("breakpoint_m8_registration", "breakpoint_m9_registration"):
        raise ValueError("Unknown sensitivity request")
    if result["audit"] is None:
        if stats["status"] == "certified" or result["schedule"] or result["states"]:
            raise ValueError("The sensitivity registration has incomplete evidence")
        return
    if {tuple((r["date"], r["vehicle_id"])) for r in result["states"]} != period.keys:
        raise ValueError("The sensitivity witness omits a duty state")
    if phase == "breakpoint_m8_registration":
        independent = ss.eb.audit(period, _m8_hardware(), SPEC, ss.eb.B, result, physical=True)
        bounds = _week_score(period, set(map(tuple, request["preferred"])), result)
        if stats["integer_score_bounds"] != bounds or bounds[0] != bounds[1]:
            raise ValueError("M8 sensitivity replay does not recover the integer certificate")
    else:
        locked = {(d, v): value for d, v, value in request["locked"]}
        independent = ss.meter_replay(period, ss.BASELINE.hardware(), SPEC, ss.BASELINE.caps,
                                      result, physical=True)
        holdout_service.audit_service_certificate(period, request["day"], locked, set(), result)
    evidence._assert_close(independent, result["audit"])


def _solve(period, request, deadline):
    evidence._admit(deadline)
    start = datetime.now(timezone.utc).isoformat()
    begin, cpu = perf_counter(), process_time()
    phase = request["phase"]
    if phase == "breakpoint_energy":
        result = evidence._solve(period, _energy_request(period, request), deadline)
    else:
        if phase == "breakpoint_m8_registration":
            result = _m8_week(period, set(map(tuple, request["preferred"])),
                              perf_counter()+deadline-monotonic())
        elif phase == "breakpoint_m9_registration":
            locked = {(d, v): value for d, v, value in request["locked"]}
            with patch.object(holdout_service, "milp", evidence._configured_milp):
                result = holdout_service.solve_service_day(
                    period, ss.BASELINE, request["day"], locked, set(), perf_counter()+deadline-monotonic())
        else:
            raise ValueError(f"Unknown sensitivity request {phase}")
        result["stats"].update(started_utc=start, seconds=perf_counter()-begin,
                               cpu_seconds=process_time()-cpu, worker_pid=os.getpid())
    _audit(period, request, result)
    return result


def _load_certificate(path, scope):
    envelope = json.loads(gzip.decompress(path.read_bytes()))
    body = envelope["body"]
    if (body["scope"] != scope or envelope["sha256"] != evidence._hash(body)
            or path.name != evidence._hash([scope, body["request"]]) + ".json.gz"):
        raise ValueError(f"Invalid sensitivity certificate: {path.name}")
    return body


def _call(period, request, directory, scope, deadline, verify):
    label = evidence._hash([scope, request])
    path = directory / (label + ".json.gz")
    if path.exists() or verify:
        body = _load_certificate(path, scope)
        if body["request"] != request:
            raise ValueError("Sensitivity proof request differs")
        result = body["result"]
        _audit(period, request, result)
    else:
        result = _solve(period, request, deadline)
        body = dict(scope=scope, request=request, result=result)
        envelope = dict(body=body, sha256=evidence._hash(body))
        evidence._publish(path, gzip.compress(evidence._encoded(envelope), compresslevel=1, mtime=0))
    if request["phase"] == "breakpoint_energy":
        result = evidence._admitted_result(period, _energy_request(period, request), result)
    return label, result


def repeat_certificate(path, deadline):
    """Repeat one selected native sensitivity request for a cross-phase audit."""
    path = Path(path)
    inputs = m10_inputs.load_inputs(sensitivity=True)
    body = _load_certificate(path, _scope(inputs))
    req, original = body["request"], body["result"]
    period, = [p for p in inputs.periods if _week(p) == req["week"]]
    _audit(period, req, original)
    repeated = _solve(period, req, deadline)
    a, b = evidence._summary(original), evidence._summary(repeated)
    keys = ("status", "status_code", "objective", "objective_lower", "objective_upper", "schedule_sha256")
    checks = {k: (math.isclose(a[k], b[k], rel_tol=0., abs_tol=ss.EPS)
                  if k in ("objective", "objective_lower", "objective_upper") and
                  a[k] is not None and b[k] is not None else a[k] == b[k]) for k in keys}
    try:
        evidence._assert_close(repeated["audit"], original["audit"])
        checks["meter_replay"] = True
    except (ValueError, TypeError):
        checks["meter_replay"] = False
    return dict(id=path.name.removesuffix(".json.gz"), certificate_sha256=digest(path), request=req,
                original=a, repeated=b, checks=checks, match=all(checks.values()))


def _register(period, m8, preferred, directory, scope, deadline, verify):
    selected, proof_ids = set(), []
    if m8:
        label, result = _call(period, _request("breakpoint_m8_registration", period, preferred=preferred),
                              directory, scope, deadline, verify)
        proof_ids.append(label)
        status = result["stats"]["status"]
        if status == "certified":
            selected = ss.eb.selected(result)
    else:
        status, locked = "certified", {}
        for day in sorted({d for d, _ in period.keys}):
            label, result = _call(period, _request("breakpoint_m9_registration", period,
                                                    design=ss.BASELINE, day=day, locked=locked),
                                  directory, scope, deadline, verify)
            proof_ids.append(label)
            status = result["stats"]["status"]
            if status != "certified":
                break
            today = {key for key in period.keys if key[0] == day}
            chosen = today & ss.eb.selected(result)
            locked.update({key: key in chosen for key in today})
            selected.update(chosen)
    return dict(week=_week(period), method="M8_week_count_overlap_id" if m8 else "M9_daily_count_id",
                status=status, selected=sorted(selected), proof_ids=proof_ids)


def _competing_ranges(inputs, reference, fixed_rows, bills):
    network, materials = _parameters(inputs.periods)
    bound = AnnualBillBounds(inputs.periods, reference, network, materials)
    records = defaultdict(list)
    for row in fixed_rows:
        design, = [d for d in MAIN_POINTS if row["design"] == d.label]
        records[row["week"]].append(WholesaleRecord(row["week"], design, design.caps,
                                                    row["purchase_lower"], row["evidence_id"]))
    best = {basis: min((row["total_upper"] for row in bills if row["connection_basis"] == basis),
                       default=math.inf) for basis in BASES}
    dispatch = ss.DispatchGrid(inputs.periods, reference, network, None)
    rows = []
    for design in ss.design_grid(ss.COARSE_KW):
        for caps in dispatch.options(design, ss.COARSE_KW):
            if design in MAIN_POINTS and caps == design.caps:
                continue
            value = bound.annual_lower_bounds(design, caps, records)["total_eur"]["official"]
            for basis in BASES:
                lower = value[basis]
                rows.append(dict(**point_key(design, caps), scenario="official", connection_basis=basis,
                                 interval_lower=lower if math.isfinite(lower) else None, interval_upper=None,
                                 interval_upper_meaning="no_independently_billed_upper_bound",
                                 potentially_competitive=math.isfinite(lower) and lower <= best[basis]+COST_MARGIN_EUR,
                                 proof="relaxed_meter_conservation_and_wholesale_bound" if math.isfinite(lower)
                                 else "relaxed_meter_capacity_infeasible"))
    return rows


def _analysis(inputs, directory, scope, deadline, verify):
    reg_jobs = [(p, i < 6, inputs.main_reference & p.keys, directory, scope, deadline, verify)
                for i,p in enumerate(inputs.periods)]
    with ProcessPoolExecutor(max_workers=evidence.WORKERS, mp_context=multiprocessing.get_context("spawn")) if not verify else _Serial() as pool:
        regs = list(pool.map(_register, *zip(*reg_jobs, strict=True)))
        if any(r["status"] != "certified" for r in regs):
            return dict(status="registration_unresolved", registration=regs), [], [], []
        reference = set(tuple(k) for r in regs for k in r["selected"])
        jobs = [(p, _request("breakpoint_energy", p, design=d, fixed=reference & p.keys),
                 directory, scope, deadline, verify) for d in MAIN_POINTS for p in inputs.periods]
        calls = list(pool.map(_call, *zip(*jobs, strict=True)))
    annual, weekly = [], []
    design_status = {}
    for i, design in enumerate(MAIN_POINTS):
        pairs = calls[i*len(inputs.periods):(i+1)*len(inputs.periods)]
        traces = []
        statuses = []
        for period, (label,result) in zip(inputs.periods, pairs, strict=True):
            stats = result["stats"]
            statuses.append(stats["status"])
            audit = result["audit"]
            traces.append(dict(purchase_lower=stats["objective_lower"], audit=audit))
            weekly.append(dict(**point_key(design, design.caps), week=_week(period), status=stats["status"],
                               purchase_lower=stats["objective_lower"], purchase_upper=stats["objective_upper"],
                               evidence_id=label, registered=sorted(reference & period.keys),
                               meter=None if audit is None else {k:audit[k] for k in
                                   ("site_grid_kwh","site_quarter_peak_kw","purchase_eur")}))
        physical = False if "infeasible" in statuses else (True if all(x["audit"] is not None for x in traces) else None)
        certified = set(statuses) <= ss.ENERGY_ACCEPTED
        design_status[design.label] = dict(completes_registered=physical, bill_admitted=certified,
                                          weeks=Counter(statuses))
        if certified:
            annual.extend(dict(**point_key(design, design.caps), **row)
                          for row in invoices(inputs.periods, design, traces) if row["scenario"] == "official")
    ranges = _competing_ranges(inputs, reference, weekly, annual)
    unknown = {basis:sum(r["connection_basis"] == basis and r["potentially_competitive"] for r in ranges)
               for basis in BASES}
    report = dict(status="complete", registered=len(reference), original_registered=len(inputs.main_reference),
                  registered_m8=sum(len(r["selected"]) for r in regs[:6]),
                  registered_m9=sum(len(r["selected"]) for r in regs[6:]),
                  added=sorted(reference-inputs.main_reference), removed=sorted(inputs.main_reference-reference),
                  primary_points=design_status, registration=regs,
                  rank_status={basis:"unresolved" if n else "no_unbilled_coarse_point_threatens"
                               for basis,n in unknown.items()}, potentially_competitive_points=unknown,
                  competition_coverage="priced coarse operating limits; no competing optimization",
                  time_limit_per_request_s=ss.fc.SOLVE_SECONDS,
                  accepted_timeout_width_eur=evidence.CONTINUATION_TIMEOUT_GAP_EUR)
    return report, annual, weekly, ranges


class _Serial:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    map = staticmethod(map)


def run(output, *, started=None, verify=False):
    if not verify:
        checked_output(output, ss.eb.ROOT)
        output.mkdir()
    inputs = m10_inputs.load_inputs(sensitivity=True)
    scope = _scope(inputs)
    directory = output / "certificates"
    if not verify:
        directory.mkdir()
    deadline = math.inf if verify else monotonic()+ROUND_SECONDS-CLOSING_SECONDS-elapsed(started)
    try:
        with patch.dict(os.environ, evidence.WORKER_ENV):
            report, annual, weekly, ranges = _analysis(inputs, directory, scope, deadline, verify)
    except ss.fc.StudyLimit as exc:
        if verify:
            raise
        report, annual, weekly, ranges = dict(status="stopped_clock", reason=str(exc)), [], [], []
    journal = []
    for path in sorted(directory.glob("*.json.gz")):
        body = _load_certificate(path, scope)
        request, stats = body["request"], body["result"]["stats"]
        journal.append(dict(id=path.name.removesuffix(".json.gz"), **request, certificate_sha256=digest(path),
                            **{k:stats[k] for k in ("status","status_code","started_utc","seconds","cpu_seconds",
                                                  "objective_lower","objective_upper","absolute_gap","worker_pid")}))
    report.update(scope=scope, input_sha256=inputs.source_sha256, excluded_intervals=inputs.excluded_intervals,
                  native_requests=len(journal), native_status=Counter(r["status"] for r in journal),
                  solver_seconds=math.fsum(r["seconds"] for r in journal),
                  first_native_utc=min((r["started_utc"] for r in journal),default=None))
    tables = {"summary.json":report, "annual_bills.csv":annual, "weekly_points.csv":weekly,
              "competitor_intervals.csv":ranges, "solves.csv":journal}
    if verify:
        if report != json.loads(evidence._encoded(json.loads((output/"summary.json").read_bytes()))):
            if evidence._encoded(report) != evidence._encoded(json.loads((output/"summary.json").read_bytes())):
                raise ValueError("Sensitivity summary differs from its archived replay")
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            for name, value in tables.items():
                target = Path(temporary)/name
                _write(target,value)
                if target.read_bytes() != (output/name).read_bytes():
                    raise ValueError(f"Sensitivity replay differs: {name}")
    else:
        for name,value in tables.items():
            _write(output/name,value)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--verify", type=Path)
    parser.add_argument("--started", type=datetime.fromisoformat)
    args = parser.parse_args(argv)
    if args.output and not args.started:
        parser.error("--output requires the timezone-aware first progress timestamp")
    report = run(args.verify or args.output, started=args.started, verify=args.verify is not None)
    print(evidence._encoded(report).decode("utf-8"))
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
