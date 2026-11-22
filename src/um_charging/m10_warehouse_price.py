"""Whole-sample warehouse 15 kW break-even prices against matching port hardware."""
from collections import defaultdict
import csv
import json
import math
from pathlib import Path

from . import site_sizing as ss
from .__main__ import digest
from .m10_evidence import Request
from .m10_policy_costs import invoices, point_key
from .site_sizing_screen import COST_MARGIN_EUR


def screened_points(refinement):
    source = refinement / "screen_evidence.jsonl"
    manifest = json.loads((refinement / "manifest.json").read_bytes())
    if digest(source) != manifest["products"][source.name]:
        raise ValueError("The refinement screen differs from its manifest")
    designs = [ss.Design(1, port, 15) for port in (20, 40)]
    with source.open(encoding="utf-8") as stream:
        rows = [r for line in stream if (r := json.loads(line))["design"] in {d.label for d in designs}]
    grid = ss.DispatchGrid([], set(), {}, None)
    expected = {(d.label, caps) for d in designs for caps in grid.options(d, ss.FINE_KW)}
    if (len(rows) != len(expected) or {(r["design"], tuple(r["caps_kw"])) for r in rows} != expected
            or any(ss.Design(r["port_plugs"], r["port_kw"], r["warehouse_kw"]).label != r["design"]
                   or r["priced"] or r["missing_ratings_kw"] != [15] for r in rows)):
        raise ValueError("Warehouse 15 kW screen does not cover the fine operating grid")
    return rows


def price_interval(comparator, options, unresolved, factor):
    """Difference of optimal operating-point costs using opposite interval endpoints."""
    if not math.isfinite(factor) or factor <= 0 or not options:
        raise ValueError("A positive annuity and a feasible same-service point are required")
    if (comparator["total_lower"] is None or comparator["total_upper"] is None
            or any(r["known_lower"] > r["known_upper"] + COST_MARGIN_EUR for r in options)):
        raise ValueError("A complete comparator and ordered cost intervals are required")
    lower = comparator["total_lower"] - min(r["known_upper"] for r in options)
    upper = None if unresolved else comparator["total_upper"] - min(r["known_lower"] for r in options)
    threshold = min(r["known_upper"] for r in options)
    points = [[r["port_cap_kw"], r["warehouse_cap_kw"]] for r in options
              if r["known_lower"] <= threshold + COST_MARGIN_EUR]
    return dict(annual_allowance_lower_eur_2025=lower, annual_allowance_upper_eur_2025=upper,
                net_equipment_lower_eur_2026=lower/factor,
                net_equipment_upper_eur_2026=None if upper is None else upper/factor,
                feasible_minimum_points=points, unresolved_points=unresolved)


def _week_meter(period, design, caps, fixed, req, result, witness):
    active = ss._active_build(design, caps)
    if (req.phase != "energy" or req.week != period.days[0]["week_start"] or req.caps != caps
            or req.fixed != fixed or req.prefer
            or not ss._dominates(ss._active_build(req.design, req.caps), active)):
        raise ValueError("Warehouse procurement witness scope differs")
    stat, audit = result["stats"], result["audit"]
    if witness is not None:
        expected = "identical_request" if ss._active_build(req.design, req.caps) == active else "fitting_superset_same_caps"
        if witness["source"] != expected or stat["status"] not in ss.ENERGY_ACCEPTED:
            raise ValueError("The fixed screening donor was not admitted on these caps")
    elif req.design != active:
        raise ValueError("A new warehouse request did not identify its target hardware")
    if audit is None:
        if stat["status"] in ss.ENERGY_ACCEPTED:
            raise ValueError("Admitted warehouse certificate omits its meter")
        return None
    if ss.eb.selected(result) != set(fixed):
        raise ValueError("Warehouse schedule does not serve the exact registered vehicle-days")
    meter = ss.meter_replay(period, active.hardware(), ss.eb.DEFAULT_SPEC, caps, result)
    if not meter["passed"]:
        raise ValueError("Warehouse schedule failed target replay")
    for i, site in enumerate(ss.SITES):
        for field, frozen in (("site_grid_kwh","site_kwh_floor"), ("site_quarter_peak_kw","site_peak_floor")):
            ss.close(meter[field][site], audit[field][site], ("donor replay", field, site))
            if witness is not None:
                ss.close(meter[field][site], witness[frozen][i], ("fixed refinement meter", frozen, site))
    if witness is not None:
        ss.close(meter["purchase_eur"], witness["purchase_upper_eur_2021"], "fixed purchase")
    ss.close(meter["purchase_eur"], audit["purchase_eur"], "warehouse replay")
    ss.close(meter["purchase_eur"], stat["objective_upper"], "warehouse incumbent")
    if (stat["status"] in ss.ENERGY_ACCEPTED and (stat["objective_lower"] is None
            or not math.isfinite(stat["objective_lower"]) or stat["objective_lower"] > meter["purchase_eur"] + ss.EPS)):
        raise ValueError("Missing or inverted admitted warehouse purchase bound")
    return meter


