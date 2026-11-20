"""Archive-only proof loading and validation for the site-sizing screen."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import gzip
import json
import math
from pathlib import Path

from . import site_sizing as ss
from .__main__ import digest
from .cabinet_audit import audit_settlement


@dataclass(frozen=True)
class ArchiveWeek:
    week: str
    design: ss.Design
    caps: tuple[int, int]
    status: str
    lower_eur: float | None
    upper_eur: float | None
    audit: dict | None
    proof: str
    proof_sha256: str
    source_commit: str

    @property
    def scope(self):
        return self.week, self.design, self.caps


@dataclass(frozen=True)
class PointPlan:
    status: str
    proof: ArchiveWeek | None = None
    missing: tuple = ()
    weeks: tuple[ArchiveWeek, ...] = ()


@dataclass(frozen=True)
class AnnualPoint:
    design: ss.Design
    caps: tuple[int, int]
    weeks: tuple[ArchiveWeek, ...]
    dispatch: dict
    totals: dict


@dataclass
class Evidence:
    publication: dict
    network: dict
    materials: dict
    scenarios: tuple[str, ...]
    periods: dict
    reference: set
    cases: dict
    prescan_points: tuple
    pilot_summary: dict
    archive_sha256: dict
    archive_records: tuple[ArchiveWeek, ...]
    pilot_records: tuple[ArchiveWeek, ...]
    records_by_week: dict
    archive_index: tuple
    combined_index: tuple
    annual_points: tuple[AnnualPoint, ...] = field(default=())

    def point_plan(self, design, caps, *, include_pilot=True):
        """Reuse only an accepted optimum at the same caps that fits the requested build."""
        at_caps, infeasible = self.combined_index if include_pilot else self.archive_index
        active = ss._active_build(design, caps)
        for record in infeasible:
            if record.design == active and record.caps == caps:
                return PointPlan("infeasible_solve", record)
        for record in infeasible:
            if ss._dominates(record.design, active) and all(
                upper >= cap for upper, cap in zip(record.caps, caps, strict=True)
            ):
                return PointPlan("infeasible_monotonicity", record)
        accepted = []
        missing = []
        for week in self.periods:
            available = at_caps.get((week, caps), {})
            direct = available.get(active)
            if direct is not None:
                accepted.append(direct)
                continue
            wider = next((record for hardware, record in available.items()
                          if ss._dominates(hardware, active)
                          and record.audit["used_plugs"][ss.PORT] <= active.port_plugs
                          and all(record.audit["site_peak_kw"][site] <= limit + ss.EPS
                                  for site, limit in zip(ss.SITES, active.caps, strict=True))), None)
            if wider is None:
                missing.append((week, active, caps))
            else:
                accepted.append(wider)
        return PointPlan("needs_solves" if missing else "settled",
                         missing=tuple(missing), weeks=tuple(accepted))


def _require(valid, message):
    if not valid:
        raise ValueError(message)


def _verified_digest(path, expected):
    actual = digest(path)
    _require(actual == expected, f"Archive or input hash changed: {path}")
    return actual


def _ledgers(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            # An interrupted last write is not a solver proof.
            if i != len(lines) - 1 or line.endswith("}"):
                raise


def _load_week(folder, row, source, prefix, cases, periods, reference, expected_sha=None):
    ident = row["id"]
    _require(Path(ident).name == ident and ident.isdecimal(), ("Invalid proof id", ident))
    proof_file = folder / (ident + ".json.gz")
    proof = prefix + "/" + ident
    sha = digest(proof_file) if expected_sha is None else _verified_digest(proof_file, expected_sha)
    with gzip.open(proof_file, "rt", encoding="utf-8") as file:
        witness = json.load(file)
    _require(all(witness.get(key) == value for key, value in row.items()),
             ("Ledger differs from gzip", proof))
    stats = witness["result"]["stats"]
    _require(all(row[key] == value for key, value in stats.items()),
             ("Ledger differs from solver statistics", proof))
    _require(row["model"] == "grouped" and row["delay_min"] == 0 and row["phase"] == "energy",
             ("Different charging model", proof))
    week = row["week"]
    design = cases[row["design"]]
    caps = tuple(row["caps_kw"])
    _require(design == ss._active_build(design, caps) and
             all(0 <= cap <= installed for cap, installed in zip(caps, design.caps, strict=True)),
             ("Invalid active facility/caps", proof))
    status = row["status"]
    lower = row["objective_lower"]
    upper = row["objective_upper"]
    if status == "infeasible":
        _require(row["status_code"] == 2 and witness["result"]["audit"] is None,
                 ("Invalid infeasibility proof", proof))
    elif status in ss.ENERGY_ACCEPTED:
        standard = row["absolute_gap"] is not None and (
            row["absolute_gap"] <= ss.fc.ABSOLUTE_COST_GAP + 1e-9
            or row["relative_gap"] is not None and row["relative_gap"] <= ss.fc.RELATIVE_COST_GAP + 1e-12)
        timed_out = row["status_code"] == 1 and "time limit" in row["message"].lower()
        _require(lower is not None and upper is not None and math.isfinite(lower)
                 and math.isfinite(upper) and lower <= upper, ("Invalid accepted interval", proof))
        _require((status == "certified" and row["status_code"] == 0 and standard)
                 or (status == "bounded" and timed_out and
                     row["absolute_gap"] <= ss.TIMEOUT_COST_GAP_EUR + 1e-9),
                 ("Improper weekly certificate", proof))
        native = row["native_mip_dual_bound"]
        _require(lower == native or (status == "certified" and native is None and lower == upper),
                 ("Accepted lower does not reproduce solver bound", proof))
    elif status == "unresolved":
        # A time limit may fail to deliver a usable dual bound or an incumbent.
        # Only an actual finite solver dual bound can support screening.
        if (row["status_code"] != 1 or lower is None or not math.isfinite(lower)
                or row["native_mip_dual_bound"] != lower
                or upper is not None and (not math.isfinite(upper) or lower > upper)):
            lower = None
    else:
        raise ValueError(("Unknown energy proof status", proof, status))
    result = witness["result"]
    audit = result["audit"]
    _require(row["audited"] == (audit is not None), ("Ledger audit mismatch", proof))
    if audit is not None:
        _require(audit["passed"] is True and ss.eb.selected(result) == reference & periods[week].keys,
                 ("Saved replay failed or uses a different service cohort", proof))
        ss.close(audit["purchase_eur"], upper, proof)
        if expected_sha is not None:
            replay = ss.meter_replay(periods[week], design.hardware(), ss.eb.DEFAULT_SPEC, caps, result)
            _require(replay["passed"] is True, ("Independent pilot replay failed", proof))
            ss.close(replay["purchase_eur"], audit["purchase_eur"], proof)
            for field in ("site_grid_kwh", "site_peak_kw", "site_quarter_peak_kw"):
                for site in ss.SITES:
                    ss.close(replay[field][site], audit[field][site], (proof, field, site))
            _require(replay["used_plugs"] == audit["used_plugs"], ("Pilot replay plug mismatch", proof))
    else:
        _require(status not in ss.ENERGY_ACCEPTED, ("No accepted schedule audit", proof))
    return ArchiveWeek(week, design, caps, status, lower, upper, audit, proof, sha, source)


def _weekly_index(records):
    accepted = defaultdict(dict)
    infeasible = {}
    feasible = set()
    for record in records:
        if record.status in ss.ENERGY_ACCEPTED:
            accepted[record.week, record.caps][record.design] = record
            feasible.add(record.scope)
        elif record.status == "infeasible":
            infeasible[record.scope] = record
    _require(not feasible.intersection(infeasible), "Conflicting archived weekly proof statuses")
    return dict(accepted), tuple(infeasible.values())


def _read_inputs(archive, pilot_run, publication):
    metadata = ss.eb.read_json(archive / "publication_recovery.json")
    supplemental = ss.eb.read_json(archive / "coarse_completion" / "summary.json")
    inventory = ss.eb.read_json(pilot_run / "inventory.json")
    pilot_summary = ss.eb.read_json(pilot_run / "pilot" / "summary.json")
    pilot_audit = ss.eb.read_json(pilot_run / "pilot_audit.json")
    inputs = publication["inputs_sha256"]
    _require(bool(inputs) and inputs == metadata["inputs_sha256"] == supplemental["input_hashes"]
             == inventory["input_hashes"] == pilot_summary["inputs_sha256"] == pilot_audit["inputs_sha256"],
             "Archive, pilot, and published inputs do not match")
    for name, expected in inputs.items():
        _verified_digest(ss.eb.ROOT / name, expected)
    _require(metadata["source"] == publication["source"]
             and pilot_summary["source"] == inventory["source"]
             and not pilot_summary["source"]["dirty"] and pilot_audit["status"] == "passed",
             "Archive or pilot solver/source provenance mismatch")
    archive_hashes = {}
    for key, value in publication["offline_evidence"]["files_sha256"].items():
        if key in ("publication_recovery.json", "coarse_completion/summary.json"):
            archive_hashes["archive/" + key] = _verified_digest(archive / key, value)
    for name, expected in inventory["archive_ledger_sha256"].items():
        actual = _verified_digest(archive / name, expected)
        published_hash = publication["offline_evidence"]["files_sha256"].get(name)
        _require(published_hash is None or actual == published_hash, ("Published ledger mismatch", name))
        archive_hashes["archive/" + name] = actual
    archive_hashes["pilot_run/inventory.json"] = _verified_digest(
        pilot_run / "inventory.json", pilot_summary["inventory_sha256"])
    for name in ("pilot/summary.json", "pilot_audit.json"):
        archive_hashes["pilot_run/" + name] = digest(pilot_run / name)
    _require(inventory["source_by_archived_run"]["coarse_completion"] == supplemental["source"]["commit"]
             and all(source == metadata["source"]["commit"]
                     for name, source in inventory["source_by_archived_run"].items()
                     if name != "coarse_completion"),
             "Archive ledger source mapping differs from published provenance")
    return inventory, pilot_summary, pilot_audit, archive_hashes


def _load_pilot(pilot_run, summary, audit, hashes, cases, periods, reference):
    audit_records = {item["proof"]: item for item in audit["records"]}
    summary_records = {"pilot/" + item["proof"]: item for item in summary["results"]}
    _require(len(audit_records) == len(summary_records) == summary["completed_sample_size"]
             and audit_records.keys() == summary_records.keys(), "Pilot proof manifests differ")
    rows = []
    for ledger in sorted((pilot_run / "pilot").glob("worker-*/solves.jsonl")):
        folder = ledger.parent
        prefix = f"pilot/{folder.name}"
        hashes[f"pilot_run/{prefix}/solves.jsonl"] = digest(ledger)
        for row in _ledgers(ledger):
            name = f"{prefix}/{row['id']}"
            recorded = summary_records.pop(name)
            audited = audit_records[name]
            _require(all(row[key] == recorded[key] == audited[key]
                         for key in ("week", "design", "caps_kw", "status"))
                     and [row["objective_lower"], row["objective_upper"]] == audited["bounds_eur_2021"]
                     and row["objective_lower"] == recorded["lower_eur_2021"]
                     and row["objective_upper"] == recorded["upper_eur_2021"]
                     and row["audited"] == recorded["replay_passed"] == audited["replay_passed"]
                     and recorded["proof_sha256"] == audited["proof_sha256"], ("Pilot manifest mismatch", name))
            rows.append(_load_week(folder, row, summary["source"]["commit"], "pilot_run/" + prefix,
                                   cases, periods, reference, recorded["proof_sha256"]))
    _require(not summary_records and dict(Counter(r.status for r in rows)) == summary["status_counts"],
             "Pilot ledger does not contain all results")
    return tuple(rows)


def _annual_point(evidence, design, caps, weeks):
    purchase = math.fsum(w.audit["purchase_eur"] for w in weeks)
    volumes = {site: math.fsum(w.audit["site_grid_kwh"][site] for w in weeks) for site in ss.SITES}
    peaks = {site: max(w.audit["site_quarter_peak_kw"][site] for w in weeks) for site in ss.SITES}
    bills = {}
    for scenario in evidence.scenarios:
        bill = ss.settle(evidence.network, purchase, volumes, peaks, scenario)
        audit_settlement(evidence.network, purchase, volumes, peaks, scenario, bill)
        bills[scenario] = bill
    dispatch = dict(design=design.label, caps_kw=caps,
                    status="bounded" if any(w.status == "bounded" for w in weeks) else "certified",
                    purchase_eur=purchase, lower_eur=math.fsum(w.lower_eur for w in weeks),
                    weeks=[{"solve": w.proof.removeprefix("archive/")} for w in weeks], bills=bills,
                    site_grid_kwh=volumes, site_quarter_peak_kw=peaks)
    known, _, connections = ss.annual_capital_costs(design, evidence.materials)
    totals = {
        scenario: {basis: math.fsum((known, connection, bill["annual_total_eur_2025"]))
                   for basis, connection in connections.items()}
        for scenario, bill in bills.items()
    }
    return AnnualPoint(design, caps, weeks, dispatch, totals)


def _reconstruct_points(evidence, registered_points):
    coarse = set(ss.design_grid(ss.COARSE_KW))
    grid = ss.DispatchGrid([], None, None, None)
    statuses = defaultdict(Counter)
    annual_points = []
    registration = {(p["design"], tuple(p["caps_kw"])): p for p in registered_points}
    for row in evidence.publication["service"]:
        if not row["same_service"]:
            continue
        design = evidence.cases[row["design"]]
        coarse_caps = set(grid.options(design, ss.COARSE_KW)) if design in coarse else set()
        for caps in grid.options(design, ss.FINE_KW):
            is_coarse = caps in coarse_caps
            plan = evidence.point_plan(design, caps, include_pilot=False)
            statuses["coarse" if is_coarse else "fine"][plan.status] += 1
            if plan.status == "settled":
                annual_points.append(_annual_point(evidence, design, caps, plan.weeks))
            if not is_coarse:
                saved = registration.pop((design.label, caps))
                _, missing, _ = ss.annual_capital_costs(design, evidence.materials)
                _require(saved["status"] == plan.status and saved["priced"] == (not missing),
                         ("Prior inventory scope, status, or price coverage differs", design.label, caps))
                registered_missing = tuple((w["week"], evidence.cases[w["design"]], tuple(w["caps_kw"]))
                                           for w in saved["weeks"] if w["action"] == "solve")
                _require(registered_missing == plan.missing,
                         ("Prior inventory missing weekly scopes differ", design.label, caps))
    counts = evidence.publication["observed_cost_checkpoints"]
    _require(not registration and not statuses["coarse"]["needs_solves"], "Grid coverage differs from publication")
    for grid_name, by_status in statuses.items():
        _require(by_status["settled"] == counts[f"{grid_name}_replayed"]
                 and by_status["infeasible_solve"] + by_status["infeasible_monotonicity"]
                 == counts[f"{grid_name}_certified_infeasible"],
                 ("Published point counts do not reproduce", grid_name, dict(by_status)))
    return tuple(annual_points)


def load_evidence(archive_directory, pilot_parent_directory):
    """Read archived proofs and reconstruct the published annual sample without solving."""
    archive = Path(archive_directory)
    pilot_run = Path(pilot_parent_directory)
    publication = ss.eb.read_json(ss.eb.WEEKS.with_name("site_sizing.json"))
    inventory, summary, audit, hashes = _read_inputs(archive, pilot_run, publication)
    periods = {period.days[0]["week_start"]: period for period in ss.fc._periods("full")}
    cases = {design.label: design for design in ss.design_grid(ss.FINE_KW)}
    reference = set(map(tuple, publication["reference_service"]))
    baseline, = [set(map(tuple, row["selected"])) for row in ss.eb.read_json(ss.fc.BASELINE)["full"]
                 if row["rule"] == ss.eb.B and row["facility"] == "one" and row["spec"] == "S300"]
    _require(reference == baseline, "Published service differs from the matched baseline")
    records = []
    for directory, source in inventory["source_by_archived_run"].items():
        folder = archive / directory
        for row in _ledgers(folder / "solves.jsonl"):
            if row["phase"] == "energy":
                records.append(_load_week(folder, row, source, "archive/" + directory,
                                          cases, periods, reference))
    records = tuple(records)
    pilot_records = _load_pilot(pilot_run, summary, audit, hashes, cases, periods, reference)
    by_week = defaultdict(list)
    for record in records + pilot_records:
        if record.lower_eur is not None:
            by_week[record.week].append(record)
    network = ss.load_network()
    scenarios = ("N0", *network["tariffs"], *network["capacity_sensitivities_eur_per_kw_year"])
    materials = ss._load_costs(ss.eb.ROOT / "studies/day-ahead/connection_cost.json", network)
    prescan = tuple(point for point in inventory["points"] if point["priced"] and point["status"] == "needs_solves")
    _require(len(prescan) == inventory["remaining_priced"], "Priced pending count differs from prior inventory")
    evidence = Evidence(publication, network, materials, scenarios, periods, reference, cases, prescan,
                        summary, hashes, records, pilot_records, dict(by_week),
                        _weekly_index(records), _weekly_index(records + pilot_records))
    evidence.annual_points = _reconstruct_points(evidence, inventory["points"])
    return evidence


class BacktestFailure(ValueError):
    """Stop the screen and preserve the disproving row and partial backtest."""

    def __init__(self, report, witness):
        super().__init__(f"Archive lower-bound backtest failed: {witness}")
        self.report = {**report, "status": "failed", "violation": witness}


def _sample(result, margin, row, suffix, report):
    result["checks"] += 1
    minimum = "min_margin_" + suffix
    if result.get(minimum) is None or margin < result[minimum]:
        result[minimum] = margin
    row = {**row, "margin_" + suffix: margin}
    result["tightest"].append(row)
    result["tightest"].sort(key=lambda item: item["margin_" + suffix])
    del result["tightest"][5:]
    if margin < 0:
        raise BacktestFailure(report, row)


def _winner_regression(evidence):
    operations = defaultdict(list)
    for point in evidence.annual_points:
        operations[point.design].append(point.dispatch)
    grid = ss.DispatchGrid([], None, None, None)
    grid.check_order(operations)
    _, winners = ss.annual_tables(operations, evidence.materials, evidence.scenarios)
    rows = []
    for old in evidence.publication["winners"]:
        key = old["scenario"], old["connection_basis"]
        actual = winners[key]
        rows.append(dict(scenario=key[0], connection_basis=key[1], design=actual["design"],
                         caps_kw=actual["caps_kw"], published_design=old["design"],
                         published_caps_kw=old["caps_kw"], published_eur=old["annual_total_eur"],
                         replayed_eur=actual["annual_total_eur"],
                         difference_eur=actual["annual_total_eur"] - old["annual_total_eur"]))
    _require(len(rows) == len(winners), "Some published scenarios did not reproduce")
    return dict(checks=len(rows), max_difference_eur=max(abs(row["difference_eur"]) for row in rows),
                monotone_wholesale_checks=grid.energy_checks, rows=rows)


def backtest(evidence, bounds):
    """Check every accepted weekly proof and every published six-week point."""
    weekly = dict(checks=0, fallback_checks=0, min_margin_eur_2021=None, tightest=[],
                  accepted_pilot_records=0)
    annual = dict(points=0, checks=0, min_margin_eur_2025=None, tightest=[],
                  wholesale=dict(checks=0, min_margin_eur_2025=None, tightest=[]),
                  network=dict(checks=0, min_margin_eur_2025=None, tightest=[]), fallback_week_uses=0)
    report = dict(status="passed", weekly=weekly, annual=annual)
    for record in evidence.archive_records + evidence.pilot_records:
        if record.status not in ss.ENERGY_ACCEPTED:
            continue
        found = bounds.weekly_lower_bound(record.week, record.design, record.caps,
                                          evidence.records_by_week[record.week],
                                          exclude_scopes={(record.design, record.caps)})
        weekly["fallback_checks"] += found.proof is None
        weekly["accepted_pilot_records"] += record.proof.startswith("pilot_run/")
        _sample(weekly, record.upper_eur - found.lower_eur,
                dict(week=record.week, design=record.design.label, caps_kw=record.caps,
                     actual=record.upper_eur, lower=found.lower_eur, proof=record.proof,
                     selected_lower_proof=found.proof), "eur_2021", report)
    for point in evidence.annual_points:
        description = dict(design=point.design.label, caps_kw=point.caps)
        active = ss._active_build(point.design, point.caps)
        excluded = {(active, point.caps), *((week.design, week.caps) for week in point.weeks)}
        lower = bounds.annual_lower_bounds(point.design, point.caps, evidence.records_by_week,
                                           exclude_scopes=excluded)
        annual["points"] += 1
        annual["fallback_week_uses"] += sum(value.proof is None for value in lower["weekly"].values())
        for scenario, bill in point.dispatch["bills"].items():
            context = {**description, "scenario": scenario}
            purchase = bill["annual_energy_eur_2025"]
            network = math.fsum((bill["annual_network_energy_eur_2025"], bill["annual_capacity_eur_2025"]))
            _sample(annual["wholesale"], purchase - lower["purchase_eur"],
                    {**context, "actual": purchase, "lower": lower["purchase_eur"]}, "eur_2025", report)
            _sample(annual["network"], network - lower["network_eur"][scenario],
                    {**context, "actual": network, "lower": lower["network_eur"][scenario]}, "eur_2025", report)
            for basis, value in point.totals[scenario].items():
                annual_lower = lower["total_eur"][scenario][basis]
                _sample(annual, value - annual_lower,
                        {**context, "connection_basis": basis, "actual": value,
                         "lower": annual_lower}, "eur_2025", report)
    report["published_winners"] = _winner_regression(evidence)
    for row in report["published_winners"]["rows"]:
        if (abs(row["difference_eur"]) > 1e-6 or row["design"] != row["published_design"]
                or tuple(row["caps_kw"]) != tuple(row["published_caps_kw"])):
            raise BacktestFailure(report, row)
    return report
