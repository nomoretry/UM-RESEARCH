"""Lower bounds for screened operating caps in the matched-service study."""

from dataclasses import dataclass
from itertools import product
import math

from . import site_sizing as ss
from .cabinet_tariff import annual_factors, annual_repeats, network_rates, settle


@dataclass(frozen=True)
class WholesaleRecord:
    week: str
    design: ss.Design
    caps: tuple[int, int]
    lower_eur: float
    proof: str | None


def network_lower_bound(network, scenario, caps, annual_hours, annual_kwh):
    """Lower-bound annual capacity plus network energy charges in 2025 euros.

    If a meter can fill at most H quarter-equivalent hours, its peak is at
    least its annual energy divided by H. Its tariff band can further limit H.
    Relax the charge allocation to arbitrary nonnegative energy at each meter
    within these bounds. For any fixed pair of bands the cost is linear in
    port energy, so one end of the feasible energy split minimizes it.
    """
    if scenario not in ("N0", *network["tariffs"], *network["capacity_sensitivities_eur_per_kw_year"]):
        raise ValueError(f"Unknown network settlement scenario: {scenario}")
    boundary = network["full_load_hours_boundary"]
    choices = []
    for cap, hours in zip(caps, annual_hours, strict=True):
        # An idle meter requires no occupied intervals and incurs no charges.
        bands = [(0., 0.)]
        if cap > 0 and hours > 0:
            for band, upper_hours in (("low", min(hours, boundary)), ("high", hours)):
                # Allow both bands at the breakpoint, regardless of which the
                # exact settlement assigns there. This only enlarges the set.
                if band == "high" and hours < boundary:
                    continue
                capacity_rate, energy_rate = network_rates(network, scenario, band)
                if min(capacity_rate, energy_rate) < 0:
                    raise ValueError("The network bound requires nonnegative tariff rates")
                unit = energy_rate + capacity_rate / upper_hours
                bands.append(((cap + ss.EPS) * upper_hours, unit))
        choices.append(bands)

    best = math.inf
    # Give the energy balance and quarter limits the replay tolerance in the
    # conservative direction. Never use a roundoff difference to screen a point.
    total = max(0., annual_kwh - ss.EPS)
    for (port_size, port_unit), (warehouse_size, warehouse_unit) in product(*choices):
        lo = max(0., total - warehouse_size)
        hi = min(total, port_size)
        if lo > hi:
            continue
        port_kwh = hi if port_unit < warehouse_unit else lo
        minimum = math.fsum((port_kwh * port_unit, (total - port_kwh) * warehouse_unit))
        best = min(best, minimum)
    _, network_factor = annual_factors(network)
    return max(0., best * network_factor - ss.EPS)


def _meter_end_costs(network, scenario, site, energies, known_peak, cap, hours):
    """Infimum of one meter's settled charge at both ends of an energy cell.

    The middle reading selects the attainable bands on the open cell (or at
    a singleton). Inside each band the two components returned by settle()
    are linear in peak and kWh respectively. Extend those settled components
    to the ends to include one-sided limits without changing the tariff's
    equality convention. Nonnegative capacity prices make the lowest
    admissible peak optimal within each band.
    """
    left, middle, right = energies
    if middle == 0:
        return (0., 0.) if known_peak == 0 else (math.inf, math.inf)
    repeat = annual_repeats(network)
    boundary = network["full_load_hours_boundary"]

    def peak_floor(energy):
        return min(cap, max(known_peak, energy * repeat / hours))

    floor = peak_floor(middle)
    split = middle * repeat / boundary
    costs = [math.inf, math.inf]
    zero = dict.fromkeys(ss.SITES, 0.)
    for band, lower, upper in (("low", max(floor, split), cap),
                               ("high", floor, min(split, cap))):
        if lower > upper:
            continue
        probe = (lower + upper) / 2
        bill = settle(network, 0., {**zero, site: middle}, {**zero, site: probe}, scenario)
        if bill["sites"][site]["band"] != band:
            # A singleton at the breakpoint belongs to exactly one actual band.
            continue
        for i, energy in enumerate((left, right)):
            peak = peak_floor(energy)
            if band == "low":
                peak = max(peak, energy * repeat / boundary)
            cost = math.fsum((bill["annual_capacity_eur_2025"] * (peak / probe),
                              bill["annual_network_energy_eur_2025"] * (energy / middle)))
            costs[i] = min(costs[i], cost)
    return costs


