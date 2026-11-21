"""Coarse operating limits and twelve-week fixed-service invoices."""
from collections import Counter, defaultdict
from datetime import datetime
from itertools import product
import math
from statistics import mean

from . import site_sizing as ss
from .cabinet_tariff import annual_factors
from .m10_evidence import Request
from .site_sizing_bounds import AnnualBillBounds, WholesaleRecord
from .site_sizing_screen import COST_MARGIN_EUR


_POINT = dict(design="Installed hardware identifier.",
              port_cap_kw="Port quarter-hour demand limit, kW.",
              warehouse_cap_kw="Warehouse quarter-hour demand limit, kW.")
OPERATING_COLUMNS = dict(
    **_POINT, week="Berlin week starting date.", point_status="Twelve-week fixed-service classification.",
    status="Weekly solve classification; not_required identifies an unexamined week at an excluded point.",
    method="Weekly proof method.", evidence_id="Weekly solve or service proof identifier.",
    purchase_lower="Lower bound on weekly procurement, EUR 2021.",
    purchase_upper="Replayed weekly procurement, EUR 2021.",
    port_kwh="Weekly port grid energy, kWh.", warehouse_kwh="Weekly warehouse grid energy, kWh.",
    port_peak_kw="Maximum port mean quarter demand, kW.", warehouse_peak_kw="Maximum warehouse mean quarter demand, kW.")
ANNUAL_COLUMNS = dict(
    **_POINT, scenario="Network tariff.", connection_basis="New or existing grid connection.",
    status="Twelve-week point classification.", missing_ratings_kw="Space-separated unquoted charger sizes, kW.",
    equipment="Known annual charger capital recovery and maintenance, EUR 2025/year.",
    connection="Annual connection capacity charge, EUR 2025/year.",
    purchase_lower="Annual wholesale lower bound, EUR 2025/year.",
    purchase_upper="Annual replayed wholesale procurement, EUR 2025/year.",
    network_energy="Annual metered network volume charge, EUR 2025/year.",
    demand="Annual metered capacity charge, EUR 2025/year.",
    total_lower="Lower bound in EUR 2025/year. For settled points the published meter trace is frozen.",
    total_upper="Replayed annual invoice under the registered weekly gap rule, EUR 2025/year.",
    witness_upper="Feasible replayed annual invoice before the gap rule, EUR 2025/year; blank without all weeks or a quote.",
    rank_best="Best possible point rank among priced points of this tariff and connection basis.",
    rank_worst="Conservative worst possible point rank, allowing ties within the numerical margin.")


def _parameters(periods):
    six = ss.load_network()
    # The independent 50 kW equipment benchmark takes six reference entries.
    # Capital recovery does not depend on the length of the operating sample.
    materials = ss._load_costs(ss.CONNECTION_INPUT, six)
    network = {**six, "annualization": {**six["annualization"], "sample_weeks": len(periods)}}
    return network, materials


def _point(design, caps):
    return dict(design=design.label, port_cap_kw=caps[0], warehouse_cap_kw=caps[1])


def _contains(large, high, small, low):
    return ss._dominates(large, small) and all(a >= b for a, b in zip(high, low, strict=True))


def _row(label, result):
    stats = result["stats"]
    row = dict(status=stats["status"], solve=label, lower_eur=stats["objective_lower"],
               upper_eur=stats["objective_upper"], method="weekly_request")
    if result["audit"] is not None:
        for key in ("purchase_eur", "site_peak_kw", "site_grid_kwh", "site_quarter_peak_kw", "used_plugs"):
            row[key] = result["audit"][key]
    return row


