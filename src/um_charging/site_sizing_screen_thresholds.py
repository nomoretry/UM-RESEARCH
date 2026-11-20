"""Check how screened, priced operating points can move equipment price thresholds."""

from collections import defaultdict
import math

from .site_sizing import Design


def _check_published(actual, expected, quantity):
    if not math.isclose(actual, expected, rel_tol=0., abs_tol=1e-6):
        raise ValueError(f"Published {quantity} was {expected}, recalculated {actual}")


def _threshold(value, low, high, witness, *, quote_factor=None):
    result = dict(
        status="unchanged" if low == high else "interval",
        evaluated_annual_eur_per_unit_2025=value,
        annual_eur_per_unit_2025_bounds=[low, high],
        screened_bound_witness=witness,
    )
    if quote_factor is not None:
        result.update(evaluated_net_equipment_eur_2026=value / quote_factor,
                      net_equipment_eur_2026_bounds=[low / quote_factor, high / quote_factor])
    return result


def quote_threshold_ranges(publication, excluded_points, *, evaluated_points=(), interval_points=(),
                           verify_published=True, include_all_witnesses=False):
    """Recompute published thresholds with screened bills replaced by their lower limits.

    ``excluded_points`` contains triples of installed design, operating caps, and annual
    lower bills keyed by (tariff scenario, connection basis). ``evaluated_points``
    has the same shape with settled bills. ``interval_points`` has a fourth entry
    with audited upper bills when available. A higher incumbent quote first ties a
    design that uses fewer of those units. Improving a rival bill can lower that
    quote or increase the break-even annual cost of the port-only HYC50.
    Ranges concern the assessed and screened points, conditional on the published
    winner and other quotes. Points awaiting a solve may still change the thresholds.
    """
    designs = {r["design"]: Design(r["port_plugs"], r["port_kw"], r["warehouse_kw"])
               for r in publication["service"]}
    amounts = defaultdict(dict)
    for row in publication["cost_rows"]:
        for basis, total in row["total_eur"].items():
            if total is not None:
                amounts[row["scenario"], basis][designs[row["design"]]] = total
    annual_cost = {int(k): v for k, v in publication["investment"]["annual_charger_eur_2025_by_kw"].items()}
    factor = publication["model_policy"]["equipment_cost_from_net_2026_to_annual_2025"]
    if not math.isfinite(factor) or factor <= 0.:
        raise ValueError("The quote annualization factor must be positive and finite")
    screened = defaultdict(list)
    winner_keys = {(r["scenario"], r["connection_basis"]) for r in publication["winners"]}

    def add_evaluated(design, bills):
        if any(kw not in annual_cost for kw in design.chargers()):
            raise ValueError(f"Equipment prices are missing for evaluated build {design.label}")
        if not all(key in winner_keys and math.isfinite(value) for key, value in bills.items()):
            raise ValueError(f"Invalid evaluated bills for {design.label}")
        for key, cost in bills.items():
            amounts[key][design] = min(cost, amounts[key].get(design, math.inf))

    for design, _, bills in evaluated_points:
        add_evaluated(design, bills)
    all_lower_bills = list(excluded_points)
    for design, caps, lower_bills, upper_bills in interval_points:
        if not all(key in lower_bills and lower_bills[key] <= upper for key, upper in upper_bills.items()):
            raise ValueError(f"Interval bounds are inverted for {design.label} at {caps}")
        add_evaluated(design, upper_bills)
        all_lower_bills.append((design, caps, lower_bills))
    for design, caps, lower_bills in all_lower_bills:
        if any(kw not in annual_cost for kw in design.chargers()):
            raise ValueError(f"Equipment prices are missing for screened build {design.label}")
        # A capacity relaxation with no feasible allocation may have a +infinity bound.
        if lower_bills.keys() != winner_keys or not all(v > -math.inf for v in lower_bills.values()):
            raise ValueError(f"Invalid screened bills for {design.label} at {caps}")
        for key, cost in lower_bills.items():
            screened[key].append((cost, design, tuple(caps)))

    hyc50 = Design(1, 50, 0)
    rows = []

    def witness_list(result, improving):
        if include_all_witnesses:
            result["screened_bound_witnesses"] = [dict(design=design.label, caps_kw=caps)
                                                  for _, design, caps in sorted(improving)]

    for winner in publication["winners"]:
        key = winner["scenario"], winner["connection_basis"]
        incumbent = designs[winner["design"]]
        rating = incumbent.chargers()[0]
        count = incumbent.chargers().count(rating)
        bill = winner["annual_total_eur"]
        installed = annual_cost[rating]
        quote_factor = factor if rating != 50 else None
        evaluated = amounts[key]

        # When equipment quotes move, a design using fewer units has a smaller price slope.
        def crossover(design, cost):
            avoided = count - design.chargers().count(rating)
            return installed + (cost - bill) / avoided if avoided > 0 else math.inf

        low_quote, alternative = min((crossover(design, cost), design) for design, cost in evaluated.items())
        reversals = [(value, design, caps) for cost, design, caps in screened[key]
                     if (value := crossover(design, cost)) < low_quote]
        alternative_bound = min(reversals, default=None)
        row = dict(scenario=key[0], connection_basis=key[1], design=incumbent.label, port_rating_kw=rating)
        if math.isfinite(low_quote):
            if verify_published:
                prior = winner["price_reversal"]
                _check_published(low_quote, prior["annual_eur_per_unit_2025"], "price reversal")
                if quote_factor is not None:
                    _check_published(low_quote / quote_factor, prior["net_equipment_eur_2026"], "net price reversal")
            lower, witness = low_quote, None
            if alternative_bound is not None and alternative_bound[0] < lower:
                lower, design, caps = alternative_bound
                witness = dict(design=design.label, caps_kw=caps)
            row["price_reversal"] = _threshold(low_quote, lower, low_quote, witness, quote_factor=quote_factor)
            row["price_reversal"]["evaluated_alternative"] = alternative.label
            witness_list(row["price_reversal"], reversals)

        if hyc50 in evaluated and math.isfinite(crossover(hyc50, evaluated[hyc50])):
            hyc_bill = evaluated[hyc50]
            hyc_comparisons = [(cost, design, caps) for cost, design, caps in screened[key]
                               if design == hyc50 and cost < hyc_bill]
            hyc_bound = min(hyc_comparisons, default=None)
            lower, witness = hyc_bill, None
            if hyc_bound is not None and hyc_bound[0] < lower:
                lower, _, caps = hyc_bound
                witness = dict(design=hyc50.label, caps_kw=caps)
            evaluated_quote = crossover(hyc50, hyc_bill)
            annual_break_even = annual_cost[50] + bill - hyc_bill
            if verify_published:
                prior_hyc = winner["port_only_hyc50_comparison"]
                _check_published(hyc_bill, prior_hyc["annual_total_eur"], "HYC50 annual bill")
                _check_published(evaluated_quote, prior_hyc["annual_eur_per_unit_2025"], "incumbent quote vs. HYC50")
                if quote_factor is not None:
                    _check_published(evaluated_quote / quote_factor, prior_hyc["net_equipment_eur_2026"],
                                     "net incumbent quote vs. HYC50")
                _check_published(annual_break_even, prior_hyc["hyc50_annual_eur_per_unit_2025"], "HYC50 break-even cost")
            row["incumbent_quote_vs_hyc50"] = _threshold(evaluated_quote, crossover(hyc50, lower), evaluated_quote,
                                                         witness, quote_factor=quote_factor)
            row["hyc50_annual_break_even"] = _threshold(annual_break_even, annual_break_even,
                                                       annual_cost[50] + bill - lower, witness)
            witness_list(row["incumbent_quote_vs_hyc50"], hyc_comparisons)
            witness_list(row["hyc50_annual_break_even"], hyc_comparisons)
        rows.append(row)
    return rows


