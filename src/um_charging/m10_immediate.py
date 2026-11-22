"""First-eligible immediate charging with independent segment-end and meter replay."""
from collections import defaultdict
from itertools import groupby
import math

from . import energy_boundary as eb
from . import fleet_changeover as fc
from .fleet_service import EPS, SITES, _events, subset_case


def _segments(period, registered):
    fixed = {key for key in registered if key[0] in period.offset}
    if not fixed <= period.keys:
        raise ValueError("Registered vehicle-day absent from this period")
    segments = [list(group) for chain in period.chains for keep, group in
                groupby(chain, key=fixed.__contains__) if keep]
    if {key for segment in segments for key in segment} != fixed:
        raise ValueError("Registered vehicle-day absent from the continuous service calendar")
    return segments


def _zero():
    return dict.fromkeys(SITES, 0.)


def _fits_soc(soc, spec):
    return spec.reserve_kwh - EPS <= soc <= spec.capacity_kwh + EPS


def _released(period, day, vehicle, site, minute, first):
    # The uncut dwell's initial release determines queue priority across midnight.
    # At a new registered segment the vehicle can enter no earlier than its start.
    starts = [a for (v, s, _), windows in period.windows.items() if (v, s) == (vehicle, site)
              for a, b in windows if a <= minute < b]
    if len(starts) != 1:
        raise ValueError(("Ambiguous released dwell", day, vehicle, site, minute))
    return max(starts[0], period.offset[first])


def _charge_interval(rows, day, site, start, end, ranked, hardware, reservations, levels, spec):
    # A connector used for any positive energy remains reserved through the quarter.
    # Power can be redistributed sooner, at an actual filling or departure event.
    quarter = math.floor(start / 15)
    held = reservations[site]
    other = {v for s, owners in reservations.items() if s != site for v in owners}
    now = start
    while now < end:
        remaining = hardware["power_kw"]
        powers = {}
        until = end
        # Existing reservations precede other arrivals, each group remains FIFO.
        for vehicle in sorted(ranked, key=lambda v: v not in held):
            room = spec.capacity_kwh - levels[vehicle]
            if room <= 1e-10 or vehicle in other or remaining <= 0:
                continue
            if vehicle not in held:
                free = next((p for p in range(1, hardware["interfaces"] + 1) if p not in held.values()), None)
                if free is None:
                    continue
                held[vehicle] = free
            power = min(spec.truck_kw, remaining)
            powers[vehicle] = power
            remaining -= power
            until = min(until, now + 60 * room / (spec.efficiency * power))
        if not powers:
            break
        if not until > now:
            raise ValueError("Immediate charging failed to advance its event clock")
        for vehicle, power in powers.items():
            rows.append(dict(date=day, vehicle_id=vehicle, site=site, plug=held[vehicle],
                             reservation_slot=quarter, start_min=now, end_min=until, power_kw=power))
            levels[vehicle] += spec.efficiency * power * (until - now) / 60
        now = until


def simulate_week(period, design, registered, *, spec=eb.DEFAULT_SPEC):
    """Execute the policy forward, then independently reconstruct its service and whole bill meters."""
    segments = _segments(period, registered)
    owners = {key: segment[0] for segment in segments for key in segment}
    hardware = design.hardware()
    levels, halted, failures, rows = {}, set(), {}, []
    for day, case in sorted(period.cases.items()):
        keys = sorted(key for key in owners if key[0] == day)
        if not keys:
            continue
        active = subset_case(case, [v for _, v in keys])
        releases = {}
        departures = defaultdict(list)
        arrivals = defaultdict(list)
        for key in keys:
            _, vehicle = key
            if owners[key] == key:
                levels[vehicle] = spec.boundary_kwh
            for a, b, energy, track in active["trucks"][vehicle]["trips"]:
                departures[a].append((vehicle, energy, track))
                arrivals[b].append((vehicle, energy))
            for a, b, site in active["trucks"][vehicle]["windows"]:
                release = _released(period, day, vehicle, site, period.offset[day] + a, owners[key][0])
                releases[vehicle, site, a, b] = release
        previous_quarter = None
        for a, b, available in _events(active):
            for vehicle, energy in arrivals[a]:
                if owners[day, vehicle] not in halted:
                    levels[vehicle] -= energy
            for vehicle, energy, track in departures[a]:
                owner = owners[day, vehicle]
                if owner not in halted and not _fits_soc(levels[vehicle] - energy, spec):
                    failures[day, vehicle] = track
                    halted.add(owner)
            start, end = period.offset[day] + a, period.offset[day] + b
            quarter = math.floor(start / 15)
            if quarter != previous_quarter:
                reservations = {site: {} for site in SITES}
                previous_quarter = quarter
            for site, available_vehicles in available.items():
                queue = []
                for vehicle in available_vehicles:
                    if owners[day, vehicle] in halted:
                        continue
                    arrival, = (r for (v, s, left, right), r in releases.items()
                                if (v, s) == (vehicle, site) and left <= a < b <= right)
                    queue.append((arrival, int(vehicle), vehicle))
                ranked = [v for _, _, v in sorted(queue)]
                _charge_interval(rows, day, site, start, end, ranked, hardware[site], reservations, levels, spec)
        # A trip ending at local midnight has no subsequent interval on this date.
        for vehicle, energy in arrivals[1440]:
            if owners[day, vehicle] not in halted:
                levels[vehicle] -= energy
    result = replay_week(period, design, registered, rows, spec=spec)
    replayed = {(r["date"], r["vehicle_id"]): r["failure"]["track_id"] for r in result["days"]
                if r["status"] == "trip_infeasible"}
    if failures != replayed:
        raise ValueError(("Independent replay disagrees on failed trips", failures, replayed))
    return result


