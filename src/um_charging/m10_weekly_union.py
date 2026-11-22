"""Single-week priced coarse minima, conservative facility union and exact no-warehouse check."""
from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
import json
import math
from pathlib import Path

from . import holdout_inputs as hi, site_sizing as ss
from .__main__ import digest
from .cabinet_tariff import annual_factors
from .m10_costs import _contains, _parameters, _rank_designs
from .m10_evidence import Request
from .m10_service import MISSING_DUTY
from .site_sizing_bounds import AnnualBillBounds, WholesaleRecord, network_lower_bound
from .site_sizing_screen import COST_MARGIN_EUR


BASES = ("new", "existing")


def _fractional_minutes(start, end):
    delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    return Fraction(delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds, 60_000_000)


def _exact_segment(days, keys):
    """Use raw decimal trips and exact time differences in an exclusive-port relaxation."""
    events = []
    for day, vehicle in keys:
        truck, = [v for v in days[day]["vehicles"] if v["vehicle_id"] == vehicle]
        for trip in truck["trips"]:
            events.append((trip["start"], trip["end"], "trip", trip["track_id"], Fraction(trip["energy_kwh"])))
        for stop in truck["stops"]:
            if stop["site"] != ss.PORT:
                continue
            start = max((stop["start"], stop["arrival"]), key=datetime.fromisoformat)
            minutes = _fractional_minutes(start, stop["end"])
            if minutes > 0:
                events.append((start, stop["end"], "window", stop["arrival_track_id"], minutes * 50 / 60))
    low = high = Fraction(150)
    trace = []
    failure = None
    for start, end, kind, track, value in sorted(events, key=lambda e: (datetime.fromisoformat(e[0]),
                                                                         datetime.fromisoformat(e[1]))):
        if kind == "window":
            high = min(Fraction(300), high + value * Fraction(9, 10))
        else:
            low, high = max(Fraction(30), low - value), min(Fraction(300), high - value)
        trace.append(dict(start=start, end=end, event=kind, track=track, event_kwh=str(value),
                          reachable_lower_kwh=str(low), reachable_upper_kwh=str(high)))
        if low > high:
            failure = dict(kind="empty_interval", track=track, deficit_kwh=str(low - high))
            break
    if failure is None and not low <= 150 <= high:
        failure = dict(kind="terminal_soc_unreachable", deficit_kwh=str(max(low - 150, 150 - high)))
    return dict(first_date=keys[0][0], last_date=keys[-1][0], first_soc_kwh=150, required_last_soc_kwh=150,
                trip_energy_kwh=str(sum((v for _, _, k, _, v in events if k == "trip"), Fraction())),
                maximum_available_port_grid_kwh=str(sum((v for _, _, k, _, v in events if k == "window"), Fraction())),
                feasible=failure is None, failure=failure, trace=trace)


def exact_no_warehouse(inputs):
    """Read only the first holdout's registered selection-period file, without float conversion."""
    name = hi.WEEKS.relative_to(ss.eb.ROOT).as_posix()
    sha = digest(hi.WEEKS)
    if sha != inputs.source_sha256[name] or MISSING_DUTY not in inputs.registered:
        raise ValueError("Exact proof input differs from fixed-R selection")
    raw = json.loads(hi.WEEKS.read_bytes(), parse_float=Decimal)
    period, = [p for p in inputs.periods if MISSING_DUTY in p.keys]
    week = period.days[0]["week_start"]
    days = {row["date"]: row for row in raw["days"] if row["week_start"] == week}
    chains, _, _ = ss.eb.calendar(list(days.values()))
    chain, = [c for c in chains if MISSING_DUTY in c]
    if chain not in period.chains:
        raise ValueError("Exact proof and planning calendar have different vehicle links")
    i = chain.index(MISSING_DUTY)
    segments = [_exact_segment(days, chain[a:b+1]) for a in range(i+1) for b in range(i, len(chain))]
    if any(s["feasible"] for s in segments):
        raise ValueError("Exclusive-port relaxation did not establish the decisive impossibility")
    return dict(week=week, date=MISSING_DUTY[0], vehicle_id=MISSING_DUTY[1], source_path=name,
                source_sha256=sha, exclusive_port_kw=50, warehouse_kw=0, charge_efficiency="9/10",
                numeric_representation="exact decimal inputs converted to rational kWh and elapsed minutes",
                registered=True, all_segments_infeasible=True, segments=segments)


