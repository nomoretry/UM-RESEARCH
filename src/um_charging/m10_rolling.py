"""Causal calendar-day procurement with realized end-of-day SOC fixed at 150 kWh."""
from math import fsum, isfinite
from types import SimpleNamespace

from . import site_sizing as ss
from .m10_evidence import CONTINUATION_TIMEOUT_GAP_EUR, Request


def rolling_day_period(period, day, reference):
    """Expose today's fixed duties, released civil-day stops and published day-ahead prices."""
    case = period.cases[day]
    trucks = {v: {"trips": list(t["trips"]), "windows": list(t["windows"])}
              for v, t in case["trucks"].items() if (day, v) in reference}
    keys = {(day, v) for v in trucks}
    # The original arrival already governs warehouse release in build_case. The
    # local window ID carries no future trip ID or post-midnight departure time.
    windows = {(v, site, i): [(a, b)] for v, t in trucks.items()
               for i, (a, b, site) in enumerate(t["windows"])}
    return SimpleNamespace(days=[{"date": day, "week_start": "day:" + day}], keys=keys,
                           cases={day: {"date": day, "warehouse_release_min": case["warehouse_release_min"],
                                        "trucks": trucks}}, prices={day: list(period.prices[day])},
                           chains=[[key] for key in sorted(keys)], links=[], breaks=[], nights=[],
                           windows=windows, offset={day: 0})


def rolling_requests(period, design, caps, reference):
    """One realized dispatch per nonempty day. Empty days require no optimization."""
    result = []
    for day in period.cases:
        fixed = tuple(sorted(key for key in period.keys & reference if key[0] == day))
        if fixed:
            result.append(Request("day:" + day, design, "rolling_energy", tuple(caps), fixed, ()))
    return result


def rolling_week(period, design, caps, reference, pairs):
    """Reassemble ordered local certificates and replay the complete registered week on its original clock."""
    fixed = period.keys & reference
    requests = rolling_requests(period, design, caps, reference)
    if len(requests) != len(pairs) or len({label for label, _ in pairs}) != len(pairs):
        raise ValueError("Missing or repeated rolling-day certificate")
    statuses, details, intervals, schedule, states = [], [], [], [], []
    for req, (label, result) in zip(requests, pairs, strict=True):
        day = req.week.removeprefix("day:")
        stats = result["stats"]
        statuses.append(stats["status"])
        details.append(dict(date=day, id=label, status=stats["status"], fixed=list(req.fixed),
                            objective_lower=stats["objective_lower"], objective_upper=stats["objective_upper"]))
        if result["audit"] is None:
            continue
        if ss.eb.selected(result) != set(req.fixed) or any(row["date"] != day for row in result["schedule"]):
            raise ValueError("Rolling witness contains different duties or a different day")
        for r in result["states"]:
            ss.close(r["x"], ss.eb.DEFAULT_SPEC.boundary_kwh, (day, "realized incoming SOC"))
            ss.close(r["y"], ss.eb.DEFAULT_SPEC.boundary_kwh, (day, "locked outgoing SOC"))
        shift = period.offset[day]
        schedule.extend({**r, "start_min": shift + r["start_min"], "end_min": shift + r["end_min"],
                         "reservation_slot": shift // 15 + r["reservation_slot"]} for r in result["schedule"])
        states.extend(result["states"])
        ss.close(stats["objective_upper"], result["audit"]["purchase_eur"], (day, "native upper vs meter"))
        intervals.append((stats["objective_lower"], stats["objective_upper"], result["audit"]["purchase_eur"]))
    week = period.days[0]["week_start"]
    out = dict(week=week, design=design.label, caps_kw=list(caps), days=details,
               purchase_lower=None, purchase_upper=None, audit=None, schedule=schedule, states=states)
    if "infeasible" in statuses:
        return {**out, "status": "infeasible"}
    if len(intervals) != len(pairs):
        return {**out, "status": "unresolved"}
    upper = fsum(v for _, _, v in intervals)
    merged = dict(states=states, schedule=schedule, stats={"objective": upper})
    if ss.eb.selected(merged) != fixed:
        raise ValueError("Rolling week omits a registered vehicle-day")
    audit = ss.meter_replay(period, design.hardware(), ss.eb.DEFAULT_SPEC, caps, merged)
    out.update(audit=audit, purchase_upper=upper)
    if any(v is None or not isfinite(v) for v, _, _ in intervals):
        return {**out, "status": "unresolved"}
    lower = fsum(min(v, m) for v, _, m in intervals)
    # Sum widths locally, keeping the weekly acceptance threshold independent of
    # the magnitude (and sign) of spot prices and floating-point cancellation.
    width = fsum(max(0., u - v) for v, u, _ in intervals)
    status = "certified"
    if any(s not in ss.ENERGY_ACCEPTED for s in statuses):
        status = "unresolved"
    elif "bounded" in statuses:
        status = "bounded" if width <= CONTINUATION_TIMEOUT_GAP_EUR else "unresolved"
    return {**out, "status": status, "purchase_lower": lower, "absolute_gap": width}
