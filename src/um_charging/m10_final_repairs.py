"""The separately limited physical diagnosis and priced F40 staircase."""
from dataclasses import dataclass
import math

from . import site_sizing as ss
from .m10_costs import _parameters
from .m10_final_bills import capital, invoice


F20 = ss.Design(1, 20, 20)
F40 = ss.Design(1, 40, 20)
LIMIT = 6
BASES = ("new", "existing")
PRICED_STAIRCASE = (ss.Design(1, 50, 20), ss.Design(1, 40, 30),
                    ss.Design(1, 40, 40), ss.Design(1, 40, 50))


@dataclass(frozen=True)
class Increase:
    base: ss.Design
    design: ss.Design
    site: str
    added: int


def physical_order(starts):
    upgrades = []
    for base in starts:
        if base not in (F20, F40):
            raise ValueError("Only the registered full-information recommendations can trigger repair")
        for k in ss.FINE_KW:
            if k > base.port_kw:
                upgrades.append(Increase(base, ss.Design(base.port_plugs, k, base.warehouse_kw), ss.PORT, k-base.port_kw))
            if k > base.warehouse_kw:
                upgrades.append(Increase(base, ss.Design(base.port_plugs, base.port_kw, k), ss.WAREHOUSE, k-base.warehouse_kw))
    return sorted(upgrades, key=lambda r: (r.added, r.base.port_kw, r.base.warehouse_kw,
                                           r.base.port_plugs, r.site != ss.PORT, r.design.label))


def _inclusion_exclusion(design, week, fixed_proofs):
    """A containing rated design's fixed-R infeasibility excludes its subset."""
    for (other, w), trace in fixed_proofs.items():
        if w == week and trace["status"] == "infeasible" and ss._dominates(other, design):
            return dict(status="infeasible", proof_id=trace.get("proof_id"),
                        source="inclusion_exclusion", containing_design=other.label)
    return None


def _overall(rows):
    values = {r["status"] for r in rows}
    return "infeasible" if "infeasible" in values else "certified" if values == {"certified"} else "unresolved"


def _physical_trace(design, periods, reference, failures, cache, verify, admit):
    by_week = {p.days[0]["week_start"]: p for p in periods}
    ordered = sorted(by_week, key=lambda week: (week not in failures, week))
    traces = {}
    for week in ordered:
        if proof := _inclusion_exclusion(design, week, cache):
            traces[week] = proof
    if traces:
        return "infeasible", False, traces
    for week in ordered:
        p = by_week[week]
        if not (reference & p.keys):
            traces[week] = dict(status="certified", proof_id=None, source="empty_registered_week")
        elif (design, week) in cache:
            traces[week] = {**cache[design, week], "source": "direct_proof"}
        elif admit(design):
            row = verify(p, design, reference & p.keys)
            traces[week] = cache[design, week] = {**row, "source": "direct_proof"}
        if traces.get(week, {}).get("status") == "infeasible":
            return "infeasible", design in admit.used, traces
    if len(traces) != len(ordered):
        return "unexamined", False, traces
    return _overall(traces.values()), design in admit.used, traces


class Allowance:
    def __init__(self):
        self.used = set()

    def __call__(self, design):
        if design in self.used:
            return True
        if len(self.used) < LIMIT:
            self.used.add(design)
            return True
        return False


def _limits(rows, state):
    tested = [r for r in rows if state(r) == "certified"]
    possible = [r for r in rows if state(r) != "infeasible"]
    low = min((r["added_kw"] for r in possible), default=None)
    high = min((r["added_kw"] for r in tested), default=None)
    return dict(minimum_possible_added_kw=low, verified_added_kw=high,
                minimum_added_kw=low if low == high else None,
                verified_designs=[r["design"] for r in tested if r["added_kw"] == high])


def physical_repairs(periods, reference, failures, fixed_proofs, verify, daily):
    """Search the sealed order, with a separate six-design physical allowance."""
    admit = Allowance()
    cache = dict(fixed_proofs)
    output, daily_cache = [], {}
    for entry in physical_order(failures):
        design, base = entry.design, entry.base
        status, used, weeks = _physical_trace(design, periods, reference, failures[base], cache, verify, admit)
        if status == "certified":
            if design not in daily_cache and admit(design):
                chronological = sorted(periods, key=lambda p: (
                    p.days[0]["week_start"] not in failures[base], p.days[0]["week_start"]))
                daily_cache[design] = {p.days[0]["week_start"]: daily(p, design, reference & p.keys)
                                      for p in chronological}
                used = True
            policy = _overall(daily_cache[design].values()) if design in daily_cache else "unresolved"
        else:
            policy = "unresolved"
        output.append(dict(base=base.label, design=design.label, site=entry.site, added_kw=entry.added,
                           fixed_service=status, daily_service=policy, counted=used,
                           weeks=weeks, daily_weeks=daily_cache.get(design, {})))
    results = []
    for base in failures:
        scoped = [r for r in output if r["base"] == base.label]
        results.append(dict(base=base.label, fixed_service=_limits(scoped, lambda r:r["fixed_service"]),
                            daily_service=_limits(scoped, lambda r:r["daily_service"]),
                            both=_limits(scoped, lambda r:_overall(
                                [{"status":r["fixed_service"]}, {"status":r["daily_service"]}]))))
    return dict(limit=LIMIT, counted_designs=sorted(d.label for d in admit.used), options=output, minima=results)


def priced_repairs(periods, reference, failure_weeks, fixed_proofs, verify, buy, *, complete_reference=None):
    """Test all four priced F40 increases and compare incremental annual fixed fees."""
    cache = dict(fixed_proofs)
    admit = Allowance()
    output = []
    parameters = _parameters(periods)
    _, materials = parameters
    for design in PRICED_STAIRCASE:
        status, used, trace = _physical_trace(design, periods, reference, failure_weeks, cache, verify, admit)
        bills = {}
        if status == "certified":
            # A bill always gets an exact request for this hardware, even when
            # a different repair's feasible trace would physically fit it.
            admit(design)
            used = True
            weeks = [buy(p, design, reference & p.keys) for p in periods]
            for basis in BASES:
                full = (invoice(periods, design, weeks, scenario="official", basis=basis, parameters=parameters)
                        if all(w["status"] in ss.ENERGY_ACCEPTED for w in weeks) else None)
                added = math.fsum(capital(design, materials, basis)) - math.fsum(capital(F40, materials, basis))
                old = (complete_reference or {}).get(basis)
                difference = ([full["annual_total_lower"]-old["annual_total_upper"],
                               full["annual_total_upper"]-old["annual_total_lower"]] if full and old else None)
                bills[basis] = dict(extra_fixed_eur_2025=added, full=full, difference=difference,
                                    cost_status="settled" if full else "unresolved")
        output.append(dict(design=design.label, fixed_service=status, counted=used, weeks=trace, bills=bills))
    winner = {}
    for basis in BASES:
        restored = [r for r in output if r["fixed_service"] == "certified"]
        if not restored:
            winner[basis] = dict(status="unidentified_within_staircase")
            continue
        best = min(r["bills"][basis]["extra_fixed_eur_2025"] for r in restored)
        eligible = [r for r in restored if abs(r["bills"][basis]["extra_fixed_eur_2025"] - best) <= ss.EPS]
        winner[basis] = dict(status="restored", designs=[r["design"] for r in eligible],
                             extra_fixed_eur_2025=best,
                             unresolved_options=[r["design"] for r in output if r["fixed_service"] == "unresolved"])
    return dict(limit=LIMIT, counted_designs=sorted(d.label for d in admit.used), options=output, minima=winner)
