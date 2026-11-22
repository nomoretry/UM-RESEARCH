"""Freeze the sealed coarse strategies and inventory exact twelve-week quote coverage."""
from collections import defaultdict
import csv
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path

from . import m10_inputs, site_sizing as ss
from .__main__ import digest
from .cabinet_tariff import annual_factors
from .m10_costs import _parameters
from .m10_evidence import Request


PRIORITY = (ss.Design(1, 20, 15), ss.Design(1, 40, 15))
POINT_FIELDS = ("design", "port_plugs", "port_kw", "warehouse_kw", "port_cap_kw",
                "warehouse_cap_kw", "missing_ratings_kw")
TABLE_FIELDS = {
    "frozen_facilities": ("scenario", "connection_basis", "design", "port_plugs", "port_kw", "warehouse_kw",
                          "port_cap_kw", "warehouse_cap_kw", "registered_vehicle_days", "weeks", "dispatch_status",
                          "rank_best", "rank_worst", "minimum_lower_eur_2025", "minimum_upper_eur_2025",
                          "frozen_point_lower_eur_2025", "frozen_point_upper_eur_2025", "weekly_proof_ids"),
    "unquoted_coverage": (*POINT_FIELDS, "audited_weeks", "settled_tariff_cases", "coverage", "settlement_source",
                          "weekly_proof_ids"),
    "quote_thresholds": (*POINT_FIELDS, "scenario", "connection_basis", "comparison_design",
                         "comparison_port_cap_kw", "comparison_warehouse_cap_kw", "comparison_lower_eur_2025",
                         "comparison_upper_eur_2025", "settlement_source", "weekly_proof_ids", "other_cost_lower_eur_2025",
                         "other_cost_upper_eur_2025", "annual_allowance_lower_eur_2025",
                         "annual_allowance_upper_eur_2025", "net_equipment_lower_eur_2026",
                         "net_equipment_upper_eur_2026", "quote_scope"),
    "warehouse_15kw_coverage": ("design", "scenario", "connection_basis", "registered_points", "settled_points",
                                "coverage"),
}


def _csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _point(row):
    return row["design"], (int(row["port_cap_kw"]), int(row["warehouse_cap_kw"]))


def _case(row):
    return row["scenario"], row["connection_basis"]


def _number(row, field):
    value = float(row[field])
    if not math.isfinite(value):
        raise ValueError(f"Nonfinite settlement field: {field}")
    return value


def _index(rows, key):
    result = {}
    for row in rows:
        k = key(row)
        if k in result:
            raise ValueError(f"Duplicate archived settlement key: {k}")
        result[k] = row
    return result


def _week_proofs(rows, expected, ledger):
    """Only accepted fixed-R purchase certificates for every distinct week qualify."""
    indexed = _index(rows, lambda r: r["week"])
    accepted = []
    for week in expected:
        w = indexed.get(week)
        if w is None or w["status"] not in ss.ENERGY_ACCEPTED:
            continue
        solve = ledger[w["evidence_id"]]
        if (solve["week"] != week or solve["phase"] != "energy" or solve["audited"] != "True"
                or solve["status"] not in ss.ENERGY_ACCEPTED):
            raise ValueError("Archived weekly settlement lacks an audited fixed-R purchase certificate")
        accepted.append(w["evidence_id"])
    if set(indexed) - set(expected):
        raise ValueError("Settlement contains a week outside the frozen twelve-week calendar")
    return accepted


def _freeze(winners, cases, annual, weekly, ledger, service, weeks):
    by_case = _index(winners, _case)
    if set(by_case) != set(cases):
        raise ValueError("Sealed winners do not cover every tariff and connection basis")
    frozen = []
    for case in cases:
        winner = by_case[case]
        best = winner["incumbent"]
        if (not best or best["missing_ratings_kw"] or best["rank_best"] != 1 or best["rank_worst"] != 1
                or winner["possible_minimum_designs"] != [best["design"]]):
            raise ValueError(f"No unique priced coarse minimum for {case}")
        point = best["design"], tuple(best["caps_kw"])
        row = annual[point, case]
        hardware = service[point[0]]
        proofs = _week_proofs(weekly[point], weeks, ledger)
        if (row["status"] not in ss.ENERGY_ACCEPTED or row["missing_ratings_kw"]
                or not hardware["same_service"] or len(proofs) != len(weeks)):
            raise ValueError(f"Coarse minimum lacks exact same-service settlement at {point}")
        ss.close(_number(row, "total_upper"), best["total_upper"], "frozen point annual upper bound")
        ss.close(best["total_upper"], winner["minimum_upper"], "minimum feasible upper bound")
        if winner["minimum_lower"] > winner["minimum_upper"] + ss.EPS:
            raise ValueError("Inverted coarse minimum bounds")
        frozen.append(dict(scenario=case[0], connection_basis=case[1], design=point[0],
                           port_plugs=hardware["port_plugs"], port_kw=hardware["port_kw"],
                           warehouse_kw=hardware["warehouse_kw"], port_cap_kw=point[1][0],
                           warehouse_cap_kw=point[1][1], registered_vehicle_days=hardware["completed_registered"],
                           weeks=len(proofs), dispatch_status=row["status"], rank_best=best["rank_best"],
                           rank_worst=best["rank_worst"], minimum_lower_eur_2025=winner["minimum_lower"],
                           minimum_upper_eur_2025=winner["minimum_upper"],
                           frozen_point_lower_eur_2025=_number(row, "total_lower"),
                           frozen_point_upper_eur_2025=_number(row, "total_upper"),
                           weekly_proof_ids=" ".join(proofs)))
    return frozen