class CoarseDispatch(ss.DispatchGrid):
    """Run the M8 grid order, scheduling independent weeks together at each point."""
    def __init__(self, inputs, service, network, evidence):
        super().__init__(inputs.periods, inputs.registered, network, evidence)
        self.failures = []
        self.counts = Counter()
        self.verified = set()
        self.records = defaultdict(list)
        self.records_seen = set()
        for design, item in sorted(service.items(), reverse=True):
            for w in item["weeks"]:
                if w["status"] == "shortfall":
                    self.failures.append((design, design.caps, w["week"], w["evidence_id"]))

    def excluded(self, design, caps):
        active = ss._active_build(design, caps)
        return next(((week, proof) for large, high, week, proof in self.failures
                     if _contains(large, high, active, caps)), None)

    def _reuse(self, week, period, design, caps):
        cache = self.cache[week, caps, 0]
        if design in cache:
            return {**cache[design], "method": "identical_request"}
        for large, row in cache.items():
            if (row["status"] not in ss.ENERGY_ACCEPTED or not ss._dominates(large, design)
                    or row["used_plugs"][ss.PORT] > design.port_plugs
                    or any(row["site_peak_kw"][s] > k + ss.EPS for s, k in zip(ss.SITES, design.caps, strict=True))):
                continue
            # The wider solve supplies a lower bound. Independently confirm
            # that its physical schedule supplies the upper bound on this build.
            key = row["solve"], design, caps
            if key not in self.verified:
                result = self.evidence.get(row["solve"])
                replay = ss.meter_replay(period, design.hardware(), ss.eb.DEFAULT_SPEC, caps, result)
                if ss.eb.selected(result) != self.reference & period.keys:
                    raise ValueError(("fixed service reuse", week, design, caps))
                ss.close(replay["purchase_eur"], row["purchase_eur"], key)
                for s in ss.SITES:
                    for measurement in ("site_grid_kwh", "site_quarter_peak_kw"):
                        ss.close(replay[measurement][s], row[measurement][s], key)
                self.verified.add(key)
            return {**row, "method": "larger_hardware_schedule"}
        return None

    def _weeks(self, design, caps):
        active = ss._active_build(design, caps)
        rows, missing, requests = [], [], []
        for i, period in enumerate(self.periods):
            week = period.days[0]["week_start"]
            row = self._reuse(week, period, active, caps)
            rows.append(row)
            if row is None:
                missing.append(i)
                requests.append(Request.make(period, active, "energy", caps, fixed=self.reference & period.keys))
        for i, (label, result) in zip(missing, self.evidence.batch(requests), strict=True):
            rows[i] = _row(label, result)
        for period, row in zip(self.periods, rows, strict=True):
            week = period.days[0]["week_start"]
            self.cache[week, caps, 0][active] = row
            self.counts[row["method"]] += 1
            if row["solve"] not in self.records_seen and row["lower_eur"] is not None:
                self.records[week].append(WholesaleRecord(week, active, caps, row["lower_eur"], row["solve"]))
                self.records_seen.add(row["solve"])
            if row["status"] == "infeasible":
                self.failures.append((active, caps, week, row["solve"]))
        return rows

    def weekly(self, period, design, caps, delay, exact):
        return self.cache[period.days[0]["week_start"], caps, delay][ss._active_build(design, caps)]

    def dispatch(self, design, caps, *, delay=0, exact=False):
        failure = self.excluded(design, caps)
        if failure is not None:
            week, label = failure
            rows = [(dict(status="infeasible", solve=label, method="infeasible_superset")
                     if p.days[0]["week_start"] == week else dict(status="not_required", method="excluded_point"))
                    for p in self.periods]
            self.counts["points_excluded_by_inclusion"] += 1
            return dict(design=design.label, caps_kw=caps, status="infeasible", weeks=rows)
        weeks = self._weeks(design, caps)
        if any(w["status"] not in ss.ENERGY_ACCEPTED for w in weeks):
            status = "infeasible" if any(w["status"] == "infeasible" for w in weeks) else "unresolved"
            return dict(design=design.label, caps_kw=caps, status=status, weeks=weeks)
        return super().dispatch(design, caps)


def _weekly_table(bounds, design, point):
    for week, w in zip(bounds.weeks, point["weeks"], strict=True):
        lower = w.get("lower_eur")
        if w["status"] == "unresolved":
            lower = max(bounds.weekly_floor[week] - ss.EPS, lower if lower is not None else -math.inf)
        kwh, peak = w.get("site_grid_kwh", {}), w.get("site_quarter_peak_kw", {})
        yield dict(**_point(design, point["caps_kw"]), week=week, point_status=point["status"],
                   status=w["status"], method=w["method"], evidence_id=w.get("solve"),
                   purchase_lower=lower, purchase_upper=w.get("purchase_eur"),
                   port_kwh=kwh.get(ss.PORT), warehouse_kwh=kwh.get(ss.WAREHOUSE),
                   port_peak_kw=peak.get(ss.PORT), warehouse_peak_kw=peak.get(ss.WAREHOUSE))


