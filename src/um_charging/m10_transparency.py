"""Reassess the original weekly gap from completed certificates, without solving."""
from collections import Counter, defaultdict
from datetime import datetime
import math

from . import site_sizing as ss
from .site_sizing_bounds import WholesaleRecord
from .m10_costs import _invoice_rows, _point, _rank_designs, _row, COST_MARGIN_EUR


TRANSPARENCY_COLUMNS = dict(
    scenario="Network tariff.", connection_basis="New or existing connection.",
    comparison="Minimum-design conclusion under the two weekly acceptance rules, using all issued evidence.",
    current_minimum_set="Space-separated hardware whose intervals permit rank one at EUR 0.10.",
    original_minimum_set="Space-separated hardware whose intervals permit rank one at EUR 0.05.",
    current_minimum_lower="Minimum lower bound, EUR 2025/year, EUR 0.10 rule.",
    current_minimum_upper="Admitted upper bound, EUR 2025/year, EUR 0.10 rule.",
    original_minimum_lower="Minimum lower bound, EUR 2025/year, EUR 0.05 rule.",
    original_minimum_upper="Admitted upper bound, EUR 2025/year, EUR 0.05 rule.",
    affected_points="Point count drawing on a newly admitted weekly interval under the EUR 0.10 rule.",
    original_unsettled_points="Count of newly admitted points without a complete admissible EUR 0.05 trace.",
    changed_design_ranks="Space-separated hardware with different best/worst rank bounds.",
    historical_outcome="Actual outcome of the original stop rule when the fourth unresolved group arrived.")

OLD_POINT_COLUMNS = dict(
    design="Installed hardware identifier.", port_cap_kw="Port quarter cap, kW.",
    warehouse_cap_kw="Warehouse quarter cap, kW.", scenario="Network tariff.", connection_basis="Connection basis.",
    current_status="Current point status.", original_status="Point status using the original threshold and available proofs.",
    wider_ids="Newly admitted weekly evidence IDs used at the current point.",
    alternative_ids="Original-rule replacement certificate IDs, when available.",
    unresolved_weeks="Weeks without an admitted original-rule proof.",
    current_lower="Current lower invoice bound, EUR 2025/year.", current_upper="Current admitted upper, EUR 2025/year.",
    original_lower="Original-rule lower invoice bound, EUR 2025/year.", original_upper="Original admitted upper, EUR 2025/year.",
    witness_upper="Replayed original-rule physical invoice before admission, EUR 2025/year.",
    excludes_minimum="True if original-rule lower strictly exceeds the best admitted invoice by the registered margin.")


def _ledger(evidence, dispatch):
    status, compatible, records = {}, defaultdict(list), defaultdict(list)
    periods = {p.days[0]["week_start"]: p for p in dispatch.periods}
    for r in evidence.records:
        status[r["id"]] = r
        if r["phase"] != "energy":
            continue
        req = evidence.request_for(r["id"])
        if req.fixed != tuple(sorted(periods[req.week].keys & dispatch.reference)):
            continue
        if r["objective_lower"] is not None and math.isfinite(r["objective_lower"]):
            records[req.week].append(WholesaleRecord(req.week, req.design, req.caps, r["objective_lower"], r["id"]))
        if r["original_status"] in ss.ENERGY_ACCEPTED:
            compatible[req.week, req.caps].append((req.design, r["id"]))
    return status, compatible, records


def _old_week(dispatch, period, design, caps, current, compatible, ledger):
    week = period.days[0]["week_start"]
    target = ss._active_build(design, caps)
    orig = ledger[current["solve"]]["original_status"] if current.get("solve") else "unresolved"
    if orig in ss.ENERGY_ACCEPTED:
        return dict(current, status=orig)
    # Preserve the frozen witness wherever it passes. Otherwise use the exact
    # request first and then M8's descending hardware order at identical caps.
    matches = sorted(compatible[week, caps], reverse=True)
    matches.sort(key=lambda pair: pair[0] != target)
    for hardware, label in matches:
        if not ss._dominates(hardware, target):
            continue
        result = dispatch.evidence.get(label)
        row = _row(label, result)
        if (row["used_plugs"][ss.PORT] > target.port_plugs or
                any(row["site_peak_kw"][s] > k + ss.EPS for s, k in zip(ss.SITES, target.caps, strict=True))):
            continue
        dispatch.replay_transfer(period, target, caps, row)
        return dict(row, status=ledger[label]["original_status"], method="original_rule_alternative")
    return dict(current, status=orig)