def _break_even(frozen, row, missing, factor):
    """Net-price allowance for the missing equipment together, retaining negative thresholds."""
    if not missing or not math.isfinite(factor) or factor <= 0:
        raise ValueError("Break-even requires missing equipment and a positive annualization factor")
    known = math.fsum(_number(row, k) for k in ("equipment", "connection", "network_energy", "demand"))
    other_low = known + _number(row, "purchase_lower")
    other_high = known + _number(row, "purchase_upper")
    if other_low > other_high + ss.EPS:
        raise ValueError("Inverted other-cost interval")
    low = frozen["minimum_lower_eur_2025"] - other_high
    high = frozen["minimum_upper_eur_2025"] - other_low
    return dict(other_cost_lower_eur_2025=other_low, other_cost_upper_eur_2025=other_high,
                annual_allowance_lower_eur_2025=low, annual_allowance_upper_eur_2025=high,
                net_equipment_lower_eur_2026=low/factor, net_equipment_upper_eur_2026=high/factor,
                quote_scope="one_net_unit" if len(missing) == 1 else "joint_net_equipment_sum")


def _read_certificate(archive, proof, ledger):
    source = ledger[proof]
    directory = {"parent": archive / "inherited", "current": archive}[source["certificate_origin"]]
    payload = (directory / "certificates" / (proof + ".json.gz")).read_bytes()
    if hashlib.sha256(payload).hexdigest() != source["certificate_sha256"]:
        raise ValueError(f"Quote transfer certificate differs from sealed ledger: {proof}")
    body = json.loads(gzip.decompress(payload))["body"]
    request = Request.from_json(body["request"])
    if request.identifier(body["scope"]) != proof:
        raise ValueError(f"Quote transfer certificate request differs: {proof}")
    return request, body["result"]


def _transfer_meter(design, caps, row, period, reference, ledger, read_proof):
    proof = row["proof"]
    record = ledger[proof]
    request, result = read_proof(proof)
    target = ss._active_build(design, caps)
    donor = ss._active_build(request.design, request.caps)
    registered = reference & period.keys
    expected_source = "identical_request" if donor == target else "fitting_superset_same_caps"
    if (request.week != row["week"] or record["week"] != request.week or request.phase != "energy"
            or record["phase"] != request.phase or record["design"] != request.design.label
            or request.caps != caps or (int(record["port_cap_kw"]), int(record["warehouse_cap_kw"])) != caps
            or record["status"] not in ss.ENERGY_ACCEPTED or record["audited"] != "True"
            or request.fixed != tuple(sorted(registered)) or ss.eb.selected(result) != registered
            or row["source"] != expected_source or not ss._dominates(donor, target)):
        raise ValueError(("Invalid same-cap fixed-service transfer", design.label, caps, proof))
    audit = ss.meter_replay(period, target.hardware(), ss.eb.DEFAULT_SPEC, caps, result)
    if not audit["passed"]:
        raise ValueError(("Invalid target schedule", proof))
    for i, site in enumerate(ss.SITES):
        ss.close(audit["site_grid_kwh"][site], row["site_kwh_floor"][i], (proof, site, "transferred kWh"))
        ss.close(audit["site_quarter_peak_kw"][site], row["site_peak_floor"][i], (proof, site, "transferred peak"))
    upper = audit["purchase_eur"]
    ss.close(upper, _number(record, "objective_upper"), (proof, "admitted purchase"))
    ss.close(upper, row["purchase_upper_eur_2021"], (proof, "screen purchase"))
    lower = _number(record, "objective_lower")
    if lower > upper + ss.EPS:
        raise ValueError(("Invalid transfer lower bound", proof))
    return min(lower, upper), audit


