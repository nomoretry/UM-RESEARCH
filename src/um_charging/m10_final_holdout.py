"""Execute the frozen holdout matrix on separately supplied calendar periods."""
from copy import deepcopy
import json

from . import energy_boundary as eb, site_sizing as ss
from .holdout_inputs import diagnose_fixed
from .m10_final_evidence import FinalRequest
from .m10_immediate import simulate_week
from .m10_policy_grid import _rolling_days
from .m10_rolling import rolling_requests, rolling_week


F20 = ss.Design(1, 20, 20)
F40 = ss.Design(1, 40, 20)
B = ss.BASELINE
I = ss.Design(2, 100, 20)
D30 = ss.Design(1, 30, 20)
FULL, ROLLING, IMMEDIATE = "full", "rolling", "immediate"
MAIN, PARKING = "main", "parking_gap"
ACTIVITIES = (("energy_plus_10", 1.10), ("energy_plus_20", 1.20))
TARIFFS = ("N0", "frank", "official", "capacity_0", "capacity_22_79", "capacity_208_38")
BASES = ("new", "existing")
ACCEPTED = frozenset(ss.ENERGY_ACCEPTED)
PASSED = "passed"
VERIFIED_FAILURE = "failure_independent"
NATIVE_FAILURE = "failure_solver_only"
UNRESOLVED = "unresolved"


def week_of(period):
    return period.days[0]["week_start"]


def point_id(policy, design, caps):
    return f"{policy}:{design.label}:{caps[0]}:{caps[1]}"


def build_plan(matrix):
    """Confirm exact archived operating points before releasing any work."""
    builds = {d.label: d for d in (F20, F40, B, I, D30)}
    expected = {
        FULL: [(F20, F20.caps), (F40, (20, 20)), (F40, F40.caps),
               (B, (20, 20)), (B, (50, 20)), (B, B.caps)],
        ROLLING: [(F20, F20.caps), (D30, D30.caps), (F40, F40.caps)],
        IMMEDIATE: [(F20, F20.caps), (F40, F40.caps), (I, I.caps)],
    }
    plans = {}
    for mode, points in expected.items():
        stored = [(builds[label], tuple(caps)) for label, caps in matrix[mode]]
        if len(stored) != len(points) or set(stored) != set(points):
            raise ValueError(f"Archived holdout matrix changed for {mode}")
        plans[mode] = stored
    union = matrix["union"]
    if (union["design"], tuple(json.loads(union["caps_kw"])),
            union["all_weekly_minima_classified"]) != (F40.label, F40.caps, "True"):
        raise ValueError("The frozen weekly union changed")
    frozen = {(r["scenario"], r["connection_basis"]):
              (r["design"], (int(r["port_cap_kw"]), int(r["warehouse_cap_kw"])))
              for r in matrix["frozen_full_information"]}
    expected_frozen = {}
    for tariff in TARIFFS:
        for basis in BASES:
            d = F40 if tariff in ("N0", "official") or (tariff, basis) == ("frank", "existing") else F20
            expected_frozen[tariff, basis] = d.label, d.caps
    if len(matrix["frozen_full_information"]) != 12 or frozen != expected_frozen:
        raise ValueError("Twelve archived full-information roles changed")
    for mode, required in ((IMMEDIATE, I), (ROLLING, None)):
        selected = matrix["policies"][mode]
        choices = {(r["scenario"], r["connection_basis"]): (r["design"], tuple(r["caps"])) for r in selected}
        if len(selected) != 12 or choices != {
                (tariff, basis): (d.label, d.caps)
                for tariff in TARIFFS for basis in BASES
                for d in (required or (D30 if tariff == "capacity_208_38" else F40),)}:
            raise ValueError(f"Archived operating-policy selection changed for {mode}")
    return plans