def _meter_rows(period, design, fixed, rows, spec):
    """Rebuild simultaneous kW, quarter means and native-hour costs from positive energy rows."""
    hardware = design.hardware()
    by_day, by_site, vehicle_loads = defaultdict(list), defaultdict(lambda: defaultdict(float)), defaultdict(list)
    quarter_energy, quarter_vehicles = defaultdict(float), defaultdict(set)
    grid, expenses = defaultdict(_zero), defaultdict(_zero)
    for row in rows:
        day, v, site = row["date"], row["vehicle_id"], row["site"]
        key = day, v
        a, b, power, q, plug = (row[k] for k in ("start_min", "end_min", "power_kw", "reservation_slot", "plug"))
        if (key not in fixed or site not in SITES or type(plug) is not int or type(q) is not int
                or not 1 <= plug <= hardware[site]["interfaces"] or not all(math.isfinite(x) for x in (a, b, power))
                or not q * 15 <= a < b <= (q + 1) * 15 or not 0 < power <= spec.truck_kw + EPS):
            raise ValueError(("Invalid immediate meter row", row))
        offset = period.offset[day]
        if not any(s == site and offset + left <= a < b <= offset + right
                   for left, right, s in period.cases[day]["trucks"][v]["windows"]):
            raise ValueError(("Charge outside released window", row))
        by_day[key].append((a, b, power))
        vehicle_loads[v].append((a, b))
        by_site[site][a] += power
        by_site[site][b] -= power
        kwh = power * (b - a) / 60
        quarter_energy[site, q] += kwh
        quarter_vehicles[site, q].add(v)
        grid[key][site] += kwh
        # A complete quarter lies in exactly one of the source's native price hours.
        hour = math.floor((a-offset) / 60)
        expenses[key][site] += kwh * period.prices[day][hour] / 1000
    fc._reservations(rows)
    for vehicle, spans in vehicle_loads.items():
        spans.sort()
        if any(end > following for (_, end), (following, _) in zip(spans, spans[1:])):
            raise ValueError(("Vehicle charged twice simultaneously", vehicle))
    peaks = _zero()
    for site, changes in by_site.items():
        level = 0.
        for t, delta in sorted(changes.items()):
            level += delta
            peaks[site] = max(peaks[site], level)
            if level > hardware[site]["power_kw"] + EPS:
                raise ValueError(("Instantaneous site power", site, t, level))
    quarter_peaks = {s: 4 * max((x for (site, _), x in quarter_energy.items() if site == s), default=0.)
                     for s in SITES}
    if any(quarter_peaks[s] > cap + EPS for s, cap in zip(SITES, design.caps, strict=True)):
        raise ValueError("Immediate schedule exceeds the rated quarter limit")
    meters = {s: math.fsum(value[s] for value in grid.values()) for s in SITES}
    purchase = {s: math.fsum(value[s] for value in expenses.values()) for s in SITES}
    audit = dict(passed=True, site_grid_kwh=meters, site_purchase_eur_2021=purchase,
                 purchase_eur=math.fsum(purchase.values()), site_peak_kw=peaks, site_quarter_peak_kw=quarter_peaks,
                 used_plugs={s: max((len(v) for (site, _), v in quarter_vehicles.items() if site == s), default=0)
                             for s in SITES})
    return by_day, grid, expenses, audit


