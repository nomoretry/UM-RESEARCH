from itertools import product

import pytest

from um_charging import site_sizing as ss
from um_charging.cabinet_tariff import annual_repeats, load_network, settle
from um_charging.site_sizing_bounds import (
    AnnualBillBounds, known_peak_network_lower_bound, network_lower_bound,
)


def small_network():
    network = load_network()
    network["annualization"] = {"weeks_per_year": 1, "sample_weeks": 1}
    network["full_load_hours_boundary"] = 2.
    network["price_level"]["cpi"] = dict.fromkeys(("2021", "2024", "2025"), 100.)
    return network


@pytest.mark.parametrize("scenario", (
    "N0", "frank", "official", "capacity_0", "capacity_22_79", "capacity_208_38",
))
def test_known_meter_bound_against_every_enumerated_completion(scenario):
    network = small_network()
    network["annualization"]["weeks_per_year"] = 4
    caps, hours = (2., 2.), (3., 3.)
    peaks = (.5, 1.)
    known = tuple(peak / 4 for peak in peaks)
    repeat = annual_repeats(network)
    bounds = {}
    seen = set()
    for p1, p2, w1, w2 in product((0., 1., 2.), repeat=4):
        unknown = (p1 + p2 + w1 + w2) / 4
        if unknown not in bounds:
            old = network_lower_bound(network, scenario, caps, hours, (sum(known) + unknown) * repeat)
            new = known_peak_network_lower_bound(network, scenario, caps, hours, known, peaks, unknown, old)
            assert new >= old
            bounds[unknown] = new
        energy = {ss.PORT: known[0] + (p1 + p2) / 4, ss.WAREHOUSE: known[1] + (w1 + w2) / 4}
        peak = {ss.PORT: max(peaks[0], p1, p2), ss.WAREHOUSE: max(peaks[1], w1, w2)}
        actual = settle(network, 0., energy, peak, scenario)
        assert bounds[unknown] <= actual["annual_total_eur_2025"]
        seen.update(site["band"] for site in actual["sites"].values())
    assert seen == {"low", "high"}


@pytest.mark.parametrize(("scenario", "expected"), (("frank", .85), ("official", .4)))
def test_singleton_split_at_two_simultaneous_tariff_boundaries(scenario, expected):
    network = small_network()
    bands = network["tariffs"][scenario]["bands"]
    for band, rate in (("low", 1.), ("high", .1)):
        bands[band].update(capacity_eur_per_kw_year=0., energy_eur_per_kwh=rate)
    # Each peak is fixed at 1 kW. Exactly two kWh at each meter is the
    # sole allocation putting both in the official high band. Under Frank
    # at most one can be high, with at most 3.5 kWh at that meter.
    value = known_peak_network_lower_bound(network, scenario, (1, 1), (8, 8), (.5, .5), (1, 1), 3., 0.)
    assert value == pytest.approx(expected, abs=1.01 * ss.EPS)


@pytest.mark.parametrize("scenario", ("frank", "official"))
def test_interior_peak_at_tariff_boundary_and_its_one_sided_limit(scenario):
    network = small_network()
    bands = network["tariffs"][scenario]["bands"]
    bands["low"].update(capacity_eur_per_kw_year=7., energy_eur_per_kwh=0.)
    bands["high"].update(capacity_eur_per_kw_year=0., energy_eur_per_kwh=100.)
    # The cheapest low-band charge is 7 EUR at 1 kW under Frank, or
    # arbitrarily close above 1 kW under the official boundary rule.
    value = known_peak_network_lower_bound(network, scenario, (2, 0), (6, 0), (.5, 0), (.5, 0), 1.5, 0.)
    assert value == pytest.approx(7., abs=1.01 * ss.EPS)


def test_fully_known_and_absent_meter_evidence():
    network = small_network()
    bounds = AnnualBillBounds([], set(), network, {})
    bounds.weeks = ("one", "two")
    bounds.weekly_kwh = {"one": 1., "two": 1.}
    bounds.annual_kwh = 2.
    bounds.annual_hours = (6., 0.)
    audit = {"site_grid_kwh": {ss.PORT: 1., ss.WAREHOUSE: 0.},
             "site_quarter_peak_kw": {ss.PORT: 1., ss.WAREHOUSE: 0.}}
    relaxed = bounds.network_with_known_peaks((2, 0), {})
    both = bounds.network_with_known_peaks((2, 0), {"one": audit, "two": audit})
    for scenario in bounds.scenarios:
        assert relaxed[scenario] == network_lower_bound(network, scenario, (2, 0), (6, 0), 2.)
        exact = settle(network, 0., {ss.PORT: 2., ss.WAREHOUSE: 0.}, audit["site_quarter_peak_kw"], scenario)
        assert both[scenario] == pytest.approx(exact["annual_total_eur_2025"], abs=1.01 * ss.EPS)
    with pytest.raises(ValueError, match="outside the settlement"):
        bounds.network_with_known_peaks((2, 0), {"other": audit})