def scenario_periods(main_periods, parking_periods):
    """Keep all duties, dates, native prices and links fixed when scaling trip kWh."""
    result = {MAIN: list(main_periods), PARKING: list(parking_periods)}
    for name, factor in ACTIVITIES:
        scaled = []
        for period in result[MAIN]:
            days = deepcopy(period.days)
            for day in days:
                for truck in day["vehicles"]:
                    for trip in truck["trips"]:
                        trip["energy_kwh"] = float(trip["energy_kwh"]) * factor
            variant = eb.Period(days, period.prices)
            if variant.keys != period.keys or variant.chains != period.chains or variant.links != period.links:
                raise ValueError("Scaling energy changed the physical service calendar")
            scaled.append(variant)
        result[name] = scaled
    main = {week_of(p): p for p in result[MAIN]}
    parking = {week_of(p): p for p in result[PARKING]}
    if not main or list(main) != list(parking) or len(main) != len(result[MAIN]):
        raise ValueError("The parking variant must preserve every complete calendar week")
    for w, p in parking.items():
        original = main[w]
        if (p.keys, p.chains, p.links, p.prices) != (original.keys, original.chains, original.links, original.prices):
            raise ValueError("Parking eligibility changed dates, tasks, prices, or carry-over evidence")
        for day, case in p.cases.items():
            for vehicle, truck in case["trucks"].items():
                old = original.cases[day]["trucks"][vehicle]
                if truck["trips"] != old["trips"] or not set(truck["windows"]) <= set(old["windows"]):
                    raise ValueError("Parking eligibility changed trips or added windows")
    return result


def _zero_audit():
    return dict(passed=True, purchase_eur=0., daily_eur={}, site_grid_kwh=dict.fromkeys(ss.SITES, 0.),
                site_quarter_peak_kw=dict.fromkeys(ss.SITES, 0.), site_peak_kw=dict.fromkeys(ss.SITES, 0.))


def _zero(period):
    return dict(week=week_of(period), fixed=[], status="certified", service=PASSED, proof_id=None,
                source="empty_registered_set", purchase_lower=0., purchase_upper=0.,
                audit=_zero_audit(), schedule=[], states=[], days=[])


def _known_failure(rows):
    failures = [r["week"] for r in rows if r["service"] in (VERIFIED_FAILURE, NATIVE_FAILURE)]
    return failures