def known_peak_network_lower_bound(network, scenario, caps, annual_hours, known_kwh,
                                   known_peaks, unassigned_kwh, relaxed_eur):
    """Tighten a relaxed tariff bill with fixed six-week meter contributions.

    known_kwh contains audited sample energy (before annualization). One
    variable allocates the remaining sample energy to the port. Between
    consecutive breakpoints the feasible tariff bands are constant and their
    least admissible peaks are affine in the allocation. Each band's charge
    is then affine, so its infimum is at a cell end. Check singletons as well
    as both limits of open cells to honor the two tariffs' distinct ties.
    """
    if any(p > cap + ss.EPS for p, cap in zip(known_peaks, caps, strict=True)):
        raise ValueError("An audited quarter peak exceeds its operating cap")
    if unassigned_kwh == 0:
        bill = settle(network, 0., dict(zip(ss.SITES, known_kwh, strict=True)),
                      dict(zip(ss.SITES, known_peaks, strict=True)), scenario)
        return max(relaxed_eur, bill["annual_total_eur_2025"] - ss.EPS)

    repeat = annual_repeats(network)
    boundary = network["full_load_hours_boundary"]
    # Keep equality at a contracted cap: extending an exact breakpoint by
    # EPS could open a different tariff band. An already observed, audited
    # peak that exceeds the cap by numerical roundoff must still fit.
    upper = tuple(max(cap, peak) for cap, peak in zip(caps, known_peaks, strict=True))
    room = [cap * hours / repeat - energy
            for cap, hours, energy in zip(upper, annual_hours, known_kwh, strict=True)]
    lo = max(0., unassigned_kwh - room[1])
    hi = min(unassigned_kwh, room[0])
    if lo > hi:
        return math.inf

    cuts = {lo, hi}
    for i, (peak, cap, hours, fixed) in enumerate(zip(known_peaks, upper, annual_hours, known_kwh, strict=True)):
        # Switches of max(known peak, energy / hours) and of the band's
        # intersection with that floor or the cap.
        for annual_energy in (peak * hours, peak * boundary, cap * boundary):
            assigned = annual_energy / repeat - fixed
            port_assigned = assigned if i == 0 else unassigned_kwh - assigned
            if lo < port_assigned < hi:
                cuts.add(port_assigned)
    cuts = sorted(cuts)
    cells = [(x, x) for x in cuts] + list(zip(cuts, cuts[1:]))
    best = math.inf
    for left, right in cells:
        split = (left, (left + right) / 2, right)
        port = tuple(known_kwh[0] + x for x in split)
        warehouse = tuple(known_kwh[1] + (unassigned_kwh - x) for x in split)
        p = _meter_end_costs(network, scenario, ss.PORT, port, known_peaks[0], upper[0], annual_hours[0])
        w = _meter_end_costs(network, scenario, ss.WAREHOUSE, warehouse, known_peaks[1], upper[1], annual_hours[1])
        best = min(best, p[0] + w[0], p[1] + w[1])
    return max(relaxed_eur, best - ss.EPS)


