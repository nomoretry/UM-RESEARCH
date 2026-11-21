"""Certify the twelve-week registered service on the coarse hardware grid."""
from dataclasses import asdict
import gzip
import json

from . import holdout_inputs as hi
from . import m10_inputs
from . import site_sizing as ss
from .__main__ import digest
from .m10_evidence import Request


GATES = (ss.BASELINE, ss.Design(1, 20, 20), ss.Design(1, 40, 20))
MISSING_DUTY = ("2021-11-26", "1")
M9_PORT_ONLY = ss.Design(1, 50, 0)


def _week(period):
    return period.days[0]["week_start"]


def _m9_proof(archive, period, fixed):
    """Match the published ledger, physical input and full dated duty request."""
    published = ss.eb.read_json(m10_inputs.M9_REGISTRATION)
    manifest = ss.eb.read_json(archive / "manifest.json")
    ledger = archive / "solves.jsonl"
    if (digest(ledger) != published["ledger_sha256"]
            or manifest["input_hashes"] != published["inputs_sha256"]
            or manifest["source_commit"] != published["source_commit"]):
        raise ValueError("M9 source, ledger or input hashes differ from the published registration")
    original, = [p for p in hi.load_periods() if _week(p) == _week(period)]
    if vars(original) != vars(period):
        raise ValueError("M9 fixed-R calendar, released windows, prices or chain boundaries differ")
    request = dict(sample="fixed_R", week=_week(period), design=M9_PORT_ONLY.label,
                   caps=list(M9_PORT_ONLY.caps), phase="dispatch", day=None,
                   duties=[list(k) for k in sorted(fixed)], locked=[])
    with ledger.open(encoding="utf-8") as stream:
        rows = [r for line in stream if (r := json.loads(line))["request"] == request]
    if len(rows) != 1:
        raise ValueError("The exact M9 no-warehouse fixed-R request is absent or duplicated")
    row, = rows
    path = archive / row["file"]
    if digest(path) != row["sha256"] or row["status"] != "infeasible" or row["audited"]:
        raise ValueError("Invalid M9 fixed-R infeasibility record")
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        result = json.load(stream)
    if (result["stats"]["status_code"] != 2 or result["stats"]["status"] != "infeasible"
            or result["audit"] is not None):
        raise ValueError("M9 certificate does not establish infeasibility")
    return dict(source_commit=manifest["source_commit"], ledger_sha256=published["ledger_sha256"],
                certificate=row["file"], certificate_sha256=row["sha256"], request=request,
                hardware=M9_PORT_ONLY.hardware(), status_code=2)


def no_warehouse_proofs(inputs, designs, archive):
    """Check each design against the port-only proof or a one-truck relaxation."""
    period, = [p for p in inputs.periods if MISSING_DUTY in p.keys]
    fixed = inputs.registered & period.keys
    if MISSING_DUTY not in fixed:
        raise ValueError("The preregistered no-warehouse witness is outside the weekly registration")
    old = _m9_proof(archive, period, fixed)
    # A truck that has exclusive use of a 100-kW port (50 kW on board) has
    # no charger sharing or site-power restriction. Every possible carry-over
    # segment containing the missing duty is tested, even outside the fixed R.
    relaxation = hi.diagnose_fixed(period, MISSING_DUTY, ss.Design(2, 100, 0))
    exclusions = {}
    for design in designs:
        if design.warehouse_kw:
            continue
        if ss._dominates(M9_PORT_ONLY, design):
            method = "m9_fixed_R_infeasible_superset"
        elif not relaxation["single_truck_relaxation_feasible"]:
            method = "all_single_truck_segments_infeasible"
        else:
            continue  # This design must receive its own fixed-R weekly solve.
        exclusions[design.label] = dict(
            id=f"no-warehouse-{design.label}", method=method, hardware=design.hardware(),
            caps_kw=list(design.caps), week=_week(period), fixed=old["request"]["duties"],
            signed_energy="charging_only", vehicle_limit_kw=ss.eb.DEFAULT_SPEC.truck_kw)
    return dict(m9=old, single_truck_relaxation=relaxation, exclusions=exclusions)


