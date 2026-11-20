"""Reconstruct audited bills and validate peak-informed lower bounds without solving."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
import gzip
import json
import math
from pathlib import Path

from . import site_sizing as ss
from .__main__ import digest
from .cabinet_tariff import annual_factors
from .site_sizing_bounds import AnnualBillBounds
from .site_sizing_screen import COST_MARGIN_EUR
from .site_sizing_screen_evidence import (
    BacktestFailure, _annual_point, _ledgers, _load_week, _require, _weekly_index, load_evidence,
)


def _key(row):
    return row["design"], tuple(row["caps_kw"])


def _check_totals(computed, saved):
    _require(computed.keys() == saved.keys(), "Annual invoice tariff cases changed")
    for scenario, amounts in computed.items():
        _require(amounts.keys() == saved[scenario].keys(), "Annual invoice connection bases changed")
        for basis, value in amounts.items():
            ss.close(value, saved[scenario][basis], (scenario, basis))


def _by_week(records):
    result = defaultdict(list)
    for record in records:
        if record.lower_eur is not None:
            result[record.week].append(record)
    return dict(result)


@dataclass
class Archive:
    evidence: object
    bounds: AnnualBillBounds
    summary: dict
    screening: dict
    phase2_audit: dict
    records_by_id: dict
    ranking_by_week: dict
    quotes_by_week: dict
    quote_evidence: object
    roots: dict
    rank_ids: set
    ranked_settlements: tuple = ()
    verified_meters: set = field(default_factory=set)

    def _verify_meters(self, record, design, caps):
        """Check reuse on the actual billed build and replay each distinct meter trace once."""
        active = ss._active_build(design, caps)
        key = record.proof, active
        _require(record.caps == caps and ss._dominates(record.design, active)
                 and record.audit is not None and record.audit["passed"] is True
                 and record.audit["used_plugs"][ss.PORT] <= active.port_plugs
                 and all(record.audit["site_peak_kw"][site] <= limit + ss.EPS
                         for site, limit in zip(ss.SITES, active.caps, strict=True)),
                 ("Weekly schedule does not fit billed hardware and caps", key, caps))
        if key in self.verified_meters:
            return
        origin, name = record.proof.split("/", 1)
        path = self.roots[origin] / (name + ".json.gz")
        _require(digest(path) == record.proof_sha256, ("Meter proof file changed", record.proof))
        with gzip.open(path, "rt", encoding="utf-8") as file:
            schedule = json.load(file)["result"]
        replay = ss.meter_replay(self.evidence.periods[record.week], active.hardware(),
                                 ss.eb.DEFAULT_SPEC, caps, schedule)
        _require(replay["passed"] and replay["used_plugs"] == record.audit["used_plugs"],
                 ("Physical meter replay failed", key))
        ss.close(replay["purchase_eur"], record.audit["purchase_eur"], key)
        for measurement in ("site_grid_kwh", "site_peak_kw", "site_quarter_peak_kw"):
            for site in ss.SITES:
                ss.close(replay[measurement][site], record.audit[measurement][site], (key, measurement, site))
        self.verified_meters.add(key)

    def _row_records(self, row, field_name):
        design = self.evidence.cases[row["design"]]
        caps = tuple(row["caps_kw"])
        records = []
        for item in row[field_name]:
            record = self.records_by_id[item["proof"]]
            _require(record.week == item["week"] and record.design.label == item["design"]
                     and record.caps == tuple(item["caps_kw"]) == caps
                     and record.proof_sha256 == item["proof_sha256"] and record.status == item["status"]
                     and record.lower_eur == item["lower_eur_2021"] and record.upper_eur == item["upper_eur_2021"]
                     and item["audited"] == (record.audit is not None)
                     and (row["kind"] == "threshold" or record.proof in self.rank_ids),
                     ("Mismatched or quote-only weekly proof", row["design"], item["proof"]))
            if record.audit is not None:
                self._verify_meters(record, design, caps)
            records.append(record)
        _require(len({r.week for r in records}) == len(records), "Repeated proof week")
        return tuple(records)

    def accepted(self, row):
        records = self._row_records(row, "weeks")
        _require(all(r.status in ss.ENERGY_ACCEPTED for r in records), "A failed week cannot fix a meter")
        return records

    def upper(self, row):
        """Return the feasible six-week replay invoice, when all six schedules exist."""
        records = self.accepted(row) + self._row_records(row, "failed_weeks")
        saved = row["totals_eur"] if row["status"] == "settled" else row["annual_upper_totals_eur"]
        if set(r.week for r in records) != set(self.evidence.periods) or any(r.audit is None for r in records):
            _require(saved is None, ("Upper invoice lacks six replayed schedules", _key(row)))
            return None
        _require(len(records) == len(self.evidence.periods), "Duplicated weeks in upper invoice")
        records = tuple(replace(r, lower_eur=r.upper_eur) if r.lower_eur is None else r
                        for r in sorted(records, key=lambda r: r.week))
        upper = _annual_point(self.evidence, self.evidence.cases[row["design"]], tuple(row["caps_kw"]), records)
        _require(saved is not None, ("Missing archived six-week upper invoice", _key(row)))
        _check_totals(upper.totals, saved)
        return upper.totals

    def bill_lower(self, design, caps, accepted, *, quotes=False):
        """Keep the original wholesale and capital bounds; condition network on accepted weeks."""
        records_by_week = self.quotes_by_week if quotes else self.ranking_by_week
        base = self.bounds.annual_lower_bounds(design, caps, records_by_week)
        audits = {}
        for record in accepted:
            _require(record.week not in audits and record.status in ss.ENERGY_ACCEPTED
                     and (quotes or record.proof in self.rank_ids), "Invalid accepted schedule in peak bound")
            self._verify_meters(record, design, caps)
            audits[record.week] = record.audit
        network = self.bounds.network_with_known_peaks(caps, audits)
        totals = {case: {basis: math.fsum((base["purchase_eur"], cost, base["equipment_eur"], connection))
                         for basis, connection in base["connection_eur"].items()}
                  for case, cost in network.items()}
        _require(all(network[case] >= prior for case, prior in base["network_eur"].items()),
                 ("Peak-informed bound below original network relaxation", design.label, caps))
        return {**base, "network_eur": network, "relaxed_network_eur": base["network_eur"], "total_eur": totals}


def load_archive(coarse, pilot, screen):
    """Verify all formal ledgers and proof hashes against the archived independent audit."""
    coarse, pilot, screen = map(Path, (coarse, pilot, screen))
    baseline = screen / "published_baseline.json"
    evidence = load_evidence(coarse, pilot, publication_path=baseline)
    summary = ss.eb.read_json(screen / "formal/summary.json")
    audit = ss.eb.read_json(screen / "phase2_audit.json")
    screening = ss.eb.read_json(screen / "screening.json")
    _require(audit["status"] == "raw_replay_passed" and not audit["incomplete_proof_files"]
             and not audit["surplus_closed_worker_proofs"] and not summary["unfinished_attempts"]
             and audit["source"] == summary["source"] and not summary["source"]["dirty"]
             and audit["source_summary_sha256"] == digest(screen / "formal/summary.json")
             and summary["published_baseline_sha256"] == audit["published_baseline_sha256"] == digest(baseline)
             and summary["screening_sha256"] == digest(screen / "screening.json")
             and summary["threshold_points_sha256"] == digest(screen / "threshold_points.json")
             and screening["archive_sha256"] == evidence.archive_sha256
             and summary["inputs_sha256"] == evidence.publication["inputs_sha256"] == screening["inputs_sha256"],
             "Original and formal evidence do not describe the same audited inputs")
    manifest = {r["proof"]: r for r in summary["results"]}
    original = evidence.archive_records + evidence.pilot_records
    ranking = list(original)
    formal = []
    checked_ledgers = {}
    for ledger in sorted((screen / "formal").glob("worker-*/solves.jsonl")):
        prefix = ledger.parent.relative_to(screen).as_posix()
        checked_ledgers[ledger.relative_to(screen).as_posix()] = digest(ledger)
        for item in _ledgers(ledger):
            name = prefix + "/" + item["id"]
            info = manifest.pop(name)
            checksum = audit["formal_proofs_sha256"][name]
            _require(checksum == info["proof_sha256"] and info["kind"] in {"ranking", "threshold"},
                     ("Unknown formal proof or purpose", name))
            record = _load_week(ledger.parent, item, summary["source"]["commit"], prefix,
                                evidence.cases, evidence.periods, evidence.reference, checksum)
            formal.append(record)
            if info["kind"] == "ranking":
                ranking.append(record)
    _require(not manifest and checked_ledgers == audit["solver_ledgers_sha256"]
             and len(formal) == summary["solver_calls"] == len(audit["formal_proofs_sha256"])
             and Counter(r.status for r in formal) == Counter(summary["solver_status"])
             and sum(r.audit is not None for r in formal) == audit["audited_feasible_schedules"],
             "Formal and independently audited weekly proof registers differ")
    all_records = (*original, *formal)
    by_id = {r.proof: r for r in all_records}
    _require(len(by_id) == len(all_records), "Repeated archive proof identifier")
    archive = Archive(evidence, AnnualBillBounds(evidence.periods.values(), evidence.reference,
                                                evidence.network, evidence.materials),
                      summary, screening, audit, by_id, _by_week(ranking), _by_week(all_records),
                      replace(evidence, combined_index=_weekly_index(all_records)),
                      {"archive": coarse, "pilot_run": pilot, "formal": screen / "formal"},
                      {r.proof for r in ranking})
    # The loader already independently replays these two archives on their original hardware.
    archive.verified_meters.update((r.proof, r.design) for r in (*evidence.pilot_records, *formal)
                                   if r.audit is not None)
    points = list(evidence.annual_points)
    for row in summary["points"]:
        if row["kind"] == "ranking" and row["status"] == "settled":
            design = evidence.cases[row["design"]]
            records = archive.accepted(row)
            _require(tuple(r.week for r in records) == tuple(evidence.periods), "Incomplete formal settlement")
            point = _annual_point(evidence, design, tuple(row["caps_kw"]), records)
            _check_totals(point.totals, row["totals_eur"])
            points.append(point)
    _require(len({(p.design, p.caps) for p in points}) == len(points), "Duplicate ranked settlement")
    archive.ranked_settlements = tuple(points)
    return archive


def _holdout_purchase(archive, point, held):
    # A wider accepted solve sometimes supplies the billed dispatch. Exclude both that
    # physical scope and the target's scope, across duplicate solves and archive names.
    purchase = archive.bounds.weekly_lower_bound(
        held.week, point.design, point.caps, archive.ranking_by_week[held.week],
        exclude_scopes=((point.design, point.caps), (held.design, held.caps)),
    )
    _require(purchase.proof != held.proof, "Held-out wholesale proof supplied its own lower bound")
    return purchase


def backtest(archive):
    """Hide each of six weeks; keep actual purchases and quarter meters for the other five."""
    bounds = archive.bounds
    factor, _ = annual_factors(bounds.network)
    coarse = set(ss.design_grid(ss.COARSE_KW))
    grid = ss.DispatchGrid([], None, None, None)
    report = dict(status="passed", solver_calls=0, coarse_points=0, priced_fine_points=0,
                  held_out_weeks=0, fallback_week_uses=0, checks=0, network_checks=0,
                  min_margin_eur_2025=None, min_network_margin_eur_2025=None,
                  min_improvement_over_relaxed_eur_2025=None, tightest=[])
    for point in archive.ranked_settlements:
        is_coarse = point.design in coarse and point.caps in grid.options(point.design, ss.COARSE_KW)
        equipment, missing, connections = ss.annual_capital_costs(point.design, archive.evidence.materials)
        if missing and not is_coarse:
            continue
        report["coarse_points" if is_coarse else "priced_fine_points"] += 1
        all_weeks = {r.week: r for r in point.weeks}
        _require(len(point.weeks) == len(all_weeks) == 6 and all_weeks.keys() == set(bounds.weeks),
                 ("Missing replay for settled point", point.design.label, point.caps))
        for r in point.weeks:
            _require(r.status in ss.ENERGY_ACCEPTED and r.proof in archive.rank_ids,
                     ("Unexpected week in settled ranking", r.proof))
            archive._verify_meters(r, point.design, point.caps)
        relaxed = bounds.network_with_known_peaks(point.caps, {})
        for held in point.weeks:
            visible = {week: r.audit for week, r in all_weeks.items() if week != held.week}
            network = bounds.network_with_known_peaks(point.caps, visible)
            other_proof = _holdout_purchase(archive, point, held)
            purchase = math.fsum([other_proof.lower_eur, *(a["purchase_eur"] for a in visible.values())]) * factor
            report["held_out_weeks"] += 1
            report["fallback_week_uses"] += other_proof.proof is None
            for case, network_lower in network.items():
                bill = point.dispatch["bills"][case]
                actual_network = math.fsum((bill["annual_network_energy_eur_2025"], bill["annual_capacity_eur_2025"]))
                network_margin = actual_network - network_lower
                improvement = network_lower - relaxed[case]
                detail = dict(design=point.design.label, caps_kw=point.caps, held_week=held.week, scenario=case,
                              held_proof=held.proof, other_wholesale_proof=other_proof.proof,
                              held_week_wholesale_lower_eur_2021=other_proof.lower_eur,
                              known_peak_network_lower_eur=network_lower, actual_network_eur=actual_network,
                              relaxed_network_lower_eur=relaxed[case])
                if network_margin < 0 or improvement < 0:
                    raise BacktestFailure(report, {**detail, "network_margin_eur_2025": network_margin,
                                                   "improvement_over_relaxed_eur_2025": improvement})
                report["network_checks"] += 1
                for name, value in (("min_network_margin_eur_2025", network_margin),
                                    ("min_improvement_over_relaxed_eur_2025", improvement)):
                    if report[name] is None or value < report[name]:
                        report[name] = value
                for basis, connection in connections.items():
                    annual_lower = math.fsum((purchase, network_lower, equipment, connection))
                    actual = point.totals[case][basis]
                    margin = actual - annual_lower
                    report["checks"] += 1
                    detail_basis = {**detail, "connection_basis": basis, "annual_lower_eur_2025": annual_lower,
                                    "actual_annual_eur_2025": actual, "margin_eur_2025": margin}
                    if margin < 0:
                        raise BacktestFailure(report, detail_basis)
                    if report["min_margin_eur_2025"] is None or margin < report["min_margin_eur_2025"]:
                        report["min_margin_eur_2025"] = margin
                    tightest = report["tightest"]
                    if len(tightest) < 10 or margin < tightest[-1]["margin_eur_2025"]:
                        tightest.append(detail_basis)
                        tightest.sort(key=lambda r: r["margin_eur_2025"])
                        del tightest[10:]
    expected_coarse = archive.evidence.publication["observed_cost_checkpoints"]["coarse_replayed"]
    expected_fine = archive.phase2_audit["partial_ranked_minima"]["priced_fine_counts"]["settled"]
    _require(report["coarse_points"] == expected_coarse and report["priced_fine_points"] == expected_fine
             and report["checks"] == (expected_coarse + expected_fine) * len(bounds.weeks) * 2 * len(bounds.scenarios),
             ("Incomplete holdout coverage", report))
    return report


def _winner_comparison(archive):
    operations = defaultdict(list)
    for point in archive.ranked_settlements:
        operations[point.design].append(point.dispatch)
    _, minima = ss.annual_tables(operations, archive.evidence.materials, archive.evidence.scenarios)
    comparisons = []
    for before in archive.evidence.publication["winners"]:
        case, basis = before["scenario"], before["connection_basis"]
        row = minima[case, basis]
        change = row["annual_total_eur"] - before["annual_total_eur"]
        same = row["design"] == before["design"] and tuple(row["caps_kw"]) == tuple(before["caps_kw"])
        _require(same and change == 0, ("Existing minimum differs from its publication", case, basis))
        comparisons.append(dict(scenario=case, connection_basis=basis, design=row["design"],
                                caps_kw=row["caps_kw"], annual_total_eur=row["annual_total_eur"],
                                annual_change_eur=change))
    _require(len(minima) == len(comparisons) == 12, "Missing published minimum")
    return comparisons


def classify_remaining(archive):
    """Compare every previously unresolved ranking point with all twelve reproduced minima."""
    winners = _winner_comparison(archive)
    prior = archive.phase2_audit["partial_ranked_minima"]
    remaining = [row for row in archive.summary["points"] if row["kind"] == "ranking" and row["status"] == "unresolved"]
    _require(remaining == prior["unresolved_operating_points"] and
             len(remaining) == archive.summary["unresolved_priced_points"] == prior["priced_fine_counts"]["unresolved"],
             "Formal and audited unresolved ranking manifests differ")
    counts = dict(prior["priced_fine_counts"])
    points = []
    for row in remaining:
        design, caps = archive.evidence.cases[row["design"]], tuple(row["caps_kw"])
        accepted = archive.accepted(row)
        lower = archive.bill_lower(design, caps, accepted)
        upper = archive.upper(row)
        rows = []
        for winner in winners:
            case, basis = winner["scenario"], winner["connection_basis"]
            low, high = lower["total_eur"][case][basis], upper[case][basis] if upper else None
            _require(low >= row["annual_lower_totals_eur"][case][basis] and (high is None or low <= high),
                     ("Invalid or weaker final interval", design.label, caps, case, basis, low, high))
            rows.append(dict(scenario=case, connection_basis=basis, lower_eur=low, upper_eur=high,
                             minimum_eur=winner["annual_total_eur"], margin_eur=low - winner["annual_total_eur"]))
        min_margin = min(item["margin_eur"] for item in rows)
        status = "excluded_by_known_peak_lower_bound" if min_margin > COST_MARGIN_EUR else "unresolved"
        if status != "unresolved":
            counts["unresolved"] -= 1
            counts[status] = counts.get(status, 0) + 1
        points.append(dict(
            design=design.label, caps_kw=caps, status=status, min_margin_eur=min_margin, annual_comparison=rows,
            accepted_weeks=[dict(week=r.week, status=r.status, proof=r.proof, proof_sha256=r.proof_sha256,
                                 site_grid_kwh=r.audit["site_grid_kwh"], site_quarter_peak_kw=r.audit["site_quarter_peak_kw"])
                            for r in accepted],
            unaccepted_weeks=row["failed_weeks"], missing_weeks=row["missing_weeks"],
            annual_wholesale_lower_eur=lower["purchase_eur"],
            wholesale_weekly_lower_proofs=[dict(week=w, proof=r.proof, lower_eur_2021=r.lower_eur)
                                          for w, r in lower["weekly"].items()],
            relaxed_network_eur=lower["relaxed_network_eur"], known_peak_network_eur=lower["network_eur"],
            equipment_eur=lower["equipment_eur"], connection_eur=lower["connection_eur"],
        ))
    _require(sum(counts.values()) == prior["priced_fine_points"], "Priced operating point count changed")
    return dict(status="failed" if counts["unresolved"] else "passed", solver_calls=0, points=points,
                counts=counts, priced_fine_points=prior["priced_fine_points"], winner_comparison=winners)
