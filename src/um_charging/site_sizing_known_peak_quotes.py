"""Recompute equipment price thresholds from the screened grid and archived meters."""

from collections import Counter

from .site_sizing_screen_thresholds import quote_threshold_ranges, select_quote_witnesses


_METRICS = ("price_reversal", "incumbent_quote_vs_hyc50", "hyc50_annual_break_even")


def _flatten(totals):
    return {(tariff, basis): value for tariff, by_basis in totals.items()
            for basis, value in by_basis.items()}


def recompute_quote_thresholds(archive):
    """Return all three threshold ranges at each published priced minimum.

    An accepted ranking settlement uses its audited schedule for billing. A
    quote-only point with a timed-out week retains its lower and upper bills,
    even when that week qualified for the ranking's ordinary gap allowance.
    """
    publication = archive.evidence.publication
    prices = {int(rating) for rating in publication["investment"]["annual_charger_eur_2025_by_kw"]}
    settled = [(point.design, point.caps, _flatten(point.totals)) for point in archive.ranked_settlements
               if all(rating in prices for rating in point.design.chargers())]
    intervals, excluded, point_evidence = [], [], []

    def add_interval(design, caps, accepted, status, kind, upper):
        bound = archive.bill_lower(design, caps, accepted, quotes=True)
        lower = bound["total_eur"]
        intervals.append((design, caps, _flatten(lower), _flatten(upper or {})))
        point_evidence.append(dict(design=design.label, caps_kw=caps, kind=kind, status=status,
                                   accepted_weeks=[dict(week=week.week, proof=week.proof,
                                                        proof_sha256=week.proof_sha256) for week in accepted],
                                   lower_eur_2025=lower, upper_eur_2025=upper))

    quote_keys = set()
    for row in archive.summary["points"]:
        design = archive.evidence.cases[row["design"]]
        caps = tuple(row["caps_kw"])
        kind, status = row["kind"], row["status"]
        if kind == "threshold":
            quote_keys.add((design.label, caps))
        if status in {"infeasible_solve", "infeasible_monotonicity"}:
            continue
        if status == "settled" and kind == "ranking":
            continue
        if status not in {"settled", "excluded_by_interval", "threshold_interval", "unresolved"}:
            raise ValueError(f"Unfinished quote evidence for {design.label} at {caps}: {status}")
        accepted = archive.accepted(row)
        upper = archive.upper(row)
        if status == "settled" and all(week.status == "certified" for week in accepted):
            settled.append((design, caps, _flatten(upper)))
        else:
            add_interval(design, caps, accepted, status, kind, upper)

    # Screening checked every finite cost exclusion against all three types of
    # crossover. Adding audited alternatives can only tighten those thresholds:
    # a lower bill that could not improve a published endpoint still cannot
    # improve it after that bill's lower limit increases.
    witnesses = select_quote_witnesses(publication, archive.screening)
    material = {(row["design"], tuple(row["caps_kw"])) for row in witnesses["selected"] + witnesses["unselected"]}
    for row in archive.screening["points"]:
        design = archive.evidence.cases[row["design"]]
        caps = tuple(row["caps_kw"])
        key = design.label, caps
        if row["status"] != "excluded_by_annual_lower_bound" or key in quote_keys:
            continue
        costs = row["annual_comparison"]
        if all(r["no_relaxed_load_split"] for r in costs):
            continue
        if key in material:
            plan = archive.quote_evidence.point_plan(design, caps)
            if plan.status in {"infeasible_solve", "infeasible_monotonicity"}:
                continue
            add_interval(design, caps, plan.weeks, plan.status, "screened", None)
        else:
            excluded.append((design, caps, {(r["scenario"], r["connection_basis"]): r["lower_eur"]
                                           for r in costs}))

    rows = quote_threshold_ranges(publication, excluded, evaluated_points=settled, interval_points=intervals,
                                  verify_published=False)
    counts = {metric: Counter(exact=0, interval=0) for metric in _METRICS}
    for row in rows:
        for metric in _METRICS:
            entry = row[metric]
            low, high = entry["annual_eur_per_unit_2025_bounds"]
            entry["status"] = "exact" if low == high else "interval"
            counts[metric][entry["status"]] += 1
    return dict(quote_thresholds=rows, counts={key: dict(values) for key, values in counts.items()},
                point_evidence=point_evidence, finite_screened_without_quote_effect=len(excluded),
                missing_price_scope="Published settlements only; unpriced refined caps were not completed.")
