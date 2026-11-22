"""Screen twelve-week operating caps from fixed-service certificates and charging windows."""
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from functools import lru_cache
import json
import math

from . import site_sizing as ss
from .cabinet_tariff import annual_factors
from .m10_costs import _contains, _parameters
from .site_sizing_bounds import AnnualBillBounds, known_peak_network_lower_bound, network_lower_bound
from .site_sizing_screen import COST_MARGIN_EUR


BACKTEST_COLUMNS = (
    "design", "port_cap_kw", "warehouse_cap_kw", "held_week", "scenario", "connection_basis",
    "purchase_lower_eur_2025", "network_lower_eur_2025", "equipment_eur_2025", "connection_eur_2025",
    "annual_lower_eur_2025", "actual_eur_2025", "margin_eur_2025", "passed", "reason", "frozen_proof_ids")


def _read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


@dataclass(frozen=True)
class Scope:
    week: str
    design: ss.Design
    caps: tuple
    proof: str
    lower: float | None = None


class PhysicalWindows:
    """Upper bound on kWh deliverable within the actually usable pieces of each quarter."""
    def __init__(self, periods, reference):
        self.shapes = {}
        self.hours = {}
        for period in periods:
            week = period.days[0]["week_start"]
            quarters = ss.fc._physical_quarters(period, period.keys & reference)
            for site in ss.SITES:
                # Count the multiplicity of identical within-quarter patterns.
                patterns = Counter()
                for intervals in quarters.values():
                    shape = tuple((right - left, len(by_site[site])) for _, left, right, by_site in intervals
                                  if by_site[site])
                    if shape:
                        patterns[shape] += 1
                self.shapes[week, site] = patterns
                self.hours[week, site] = sum(patterns.values()) * .25

    @lru_cache(maxsize=None)
    def upper(self, week, site, plugs, rating, cap):
        # Relax the truck identity and whole-quarter reservation constraints.
        # A quarter cap constrains the integral; it is not an instantaneous kW limit.
        truck = ss.eb.DEFAULT_SPEC.truck_kw
        return math.fsum(
            n * min((cap + ss.EPS) * .25, math.fsum(
                minutes / 60 * min(rating + ss.EPS, min(plugs, count) * (truck + ss.EPS))
                for minutes, count in pieces))
            for pieces, n in self.shapes[week, site].items()) if plugs and cap else 0.

    def envelopes(self, week, design, caps, required):
        limits = design.hardware()
        upper = tuple(self.upper(week, s, limits[s]["interfaces"], limits[s]["power_kw"], cap)
                      for s, cap in zip(ss.SITES, caps, strict=True))
        floor = tuple(max(0., required - upper[1-i] - ss.EPS) for i in range(2))
        peaks = tuple(kwh / self.hours[week, site] if self.hours[week, site] else 0.
                      for kwh, site in zip(floor, ss.SITES, strict=True))
        return upper, floor, peaks, required > math.fsum(upper) + ss.EPS


def _meter_bounds(bounds, caps, weekly):
    """Relax all unassigned energy to the two meters; preserve only proved floors."""
    known = tuple(math.fsum(w["site_kwh_floor"][i] for w in weekly) for i in (0, 1))
    peaks = tuple(max(w["site_peak_floor"][i] for w in weekly) for i in (0, 1))
    missing = [w for w in weekly if not w["proof"]]
    unassigned = math.fsum(bounds.weekly_kwh[w["week"]] - math.fsum(w["site_kwh_floor"]) for w in missing)
    if missing and unassigned <= ss.EPS:
        # M8's zero-residual shortcut settles an exactly frozen meter trace.
        # Physical peak floors are not exact measurements. Give the relaxed
        # split a positive residual without excluding the physical assignment.
        movable = max(range(2), key=lambda i: known[i])
        slack = min(known[movable], 2 * ss.EPS)
        if slack:
            known = tuple(x - slack if i == movable else x for i, x in enumerate(known))
            unassigned += slack
        if unassigned <= 0:
            # With no assignable energy and no positive floor the universal
            # relaxation remains valid even when peak readings are incomplete.
            return {s: network_lower_bound(bounds.network, s, caps, bounds.annual_hours, bounds.annual_kwh)
                    for s in bounds.scenarios}
    out = {}
    for scenario in bounds.scenarios:
        relaxed = network_lower_bound(bounds.network, scenario, caps, bounds.annual_hours, bounds.annual_kwh)
        out[scenario] = known_peak_network_lower_bound(bounds.network, scenario, caps, bounds.annual_hours,
                                                       known, peaks, unassigned, relaxed)
    return out