def _invoice_rows(design, point, bounds, records):
    status, caps = point["status"], point["caps_kw"]
    equip, missing, connection = ss.annual_capital_costs(design, bounds.materials)
    relaxed = (bounds.annual_lower_bounds(design, caps, records) if status == "unresolved" else None)
    factor = annual_factors(bounds.network)[0]
    witness_bills = {}
    if relaxed is not None and all("purchase_eur" in w for w in point["weeks"]):
        weeks = point["weeks"]
        expense = math.fsum(w["purchase_eur"] for w in weeks)
        kwh = {s: math.fsum(w["site_grid_kwh"][s] for w in weeks) for s in ss.SITES}
        peaks = {s: max(w["site_quarter_peak_kw"][s] for w in weeks) for s in ss.SITES}
        for scenario in bounds.scenarios:
            bill = ss.settle(bounds.network, expense, kwh, peaks, scenario)
            ss.audit_settlement(bounds.network, expense, kwh, peaks, scenario, bill)
            witness_bills[scenario] = bill
    for scenario, basis in product(bounds.scenarios, connection):
        low = high = witness_high = purchase_low = purchase_high = volume = demand = None
        if status in ss.ENERGY_ACCEPTED:
            bill = point["bills"][scenario]
            purchase_low = min(point["lower_eur"], point["purchase_eur"]) * factor
            purchase_high = bill["annual_energy_eur_2025"]
            volume, demand = bill["annual_network_energy_eur_2025"], bill["annual_capacity_eur_2025"]
            low = math.fsum((equip, connection[basis], purchase_low, volume, demand))
            if not missing:
                high = math.fsum((equip, connection[basis], purchase_high, volume, demand))
                ss.close(high, equip + connection[basis] + bill["annual_total_eur_2025"], "annual invoice")
                witness_high = high
        elif relaxed is not None:
            purchase_low = relaxed["purchase_eur"]
            low = relaxed["total_eur"][scenario][basis]
            if not math.isfinite(low):
                raise ValueError(("Fixed-service network relaxation infeasible at unresolved point", design, caps))
            if scenario in witness_bills:
                bill = witness_bills[scenario]
                purchase_high = bill["annual_energy_eur_2025"]
                volume = bill["annual_network_energy_eur_2025"]
                demand = bill["annual_capacity_eur_2025"]
                if not missing:
                    witness_high = math.fsum((equip, connection[basis], purchase_high, volume, demand))
                    if low > witness_high + COST_MARGIN_EUR:
                        raise ValueError(("Inconsistent unresolved invoice interval", design, caps, scenario, basis))
        yield dict(**_point(design, caps), scenario=scenario, connection_basis=basis, status=status,
                   missing_ratings_kw=" ".join(map(str, missing)), equipment=equip, connection=connection[basis],
                   purchase_lower=purchase_low, purchase_upper=purchase_high, network_energy=volume, demand=demand,
                   total_lower=low, total_upper=high, witness_upper=witness_high, rank_best=None, rank_worst=None)


def _ranks(rows):
    """Strictly separated intervals order two alternatives by the registered margin."""
    from bisect import bisect_left, bisect_right
    valid = [r for r in rows if r["total_lower"] is not None and not r["missing_ratings_kw"]]
    uppers = sorted(r["total_upper"] for r in valid if r["total_upper"] is not None)
    lowers = sorted(r["total_lower"] for r in valid)
    for row in valid:
        row["rank_best"] = 1 + bisect_left(uppers, row["total_lower"] - COST_MARGIN_EUR)
        high = row["total_upper"]
        row["rank_worst"] = len(valid) if high is None else bisect_right(lowers, high + COST_MARGIN_EUR)