def _transfer_invoice(design, caps, screened, periods, reference, ledger, read_proof, network, materials, cases):
    if screened["decision"] != "retain" or screened["priced"]:
        return [], {}
    by_week = _index(screened["weekly"], lambda r: r["week"])
    if set(by_week) != set(periods):
        raise ValueError(("Incomplete retained-point screening calendar", design.label, caps))
    proofs = [by_week[w]["proof"] for w in periods if by_week[w]["proof"]]
    if len(proofs) != len(periods):
        return proofs, {}
    meters = [_transfer_meter(design, caps, by_week[w], period, reference, ledger, read_proof)
              for w, period in periods.items()]
    lower = math.fsum(lo for lo, _ in meters) * annual_factors(network)[0]
    expense = math.fsum(m["purchase_eur"] for _, m in meters)
    kwh = {s: math.fsum(m["site_grid_kwh"][s] for _, m in meters) for s in ss.SITES}
    peaks = {s: max(m["site_quarter_peak_kw"][s] for _, m in meters) for s in ss.SITES}
    equipment, missing, connections = ss.annual_capital_costs(design, materials)
    bills = {}
    for scenario in dict.fromkeys(s for s, _ in cases):
        bill = ss.settle(network, expense, kwh, peaks, scenario)
        ss.audit_settlement(network, expense, kwh, peaks, scenario, bill)
        bills[scenario] = bill
    rows = {}
    for scenario, basis in cases:
        bill = bills[scenario]
        rows[scenario, basis] = dict(equipment=equipment, missing_ratings_kw=" ".join(map(str, missing)),
                                     connection=connections[basis], purchase_lower=lower,
                                     purchase_upper=bill["annual_energy_eur_2025"],
                                     network_energy=bill["annual_network_energy_eur_2025"],
                                     demand=bill["annual_capacity_eur_2025"])
    return proofs, rows


def _quotes(points, frozen, annual, weekly, ledger, weeks, materials, factor, transfers=None):
    inventory, thresholds = [], []
    scope = defaultdict(list)
    seen = set()
    for design, raw_caps in points:
        caps = tuple(raw_caps)
        if (design, caps) in seen:
            raise ValueError(("Duplicate refinement point", design.label, caps))
        seen.add((design, caps))
        _, missing, _ = ss.annual_capital_costs(design, materials)
        if not missing:
            continue
        point = design.label, caps
        rows = weekly.get(point, [])
        proofs = _week_proofs(rows, weeks, ledger)
        replay_proofs, replay_rows = transfers(design, caps) if transfers else ([], {})
        if proofs and replay_rows:
            raise ValueError(("Coarse and refinement settlement overlap", point))
        invoice_proofs = proofs or replay_proofs
        info = dict(design=design.label, port_plugs=design.port_plugs, port_kw=design.port_kw,
                    warehouse_kw=design.warehouse_kw, port_cap_kw=caps[0], warehouse_cap_kw=caps[1],
                    missing_ratings_kw=" ".join(map(str, missing)))
        n = 0
        for incumbent in frozen:
            case = _case(incumbent)
            row = annual.get((point, case))
            if row is not None and row["status"] in ss.ENERGY_ACCEPTED:
                source = "r012_archived_settlement"
            elif case in replay_rows:
                row = replay_rows[case]
                source = "r013_replayed_meter_settlement"
            else:
                scope[design, case].append(False)
                continue
            if len(invoice_proofs) != len(weeks) or sorted(map(int, row["missing_ratings_kw"].split())) != missing:
                raise ValueError("Unquoted exact-point settlement lacks its required twelve-week evidence")
            thresholds.append(dict(**info, scenario=case[0], connection_basis=case[1],
                                   comparison_design=incumbent["design"],
                                   comparison_port_cap_kw=incumbent["port_cap_kw"],
                                   comparison_warehouse_cap_kw=incumbent["warehouse_cap_kw"],
                                   comparison_lower_eur_2025=incumbent["minimum_lower_eur_2025"],
                                   comparison_upper_eur_2025=incumbent["minimum_upper_eur_2025"],
                                   settlement_source=source, weekly_proof_ids=" ".join(invoice_proofs),
                                   **_break_even(incumbent, row, missing, factor)))
            scope[design, case].append(True)
            n += 1
        inventory.append(dict(**info, audited_weeks=len(invoice_proofs), settled_tariff_cases=n,
                              coverage="exact_settlement" if n else "no_exact_twelve_week_settlement",
                              settlement_source=source if n else "unsettled", weekly_proof_ids=" ".join(invoice_proofs)))
    priority = []
    for design in PRIORITY:
        for incumbent in frozen:
            case = _case(incumbent)
            flags = scope[design, case]
            if not flags:
                raise ValueError(f"Priority 15 kW hardware missing from the registered point list: {design.label}")
            priority.append(dict(design=design.label, scenario=case[0], connection_basis=case[1],
                                 registered_points=len(flags), settled_points=sum(flags),
                                 coverage="exact_settlement" if any(flags) else "no_exact_twelve_week_settlement"))
    return inventory, thresholds, priority


