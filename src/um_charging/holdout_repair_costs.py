"""M9 annual costs of the two priced warehouse repairs at registered operating limits."""
from datetime import date, timedelta
import math

from . import holdout_bills as hb
from . import site_sizing as ss
from .cabinet_tariff import annual_repeats


REPAIRS = (ss.Design(1, 20, 20), ss.Design(1, 40, 20))


class RatedServiceFailure(ValueError):
    """A rated repair contradicts the archived 15 kW service witness."""


def _register(weeks, previous, annual_kwh):
    main = previous["main"]
    if (len(weeks) != 6 or len(set(weeks)) != len(weeks)
            or list(weeks) != [r["week"] for r in main["weekly"]]
            or not math.isclose(annual_kwh, main["annual_grid_kwh"], rel_tol=0., abs_tol=ss.EPS)):
        raise ValueError("Repair weeks or annual kWh differ from the verified register")
    registered, outside = {w: set() for w in weeks}, set()
    for row in main["daily"]:
        day = date.fromisoformat(row["date"])
        week = (day - timedelta(days=day.weekday())).isoformat()
        registered[week].update((row["date"], v) for v in row["registered"])
        outside.update((row["date"], v) for v in set(row["eligible"]) - set(row["registered"]))
    excluded = {(r["date"], r["vehicle_id"]) for r in main["outside"]
                if r["classification"] == "infeasible_unlimited_power"}
    if outside != excluded or any(len(registered[r["week"]]) != r["registered"] for r in main["weekly"]):
        raise ValueError("The fixed-R witness does not establish the archived daily-policy result")
    return registered


def _fixed_point(weeks, records, design, caps, registered, annual_kwh, repeats):
    point = hb._operating_point(weeks, records, caps, annual_kwh, repeats)
    if caps == design.caps and point["status"] == "infeasible":
        raise RatedServiceFailure(f"Rated {design.label} cannot serve R: {point['week_status']}")
    physical = {}
    bounds = {}
    for week in weeks:
        result = records.get(week)
        if result is None:
            physical[week] = "unresolved"
            continue
        stats = result["stats"]
        bounds[week] = [stats.get("objective_lower"), stats.get("objective_upper")]
        if result["audit"] and result["audit"]["passed"]:
            if ss.eb.selected(result) != registered[week]:
                raise ValueError(f"{design.label} {caps} served a different register in {week}")
            physical[week] = "feasible"
        else:
            physical[week] = "infeasible" if point["week_status"][week] == "infeasible" else "unresolved"
    return dict(design=design.label, **point, week_service_status=physical,
                weekly_purchase_eur_2021_bounds=bounds)


def _zero_warehouse_proof(previous, design, caps):
    """The 50 kW port and its looser quarter cap contain every tested port-only schedule."""
    if not (design.port_plugs == 1 and caps[1] == 0 and 0 < caps[0] <= design.port_kw <= ss.BASELINE.port_kw):
        raise ValueError("The zero-warehouse dominance proof does not cover this operating point")
    sources = [p for p in previous["billing"]["operating_points"]
               if p["design"] == ss.BASELINE.label and p["caps_kw"] == [ss.BASELINE.port_kw, 0]]
    if len(sources) != 1:
        raise ValueError("Expected the archived baseline's port-only operating point")
    source, = sources
    infeasible = [w for w, status in source["week_status"].items() if status == "infeasible"]
    if (source["status"] == "infeasible") != bool(infeasible):
        raise ValueError("Archived whole-period and weekly infeasibility evidence disagree")
    return dict(design=design.label, caps_kw=list(caps), source_design=source["design"],
                source_caps_kw=source["caps_kw"], infeasible_weeks=infeasible,
                status="infeasible" if infeasible else "unresolved",
                relation="subset_of_single_port_50kw_hardware_and_50kw_quarter_cap")