def _strict_point(point, design, dispatch, compatible, ledger):
    caps = point["caps_kw"]
    weeks = [_old_week(dispatch, p, design, caps, w, compatible, ledger)
             for p, w in zip(dispatch.periods, point["weeks"], strict=True)]
    missing = [p.days[0]["week_start"] for p, w in zip(dispatch.periods, weeks, strict=True)
               if w["status"] not in ss.ENERGY_ACCEPTED]
    changed = [b["solve"] for a, b in zip(point["weeks"], weeks, strict=True) if a.get("solve") != b.get("solve")]
    if missing:
        return dict(caps_kw=caps, weeks=weeks, status="unresolved"), missing, changed
    purchase = math.fsum(w["purchase_eur"] for w in weeks)
    energy = {s: math.fsum(w["site_grid_kwh"][s] for w in weeks) for s in ss.SITES}
    peaks = {s: max(w["site_quarter_peak_kw"][s] for w in weeks) for s in ss.SITES}
    bills = {}
    for scenario in ("N0", *dispatch.network["tariffs"], *dispatch.network["capacity_sensitivities_eur_per_kw_year"]):
        bill = ss.settle(dispatch.network, purchase, energy, peaks, scenario)
        ss.audit_settlement(dispatch.network, purchase, energy, peaks, scenario, bill)
        bills[scenario] = bill
    status = "bounded" if any(w["status"] == "bounded" for w in weeks) else "certified"
    return dict(caps_kw=caps, weeks=weeks, status=status, bills=bills, purchase_eur=purchase,
                lower_eur=math.fsum(w["lower_eur"] for w in weeks)), missing, changed


def _comparison(new, old):
    if not new or not old:
        return "no_admitted_upper"
    if new == old:
        return "same_unique_minimum" if len(new) == 1 else "same_unseparated_minimum_set"
    if len(new) == 1 and len(old) > 1:
        return "original_minimum_unresolved"
    return "different_minimum_sets"