def _physical_exclusion(row):
    if row["reason"] not in {"infeasible_superset", "weekly_window_capacity", "infeasible_network_relaxation"}:
        raise ValueError("An economic screen against another design cannot remove a price point")
    if not row["exclusion"]:
        raise ValueError("A physically excluded warehouse point requires its registered proof")
    return row["exclusion"]


def _comparison(assigned, historical):
    """Keep live lower bounds from unadmitted points separate from the billed software point."""
    valid = [o for o in historical if o["total_lower"] != ""]
    with_bill = [o for o in valid if o["status"] in ss.ENERGY_ACCEPTED and o["total_upper"] != ""]
    low = min((float(o["total_lower"]) for o in valid), default=None)
    best = min(with_bill, key=lambda o: (float(o["total_upper"]), int(o["port_cap_kw"]), int(o["warehouse_cap_kw"])),
               default=None)
    high = float(best["total_upper"]) if best else None
    caps = [int(best[k]) for k in ("port_cap_kw", "warehouse_cap_kw")] if best else None
    if assigned is None:
        if valid:
            raise ValueError("Missing matched-port coarse design interval")
    elif (assigned["total_lower"], assigned["total_upper"], assigned["caps_kw"]) != (low, high, caps):
        raise ValueError("Matched-port coarse result disagrees with its unrounded invoices")
    overlapping = [o for o in valid if high is None or float(o["total_lower"]) <= high + COST_MARGIN_EUR]
    def cap_list(group):
        return sorted([[int(o["port_cap_kw"]), int(o["warehouse_cap_kw"])] for o in group])
    unresolved = cap_list([o for o in overlapping if o["status"] == "unresolved"])
    status = ("unresolved" if unresolved or (best is None and any(o["status"] == "unresolved" for o in historical))
              else "settled" if best else "infeasible")
    return dict(total_lower=low, total_upper=high, caps_kw=caps, comparison_status=status,
                comparison_overlapping_caps=cap_list(overlapping), comparison_unresolved_caps=unresolved)