def _witness(period, design, result, fixed, *, physical):
    """Replay schedules under the hardware being credited, including inherited witnesses."""
    if result["audit"] is None:
        return None
    selected = ss.eb.selected(result)
    if not physical and selected != fixed:
        raise ValueError(("fixed-R certificate selects different duties", design.label, _week(period)))
    checked = ss.meter_replay(period, design.hardware(), ss.eb.DEFAULT_SPEC, design.caps,
                              result, physical=physical)
    if not checked["passed"]:
        raise ValueError(("service witness failed independent replay", design.label, _week(period)))
    return selected


def _weekly(period, fixed, status, selected, evidence_id, witness_id, method, witness_design, *,
            count_bounds=None, certified_max=False, physical=False):
    return dict(week=_week(period), status=status, evidence_id=evidence_id, witness_id=witness_id,
                method=method, witness_design=witness_design.label, witness_physical=physical,
                registered=[list(k) for k in sorted(fixed)], served=[list(k) for k in sorted(selected)],
                maximum_service_bounds=count_bounds, maximum_service_certified=certified_max)


def _gate(design, inputs, evidence):
    requests = [Request.make(p, design, "energy", design.caps, fixed=inputs.registered & p.keys)
                for p in inputs.periods]
    rows = []
    for period, (label, result) in zip(inputs.periods, evidence.batch(requests), strict=True):
        fixed = inputs.registered & period.keys
        selected = _witness(period, design, result, fixed, physical=False)
        if selected is None:
            raise ss.fc.StudyLimit(
                f"rated service check stopped: {design.label} {_week(period)} "
                f"{result['stats']['status']} ({label})")
        rows.append(_weekly(period, fixed, "complete", selected, label, label, "rated_fixed_R", design))
    return rows


def _remaining(design, inputs, evidence, known, proofs):
    rows, requests, pending = {}, [], []
    for i, period in enumerate(inputs.periods):
        fixed = inputs.registered & period.keys
        witness = next((weeks[i] for small, weeks in known.items() if ss._dominates(design, small)
                        and weeks[i]["status"] == "complete"), None)
        if witness:
            label = witness["witness_id"]
            physical = witness["witness_physical"]
            selected = _witness(period, design, evidence.get(label), fixed, physical=physical)
            if selected != fixed:
                raise ValueError("A monotone service witness selects different duties")
            rows[i] = dict(witness, method="monotone_replay")
        else:
            pending.append(i)
            requests.append(Request.make(period, design, "service", design.caps, prefer=fixed))
    fallback = {}
    exclusion = proofs["exclusions"].get(design.label)
    for i, (label, result) in zip(pending, evidence.batch(requests), strict=True):
        period = inputs.periods[i]
        fixed = inputs.registered & period.keys
        selected = _witness(period, design, result, fixed, physical=True)
        stats = result["stats"]
        row = _weekly(period, fixed, "unresolved", selected or set(), label, label,
                      "maximum_service", design, count_bounds=stats["completed_bounds"],
                      certified_max=stats["status"] == "certified", physical=True)
        if exclusion and exclusion["week"] == _week(period):
            if selected == fixed:
                raise ValueError(("fixed-R witness contradicts no-warehouse proof", design.label))
            row.update(status="shortfall", evidence_id=exclusion["id"], method=exclusion["method"])
        elif selected == fixed:
            row["status"] = "complete"
        else:
            fallback[i] = Request.make(period, design, "energy", design.caps, fixed=fixed)
        rows[i] = row
    for i, (label, result) in zip(fallback, evidence.batch(list(fallback.values())), strict=True):
        period = inputs.periods[i]
        fixed = inputs.registered & period.keys
        selected = _witness(period, design, result, fixed, physical=False)
        row = rows[i]
        if selected is not None:
            row.update(status="complete", evidence_id=label, witness_id=label, method="rated_fixed_R",
                       served=[list(k) for k in sorted(selected)], witness_physical=False)
        else:
            infeasible = result["stats"]["status"] == "infeasible"
            # A proven maximum smaller than |R| also excludes R, even if the
            # direct fixed-R solve times out. Omission by an equal-size witness alone cannot.
            maximum = row["maximum_service_bounds"][1]
            count_proof = maximum is not None and maximum < len(fixed)
            row.update(status="shortfall" if infeasible or count_proof else "unresolved",
                       evidence_id=label if infeasible or not count_proof else row["witness_id"],
                       fixed_check_id=label, method="rated_fixed_R" if infeasible else
                       "maximum_below_registered_count" if count_proof else "fixed_R_unresolved")
    return [rows[i] for i in range(len(inputs.periods))]