def freeze_coarse(archive, refinement_points, *, screening=None):
    """Rebuild the branch-B facilities and exact-price-coverage tables, without a solve."""
    archive = Path(archive)
    seal = ss.eb.read_json(archive / "seal.json")
    names = ("selection.json", "annual_costs.csv", "operating_points.csv", "solves.csv", "service_summary.json")
    source = {name: digest(archive / name) for name in names}
    if any(source[name] != seal["products"][name] for name in names):
        raise ValueError("Coarse product differs from the original seal")
    inputs = m10_inputs.load_inputs()
    run = ss.eb.read_json(archive / "run_manifest.json")
    binding = run["inputs"]
    if (binding["planning"] != inputs.source_sha256
            or list(map(tuple, binding["fixed_service"])) != sorted(inputs.registered)
            or run["timeout_interval_eur_2021"] != .10):
        raise ValueError("Frozen cohort, input hashes or timeout policy differ from the planning study")
    publication = ss.eb.WEEKS.with_name("site_sizing.json")
    for path in (publication, ss.CONNECTION_INPUT, ss.NETWORK_INPUT, ss.COST_INPUT):
        if digest(path) != binding["cost_sha256"][path.name]:
            raise ValueError(f"Equipment or tariff input differs from coarse study: {path.name}")
    weeks = [p.days[0]["week_start"] for p in inputs.periods]
    network, materials = _parameters(inputs.periods)
    scenarios = ("N0", *network["tariffs"], *network["capacity_sensitivities_eur_per_kw_year"])
    cases = [(tariff, basis) for tariff in scenarios for basis in ("new", "existing")]
    factor = ss.eb.read_json(publication)["model_policy"]["equipment_cost_from_net_2026_to_annual_2025"]
    service = ss.eb.read_json(archive / "service_summary.json")
    annual = _index(_csv(archive / "annual_costs.csv"), lambda r: (_point(r), _case(r)))
    weekly = defaultdict(list)
    for row in _csv(archive / "operating_points.csv"):
        weekly[_point(row)].append(row)
    ledger = _index(_csv(archive / "solves.csv"), lambda r: r["id"])
    frozen = _freeze(ss.eb.read_json(archive / "selection.json")["winners"], cases, annual, weekly,
                     ledger, service, weeks)
    transfers = None
    if screening is not None:
        screened = _index(screening, lambda p: (p["design"], tuple(p["caps_kw"])))
        periods = dict(zip(weeks, inputs.periods, strict=True))
        @lru_cache(maxsize=32)
        def read_proof(label):
            return _read_certificate(archive, label, ledger)

        def transfers(design, caps):
            return _transfer_invoice(design, caps, screened[design.label, caps], periods, inputs.registered,
                                     ledger, read_proof, network, materials, cases)

    inventory, thresholds, priority = _quotes(refinement_points, frozen, annual, weekly, ledger,
                                             weeks, materials, factor, transfers)
    pricing = ss.eb.read_json(ss.CONNECTION_INPUT)["charger_annualization"]
    charger = ss.eb.read_json(ss.COST_INPUT)["whole_charger_reference"]
    return dict(frozen_facilities=frozen, unquoted_coverage=inventory, quote_thresholds=thresholds,
                warehouse_15kw_coverage=priority, evidence=dict(
                    source_products_sha256=source, source_manifest_sha256=digest(archive / "run_manifest.json"),
                    source_seal_sha256=digest(archive / "seal.json"), input_sha256=inputs.source_sha256,
                    native_weeks=weeks, registered_vehicle_days=len(inputs.registered),
                    annual_cost_currency="EUR 2025/year", net_equipment_currency="EUR 2026 net",
                    annual_eur_2025_per_net_equipment_eur_2026=factor,
                    equipment_life_years=charger["equipment_life_years"], discount_rate=charger["discount_rate"],
                    installation_share=charger["installation_share_of_equipment"],
                    annual_maintenance_share=charger["maintenance_share_of_equipment_per_year"],
                    hyc50_year=charger["year"], hyc50_equipment_eur=charger["equipment_eur"],
                    hyc50_reference=charger["source"], hyc50_scope=pricing["comparability"],
                    pricing_basis=pricing["method"], covered_unquoted_points=sum(r["settled_tariff_cases"] > 0
                                                                                for r in inventory),
                    registered_unquoted_points=len(inventory), settled_threshold_cases=len(thresholds)))
