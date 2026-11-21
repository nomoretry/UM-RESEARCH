"""Re-register the holdout service after closing the specified truck-5 dwell intervals."""
from collections import Counter

from . import holdout_inputs as hi
from . import site_sizing as ss
from .holdout import compact_diagnosis, pairs, service_week
from .holdout_evidence import WallLimit


PORT_ONLY = (ss.Design(1, 20, 0), ss.Design(1, 40, 0))
REPAIRED = (ss.Design(1, 20, 20), ss.Design(1, 40, 20))
CONFIGS = ([(d, d.caps) for d in (*PORT_ONLY, *REPAIRED)] +
           [(d, (d.port_kw, 15)) for d in REPAIRED])
TARGET = ("2021-11-26", "1")


def _window_audit(ordinary, strict):
    source = hi.read_json(hi.WEEKS)
    rows = source["parking_bounds"]["mapped_intervals_at_least_1km"]

    def key(date, truck, row):
        return date, truck, row["site"], row["arrival_track_id"], row["next_track_id"]

    registered = {key(r["date"], r["vehicle_id"], r) for r in rows}
    removed = set()
    trip_count = windows = links = 0
    for before, after in zip(ordinary, strict, strict=True):
        if (before.chains, before.links, before.keys, before.prices) != (
                after.chains, after.links, after.keys, after.prices):
            raise ValueError("Closing a dwell interval changed the weekly duties, links or prices")
        links += len(after.links)
        for day, revised in zip(before.days, after.days, strict=True):
            date = day["date"]
            for vehicle, updated in zip(day["vehicles"], revised["vehicles"], strict=True):
                truck = vehicle["vehicle_id"]
                blocked = [s for s in vehicle["stops"] if key(date, truck, s) in registered]
                removed.update(key(date, truck, s) for s in blocked)
                if (truck != updated["vehicle_id"] or vehicle["trips"] != updated["trips"]
                        or [s for s in vehicle["stops"] if s not in blocked] != updated["stops"]
                        or vehicle["unmapped_gaps"] + blocked != updated["unmapped_gaps"]):
                    raise ValueError("Sensitive input changed an unregistered stop, trip or gap")
                trip_count += len(vehicle["trips"])
                base_windows = Counter(before.cases[date]["trucks"][truck]["windows"])
                new_windows = Counter(after.cases[date]["trucks"][truck]["windows"])
                if new_windows - base_windows:
                    raise ValueError("Closing a dwell created a new released charging window")
                windows += sum((base_windows - new_windows).values())
    if removed != registered:
        raise ValueError("Closed dwell records differ from the preregistered set")
    return dict(disabled_intervals=len(removed), trip_pairs=len({k[-2:] for k in removed}),
                vehicle_ids=sorted({k[1] for k in removed}), removed_released_windows=windows,
                cross_day_links=links, trip_count=trip_count)


def _main_choices(previous, periods):
    main = previous["main"]
    reference = {(row["date"], v) for row in main["daily"] for v in row["registered"]}
    outside = {(r["date"], r["vehicle_id"]) for r in main["outside"]
               if r["classification"] == "infeasible_unlimited_power"}
    if outside != set.union(*(p.keys for p in periods)) - reference:
        raise ValueError("Prior evidence does not exclude all days outside the main registration")
    selections = {d: {(r["date"], v) for r in main["daily"] for v in r["facilities"][d.label]}
                  for d in PORT_ONLY}
    for old, new in zip(PORT_ONLY, REPAIRED, strict=True):
        options = previous["repairs"]["starts"][old.label]["options"]
        minimal = ss.Design(1, old.port_kw, 15)
        if not any(r["design"] == minimal.label and r["fixed_R_status"] == "feasible" for r in options):
            raise ValueError("Main sample lacks the six-week fixed service witness at 15 kW")
        # A 15 kW hardware schedule also fits a 20 kW unit with a 15 kW quarter cap.
        selections[new] = reference
    return reference, selections


class _DailyLog:
    """Keep earlier certified dates when the formal deadline interrupts a week."""
    def __init__(self, log):
        self.log = log
        self.count = 0
        self.expired = False

    def call(self, *args, **kwargs):
        if not self.expired:
            if self.count >= 196:
                raise ValueError("The sensitivity exceeds its preregistered 196 calls")
            try:
                result = self.log.call(*args, **kwargs)
            except WallLimit:
                self.expired = True
            else:
                self.count += 1
                return result
        return {"stats": {"status": "unresolved"}}