class _Execution:
    def __init__(self, scenarios, matrix, evidence, save, progress):
        if set(scenarios) != {MAIN, PARKING, *(s for s, _ in ACTIVITIES)}:
            raise ValueError("Expected main, parking and both energy-margin calendar variants")
        self.scenarios = scenarios
        self.matrix = matrix
        self.evidence = evidence
        self.save = save
        self.progress = progress
        self.plans = build_plan(matrix)
        self.registration = {}
        self.refs = {}
        self.unresolved = set()
        self.out = dict(schema=1, status="running", reference=[], reference_complete=False, registration=[],
                        points=[], billing_roles=[], primary=None, secondary=[], sensitivities={},
                        stop_reporting={}, unresolved_weekly_groups=[])

    def checkpoint(self):
        if self.save is not None:
            self.save("outcome", self.out)

    def milestone(self, description):
        self.checkpoint()
        if self.progress is not None:
            self.progress(description)

    def _pause(self, text, req, proof):
        self.out["pause"] = dict(reason=text, request=proof, week=req.week, phase=req.phase,
                                 scenario=req.scenario, design=req.design.label, caps=list(req.caps))
        self.checkpoint()
        raise ss.fc.StudyLimit(text)

    def _check_admission(self, req, proof, result, *, new, primary=False, unresolved=None):
        stat = result["stats"]
        unresolved = stat["status"] == UNRESOLVED if unresolved is None else unresolved
        if unresolved:
            policy = ROLLING if req.phase == "rolling_energy" else FULL
            group = (req.scenario, req.week, req.design.label, req.caps, policy)
            self.unresolved.add(group)
            self.out["unresolved_weekly_groups"] = sorted(self.unresolved)
            if new:
                self.evidence.record_unresolved(req)
        if primary and stat["status_code"] == 1 and new:
            self.out["primary"] = dict(classification=UNRESOLVED,
                shared_proof=point_id(FULL, F40, F40.caps), bases=list(BASES),
                failed_weeks=[], timeout_week=req.week)
            self._pause("The primary fixed-R integer feasibility proof timed out", req, proof)
        self.evidence.check(limit_unresolved=True)

    def _register(self, sample, p, design, caps, reference):
        w = week_of(p)
        cache = sample, w, design, caps, tuple(sorted(reference))
        if cache in self.registration:
            return self.registration[cache]
        rows = []
        group = dict(sample=sample, week=w, design=design.label, caps_kw=list(caps), days=rows)
        self.out["registration"].append(group)
        self.registration[cache] = group
        locked = {}
        for d in p.days:
            day = d["date"]
            keys = {k for k in p.keys if k[0] == day}
            row = dict(date=day, eligible=sorted(k[1] for k in keys), selected=[] if not keys else None,
                       evidence_id=None, status="empty" if not keys else "not_dispatched")
            rows.append(row)
            if not keys or len(locked) != sum(k[0] < day for k in p.keys):
                continue
            req = FinalRequest(sample, w, design, "registration", caps, date=day,
                               locked=locked, reference=reference)
            new = self.evidence.is_new(req)
            (proof, result), = self.evidence.batch([req])
            stat = result["stats"]
            row.update(evidence_id=proof, status=stat["status"], native_status=stat["status_code"],
                       score_bounds=stat.get("integer_score_bounds"))
            if stat["status"] == "certified" and result["audit"] is not None:
                selected = keys & eb.selected(result)
                row["selected"] = sorted((v for _, v in selected), key=int)
                locked.update({k: k in selected for k in keys})
            self._check_admission(req, proof, result, new=new)
        group["reference"] = (sorted(k for k, keep in locked.items() if keep)
                              if len(locked) == len(p.keys) else None)
        return group

    def _register_baseline(self, sample):
        refs = self.refs[sample] = {}
        for p in self.scenarios[sample]:
            group = self._register(sample, p, B, B.caps, set())
            refs[week_of(p)] = None if group["reference"] is None else set(group["reference"])
        return refs

    def _fixed(self, sample, p, design, caps, ref, daily=None):
        w = week_of(p)
        req = FinalRequest(sample, w, design, "fixed_service", caps, fixed=ref)
        new = self.evidence.is_new(req)
        (proof, result), = self.evidence.batch([req])
        stat = result["stats"]
        independent = []
        status = stat["status"]
        if status == "infeasible":
            for key in sorted(ref):
                detail = diagnose_fixed(p, key, design)
                if not detail["single_truck_relaxation_feasible"]:
                    independent.append(detail)
            classification = VERIFIED_FAILURE if independent else NATIVE_FAILURE
        elif status == "certified" and result["audit"] is not None:
            if not result["audit"]["passed"] or eb.selected(result) != ref:
                raise ValueError("The fixed-R proof used a different cohort or failed physical replay")
            classification = PASSED
        else:
            classification = UNRESOLVED
        # Joint integer evidence is primary. A daily policy can omit a duty
        # despite a feasible fixed cohort. A timed-out daily proof has no winner.
        observed = daily["reference"] if daily is not None else None
        support = (dict(retained=ref <= set(observed), missing=sorted(ref - set(observed)))
                   if observed is not None else None)
        if daily is not None and observed is None:
            classification = UNRESOLVED
        return req, proof, result, new, dict(week=w, fixed=sorted(ref), service=classification,
            fixed_service_status=status, native_status=stat["status_code"], proof_id=proof,
            independent_diagnosis=independent, daily_order_support=support, status=status,
            purchase_lower=None, purchase_upper=None, audit=None, schedule=[], states=[])

    def _full(self, sample, p, design, caps, ref, weeks, *, service_only=False, daily_at_caps=False):
        if not ref:
            weeks.append(_zero(p))
            return
        daily = None
        if design != B and (caps == design.caps or daily_at_caps):
            daily = self._register(sample, p, design, caps, ref)
        primary = sample == MAIN and design == F40 and caps == F40.caps
        req, proof, result, new, row = self._fixed(sample, p, design, caps, ref, daily)
        weeks.append(row)
        self._check_admission(req, proof, result, new=new, primary=primary,
                              unresolved=row["service"] == UNRESOLVED)
        if service_only or row["service"] != PASSED:
            return
        req = FinalRequest(sample, week_of(p), design, "energy", caps, fixed=ref)
        new = self.evidence.is_new(req)
        (proof, result), = self.evidence.batch([req])
        stat = result["stats"]
        if stat["status"] == "infeasible":
            raise ValueError("Procurement contradicted the passed fixed-R integer proof")
        row.update(status=stat["status"], purchase_proof_id=proof, audit=result["audit"],
                   schedule=result["schedule"], states=result["states"],
                   purchase_lower=stat["objective_lower"], purchase_upper=stat["objective_upper"])
        self._check_admission(req, proof, result, new=new)

    def _rolling(self, p, design, caps, ref, weeks):
        requests = [FinalRequest(MAIN, week_of(p), design, "rolling_energy", caps, fixed=r.fixed,
                                 date=r.week.removeprefix("day:"))
                    for r in rolling_requests(p, design, caps, ref)]
        new = any(self.evidence.is_new(req) for req in requests)
        pairs = self.evidence.batch(requests)
        row = rolling_week(p, design, caps, ref, pairs)
        seen = {(r["date"], r["vehicle_id"]) for r in row["states"]}
        previous = {b: a for chain in p.chains for a, b in zip(chain, chain[1:]) if {a, b} <= ref}
        unknown, conditional = set(), set()
        for opt in row["days"]:
            keys = {tuple(key) for key in opt["fixed"]}
            if any(previous.get(key) in unknown for key in keys):
                conditional.add(opt["date"])
            if opt["date"] in conditional or not keys <= seen:
                unknown.update(keys)
            opt["conditional_on_unobserved_predecessor"] = opt["date"] in conditional
        for field in ("schedule", "states"):
            row["conditional_" + field] = [r for r in row[field] if r["date"] in conditional]
            row[field] = [r for r in row[field] if r["date"] not in conditional]
        row["vehicle_days"] = _rolling_days(p, row, design, caps)
        row["fixed"] = sorted(ref)
        row["proof_id"] = None
        row["service"] = (NATIVE_FAILURE if row["status"] == "infeasible" else
                          PASSED if row["audit"] is not None else UNRESOLVED)
        weeks.append(row)
        if row["status"] == UNRESOLVED and requests:
            proof, result = pairs[0]
            self._check_admission(requests[0], proof, result, new=new, unresolved=True)

    def _point(self, sample, mode, design, caps, refs, target, *, service_only=False):
        weeks = []
        point = dict(id=point_id(mode, design, caps), sample=sample, policy=mode, design=design.label,
                     port_plugs=design.port_plugs, port_kw=design.port_kw, warehouse_kw=design.warehouse_kw,
                     caps_kw=list(caps), weeks=weeks)
        target.append(point)
        for p in self.scenarios[sample]:
            ref = refs[week_of(p)]
            if ref is None:
                weeks.append(dict(week=week_of(p), fixed=None, service=UNRESOLVED, status=UNRESOLVED,
                                  source="unregistered_week", audit=None, schedule=[]))
            elif mode == FULL:
                self._full(sample, p, design, caps, ref, weeks, service_only=service_only,
                           daily_at_caps=sample == PARKING)
            elif mode == ROLLING:
                self._rolling(p, design, caps, ref, weeks)
            else:
                if caps != design.caps:
                    raise ValueError("Immediate charging is fixed at installed power")
                witness = simulate_week(p, design, ref)
                purchase = witness["audit"]["purchase_eur"]
                feasible = witness["summary"]["same_service"]
                weeks.append(dict(**witness, fixed=sorted(ref), proof_id=None,
                    service=PASSED if feasible else VERIFIED_FAILURE,
                    status="certified" if feasible else "infeasible",
                    purchase_lower=purchase, purchase_upper=purchase))
        point["failed_weeks"] = _known_failure(weeks)
        point["service"] = self._classification(weeks)
        point["bill_admitted"] = all(r["status"] in ACCEPTED and r["audit"] is not None for r in weeks)
        self.milestone(f"{sample} {point['id']}: {point['service']}")
        return point

    @staticmethod
    def _classification(weeks):
        statuses = {r["service"] for r in weeks}
        if VERIFIED_FAILURE in statuses:
            return VERIFIED_FAILURE
        if NATIVE_FAILURE in statuses:
            return NATIVE_FAILURE
        return PASSED if statuses == {PASSED} else UNRESOLVED

    def _billing_roles(self):
        done = {p["id"]: p for p in self.out["points"]}
        aliases = self.out["billing_roles"]
        winners = {(r["scenario"], r["connection_basis"]): r["design"]
                   for r in self.matrix["frozen_full_information"]}
        for tariff in TARIFFS:
            for basis in BASES:
                baseline_caps = (B.caps if tariff == "N0" else (50, 20)
                                 if tariff in ("official", "frank") else (20, 20))
                f40_caps = F40.caps if tariff in ("N0", "frank", "official") else (20, 20)
                roll = D30 if tariff == "capacity_208_38" else F40
                roles = (("B", FULL, B, baseline_caps), ("F20", FULL, F20, F20.caps),
                         ("F40", FULL, F40, f40_caps), ("U", FULL, F40, F40.caps),
                         ("I", IMMEDIATE, I, I.caps), ("D40", ROLLING, F40, F40.caps),
                         ("D30", ROLLING, D30, D30.caps), ("F20_rolling", ROLLING, F20, F20.caps),
                         ("F40_immediate", IMMEDIATE, F40, F40.caps),
                         ("F20_immediate", IMMEDIATE, F20, F20.caps))
                for role, mode, d, caps in roles:
                    initial = point_id(mode, d, caps)
                    hardware = point_id(FULL, d, d.caps) if mode == FULL else initial
                    point = done[initial]
                    fallback = mode == FULL and hardware != initial and bool(point["failed_weeks"])
                    aliases.append(dict(role=role, policy=mode, tariff=tariff, basis=basis,
                        point_id=hardware if fallback else initial, frozen_point_id=initial,
                        rated_counterfactual_point_id=hardware if mode == FULL else None,
                        fallback=fallback, uses_baseline_assets=role == "B",
                        recommended=(role in ("F20", "F40") and d.label == winners[tariff, basis]) or
                                    (role in ("D30", "D40") and d == roll) or role == "I"))

    def _sensitivity(self):
        parking_ref = self._register_baseline(PARKING)
        normal_ref = self.refs[MAIN]
        parking = dict(reference_by_week={w: sorted(r) if r is not None else None for w, r in parking_ref.items()},
                       added=[], removed=[], points=[])
        self.out["sensitivities"][PARKING] = parking
        for w, ref in parking_ref.items():
            if ref is not None and normal_ref[w] is not None:
                parking["added"].extend(sorted(ref - normal_ref[w]))
                parking["removed"].extend(sorted(normal_ref[w] - ref))
        for design, caps in self.plans[FULL]:
            self._point(PARKING, FULL, design, caps, parking_ref, parking["points"], service_only=True)
        for name, factor in ACTIVITIES:
            margin = dict(scale=factor, baseline_also_lost=[], baseline_policy_omissions=[], points=[])
            self.out["sensitivities"][name] = margin
            for d in (B, F40, F20):
                self._point(name, FULL, d, d.caps, normal_ref, margin["points"], service_only=True)
            for p in self.scenarios[name]:
                ref = normal_ref[week_of(p)]
                if not ref:
                    continue
                reg = self._register(name, p, B, B.caps, ref)
                if reg["reference"] is not None:
                    margin["baseline_policy_omissions"].extend(sorted(ref - set(reg["reference"])))
                week = next(w for w in margin["points"][0]["weeks"] if w["week"] == week_of(p))
                margin["baseline_also_lost"].extend((row["date"], row["vehicle_id"])
                    for row in week.get("independent_diagnosis", ()))

    def run(self):
        refs = self._register_baseline(MAIN)
        self.out["reference"] = sorted(k for ref in refs.values() if ref is not None for k in ref)
        self.out["reference_complete"] = all(r is not None for r in refs.values())
        self.out["reference_by_week"] = {w: sorted(r) if r is not None else None for w, r in refs.items()}
        self.milestone(f"Registered {len(self.out['reference'])} baseline vehicle-days")
        primary = self._point(MAIN, FULL, F40, F40.caps, refs, self.out["points"])
        self.out["primary"] = dict(classification=primary["service"], shared_proof=primary["id"],
                                   bases=list(BASES), failed_weeks=primary["failed_weeks"])
        for mode in (FULL, ROLLING, IMMEDIATE):
            for design, caps in self.plans[mode]:
                if (mode, design, caps) != (FULL, F40, F40.caps):
                    self._point(MAIN, mode, design, caps, refs, self.out["points"])
        results = {p["id"]: p for p in self.out["points"]}
        for order, policy, design in (("S1", ROLLING, F40), ("S2", IMMEDIATE, I), ("S3", IMMEDIATE, F40)):
            point = results[point_id(policy, design, design.caps)]
            self.out["secondary"].append(dict(endpoint=order, point_id=point["id"],
                                               classification=point["service"], failed_weeks=point["failed_weeks"]))
        self._billing_roles()
        # Eligibility of separately preregistered diagnoses is decided by
        # their gate, never by early suppression of the matrix.
        self.out["stop_reporting"] = dict(registered_matrix_closed=True,
            recommended_service_failures=[d.label for d in (F20, F40)
                if any(p["id"] == point_id(FULL, d, d.caps) and p["failed_weeks"] for p in self.out["points"])],
            prohibit_extra_unregistered_work=True)
        self.milestone("Main holdout matrix closed")
        self._sensitivity()
        self.out["status"] = "complete"
        self.checkpoint()


def execute(scenarios, matrix, evidence, *, save=None, progress=None):
    """Run in the fixed order and return durable partial evidence on an authorized stop."""
    state = _Execution(scenarios, matrix, evidence, save, progress)
    try:
        state.run()
    except ss.fc.StudyLimit as exc:
        state.out.update(status="stopped", reason=str(exc))
        state.checkpoint()
    return state.out