def _rank_designs(annual):
    designs, winners, tariffs = [], [], defaultdict(list)
    for row in annual:
        tariffs[row["scenario"], row["connection_basis"]].append(row)
    for (scenario, basis), options in tariffs.items():
        _ranks(options)
        groups = defaultdict(list)
        for row in options:
            if row["total_lower"] is not None:
                groups[row["design"]].append(row)
        ranks = []
        for label, rows in groups.items():
            with_bill = [r for r in rows if r["total_upper"] is not None]
            best = min(with_bill, key=lambda r: (r["total_upper"], r["port_cap_kw"], r["warehouse_cap_kw"]),
                       default=None)
            ranks.append(dict(design=label, scenario=scenario, connection_basis=basis,
                              total_lower=min(r["total_lower"] for r in rows),
                              total_upper=best["total_upper"] if best else None,
                              caps_kw=[best["port_cap_kw"], best["warehouse_cap_kw"]] if best else None,
                              missing_ratings_kw=rows[0]["missing_ratings_kw"], rank_best=None, rank_worst=None))
        _ranks(ranks)
        with_bill = [r for r in ranks if r["total_upper"] is not None]
        incumbent = min(with_bill, key=lambda r: (r["total_upper"], r["design"]), default=None)
        possible = [r for r in ranks if r["rank_best"] == 1]
        winners.append(dict(scenario=scenario, connection_basis=basis,
                            incumbent=incumbent, possible_minimum_designs=sorted(r["design"] for r in possible),
                            minimum_lower=min((r["total_lower"] for r in possible), default=None),
                            minimum_upper=incumbent["total_upper"] if incumbent else None))
        designs.extend(ranks)
    return designs, winners


def _hold_one_week_out(operations, dispatch, bounds):
    """Conceal each audited weekly schedule and test the bound against its purchase and invoice."""
    checked = 0
    tightest = math.inf
    for design, points in operations.items():
        equip, _, connection = ss.annual_capital_costs(design, bounds.materials)
        for point in points:
            if point["status"] not in ss.ENERGY_ACCEPTED:
                continue
            caps = point["caps_kw"]
            network_floor = bounds.network_with_known_peaks(caps, {})
            recovered = point["purchase_eur"]
            for week, w in zip(bounds.weeks, point["weeks"], strict=True):
                other = [r for r in dispatch.records[week] if r.proof != w["solve"]]
                alternate = bounds.weekly_lower_bound(week, design, caps, other)
                if alternate.lower_eur > w["purchase_eur"] + COST_MARGIN_EUR:
                    raise ValueError(("Leave-one-week-out purchase bound", design, caps, week, alternate))
                # Other weeks have fixed, known schedules under this audit.
                year = (recovered - w["purchase_eur"] + alternate.lower_eur) * annual_factors(bounds.network)[0]
                for scenario in bounds.scenarios:
                    charge = point["bills"][scenario]["annual_total_eur_2025"]
                    for capital in connection.values():
                        lower = math.fsum((equip, capital, year, network_floor[scenario]))
                        actual = math.fsum((equip, capital, charge))
                        if lower > actual + COST_MARGIN_EUR:
                            raise ValueError(("Leave-one-week-out invoice bound", design, caps, week, scenario))
                        tightest = min(tightest, actual - lower)
                        checked += 1
    return dict(annual_comparisons=checked, smallest_margin_eur_2025=tightest if checked else None)


def _neighbours(service, operations, bounds, winners):
    # M8 covers its first upper-bound winner at each tariff. Register every
    # additional overlapping minimum with precisely the same 5 kW neighbours.
    added = set(ss._refinements(service, operations, bounds.materials, bounds.scenarios))
    labels = {label for case in winners for label in case["possible_minimum_designs"]}
    extra = set()
    for design in service:
        if design.label not in labels:
            continue
        if design.port_plugs == 1:
            extra.update(ss.Design(1, k, design.warehouse_kw) for k in ss.FINE_KW
                         if k > 0 and 0 < abs(k - design.port_kw) <= 5)
        extra.update(ss.Design(design.port_plugs, design.port_kw, k) for k in ss.FINE_KW
                     if 0 < abs(k - design.warehouse_kw) <= 5)
        if design.warehouse_kw == 0:
            extra.update(ss.Design(design.port_plugs, design.port_kw, k) for k in (10, 15))
    for d in tuple(extra):
        extra.add(ss.Design(max(1, d.port_plugs), 100 if d.port_plugs == 2 else 50, d.warehouse_kw))
        extra.add(ss.Design(d.port_plugs, d.port_kw, 50))
    return sorted((added | extra) - service.keys())