def _summarize(design, weeks, proofs):
    matrix = []
    statuses = {w["status"] for w in weeks}
    verdict = "shortfall" if "shortfall" in statuses else "unresolved" if "unresolved" in statuses else "complete"
    for row in weeks:
        selected = set(map(tuple, row["served"]))
        for date, truck in row["registered"]:
            key = date, truck
            status, source = "unresolved", row["evidence_id"]
            if key in selected:
                status, source = "completed", row["witness_id"]
            elif (design.warehouse_kw == 0 and key == MISSING_DUTY and
                  not proofs["single_truck_relaxation"]["single_truck_relaxation_feasible"]):
                status, source = "not_completed", "single_truck_relaxation"
            elif row["status"] == "shortfall" and row["maximum_service_certified"]:
                status, source = "not_completed", row["witness_id"]
            matrix.append(dict(design=design.label, date=date, vehicle_id=truck,
                               status=status, evidence_id=source))
    def keys(status):
        return [[r["date"], r["vehicle_id"]] for r in matrix if r["status"] == status]
    summary = dict(design=design.label, **asdict(design), same_service=verdict == "complete", status=verdict,
                   completed_registered=len(keys("completed")), lost_vs_reference=keys("not_completed"),
                   unresolved_vs_reference=keys("unresolved"), weeks=weeks)
    return summary, matrix


def service_grid(inputs, evidence, *, m9_archive, progress=None):
    """Return hardware summaries, one row per registered duty and no-warehouse proofs."""
    designs = ss.design_grid(ss.COARSE_KW)
    proofs = no_warehouse_proofs(inputs, designs, m9_archive)
    known, service, matrix = {}, {}, []
    for design in GATES:
        known[design] = _gate(design, inputs, evidence)
        if progress:
            progress(f"额定功率服务核验 {design.label}，{len(inputs.periods)} 周，"
                     f"完成登记的 {len(inputs.registered)} 个车日。")
    for design in designs:
        evidence.check()
        if design not in known:
            known[design] = _remaining(design, inputs, evidence, known, proofs)
        service[design], duties = _summarize(design, known[design], proofs)
        matrix.extend(duties)
    # Compare all warehouse-only M8 weeks against the published maximum count
    # for the same hardware. Tie solutions may use different vehicle-days.
    m8 = ss.eb.read_json(ss.eb.WEEKS.with_name("site_sizing.json"))
    old = {r["design"]: r for r in m8["service"]}
    comparison = {}
    for design in designs:
        if design.port_plugs != 0:
            continue
        first = known[design][:6]
        expected = old[design.label]["completed"]
        bounds = [w["maximum_service_bounds"] for w in first]
        lower = sum(b[0] for b in bounds) if all(b is not None for b in bounds) else None
        upper = sum(b[1] for b in bounds) if all(b is not None for b in bounds) else None
        if lower is not None and not lower <= expected <= upper:
            raise ValueError(("warehouse-only maximum differs from M8", design.label, lower, upper, expected))
        comparison[design.label] = dict(published_maximum=expected, m10_maximum_bounds=[lower, upper])
    proofs["warehouse_only_m8"] = comparison
    return service, matrix, proofs