def _compare(daily, config_id, old):
    known = [r for r in daily if r["selected"][config_id] is not None and r["registered"] is not None]
    dates = {r["date"] for r in known}
    chosen = {(r["date"], v) for r in known for v in r["selected"][config_id]}
    reference = {(r["date"], v) for r in known for v in r["registered"]}
    main = {k for k in old if k[0] in dates}
    missing = reference - chosen
    incomplete = [r["date"] for r in daily if r["date"] not in dates]
    return dict(status="service_gap" if missing else "unresolved" if incomplete else "matched",
                served_count=None if incomplete else len(chosen), certified_count=len(chosen),
                missing=pairs(missing), added=pairs(chosen - reference),
                lost_vs_main=pairs(main - chosen), gained_vs_main=pairs(chosen - main),
                unresolved_dates=incomplete)


def run_sensitivity(log, previous, progress):
    """Return date-level certified sets, changes and relaxed physical diagnoses."""
    periods = hi.load_periods(sensitivity=True)
    windows = _window_audit(hi.load_periods(), periods)
    main_reference, old = _main_choices(previous, periods)
    recorded = _DailyLog(log)
    dates = {d["date"]: p for p in periods for d in p.days}
    daily = []
    reference = set()
    for p in periods:
        choices = service_week(recorded, "sensitivity", p, ss.BASELINE, set())
        for d in p.days:
            date = d["date"]
            eligible = sorted(v for dt, v in p.keys if dt == date)
            chosen = choices.get(date) if eligible else []
            daily.append(dict(date=date, eligible=eligible, registered=chosen, selected={}))
            if chosen is not None:
                reference.update((date, v) for v in chosen)
    known_dates = {r["date"] for r in daily if r["registered"] is not None}
    old_known = {k for k in main_reference if k[0] in known_dates}
    lost, gained = old_known - reference, reference - old_known
    progress(f"Sensitivity registration: {len(reference)} duties on {len(known_dates)} certified calendar dates")
    configs, target_outcomes = [], {}
    target_row, = [r for r in daily if r["date"] == TARGET[0]]
    for design, caps in CONFIGS:
        label = f"{design.label} @ [{caps[0]},{caps[1]}]"
        choices = {}
        for p in periods:
            if set(p.cases) <= known_dates:
                choices.update(service_week(recorded, "sensitivity", p, design, reference, caps=caps))
        for row in daily:
            row["selected"][label] = choices.get(row["date"]) if row["eligible"] else []
        summary = _compare(daily, label, old[design])
        diagnostics = [compact_diagnosis(hi.diagnose_fixed(dates[d], (d, v), design), ("single_truck",))
                       for d, v in summary["missing"]]
        configs.append(dict(id=label, design=design.label, caps_kw=list(caps),
                            diagnostics=diagnostics, **summary))
        selected = target_row["selected"][label]
        if target_row["registered"] is None:
            outcome = "unresolved"
        elif TARGET[1] not in target_row["registered"]:
            outcome = "outside_reference"
        else:
            outcome = "unresolved" if selected is None else "served" if TARGET[1] in selected else "missed"
        target_outcomes[label] = outcome
        progress(f"Sensitivity {label}: {summary['certified_count']} certified duties, {summary['status']}")
    diagnostics = []
    for key in sorted(lost):
        detail = hi.diagnose(dates[key[0]], key)
        diagnostics.append(compact_diagnosis(detail, ("unlimited",) if not detail["unlimited_feasible"]
                                              else ("truck_50kw",)))
    port_outcomes = [target_outcomes[c["id"]] for c in configs[:2]]
    port_statuses = [c["status"] for c in configs[:2]]
    return dict(status="complete" if all(not c["unresolved_dates"] for c in configs) else "unresolved",
                registered_count=len(reference) if len(daily) == len(known_dates) else None,
                certified_reference_count=len(reference), registration_lost=pairs(lost),
                registration_gained=pairs(gained), registration_diagnostics=diagnostics,
                daily=daily, configs=configs, window_audit=windows, service_calls=recorded.count,
                wall_limit_reached=recorded.expired,
                target_gap=dict(date=TARGET[0], vehicle_id=TARGET[1],
                                registered=TARGET in reference if TARGET[0] in known_dates else None,
                                by_config=target_outcomes,
                                port_only_gap_persists=None if "unresolved" in port_outcomes
                                else all(s == "missed" for s in port_outcomes)),
                port_only_insufficient=None if "unresolved" in port_statuses
                else all(s == "service_gap" for s in port_statuses))