@dataclass(frozen=True)
class _Scope:
    design: ss.Design
    caps: tuple
    proof: str


def _union(builds):
    return ss.Design(max(d.port_plugs for d in builds), max(d.port_kw for d in builds),
                     max(d.warehouse_kw for d in builds))


def _bill(network, materials, design, meters, scenario, basis):
    expense = math.fsum(w["purchase_eur"] for w in meters)
    purchases_low = math.fsum(w["lower_eur"] for w in meters) * annual_factors(network)[0]
    kwh = {s: math.fsum(w["site_grid_kwh"][s] for w in meters) for s in ss.SITES}
    peaks = {s: max(w["site_quarter_peak_kw"][s] for w in meters) for s in ss.SITES}
    bill = ss.settle(network, expense, kwh, peaks, scenario)
    ss.audit_settlement(network, expense, kwh, peaks, scenario, bill)
    equipment, missing, connection = ss.annual_capital_costs(design, materials)
    if missing:
        raise ValueError("An unpriced charger entered the weekly coarse comparison")
    fixed = equipment + connection[basis]
    network_energy = bill["annual_network_energy_eur_2025"]
    demand = bill["annual_capacity_eur_2025"]
    return dict(equipment=equipment, connection=connection[basis], network_energy=network_energy, demand=demand,
                purchase_lower=purchases_low, purchase_upper=bill["annual_energy_eur_2025"],
                total_lower=math.fsum((fixed, network_energy, demand, purchases_low)),
                total_upper=fixed + bill["annual_total_eur_2025"])