def _estimate(service, operations, dispatch, bounds, winners):
    audit = _hold_one_week_out(operations, dispatch, bounds)
    added = _neighbours(service, operations, bounds, winners)
    complete = [d for d, s in service.items() if s["same_service"]]
    incumbent = {(r["scenario"], r["connection_basis"]): r["minimum_upper"] for r in winners}
    old = {(d, p["caps_kw"]) for d, pts in operations.items() for p in pts}
    known = {(week, rec.design, rec.caps) for week, rows in dispatch.records.items() for rec in rows}
    jobs = set()
    reasons = Counter()
    for design in sorted(set(added) | set(service)):
        if dispatch.excluded(design, design.caps):
            continue
        if not any(ss._dominates(design, d) for d in complete):
            # Upper workload for a hardware whose smaller witnessed fit is
            # unknown: one maximum and one direct fixed-service check per week.
            jobs.update((phase, week, design, design.caps) for week in bounds.weeks
                        for phase in ("service", "energy"))
        for caps in dispatch.options(design, ss.FINE_KW):
            if (design, caps) in old:
                continue
            if dispatch.excluded(design, caps):
                reasons["infeasible_superset"] += 1
                continue
            active = ss._active_build(design, caps)
            lower = bounds.annual_lower_bounds(design, caps, dispatch.records)
            _, missing, _ = ss.annual_capital_costs(design, bounds.materials)
            if all(math.isinf(lower["total_eur"][case][basis]) for case, basis in incumbent):
                reasons["infeasible_network_relaxation"] += 1
                continue
            if not missing and all(best is not None and lower["total_eur"][case][basis] > best + COST_MARGIN_EUR
                                   for (case, basis), best in incumbent.items()):
                reasons["priced_above_all_incumbents"] += 1
                continue
            reasons["unquoted_comparison" if missing else "retained_priced"] += 1
            for week in bounds.weeks:
                if (week, active, caps) not in known:
                    jobs.add(("energy", week, active, caps))

    observations = dispatch.evidence.records
    durations, phases = defaultdict(list), defaultdict(list)
    cases = {d.label: d for d in ss.design_grid(ss.COARSE_KW)}
    for r in observations:
        dual = cases[r["design"]].port_plugs == 2
        stratum = r["phase"], r["week"], dual, bool(r["port_cap_kw"] and r["warehouse_cap_kw"])
        durations[stratum].append(r["seconds"])
        phases[r["phase"]].append(r["seconds"])
    work = []
    for phase, week, d, caps in sorted(jobs):
        stratum = (phase, week, d.port_plugs == 2, all(caps))
        samples = durations.get(stratum) or phases.get(phase) or [ss.fc.SOLVE_SECONDS]
        work.append(mean(samples))
    projected = None
    elapsed = cpu = 0.
    if observations:
        starts = [datetime.fromisoformat(r["started_utc"]).timestamp() for r in observations]
        elapsed = max(s + r["seconds"] for s, r in zip(starts, observations, strict=True)) - min(starts)
        cpu = math.fsum(r["seconds"] for r in observations)
        # Account for observed batch barriers and certificate I/O. Include
        # a long-tail allowance and the same closing reserve as round two.
        if cpu > 0:
            projected = math.fsum(work) * max(elapsed / cpu, 1 / dispatch.evidence.workers)
            projected += max((r["seconds"] for r in observations), default=0.) + 900
    return dict(additional_hardware=[d.label for d in added], new_operating_points=sum(reasons.values()),
                point_counts=dict(reasons), unique_weekly_requests=len(jobs),
                request_counts=dict(Counter(phase for phase, *_ in jobs)),
                estimated_solver_seconds=math.fsum(work), observed_solver_seconds=cpu,
                observed_first_to_last_solve_wall_seconds=elapsed, workers=dispatch.evidence.workers,
                projected_wall_seconds=projected, fits_four_hours=(projected <= 14400 if projected is not None else None),
                estimate_scope="Conditional upper workload before discovering further service shortfalls or schedule reuse. "
                               "Includes unquoted comparisons, up to two service calls per newly ambiguous hardware-week, "
                               "one observed longest solve and 900 closing seconds. Same machine and workers assumed.",
                leave_one_week_out=audit)