def original_rule(dispatch, bounds, operations, annual, new_designs, new_winners):
    evidence = dispatch.evidence
    ledger, compatible, records = _ledger(evidence, dispatch)
    actual = defaultdict(list)
    for row in annual:
        actual[row["design"], (row["port_cap_kw"], row["warehouse_cap_kw"])].append(row)
    old_annual, changed_points, assignments = [], [], []
    widened_on_infeasible_points = []
    for design, options in operations.items():
        for point in options:
            caps = point["caps_kw"]
            widened = [w["solve"] for w in point["weeks"] if ledger.get(w.get("solve"), {}).get("widened_interval")]
            if widened and point["status"] == "infeasible":
                widened_on_infeasible_points.append(dict(**_point(design, caps), widened_ids=widened))
            if point["status"] == "infeasible" or (not widened and point["status"] != "unresolved"):
                old_annual.extend(dict(row) for row in actual[design.label, caps])
                continue
            old, missing, changed = _strict_point(point, design, dispatch, compatible, ledger)
            rows = list(_invoice_rows(design, old, bounds, records))
            if missing:
                # Only already-admitted meter traces are frozen. Allocate the
                # remaining required kWh across both meters at admissible peaks.
                known = {week: w for week, w in zip(bounds.weeks, old["weeks"], strict=True)
                         if w["status"] in ss.ENERGY_ACCEPTED}
                grid_floor = bounds.network_with_known_peaks(caps, known)
                for r in rows:
                    low = math.fsum((r["equipment"], r["connection"], r["purchase_lower"], grid_floor[r["scenario"]]))
                    if not math.isfinite(low) or (r["witness_upper"] is not None and low > r["witness_upper"] + COST_MARGIN_EUR):
                        raise ValueError(("Invalid original-rule invoice bound", design, caps, r["scenario"]))
                    r["total_lower"] = max(low, r["total_lower"])
            old_annual.extend(rows)
            assignments.append(dict(**_point(design, caps), current_status=point["status"], original_status=old["status"],
                                    widened_ids=widened, unresolved_weeks=missing, alternative_ids=changed,
                                    strict_ids=[w.get("solve") for w in old["weeks"]]))
            for r, new in zip(rows, actual[design.label, caps], strict=True):
                if (r["scenario"], r["connection_basis"]) != (new["scenario"], new["connection_basis"]):
                    raise ValueError("Original and current tariff inventories differ")
                changed_points.append(dict(**_point(design, caps), scenario=r["scenario"], connection_basis=r["connection_basis"],
                                           current_status=new["status"], original_status=old["status"], wider_ids=" ".join(widened),
                                           alternative_ids=" ".join(changed), unresolved_weeks=" ".join(missing),
                                           current_lower=new["total_lower"], current_upper=new["total_upper"],
                                           original_lower=r["total_lower"], original_upper=r["total_upper"],
                                           witness_upper=r["witness_upper"]))
    ranks, old_winners = _rank_designs(old_annual)
    key = lambda r: (r["scenario"], r["connection_basis"])
    strict = {key(r): r for r in old_winners}
    previous_ranks = {(key(r), r["design"]): r for r in ranks}
    changes = defaultdict(list)
    for r in new_designs:
        before = previous_ranks.get((key(r), r["design"]))
        if before is None or any(before[k] != r[k] for k in ("rank_best", "rank_worst")):
            changes[key(r)].append(r["design"])
    for r in changed_points:
        upper = strict[key(r)]["minimum_upper"]
        r["excludes_minimum"] = upper is not None and r["original_lower"] > upper + COST_MARGIN_EUR
    inherited = [r for r in ledger.values() if r["certificate_origin"] == "parent" and r["original_status"] == "unresolved"]
    inherited.sort(key=lambda r: (datetime.fromisoformat(r["started_utc"]).timestamp() + r["seconds"], r["id"]))
    stopped = len(inherited) > ss.fc.MAX_UNRESOLVED
    table = []
    for new in new_winners:
        old = strict[key(new)]
        a, b = new["possible_minimum_designs"], old["possible_minimum_designs"]
        conclusion = _comparison(a, b)
        if new["minimum_upper"] is None or old["minimum_upper"] is None:
            conclusion = "no_admitted_upper"
        table.append(dict(scenario=new["scenario"], connection_basis=new["connection_basis"], comparison=conclusion,
                          current_minimum_set=" ".join(a), original_minimum_set=" ".join(b),
                          current_minimum_lower=new["minimum_lower"], current_minimum_upper=new["minimum_upper"],
                          original_minimum_lower=old["minimum_lower"], original_minimum_upper=old["minimum_upper"],
                          affected_points=sum(bool(s["widened_ids"]) for s in assignments),
                          original_unsettled_points=sum(bool(s["widened_ids"]) and s["original_status"] == "unresolved"
                                                        and s["current_status"] in ss.ENERGY_ACCEPTED for s in assignments),
                          changed_design_ranks=" ".join(sorted(changes[key(new)])),
                          historical_outcome="stopped_before_complete_cost_matrix" if stopped else "not_triggered_in_parent"))
    return dict(old_rule_transparency=table, old_rule_points=changed_points,
                old_rule_evidence=dict(
                    scope="Retrospective complete coarse inventory under the original admission threshold. The parent "
                          "stopped before computing annual ranks. For a disallowed donor, prefer an issued exact "
                          "strict proof, then a fitting strict proof on larger hardware at identical caps. Missing "
                          "weekly proofs retain physical/dual bounds. A feasible witness invoice and an admitted "
                          "upper invoice are reported separately.",
                    parent_unresolved_in_finish_order=[r["id"] for r in inherited],
                    parent_stop_trigger_id=inherited[ss.fc.MAX_UNRESOLVED]["id"] if stopped else None,
                    all_original_solve_status_counts=dict(Counter(r["original_status"] for r in ledger.values())),
                    all_widened_ids=sorted(k for k, r in ledger.items() if r["widened_interval"]),
                    widened_on_infeasible_points=widened_on_infeasible_points,
                    affected_assignments=assignments, design_ranks=ranks, winners=old_winners))
