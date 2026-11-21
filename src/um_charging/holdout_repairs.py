"""Preregistered single-site increases for the two fixed M8 builds."""
from . import site_sizing as ss
from .holdout_bills import FIXED


LIMIT = 6
OUTCOMES = {"feasible", "infeasible", "unresolved"}


def _options(start):
    for kw in ss.FINE_KW:
        if kw > start.port_kw:
            yield kw - start.port_kw, "PORT", ss.Design(1, kw, 0)
        if kw >= 10:
            yield kw, "WAREHOUSE", ss.Design(1, start.port_kw, kw)


def _overall(outcomes):
    if "infeasible" in outcomes:
        return "infeasible"
    return "feasible" if all(value == "feasible" for value in outcomes) else "unresolved"


def _minimum(options):
    possible = min((kw for kw, _, status in options if status != "infeasible"), default=None)
    verified = min((kw for kw, _, status in options if status == "feasible"), default=None)
    return dict(minimum_added_kw=possible if possible == verified else None,
                minimum_possible_added_kw=possible, verified_added_kw=verified,
                ways_at_verified_kw=[label for kw, label, status in options
                                     if kw == verified and status == "feasible"])


def repairs(periods, ref, checks, verify, *, missing_weeks=None, verify_daily=None, daily_checks=None):
    """Prove fixed-R feasibility first; daily selection needs its own certificate.

    Both callbacks take (design, period) and return feasible/infeasible/unresolved.
    For verify_daily the first two outcomes mean R retained / a registered duty omitted.
    Only fixed-R physical feasibility propagates to larger equipment.
    """
    periods = {p.days[0]["week_start"]: p for p in periods}
    weeks = sorted(periods)
    starts = FIXED[:2]
    equipment = {d.label: d for d in FIXED}
    options = {d: list(_options(d)) for d in starts}
    equipment.update((build.label, build) for rows in options.values() for _, _, build in rows)
    physical = {(equipment[label], w): value for label, rows in checks.items() for w, value in rows.items()}
    if any(w not in periods or value not in OUTCOMES for (_, w), value in physical.items()):
        raise ValueError("Invalid fixed-R repair evidence")
    missing = {base: set((missing_weeks or {}).get(base.label, ())) |
               {w for w in weeks if physical.get((base, w)) == "infeasible"} for base in starts}
    if any(not gap <= set(weeks) for gap in missing.values()):
        raise ValueError("Unknown repair week")
    empty = {w for w, p in periods.items() if not (p.keys & ref)}
    extra, direct = [], set()
    policies = {(equipment[label], w): value for label, rows in (daily_checks or {}).items()
                for w, value in rows.items()}
    if any(w not in periods or value not in OUTCOMES for (_, w), value in policies.items()):
        raise ValueError("Invalid daily-policy evidence")
    for base in starts:
        for w in (missing_weeks or {}).get(base.label, ()):
            if policies.get((base, w)) == "feasible":
                raise ValueError("Conflicting daily-policy and registered omission records")
            policies[base, w] = "infeasible"
    # Removing a non-R neighbor can shorten a served SOC segment. Only entire
    # chains can be dropped from a superset without changing R's boundary states.
    closed = {w for w, p in periods.items() if all(not (set(c) & ref) or set(c) <= ref for c in p.chains)}

    def evidence(build, week):
        if week in empty:
            return dict(status="feasible", source="empty_registered_set")
        known = physical.get((build, week))
        if known in ("feasible", "infeasible"):
            return dict(status=known, source="direct_check" if (build, week) in direct else "initial_check")
        # All builds have one port connector, one warehouse connector iff its kW is positive,
        # and both runtime caps equal installed power. A fixed dispatch may be reused unchanged.
        proofs = {}
        for (other, w), status in physical.items():
            if w != week or status == "unresolved":
                continue
            small, large = (other, build) if status == "feasible" else (build, other)
            if all(a <= b for a, b in zip(small.caps, large.caps, strict=True)):
                proofs.setdefault(status, other.label)
        if len(proofs) > 1:
            raise ValueError(("Contradictory fixed-R monotonicity evidence", build.label, week, proofs))
        if proofs:
            status, source = next(iter(proofs.items()))
            return dict(status=status, source=f"monotonic:{source}")
        return dict(status="unresolved", source="unresolved_check" if known else "not_checked")

    def allowed(build):
        if build in FIXED or build.label in extra:
            return True
        if len(extra) == LIMIT:
            return False
        extra.append(build.label)
        return True

    def policy_status(build, week):
        if (build, week) in policies:
            return policies[build, week]
        if week in empty:
            return "feasible"
        if week in closed and evidence(build, week)["status"] == "infeasible":
            return "infeasible"
        return None

    def call(callback, build, week):
        status = callback(build, periods[week])
        if status not in OUTCOMES:
            raise ValueError(("Invalid repair verification result", status))
        return status

    queue = sorted((kw, base.port_kw, direction != "PORT", base, direction, build)
                   for base in starts if missing[base] for kw, direction, build in options[base])
    finished = set()
    for _, _, _, base, direction, build in queue:
        if (base, direction) in finished:
            continue
        first = sorted(weeks, key=lambda w: (w not in missing[base], w))
        if any(evidence(build, w)["status"] == "infeasible" for w in first):
            continue
        for week in first:
            if evidence(build, week)["status"] == "unresolved":
                if (build, week) not in physical and allowed(build):
                    physical[build, week] = call(verify, build, week)
                    direct.add((build, week))
                if evidence(build, week)["status"] == "infeasible":
                    break
        if any(evidence(build, w)["status"] != "feasible" for w in weeks):
            continue
        if verify_daily is not None:
            for week in first:
                key = build, week
                if policy_status(build, week) is None and allowed(build):
                    policies[key] = call(verify_daily, build, week)
                if policy_status(build, week) != "feasible":
                    break
            if any(policy_status(build, w) != "feasible" for w in weeks):
                continue
        finished.add((base, direction))

    results = {}
    for base in starts:
        if not missing[base]:
            continue
        original = {w: evidence(base, w)["status"] for w in weeks}
        base_status = _overall(list(original.values()))
        entries = []
        for kw, direction, build in sorted(options[base], key=lambda row: (row[0], row[1] != "PORT")):
            traces = {w: evidence(build, w) for w in weeks}
            daily = {w: status for w in weeks if (status := policy_status(build, w)) is not None}
            policy = "unchecked"
            if daily:
                status = _overall([daily.get(w, "unresolved") for w in weeks])
                policy = {"feasible": "retained", "infeasible": "omitted", "unresolved": "unresolved"}[status]
            entries.append(dict(design=build.label, direction=direction, added_kw=kw,
                                fixed_R_status=_overall([e["status"] for e in traces.values()]),
                                daily_policy_status=policy, daily_policy_weeks=daily, weeks=traces))
        original_policy = _overall([policy_status(base, w) or "unresolved" for w in weeks])
        decode = {"retained": "feasible", "omitted": "infeasible", "unchecked": "unresolved",
                  "unresolved": "unresolved"}

        def summarize(rows):
            def minimum(field, start_status):
                return _minimum([(0, base.label, start_status)] +
                                [(r["added_kw"], r["design"], field(r)) for r in rows])
            physical_min = minimum(lambda r: r["fixed_R_status"], base_status)
            policy_min = minimum(lambda r: decode[r["daily_policy_status"]], original_policy)
            both_min = minimum(lambda r: _overall([r["fixed_R_status"], decode[r["daily_policy_status"]]]),
                               _overall([base_status, original_policy]))
            return dict(**physical_min, daily_policy=policy_min, joint=both_min)
        results[base.label] = dict(missing_weeks=sorted(missing[base]), fixed_R_status=base_status,
                                   policy_omission_with_feasible_R=sorted(w for w in missing[base]
                                                                         if original[w] == "feasible"),
                                   directions={s: summarize([r for r in entries if r["direction"] == s])
                                               for s in ss.SITES}, options=entries, **summarize(entries))
    return dict(extra_designs=extra, limit=LIMIT, starts=results)