def cost_results(inputs, service, evidence, *, progress=None, checkpoint=None):
    network, materials = _parameters(inputs.periods)
    bounds = AnnualBillBounds(inputs.periods, inputs.registered, network, materials)
    dispatch = CoarseDispatch(inputs, service, network, evidence)
    operations, weekly, annual = {}, [], []
    relaxation_proofs = []
    for design in sorted(service, reverse=True):
        data = service[design]
        if data["status"] == "shortfall":
            continue
        points = operations.setdefault(design, [])
        start = len(weekly)
        for caps in reversed(dispatch.options(design, ss.COARSE_KW)):
            evidence.check()
            if data["same_service"] or dispatch.excluded(design, caps):
                point = dispatch.dispatch(design, caps)
            else:
                point = dict(design=design.label, caps_kw=caps, status="unresolved",
                             weeks=[dict(status="unresolved", method="hardware_service_unresolved") for _ in bounds.weeks])
            if point["status"] == "unresolved" and math.isinf(bounds.network_with_known_peaks(caps, {})["N0"]):
                if all("purchase_eur" in w for w in point["weeks"]):
                    raise ValueError(("Complete physical witness contradicts network-energy impossibility", design, caps))
                # This contradiction spans the full sample, so it leaves the
                # individual weekly observations and their evidence IDs intact.
                proof = dict(**_point(design, caps), annual_grid_kwh=bounds.annual_kwh,
                             site_available_hours=dict(zip(ss.SITES, bounds.annual_hours, strict=True)),
                             method="No load split can deliver the fixed annual kWh under the two quarter caps.")
                relaxation_proofs.append(proof)
                point["status"] = "infeasible"
            points.append(point)
            weekly.extend(_weekly_table(bounds, design, point))
        if checkpoint:
            checkpoint(design, weekly[start:])
        if progress:
            progress(f"{design.label} 运行点完成 {len(points)} 个。")
    dispatch.check_order(operations)
    for design, points in operations.items():
        for point in points:
            annual.extend(_invoice_rows(design, point, bounds, dispatch.records))
    designs, winners = _rank_designs(annual)
    _, checked = ss.annual_tables(operations, materials, bounds.scenarios)
    for w in winners:
        key = w["scenario"], w["connection_basis"]
        if key in checked:
            ss.close(checked[key]["annual_total_eur"], w["minimum_upper"], key)
    m8 = ss.eb.read_json(ss.eb.WEEKS.with_name("site_sizing.json"))["winners"]
    current = {d.label: s["status"] for d, s in service.items()}
    reference = {(r["scenario"], r["connection_basis"]): r for r in m8}
    historical = []
    repair = {ss.Design(1, k, 20).label for k in (20, 40)}
    for w in winners:
        case = w["scenario"], w["connection_basis"]
        old = reference[case]
        historical.append(dict(scenario=case[0], connection_basis=case[1], m8_design=old["design"],
                               m8_six_week_based_annual_eur_2025=old["annual_total_eur"],
                               m8_design_twelve_week_status=current[old["design"]],
                               m9_repairs=[r for r in designs if r["design"] in repair
                                           and (r["scenario"], r["connection_basis"]) == case]))
    counts = Counter(p["status"] for opts in operations.values() for p in opts)
    stats = dict(service_excluded=sum(s["status"] == "shortfall" for s in service.values()),
                 points=sum(counts.values()), point_status_counts=dict(counts), reuse=dict(dispatch.counts),
                 monotone_energy_checks=dispatch.energy_checks, replayed_schedule_transfers=len(dispatch.verified),
                 audited_operating_tariffs=dispatch.settlement_checks, annual_cross_checks=len(checked))
    estimate = _estimate(service, operations, dispatch, bounds, winners)
    return dict(operating_points=weekly, annual_costs=annual, design_ranks=designs, winners=winners,
                network_infeasibility_proofs=relaxation_proofs,
                historical_comparison=historical, statistics=stats, refinement_estimate=estimate)