def _invoice(point, hardware, materials, network, scenario, basis, policy):
    if point["status"] in ss.ENERGY_ACCEPTED:
        bill = hb._bill(point, hardware, materials, network, scenario, basis)
    else:
        bill = dict(status=point["status"], caps_kw=point["caps_kw"])
    return dict(**bill, policy=policy)


def _ranks(bills):
    bounds = {name: b["annual_total_eur_bounds"] for name, b in bills.items()
              if b["status"] in ss.ENERGY_ACCEPTED}
    rank = {}
    for d in bills:
        if d not in bounds:
            rank[d] = [1, len(bills)]
            continue
        lo, hi = bounds[d]
        cheaper = sum(v[1] < lo for other, v in bounds.items() if other != d)
        dearer = sum(hi < v[0] for other, v in bounds.items() if other != d)
        rank[d] = [1 + cheaper, len(bills) - dearer]
    if len(bounds) != len(bills):
        return "unresolved", rank
    return ("determined" if all(a == b for a, b in rank.values()) else "overlap"), rank


def costs(weeks, runs, previous, annual_kwh):
    """Price all twelve cases using fixed-R dispatches and independently verified prior bills.

    runs collects only the two rated limits and two 15 kW service-reference limits.
    A missing week or a wide purchase gap leaves that six-week policy unpriced.
    """
    registered = _register(weeks, previous, annual_kwh)
    network = ss.load_network()
    materials = ss._load_costs(ss.CONNECTION_INPUT, network)
    m8 = ss.eb.read_json(ss.eb.WEEKS.with_name("site_sizing.json"))
    frozen = {(r["design"], r["scenario"]): tuple(r["caps_kw"]) for r in m8["cost_rows"]
              if r["design"] in {d.label for d in REPAIRS}}
    points = {}
    zero = {}
    for d in REPAIRS:
        for caps in (d.caps, (d.port_kw, 15)):
            records = runs.get((d.label, caps), {})
            if not set(records) <= set(weeks):
                raise ValueError("Found dispatch outside the six registered weeks")
            points[d.label, caps] = _fixed_point(weeks, records, d, caps, registered, annual_kwh,
                                                 annual_repeats(network))
        for caps in sorted({c for (label, _), c in frozen.items() if label == d.label and c[1] == 0}):
            zero[d.label, caps] = _zero_warehouse_proof(previous, d, caps)
    if not set(runs) <= set(points):
        raise ValueError("Found a dispatch outside the four registered repair operating points")

    cases = []
    for old in previous["billing"]["cases"]:
        scenario, basis = old["scenario"], old["connection_basis"]
        baseline = old["bills"][ss.BASELINE.label]
        combined = {ss.BASELINE.label: baseline}
        repairs = {}
        for d in REPAIRS:
            caps = frozen[d.label, scenario]
            policy = "frozen"
            if caps == d.caps:
                chosen = points[d.label, caps]
            else:
                chosen = zero[d.label, caps]
                if chosen["status"] == "infeasible":
                    chosen, policy = points[d.label, d.caps], "rated_fallback"
            main = _invoice(chosen, d, materials, network, scenario, basis, policy)
            main["frozen_caps_kw"] = list(caps)
            reference = _invoice(points[d.label, (d.port_kw, 15)], d, materials, network, scenario, basis,
                                 "service_cap_reference")
            repairs[d.label] = dict(main=main, reference=reference)
            combined[d.label] = main
        ranking_status, rank_bounds = _ranks(combined)
        cases.append(dict(scenario=scenario, connection_basis=basis, baseline=baseline, repairs=repairs,
                          ranking_status=ranking_status, rank_bounds=rank_bounds))
    expected_cases = {(s, basis) for s in ("N0", *network["tariffs"], *network["capacity_sensitivities_eur_per_kw_year"])
                      for basis in ("new", "existing")}
    if len(cases) != len(expected_cases) or {(r["scenario"], r["connection_basis"]) for r in cases} != expected_cases:
        raise ValueError("Missing or repeated tariff/access case in the verified baseline")
    return dict(cases=cases, operating_points=list(points.values()), zero_warehouse_proofs=list(zero.values()))