def _replay_day(period, key, charges, start, spec):
    day, vehicle = key
    # All trip and charge intervals are disjoint. At a shared boundary the
    # ending charge is credited before a departure, and a finished trip before a charge.
    events = [(a, b, "charge", p * (b-a) / 60, None) for a, b, p in charges]
    events.extend((period.offset[day] + a, period.offset[day] + b, "trip", energy, track)
                  for a, b, energy, track in period.cases[day]["trucks"][vehicle]["trips"])
    events.sort()
    level = start
    for a, b, kind, energy, track in events:
        if kind == "charge":
            level += energy * spec.efficiency
            if not _fits_soc(level, spec):
                raise ValueError(("Charge outside battery bounds", key, b, level))
        else:
            arrival = level - energy
            if not _fits_soc(arrival, spec):
                if any(end > a for _, end, _ in charges):
                    raise ValueError(("Charge after failed departure", key, track))
                return level, dict(track_id=track, departure_min=a, projected_arrival_soc_kwh=arrival)
            level = arrival
    return level, None


def replay_week(period, design, registered, schedule, *, spec=eb.DEFAULT_SPEC):
    """Audit the original metered schedule, including energy purchased before unsuccessful duties."""
    segments = _segments(period, registered)
    fixed = {key for segment in segments for key in segment}
    rows = list(schedule)
    by_day, grid, expenses, audit = _meter_rows(period, design, fixed, rows, spec)
    days, groups = [], []
    for segment in segments:
        first, vehicle = segment[0]
        last = segment[-1][0]
        level, failure = spec.boundary_kwh, None
        batch = []
        for key in segment:
            day, _ = key
            terminal = day == last
            start = None if failure else level
            observed = None
            if failure:
                if by_day[key]:
                    raise ValueError(("Charge on a blocked service day", key))
                status = "blocked_by_failed_trip"
            else:
                level, failure = _replay_day(period, key, by_day[key], level, spec)
                observed = level
                if failure:
                    status = "trip_infeasible"
                elif terminal and level < spec.boundary_kwh - EPS:
                    status = "terminal_shortfall"
                else:
                    status = "complete"
            actual_end = None if failure else level
            excess = (None if failure else max(0., level - spec.boundary_kwh)) if terminal else 0.
            batch.append(dict(date=day, vehicle_id=vehicle, segment_start=first, segment_end=last,
                is_segment_end=terminal, status=status, completed=status == "complete", start_soc_kwh=start,
                end_soc_kwh=actual_end, last_observed_soc_kwh=observed, failure=failure,
                site_grid_kwh=grid[key], site_purchase_eur_2021=expenses[key], terminal_excess_kwh=excess,
                terminal_excess_grid_kwh=None if excess is None else excess/spec.efficiency))
        end = batch[-1]
        groups.append(dict(vehicle_id=vehicle, segment_start=first, segment_end=last,
            status="trip_infeasible" if failure else end["status"], end_soc_kwh=end["end_soc_kwh"],
            terminal_excess_kwh=end["terminal_excess_kwh"], terminal_excess_grid_kwh=end["terminal_excess_grid_kwh"],
            site_grid_kwh={s: math.fsum(r["site_grid_kwh"][s] for r in batch) for s in SITES},
            site_purchase_eur_2021={s: math.fsum(r["site_purchase_eur_2021"][s] for r in batch) for s in SITES}))
        days.extend(batch)
    completed = sum(d["completed"] for d in days)
    missing = sum(g["end_soc_kwh"] is None for g in groups)
    known_battery = math.fsum(g["terminal_excess_kwh"] for g in groups if g["end_soc_kwh"] is not None)
    known_grid = math.fsum(g["terminal_excess_grid_kwh"] for g in groups if g["end_soc_kwh"] is not None)
    summary = dict(registered_vehicle_days=len(fixed), completed_vehicle_days=completed,
                   same_service=completed == len(fixed), unobserved_segments=missing,
                   terminal_excess_kwh=None if missing else known_battery,
                   terminal_excess_grid_kwh=None if missing else known_grid,
                   known_terminal_excess_kwh=known_battery, known_terminal_excess_grid_kwh=known_grid)
    return dict(week=period.days[0]["week_start"], design=design.label, caps_kw=list(design.caps), schedule=rows,
                days=sorted(days, key=lambda r: (r["date"], int(r["vehicle_id"]))), segments=groups,
                summary=summary, audit=audit)