class RefinementBounds:
    """Read the sealed R012 policy; holdout weeks in backtests have no certificate access."""
    def __init__(self, inputs, coarse_archive, evidence):
        self.evidence = evidence
        self.by_week = {p.days[0]["week_start"]: p for p in inputs.periods}
        self.reference = inputs.registered
        network, materials = _parameters(inputs.periods)
        self.bounds = AnnualBillBounds(inputs.periods, self.reference, network, materials)
        self.windows = PhysicalWindows(inputs.periods, self.reference)
        self.dispatch = ss.DispatchGrid(inputs.periods, self.reference, network, evidence)
        self.materials = materials
        self.factor = annual_factors(network)[0]
        self.service = json.loads((coarse_archive / "service_summary.json").read_bytes())
        selection = json.loads((coarse_archive / "selection.json").read_bytes())
        self.incumbent = {(r["scenario"], r["connection_basis"]): r["minimum_upper"] for r in selection["winners"]}
        self.week_rows = defaultdict(dict)
        for r in _read_csv(coarse_archive / "operating_points.csv"):
            key = r["design"], (int(r["port_cap_kw"]), int(r["warehouse_cap_kw"]))
            if r["week"] in self.week_rows[key]:
                raise ValueError(("Duplicate coarse point week", key, r["week"]))
            self.week_rows[key][r["week"]] = r
        self.invoices = {}
        for r in _read_csv(coarse_archive / "annual_costs.csv"):
            if r["status"] in ss.ENERGY_ACCEPTED:
                key = r["design"], (int(r["port_cap_kw"]), int(r["warehouse_cap_kw"])), r["scenario"], r["connection_basis"]
                if key in self.invoices:
                    raise ValueError(("Duplicate admitted coarse invoice", key))
                self.invoices[key] = float(r["total_upper"])
        cases = {d.label: d for d in ss.design_grid(ss.FINE_KW)}
        self.builds = {label: cases[label] for label in sorted(self.service.keys() |
                       set(selection["refinement_estimate"]["additional_hardware"]))}
        self.expected_points = selection["refinement_estimate"]["new_operating_points"]
        self.failures, self.inventory_failures = [], []
        self.service_proofs = defaultdict(list)
        for label, item in self.service.items():
            design = cases[label]
            for row in item["weeks"]:
                if row["status"] == "shortfall":
                    self.inventory_failures.append(Scope(row["week"], design, design.caps, row["evidence_id"]))
                elif row["status"] == "complete":
                    self.service_proofs[row["week"]].append((design, row["witness_id"]))
        for (label, caps), group in self.week_rows.items():
            for week, w in group.items():
                if w["status"] == "infeasible" and w["method"] not in ("infeasible_superset", "excluded_point"):
                    self.inventory_failures.append(Scope(week, ss._active_build(cases[label], caps), caps, w["evidence_id"]))
        self.failures.extend(self.inventory_failures)
        self.duals, self.at_caps = defaultdict(list), defaultdict(list)
        for record in evidence.records:
            if record["phase"] != "energy":
                continue
            req = evidence.request_for(record["id"])
            if req.fixed != tuple(sorted(self.reference & self.by_week[req.week].keys)):
                raise ValueError(("Unexpected duty set in coarse evidence", record["id"]))
            s = Scope(req.week, ss._active_build(req.design, req.caps), req.caps, record["id"], record["objective_lower"])
            if s.lower is not None and math.isfinite(s.lower):
                self.duals[req.week].append(s)
            if record["status"] in ss.ENERGY_ACCEPTED:
                self.at_caps[s.week, s.caps].append(s)
            elif record["status"] == "infeasible":
                self.failures.append(s)
        for group in self.duals.values():
            group.sort(key=lambda s: (-s.lower, s.proof))
        for group in self.at_caps.values():
            group.sort(key=lambda s: s.proof)
            group.sort(key=lambda s: s.design, reverse=True)
        self._passed = False

    @lru_cache(maxsize=None)
    def _audit(self, proof):
        audit = self.evidence.get(proof)["audit"]
        return {key: audit[key] for key in ("site_grid_kwh", "site_peak_kw", "site_quarter_peak_kw", "used_plugs", "purchase_eur")}

    @lru_cache(maxsize=None)
    def _fits(self, s, active):
        audit = self._audit(s.proof)
        if audit["used_plugs"][ss.PORT] > active.port_plugs or any(
                audit["site_peak_kw"][site] > k + ss.EPS for site, k in zip(ss.SITES, active.caps, strict=True)):
            return False
        result = self.evidence.get(s.proof)
        period = self.by_week[s.week]
        if ss.eb.selected(result) != self.reference & period.keys:
            raise ValueError(("Weekly witness omits registration", s.proof))
        checked = ss.meter_replay(period, active.hardware(), ss.eb.DEFAULT_SPEC, s.caps, result)
        if not checked["passed"]:
            raise ValueError(("Target hardware witness replay failed", s.proof, active.label))
        for site in ss.SITES:
            for key in ("site_grid_kwh", "site_quarter_peak_kw"):
                ss.close(checked[key][site], audit[key][site], (s.proof, active.label, key, site))
        ss.close(checked["purchase_eur"], audit["purchase_eur"], s.proof)
        return True

    def _donor(self, week, active, caps):
        at_caps = self.at_caps[week, caps]
        ordered = sorted(at_caps, key=lambda s: s.design != active)
        return next((s for s in ordered if ss._dominates(s.design, active) and self._fits(s, active)), None)

    def _physical_week(self, week, design, caps):
        energy = self.bounds.weekly_kwh[week]
        upper, floor, peaks, impossible = self.windows.envelopes(week, design, caps, energy)
        return dict(week=week, proof=None, source="window_capacity", site_kwh_upper=list(upper),
                    site_kwh_floor=list(floor), site_peak_floor=list(peaks), fixed_grid_kwh=energy,
                    infeasible=impossible, purchase_lower_eur_2021=self.bounds.weekly_floor[week] - ss.EPS,
                    purchase_upper_eur_2021=None, purchase_proof=None)

    def _screen_week(self, week, design, caps):
        active = ss._active_build(design, caps)
        row = self._physical_week(week, design, caps)
        if row["infeasible"]:
            return row
        dual = next((s for s in self.duals[week] if _contains(s.design, s.caps, active, caps)), None)
        if dual and dual.lower > self.bounds.weekly_floor[week]:
            row.update(purchase_lower_eur_2021=dual.lower - ss.EPS, purchase_proof=dual.proof)
        s = self._donor(week, active, caps)
        if s:
            audit = self._audit(s.proof)
            row.update(proof=s.proof, source="identical_request" if s.design == active else "fitting_superset_same_caps",
                       site_kwh_floor=[audit["site_grid_kwh"][site] for site in ss.SITES],
                       site_peak_floor=[audit["site_quarter_peak_kw"][site] for site in ss.SITES],
                       purchase_upper_eur_2021=audit["purchase_eur"])
        return row

    def _fees(self, design, caps, weekly):
        equip, missing, connections = ss.annual_capital_costs(design, self.materials)
        purchase = math.fsum(w["purchase_lower_eur_2021"] for w in weekly) * self.factor
        network = _meter_bounds(self.bounds, caps, weekly)
        for (scenario, basis), incumbent in self.incumbent.items():
            grid = network[scenario]
            total = math.fsum((equip, connections[basis], purchase, grid)) - ss.EPS
            yield dict(scenario=scenario, connection_basis=basis, equipment_eur_2025=equip,
                       unpriced_charger_kw=missing, connection_eur_2025=connections[basis],
                       purchase_lower_eur_2025=purchase, network_lower_eur_2025=grid if math.isfinite(grid) else None,
                       annual_lower_eur_2025=total if math.isfinite(total) else None, incumbent_upper_eur_2025=incumbent,
                       no_relaxed_split=total == math.inf, above_incumbent=total > incumbent + COST_MARGIN_EUR)

    def backtest(self):
        """Yield every comparison and leave screening locked after any failed fold."""
        self._passed = False
        count = 0
        for (label, caps), source in sorted(self.week_rows.items()):
            if not all(r["point_status"] in ss.ENERGY_ACCEPTED for r in source.values()):
                continue
            design = self.builds[label]
            if source.keys() != self.by_week.keys():
                raise ValueError(("Incomplete admitted point", label, caps))
            for held in self.by_week:
                weekly = []
                for week in self.by_week:
                    if week == held:
                        w = self._physical_week(week, design, caps)
                    else:
                        r = source[week]
                        w = dict(week=week, proof=r["evidence_id"], source="frozen_coarse_point",
                                 site_kwh_floor=[float(r["port_kwh"]), float(r["warehouse_kwh"])],
                                 site_peak_floor=[float(r["port_peak_kw"]), float(r["warehouse_peak_kw"])],
                                 purchase_lower_eur_2021=float(r["purchase_lower"]) - ss.EPS, infeasible=False)
                    weekly.append(w)
                physical = any(w["infeasible"] for w in weekly)
                donors = [w["proof"] for w in weekly if w["proof"]]
                fees = self._fees(design, caps, weekly) if not physical else (
                    dict(scenario=s, connection_basis=b) for s,b in self.incumbent)
                for fee in fees:
                    s, b = fee["scenario"], fee["connection_basis"]
                    actual = self.invoices[label, caps, s, b]
                    lower = fee.get("annual_lower_eur_2025")
                    margin = actual - lower if lower is not None else None
                    passed = margin is not None and margin >= 0
                    count += 1
                    yield dict(design=label, port_cap_kw=caps[0], warehouse_cap_kw=caps[1], held_week=held,
                               scenario=s, connection_basis=b, purchase_lower_eur_2025=fee.get("purchase_lower_eur_2025"),
                               network_lower_eur_2025=fee.get("network_lower_eur_2025"),
                               equipment_eur_2025=fee.get("equipment_eur_2025"), connection_eur_2025=fee.get("connection_eur_2025"),
                               annual_lower_eur_2025=lower, actual_eur_2025=actual, margin_eur_2025=margin, passed=passed,
                               reason=("passed" if passed else "no_relaxed_split" if lower is None else "lower_exceeds_invoice"),
                               frozen_proof_ids=donors)
                    if not passed:
                        return
        if not count or count != len(self.invoices) * len(self.by_week):
            raise ValueError("Incomplete leave-one-week-out comparisons")
        self._passed = True

    @staticmethod
    def _exclusion(design, caps, proofs):
        active = ss._active_build(design, caps)
        return next((s for s in proofs if _contains(s.design, s.caps, active, caps)), None)

    def _inventory(self):
        for design in sorted(self.builds.values()):
            # Reproduce the R012 counting boundary before applying any new
            # window or meter bound. Its 34 hardware labels are archive inputs.
            if self._exclusion(design, design.caps, self.inventory_failures):
                continue
            for caps in self.dispatch.options(design, ss.FINE_KW):
                if (design.label, caps) not in self.week_rows:
                    yield design, caps

    def _service_weeks(self, design, weekly):
        frozen = {w["week"]: w["proof"] for w in weekly if w["proof"]}
        proofs = {}
        for week in self.by_week:
            if week in frozen:
                proofs[week] = frozen[week]
                continue
            for hardware, proof in self.service_proofs[week]:
                if ss._dominates(design, hardware):
                    proofs[week] = proof
                    break
        return [week for week in self.by_week if week not in proofs], proofs

    def _screen_point(self, design, caps):
        equip, missing_ratings, connection = ss.annual_capital_costs(design, self.materials)
        priced = not missing_ratings
        weekly, fees, exclusion = [], [], None
        witness = self._exclusion(design, caps, self.failures)
        if witness:
            reason = "infeasible_superset"
            exclusion = dict(week=witness.week, design=witness.design.label, caps_kw=list(witness.caps),
                             proof=witness.proof)
        else:
            for week in self.by_week:
                row = self._screen_week(week, design, caps)
                weekly.append(row)
                if row["infeasible"]:
                    exclusion = dict(week=week, fixed_grid_kwh=row["fixed_grid_kwh"],
                                     maximum_delivery_kwh=sum(row["site_kwh_upper"]))
                    break
            reason = "weekly_window_capacity" if exclusion else None
        if exclusion:
            for (s, basis), incumbent in self.incumbent.items():
                fees.append(dict(scenario=s, connection_basis=basis, equipment_eur_2025=equip,
                                 unpriced_charger_kw=missing_ratings, connection_eur_2025=connection[basis],
                                 purchase_lower_eur_2025=None, network_lower_eur_2025=None, annual_lower_eur_2025=None,
                                 incumbent_upper_eur_2025=incumbent, no_relaxed_split=None, above_incumbent=None))
        else:
            fees = list(self._fees(design, caps, weekly))
            infeasible = {r["no_relaxed_split"] for r in fees}
            if len(infeasible) != 1:
                raise ValueError(("Tariff-specific feasibility contradiction", design, caps))
            if True in infeasible:
                reason = "infeasible_network_relaxation"
                exclusion = dict(weeks=[w["week"] for w in weekly], annual_grid_kwh=self.bounds.annual_kwh,
                                 available_hours=list(self.bounds.annual_hours))
            elif priced and all(r["above_incumbent"] for r in fees):
                reason = "priced_above_all_incumbents"
            else:
                reason = "retained_priced" if priced else "unquoted_comparison"
        retain = reason in ("retained_priced", "unquoted_comparison")
        missing = [w["week"] for w in weekly if not w["proof"]] if retain else []
        service_weeks, service_proofs = self._service_weeks(design, weekly) if retain else ([], {})
        return dict(design=design.label, port_plugs=design.port_plugs, port_kw=design.port_kw,
                    warehouse_kw=design.warehouse_kw, caps_kw=list(caps), priced=priced,
                    missing_ratings_kw=missing_ratings, decision="retain" if retain else "exclude", reason=reason,
                    weekly=weekly, tariffs=fees, exclusion=exclusion, missing_weeks=missing, service_weeks=service_weeks,
                    rated_service_proofs=service_proofs)

    def iter_screen(self, check=None):
        if not self._passed:
            raise RuntimeError("The complete strict leave-one-week-out backtest must pass before screening")
        inventory = list(self._inventory())
        if len(inventory) != self.expected_points or len(set(inventory)) != self.expected_points:
            raise ValueError(("R012 refinement inventory differs", len(inventory), self.expected_points))
        for design, caps in inventory:
            if check:
                check()
            yield self._screen_point(design, caps)

    def screen(self, check=None):
        return list(self.iter_screen(check))
