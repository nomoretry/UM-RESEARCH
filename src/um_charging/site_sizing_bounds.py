"""Lower bounds for screened operating caps in the matched-service study."""

from dataclasses import dataclass
from itertools import product
import math

from . import site_sizing as ss
from .cabinet_tariff import annual_factors, annual_repeats, network_rates


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


class AnnualBillBounds:
    """Precompute energy conservation and quarter availability for fixed duties."""

    def __init__(self, periods, reference, network, materials):
        self.network = network
        self.materials = materials
        self.scenarios = ("N0", *network["tariffs"], *network["capacity_sensitivities_eur_per_kw_year"])
        self.weeks = tuple(period.days[0]["week_start"] for period in periods)
        self.weekly_floor = {}
        grid_kwh = []
        quarters = dict.fromkeys(ss.SITES, 0)
        for week, period in zip(self.weeks, periods, strict=True):
            active = reference & period.keys
            # Every selected spell starts and ends at the same battery energy.
            # Summing its state balances fixes the required grid energy.
            energy = math.fsum(trip[2] for day, truck in sorted(active)
                               for trip in period.cases[day]["trucks"][truck]["trips"])
            energy /= ss.eb.DEFAULT_SPEC.efficiency
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