def select_quote_witnesses(publication, screening, *, limit=10):
    """Select every excluded point whose lower bill can move a quote threshold.

    Sort by the cheapest annual lower bill across the tariff and connection
    cases, then by design label and operating caps to make ties reproducible.
    A point unable to pack the fixed load even in the relaxation is infeasible.
    """
    if not 0 <= limit <= 10:
        raise ValueError("At most ten quote witness points may be selected")
    designs = {row["design"]: Design(row["port_plugs"], row["port_kw"], row["warehouse_kw"])
               for row in publication["service"]}
    excluded = []
    minima = {}
    for point in screening["points"]:
        if point["status"] != "excluded_by_annual_lower_bound":
            continue
        comparisons = point["annual_comparison"]
        if all(row["no_relaxed_load_split"] for row in comparisons):
            continue
        if any(row["no_relaxed_load_split"] for row in comparisons):
            raise ValueError(f"Inconsistent load relaxation for {point['design']} at {point['caps_kw']}")
        bills = {(row["scenario"], row["connection_basis"]): row["lower_eur"] for row in comparisons}
        name, caps = point["design"], tuple(point["caps_kw"])
        minima[name, caps] = min(bills.values())
        excluded.append((designs[name], caps, bills))

    affected = defaultdict(list)
    for row in quote_threshold_ranges(publication, excluded, include_all_witnesses=True):
        for metric in ("price_reversal", "incumbent_quote_vs_hyc50", "hyc50_annual_break_even"):
            if metric not in row:
                continue
            for point in row[metric]["screened_bound_witnesses"]:
                affected[point["design"], point["caps_kw"]].append({
                    "scenario": row["scenario"], "connection_basis": row["connection_basis"], "metric": metric,
                })
    ordered = sorted(affected, key=lambda key: (minima[key], *key))
    rows = [dict(design=name, caps_kw=caps, min_annual_lower_eur_2025=minima[name, caps],
                 affected_thresholds=affected[name, caps]) for name, caps in ordered]
    return dict(eligible_count=len(rows), selected=rows[:limit], unselected=rows[limit:])