class _WeeklyGrid:
    def __init__(self, inputs, coarse, evidence):
        self.evidence = evidence
        self.by_week = {p.days[0]["week_start"]: p for p in inputs.periods}
        self.reference = inputs.registered
        self.network, self.materials = _parameters(inputs.periods)
        self.one = {**self.network, "annualization": {**self.network["annualization"], "sample_weeks": 1}}
        self.bounds = {w: AnnualBillBounds([p], self.reference, self.one, self.materials)
                       for w, p in self.by_week.items()}
        designs = ss.design_grid(ss.COARSE_KW)
        self.designs = {d.label: d for d in designs}
        self.dispatch = ss.DispatchGrid(inputs.periods, self.reference, self.network, evidence)
        self.feasible = defaultdict(dict)
        self.impossible = defaultdict(list)
        self.duals = defaultdict(list)
        self.preferred = {}
        self.replayed = {}
        self.known_rows = set()
        self.week_rows = {}
        self.upper = defaultdict(lambda: math.inf)
        self.grid_bounds = {}
        service = ss.eb.read_json(coarse / "service_summary.json")
        for label, item in service.items():
            design = self.designs[label]
            for w in item["weeks"]:
                if w["status"] == "shortfall":
                    self.impossible[w["week"]].append(_Scope(design, design.caps, w["evidence_id"]))
        with (coarse / "operating_points.csv").open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                if row["status"] in ss.ENERGY_ACCEPTED:
                    caps = int(row["port_cap_kw"]), int(row["warehouse_cap_kw"])
                    self.preferred[row["week"], self.designs[row["design"]], caps] = row["evidence_id"]
        # A verify run already has the eventual R014 ledger. Reveal those
        # proofs only when the original deterministic traversal requests them.
        with (coarse / "solves.csv").open(encoding="utf-8", newline="") as stream:
            inherited = {r["id"] for r in csv.DictReader(stream) if r["phase"] == "energy"}
        for record in evidence.records:
            if record["id"] in inherited:
                self._record(record["id"], record["status"], record["objective_lower"])
        if self.known_rows != inherited:
            raise ValueError("Unified evidence omits a sealed coarse weekly request")

    def _record(self, proof, status, lower):
        if proof in self.known_rows:
            return
        req = self.evidence.request_for(proof)
        period = self.by_week[req.week]
        if req.phase != "energy" or req.fixed != tuple(sorted(period.keys & self.reference)):
            raise ValueError(("Wrong weekly fixed registration", proof))
        s = _Scope(ss._active_build(req.design, req.caps), req.caps, proof)
        if status in ss.ENERGY_ACCEPTED:
            self.feasible[req.week, req.caps][proof] = s
        if status == "infeasible":
            self.impossible[req.week].append(s)
        if lower is not None and math.isfinite(lower):
            self.duals[req.week].append(WholesaleRecord(req.week, s.design, s.caps, lower, proof))
        self.known_rows.add(proof)

    def _meter(self, w, active, caps, proof):
        key = active, caps, proof
        if key in self.replayed:
            return self.replayed[key]
        req = self.evidence.request_for(proof)
        period = self.by_week[w]
        result = self.evidence.get(proof)
        stat = result["stats"]
        if (req.week != w or req.caps != caps or not ss._dominates(ss._active_build(req.design, caps), active)
                or stat["status"] not in ss.ENERGY_ACCEPTED
                or ss.eb.selected(result) != self.reference & period.keys):
            raise ValueError(("Invalid weekly meter transfer", w, active.label, caps, proof))
        source = result["audit"]
        if (source["used_plugs"][ss.PORT] > active.port_plugs or
                any(source["site_peak_kw"][s] > k + ss.EPS for s, k in zip(ss.SITES, active.caps, strict=True))):
            self.replayed[key] = None
            return None
        audit = ss.meter_replay(period, active.hardware(), ss.eb.DEFAULT_SPEC, caps, result)
        for site in ss.SITES:
            for field in ("site_grid_kwh", "site_quarter_peak_kw"):
                ss.close(audit[field][site], source[field][site], (w, active.label, proof, field, site))
        ss.close(audit["purchase_eur"], stat["objective_upper"], proof)
        if not audit["passed"] or stat["objective_lower"] > audit["purchase_eur"] + ss.EPS:
            raise ValueError(("Invalid weekly objective interval", w, proof))
        self.replayed[key] = dict(proof=proof, status=stat["status"],
                                  lower_eur=min(stat["objective_lower"], audit["purchase_eur"]),
                                  purchase_eur=audit["purchase_eur"], site_grid_kwh=audit["site_grid_kwh"],
                                  site_quarter_peak_kw=audit["site_quarter_peak_kw"])
        return self.replayed[key]

    def _observe(self, key):
        w, d, caps = key
        active = ss._active_build(d, caps)
        old = self.preferred.get(key)
        group = self.feasible[w, caps]
        if old is not None and old not in group:
            raise ValueError(("Missing archived admitted weekly certificate", key, old))
        # Preserve the specific archived meter. Else exact active request, then
        # a more capable same-cap donor (descending design, ascending proof ID).
        donors = [s for s in group.values() if ss._dominates(s.design, active)]
        donors.sort(key=lambda s: s.proof)
        donors.sort(key=lambda s: s.design, reverse=True)
        donors.sort(key=lambda s: (s.proof != old, s.design != active))
        for s in donors:
            m = self._meter(w, active, caps, s.proof)
            if m is None:
                if s.proof == old:
                    raise ValueError(("Frozen coarse meter does not fit", key, old))
                continue
            bills = {b: _bill(self.one, self.materials, d, [m], "official", b) for b in BASES}
            for b, bill in bills.items():
                self.upper[w, b] = min(self.upper[w, b], bill["total_upper"])
            method = ("coarse_point_week" if s.proof == old else
                      "exact_active_request" if s.design == active else "fitting_superset_same_caps")
            return dict(status=m["status"], method=method, proof=s.proof, meter=m, bills=bills)
        exclusion = next((s for s in self.impossible[w] if _contains(s.design, s.caps, active, caps)), None)
        if exclusion:
            return dict(status="infeasible", method="weekly_infeasible_superset", proof=exclusion.proof)
        return None

    def _lower(self, key):
        w, d, caps = key
        bounds = self.bounds[w]
        proof = bounds.weekly_lower_bound(w, d, caps, self.duals[w])
        meter_floor = self.grid_bounds.get((w, caps))
        if meter_floor is None:
            meter_floor = network_lower_bound(self.one, "official", caps, bounds.annual_hours, bounds.annual_kwh)
            self.grid_bounds[w, caps] = meter_floor
        if math.isinf(meter_floor):
            return dict(status="infeasible", method="weekly_network_capacity", proof=proof.proof)
        equip, _, connections = ss.annual_capital_costs(d, self.materials)
        price = proof.lower_eur * annual_factors(self.one)[0]
        lows = {b: math.fsum((equip, connections[b], price, meter_floor)) - ss.EPS for b in BASES}
        excluded = all(self.upper[w, b] + COST_MARGIN_EUR < lows[b] for b in BASES)
        return dict(status="excluded_cost" if excluded else "unresolved", method="weekly_annual_lower",
                    proof=proof.proof, purchase_floor=price, network_floor=meter_floor, lows=lows)

    def solve_grid(self, progress):
        choices = [(d, c) for d in self.designs.values() for c in self.dispatch.options(d, ss.COARSE_KW)]
        for d, c in choices:
            self.evidence.check()
            for w in self.by_week:
                key = w, d, c
                row = self._observe(key)
                if row:
                    self.week_rows[key] = row
        if progress:
            progress(f"单周稳健搜索：共 {len(choices)*len(self.by_week)} 个周点，初始已有证据 {len(self.week_rows)} 个。")
        # Wider hardware first within equal software caps so new proofs may
        # discharge later requests. Submit independent missing weeks together.
        for d, caps in sorted(choices, key=lambda t: (t[1], t[0]), reverse=True):
            self.evidence.check()
            pending = []
            for w, p in self.by_week.items():
                key = w, d, caps
                if key in self.week_rows:
                    continue
                row = self._observe(key) or self._lower(key)
                self.week_rows[key] = row
                if row["status"] == "unresolved":
                    active = ss._active_build(d, caps)
                    pending.append(Request.make(p, active, "energy", caps, fixed=p.keys & self.reference))
            for req, (label, result) in zip(pending, self.evidence.batch(pending), strict=True):
                stat = result["stats"]
                self._record(label, stat["status"], stat["objective_lower"])
                key = req.week, d, caps
                row = self._observe(key) or self._lower(key)
                if row["status"] == "unresolved":
                    row.update(method="unresolved_weekly_request", request_proof=label)
                self.week_rows[key] = row

    def rated_rows(self, design):
        requests = []
        rows = {}
        for w, period in self.by_week.items():
            key = w, design, design.caps
            row = self.week_rows[key]
            if row["status"] not in ss.ENERGY_ACCEPTED:
                row = self._observe(key)
            if row is not None:
                rows[w] = row
            else:
                requests.append(Request.make(period, design, "energy", design.caps, fixed=period.keys & self.reference))
        for req, (label, result) in zip(requests, self.evidence.batch(requests), strict=True):
            stat = result["stats"]
            self._record(label, stat["status"], stat["objective_lower"])
            rows[req.week] = self._observe((req.week, design, design.caps)) or dict(status="unresolved", proof=label)
        return [rows[w] for w in self.by_week]