class AnnualBillBounds:
    """Precompute energy conservation and quarter availability for fixed duties."""

    def __init__(self, periods, reference, network, materials):
        self.network = network
        self.materials = materials
        self.scenarios = ("N0", *network["tariffs"], *network["capacity_sensitivities_eur_per_kw_year"])
        self.weeks = tuple(period.days[0]["week_start"] for period in periods)
        self.weekly_floor = {}
        self.weekly_kwh = {}
        grid_kwh = []
        quarters = dict.fromkeys(ss.SITES, 0)
        for week, period in zip(self.weeks, periods, strict=True):
            active = reference & period.keys
            # Every selected spell starts and ends at the same battery energy.
            # Summing its state balances fixes the required grid energy.
            energy = math.fsum(trip[2] for day, truck in sorted(active)
                               for trip in period.cases[day]["trucks"][truck]["trips"])
            energy /= ss.eb.DEFAULT_SPEC.efficiency
            self.weekly_kwh[week] = energy
            grid_kwh.append(energy)
            # Independent fallback when a holdout has no dominating archive
            # proof. Charging every kWh at the cheapest native hour is a bound,
            # including when that price is negative.
            cheapest = min((price for day in period.cases for price in period.prices[day]), default=0.)
            self.weekly_floor[week] = cheapest * energy / 1000
            for intervals in ss.fc._physical_quarters(period, active).values():
                for site in ss.SITES:
                    quarters[site] += any(available[site] for _, _, _, available in intervals)

        repeats = annual_repeats(network)
        self.annual_kwh = math.fsum(grid_kwh) * repeats
        self.annual_hours = tuple(quarters[site] * repeats / 4 for site in ss.SITES)

    def network_with_known_peaks(self, caps, accepted_audits):
        """Bound all six annual tariffs using only accepted, replayed schedules."""
        if set(accepted_audits) - set(self.weeks):
            raise ValueError("An accepted audit is outside the settlement weeks")
        costs = {case: network_lower_bound(self.network, case, caps, self.annual_hours, self.annual_kwh)
                 for case in self.scenarios}
        if not accepted_audits:
            return costs
        audits = accepted_audits.values()
        known_kwh = tuple(math.fsum(row["site_grid_kwh"][site] for row in audits) for site in ss.SITES)
        known_peaks = tuple(max(row["site_quarter_peak_kw"][site] for row in audits) for site in ss.SITES)
        unassigned = math.fsum(self.weekly_kwh[week] for week in self.weeks if week not in accepted_audits)
        return {case: known_peak_network_lower_bound(self.network, case, caps, self.annual_hours,
                                                     known_kwh, known_peaks, unassigned, old)
                for case, old in costs.items()}

    def weekly_lower_bound(self, week, design, caps, records, *, exclude_scopes=()):
        """Use the strongest finite lower bound from a dominating archived solve."""
        caps = tuple(caps)
        target = ss._active_build(design, caps)
        excluded = {(ss._active_build(established, limits), tuple(limits))
                    for established, limits in exclude_scopes}
        proofs = []
        for record in records:
            if record.week != week or record.lower_eur is None or not math.isfinite(record.lower_eur):
                continue
            limits = tuple(record.caps)
            hardware = ss._active_build(record.design, limits)
            if (hardware, limits) in excluded:
                continue
            if ss._dominates(hardware, target) and all(hi >= lo for hi, lo in zip(limits, caps, strict=True)):
                proofs.append(record)
        if proofs:
            record = max(proofs, key=lambda proof: proof.lower_eur)
            return WholesaleRecord(week, record.design, tuple(record.caps), record.lower_eur - ss.EPS, record.proof)
        return WholesaleRecord(week, target, caps, self.weekly_floor[week] - ss.EPS, None)

    def annual_lower_bounds(self, design, caps, records_by_week, *, exclude_scopes=()):
        """Return conservative costs in both connection bases for each tariff."""
        exclusions = tuple(exclude_scopes)
        weekly = {week: self.weekly_lower_bound(week, design, caps, records_by_week.get(week, ()),
                                                exclude_scopes=exclusions)
                  for week in self.weeks}
        wholesale_factor, _ = annual_factors(self.network)
        purchase = math.fsum(proof.lower_eur for proof in weekly.values()) * wholesale_factor
        network_costs = {case: network_lower_bound(self.network, case, caps, self.annual_hours, self.annual_kwh)
                         for case in self.scenarios}
        equipment, _, connection = ss.annual_capital_costs(design, self.materials)
        totals = {case: {basis: math.fsum((purchase, cost, equipment, investment))
                         for basis, investment in connection.items()}
                  for case, cost in network_costs.items()}
        return dict(weekly=weekly, purchase_eur=purchase, network_eur=network_costs,
                    equipment_eur=equipment, connection_eur=connection, total_eur=totals)