_COST_FIELDS = ("terminal_excess_purchase_eur_2025", "terminal_excess_volumetric_eur_2025",
                "terminal_excess_cost_eur_2025")


def _allocate_segment(segment, purchase_factor, rates):
    observed = segment["terminal_excess_grid_kwh"]
    quantities = segment["site_grid_kwh"]
    metered = math.fsum(quantities.values())
    purchase = math.fsum(segment["site_purchase_eur_2021"].values()) * purchase_factor
    variable = math.fsum(quantities[s] * rates[s] for s in SITES)
    if metered:
        mean = (purchase + variable) / metered
    else:
        mean = None
    if observed is None:
        status, undistributed, regen = "terminal_unobserved", None, None
        portions = [None] * 3
    elif observed == 0:
        status, undistributed, regen = "zero_excess", 0., 0.
        portions = [0.] * 3
    elif not metered:
        status, undistributed, regen = "no_metered_purchase", observed, observed
        portions = [None] * 3
    else:
        # The registered valuation is G times the actual segment mean. Show net
        # regeneration beyond purchased energy separately, including when G > Q.
        regen = max(0., observed - metered)
        status = "weighted_mean_with_net_regeneration" if regen > EPS else "weighted_mean"
        undistributed = 0.
        portions = [observed * purchase / metered, observed * variable / metered, observed * mean]
    return dict(**segment, attribution_status=status, metered_grid_kwh=metered,
                segment_purchase_eur_2025=purchase, segment_volumetric_eur_2025=variable,
                weighted_mean_eur_2025_per_kwh=mean, unattributed_grid_kwh=undistributed,
                above_metered_grid_kwh=regen, **dict(zip(_COST_FIELDS, portions, strict=True)))


def _aggregate_costs(groups):
    # Unknown terminal states or unpriced regenerative surplus cannot become a
    # zero by aggregation. Preserve the observed subtotal for an incomplete run.
    result = {}
    for key in ("terminal_excess_kwh", "terminal_excess_grid_kwh", "unattributed_grid_kwh",
                "above_metered_grid_kwh", *_COST_FIELDS):
        known = math.fsum(row[key] for row in groups if row[key] is not None)
        result[key] = known if all(row[key] is not None for row in groups) else None
        result["known_" + key] = known
    result["unobserved_segments"] = sum(row["attribution_status"] == "terminal_unobserved" for row in groups)
    result["no_purchase_segments_with_excess"] = sum(row["attribution_status"] == "no_metered_purchase" for row in groups)
    return result


def surplus_costs(result, *, purchase_factor_to_2025, volumetric_rates_eur_2025_per_kwh):
    """Value segment-end surplus at its own metered weighted mean, in sample-period 2025 EUR.

    The caller settles the full year's site tariffs first and supplies the actual
    energy-only rates in 2025 EUR/kWh. No capacity, connection or capital fee enters
    this disclosure. Multiply sample energy and expense by 52/12 for annual figures.
    """
    rates = volumetric_rates_eur_2025_per_kwh
    if (set(rates) != set(SITES) or not all(math.isfinite(x) for x in rates.values())
            or not math.isfinite(purchase_factor_to_2025) or purchase_factor_to_2025 <= 0):
        raise ValueError("Both currency-normalized site rates and a positive purchase-price factor are required")
    segments = [_allocate_segment(segment, purchase_factor_to_2025, rates) for segment in result["segments"]]
    by_segment = {(s["vehicle_id"], s["segment_start"]): s for s in segments}
    days = []
    for row in result["days"]:
        segment = by_segment[row["vehicle_id"], row["segment_start"]]
        fields = (*_COST_FIELDS, "unattributed_grid_kwh", "above_metered_grid_kwh")
        fees = {k: segment[k] if row["is_segment_end"] else 0. for k in fields}
        days.append(dict(**row, **fees, attribution_status=segment["attribution_status"] if row["is_segment_end"]
                         else "not_segment_end"))
    vehicles = [dict(vehicle_id=v, **_aggregate_costs([s for s in segments if s["vehicle_id"] == v]))
                for v in sorted({s["vehicle_id"] for s in segments}, key=int)]
    return dict(days=days, segments=segments, vehicles=vehicles, summary=_aggregate_costs(segments))