def _week_points(grid):
    rows = []
    for (week, design, caps), saved in sorted(grid.week_rows.items()):
        meter = saved.get("meter", {})
        for basis in BASES:
            bill = saved.get("bills", {}).get(basis, {})
            rows.append(dict(week=week, design=design.label, port_cap_kw=caps[0], warehouse_cap_kw=caps[1],
                             scenario="official", connection_basis=basis, status=saved["status"],
                             method=saved["method"], evidence_id=saved["proof"],
                             unresolved_request=saved.get("request_proof"),
                             port_kwh=meter.get("site_grid_kwh", {}).get(ss.PORT),
                             warehouse_kwh=meter.get("site_grid_kwh", {}).get(ss.WAREHOUSE),
                             port_peak_kw=meter.get("site_quarter_peak_kw", {}).get(ss.PORT),
                             warehouse_peak_kw=meter.get("site_quarter_peak_kw", {}).get(ss.WAREHOUSE),
                             purchase_lower_eur_2021=meter.get("lower_eur"), purchase_upper_eur_2021=meter.get("purchase_eur"),
                             purchase_floor_eur_2025=saved.get("purchase_floor"), network_floor_eur_2025=saved.get("network_floor"),
                             equipment=bill.get("equipment"), connection=bill.get("connection"),
                             purchase_lower=bill.get("purchase_lower"), purchase_upper=bill.get("purchase_upper"),
                             network_energy=bill.get("network_energy"), demand=bill.get("demand"),
                             total_lower=bill.get("total_lower", saved.get("lows", {}).get(basis)),
                             total_upper=bill.get("total_upper"), missing_ratings_kw=""))
    return rows