def warehouse_prices(inputs, coarse, refinement, evidence, *, progress=None):
    coarse, refinement = Path(coarse), Path(refinement)
    points = screened_points(refinement)
    refined = ss.eb.read_json(refinement / "manifest.json")
    state = refinement / "freeze_evidence.json"
    if digest(state) != refined["products"][state.name]:
        raise ValueError("Refinement freeze evidence differs from its manifest")
    archived = ss.eb.read_json(state)
    if (archived["source_seal_sha256"] != digest(coarse / "seal.json")
            or archived["source_manifest_sha256"] != digest(coarse / "run_manifest.json")
            or archived["input_sha256"] != inputs.source_sha256):
        raise ValueError("The warehouse screening inputs differ from the sealed coarse cohort")
    manifest = ss.eb.read_json(coarse / "run_manifest.json")
    if list(map(tuple, manifest["inputs"]["fixed_service"])) != sorted(inputs.registered):
        raise ValueError("Warehouse study requires the same coarse registered vehicle-days")
    seal = ss.eb.read_json(coarse / "seal.json")["products"]
    for name in ("selection.json", "annual_costs.csv"):
        if digest(coarse / name) != seal[name]:
            raise ValueError(f"Sealed comparison differs: {name}")
    selection = ss.eb.read_json(coarse / "selection.json")
    comparators = {(r["design"], r["scenario"], r["connection_basis"]): r for r in selection["design_ranks"]}
    with (coarse / "annual_costs.csv").open(newline="", encoding="utf-8") as stream:
        old_points = list(csv.DictReader(stream))
    factor = ss.eb.read_json(ss.eb.WEEKS.with_name("site_sizing.json"))["model_policy"][
        "equipment_cost_from_net_2026_to_annual_2025"]
    statuses, weekly, costs = [], [], []
    choices = defaultdict(list)
    for row in points:
        evidence.check()
        design = ss.Design(row["port_plugs"], row["port_kw"], row["warehouse_kw"])
        caps = tuple(row["caps_kw"])
        key = point_key(design, caps)
        if row["decision"] == "exclude":
            statuses.append(dict(**key, status="infeasible", source=row["reason"], proof=_physical_exclusion(row)))
            continue
        if row["decision"] != "retain":
            raise ValueError("Unknown sealed screen decision")
        # A weekly procurement request exists independently of the unpriced warehouse unit.
        proofs = {w["week"]: w for w in row["weekly"]}
        if (len(proofs) != len(row["weekly"]) or set(proofs) != {p.days[0]["week_start"] for p in inputs.periods}):
            raise ValueError("Retained warehouse point has an incomplete or repeated screening calendar")
        requests = []
        periods = {}
        targets = {}
        for period in inputs.periods:
            week = period.days[0]["week_start"]
            fixed = tuple(sorted(inputs.registered & period.keys))
            target = ss._active_build(design, caps)
            periods[week] = period
            targets[week] = Request.make(period, target, "energy", caps, fixed=fixed)
            if not proofs[week]["proof"]:
                requests.append(targets[week])
        pairs = dict(zip([r.week for r in requests], evidence.batch(requests), strict=True))
        traced = []
        for week, period in periods.items():
            donor = proofs[week]["proof"]
            label, result = ((donor, evidence.get(donor)) if donor else pairs[week])
            req = evidence.request_for(label)
            status = result["stats"]["status"]
            meter = _week_meter(period, design, caps, targets[week].fixed, req, result, proofs[week] if donor else None)
            traced.append(dict(status=status, audit=meter, purchase_lower=result["stats"]["objective_lower"]))
            weekly.append(dict(**key, week=week, evidence_id=label, status=status,
                               evidence_method=proofs[week]["source"] if donor else "exact_weekly_request",
                               purchase_lower=result["stats"]["objective_lower"], audit=meter))
        status = ("infeasible" if any(w["status"] == "infeasible" for w in traced) else
                  "unresolved" if any(w["status"] not in ss.ENERGY_ACCEPTED for w in traced) else "settled")
        statuses.append(dict(**key, status=status, source="twelve_week_replay"))
        if status == "settled":
            for bill in invoices(inputs.periods, design, traced):
                if list(bill["missing_ratings_kw"]) != [15]:
                    raise ValueError("Expected one unquoted warehouse charger")
                item = dict(**key, **bill)
                costs.append(item)
                choices[design.label, bill["scenario"], bill["connection_basis"]].append(item)
        if progress:
            progress(f"warehouse {design.label} {caps}: {status}")
    thresholds = _threshold_rows(selection["winners"], comparators, old_points, statuses, choices, factor)
    if len(thresholds) != 24:
        raise ValueError("Expected two warehouse comparisons in all twelve tariff cases")
    return dict(warehouse_points=statuses, warehouse_weeks=weekly, warehouse_bills=costs,
                warehouse_thresholds=thresholds)


def _threshold_rows(cases, comparators, old_points, statuses, choices, factor):
    thresholds = []
    for case in cases:
        scenario, basis = case["scenario"], case["connection_basis"]
        for port in (20, 40):
            design = ss.Design(1, port, 15)
            comp_key = ss.Design(1, port, 20).label, scenario, basis
            matching = [o for o in old_points if (o["design"], o["scenario"], o["connection_basis"]) == comp_key]
            if not matching:
                raise ValueError(("Missing archived comparison grid", comp_key))
            r = _comparison(comparators.get(comp_key), matching)
            item = dict(design=design.label, scenario=scenario, connection_basis=basis,
                        comparison_design=comp_key[0], comparison_caps=r["caps_kw"], comparison_lower=r["total_lower"],
                        comparison_upper=r["total_upper"], comparison_status=r["comparison_status"],
                        comparison_overlapping_caps=r["comparison_overlapping_caps"],
                        comparison_unresolved_caps=r["comparison_unresolved_caps"], net_to_annual_factor=factor)
            options = choices.get((design.label, scenario, basis), [])
            unresolved = sum(s["status"] == "unresolved" for s in statuses if s["design"] == design.label)
            item.update(annual_allowance_lower_eur_2025=None, annual_allowance_upper_eur_2025=None,
                        net_equipment_lower_eur_2026=None, net_equipment_upper_eur_2026=None,
                        feasible_minimum_points=[], unresolved_points=unresolved)
            if options and r["total_upper"] is not None:
                item.update(price_interval(r, options, unresolved, factor))
            item["status"] = ("infeasible" if not options and not unresolved else
                              "unresolved" if unresolved or r["comparison_status"] != "settled" else "settled")
            thresholds.append(item)
    return thresholds