def _weekly_choices(rows, designs):
    minima = []
    members = {b: set() for b in BASES}
    weeks = defaultdict(list)
    for r in rows:
        weeks[r["week"]].append(r)
    complete = True
    for week, points in sorted(weeks.items()):
        ranks, winners = _rank_designs(points)
        for winner in winners:
            basis = winner["connection_basis"]
            possible = winner["possible_minimum_designs"]
            if not possible or winner["minimum_upper"] is None:
                raise ValueError(("Missing any feasible priced weekly incumbent", week, basis))
            entry = [r for r in ranks if r["connection_basis"] == basis and r["design"] in possible]
            # A lower bound with no admitted schedule can still threaten a
            # weekly minimum. Keep it visible and flag the resulting union.
            unresolved = sorted({r["design"] for r in points if r["connection_basis"] == basis
                                 and r["design"] in possible and r["status"] == "unresolved"
                                 and r["total_lower"] <= winner["minimum_upper"] + COST_MARGIN_EUR})
            qualified = not unresolved
            complete &= qualified
            members[basis].update(designs[label] for label in possible)
            minima.append(dict(week=week, scenario="official", connection_basis=basis,
                               minimum_lower=winner["minimum_lower"], minimum_upper=winner["minimum_upper"],
                               possible_minimum_designs=possible, unresolved_designs=unresolved,
                               status=("unresolved" if not qualified else "unique" if len(possible) == 1 else "overlap"),
                               design_intervals=entry))
    return minima, members, complete


def _frozen_comparison(coarse, inputs):
    seal = ss.eb.read_json(coarse / "seal.json")
    for name in ("solves.csv", "operating_points.csv", "service_summary.json", "selection.json"):
        if digest(coarse / name) != seal["products"][name]:
            raise ValueError(f"Sealed coarse product differs: {name}")
    manifest = ss.eb.read_json(coarse / "run_manifest.json")
    bound = manifest["inputs"]
    if (bound["planning"] != inputs.source_sha256 or list(map(tuple, bound["fixed_service"])) != sorted(inputs.registered)
            or manifest["timeout_interval_eur_2021"] != .10):
        raise ValueError("Weekly union must use the sealed coarse cohort and certificate policy")
    selected = ss.eb.read_json(coarse / "selection.json")["winners"]
    return {r["connection_basis"]: r for r in selected if r["scenario"] == "official"}


def weekly_union(inputs, coarse, evidence, *, progress=None):
    """Compare twelve separate 52/1 weeks and settle one conservative rated union at 52/12."""
    coarse = Path(coarse)
    compare = _frozen_comparison(coarse, inputs)
    grid = _WeeklyGrid(inputs, coarse, evidence)
    grid.solve_grid(progress)
    rows = _week_points(grid)
    minima, members, complete = _weekly_choices(rows, grid.designs)
    groups = {**members, "common": set.union(*members.values())}
    facilities = []
    for basis, included in groups.items():
        design = _union(included)
        facilities.append(dict(connection_basis=basis, design=design.label, port_plugs=design.port_plugs,
                               port_kw=design.port_kw, warehouse_kw=design.warehouse_kw, caps_kw=list(design.caps),
                               member_designs=sorted(d.label for d in included), all_weekly_minima_classified=complete))
    common = _union(groups["common"])
    rated = grid.rated_rows(common)
    has_bill = all(r["status"] in ss.ENERGY_ACCEPTED for r in rated)
    if not has_bill and complete and any(r["status"] == "infeasible" for r in rated):
        raise ValueError("Weekly union's rated hardware contradicts its weekly feasible members")
    scenarios = ("N0", *grid.network["tariffs"], *grid.network["capacity_sensitivities_eur_per_kw_year"])
    costs, premiums = [], []
    for scenario in scenarios:
        for basis in BASES:
            bill = _bill(grid.network, grid.materials, common, [r["meter"] for r in rated], scenario, basis) if has_bill else {}
            costs.append(dict(design=common.label, port_cap_kw=common.port_kw, warehouse_cap_kw=common.warehouse_kw,
                              scenario=scenario, connection_basis=basis, status="settled" if has_bill else "unresolved",
                              weekly_proof_ids=[r["proof"] for r in rated], **bill))
            if scenario != "official":
                continue
            old = compare[basis]
            premiums.append(dict(design=common.label, connection_basis=basis, scenario=scenario,
                                 comparison_design=old["incumbent"]["design"], comparison_caps=old["incumbent"]["caps_kw"],
                                 comparison_lower=old["minimum_lower"], comparison_upper=old["minimum_upper"],
                                 union_lower=bill.get("total_lower"), union_upper=bill.get("total_upper"),
                                 premium_lower=bill["total_lower"] - old["minimum_upper"] if has_bill else None,
                                 premium_upper=bill["total_upper"] - old["minimum_lower"] if has_bill else None,
                                 all_weekly_minima_classified=complete))
    return dict(weekly_points=rows, weekly_minima=minima, union_facilities=facilities,
                union_costs=costs, ex_ante_premiums=premiums)
