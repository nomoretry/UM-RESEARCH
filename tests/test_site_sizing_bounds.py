from itertools import product
import math
from types import SimpleNamespace

import pytest

from um_charging import site_sizing as ss
from um_charging.cabinet_tariff import annual_repeats, load_network, settle
from um_charging.site_sizing_bounds import AnnualBillBounds, WholesaleRecord, network_lower_bound


@pytest.mark.parametrize("scenario", (
    "N0", "frank", "official", "capacity_0", "capacity_22_79", "capacity_208_38",
))
@pytest.mark.parametrize("caps", ((2, 2), (2, 0), (0, 2)))
def test_network_bound_under_all_enumerated_meter_traces(scenario, caps):
    network = load_network()
    network["full_load_hours_boundary"] = 2
    network["annualization"] = {"weeks_per_year": 4, "sample_weeks": 1}
    counts = (3, 3)
    repeats = annual_repeats(network)
    hours = [count * repeats / 4 for count in counts]
    meters = [
        sorted({(sum(trace) / 4, max(trace))
                for trace in product([k / 2 for k in range(2 * cap + 1)], repeat=count)})
        for cap, count in zip(caps, counts, strict=True)
    ]
    bounds = {}
    bands_checked = set()
    for trace in product(*meters):
        kwh = dict(zip(ss.SITES, (meter[0] for meter in trace), strict=True))
        peaks = dict(zip(ss.SITES, (meter[1] for meter in trace), strict=True))
        bill = settle(network, 0., kwh, peaks, scenario)
        total_kwh = sum(kwh.values()) * repeats
        if total_kwh not in bounds:
            bounds[total_kwh] = network_lower_bound(network, scenario, caps, hours, total_kwh)
        assert bounds[total_kwh] <= bill["annual_total_eur_2025"]
        bands_checked.update(row["band"] for row in bill["sites"].values() if row["peak_kw"])
    assert bands_checked == {"low", "high"}


def test_network_bound_detects_empty_relaxation_without_inventing_a_price():
    network = load_network()
    assert math.isinf(network_lower_bound(network, "official", (0, 2), (2, 3), 7))
    assert network_lower_bound(network, "official", (0, 0), (0, 0), 0) == 0


def test_wholesale_bound_filters_weeks_caps_hardware_and_all_held_out_aliases(monkeypatch):
    week = "2021-09-27"
    period = SimpleNamespace(
        days=[{"week_start": week}], keys={(week, "a")},
        cases={week: {"trucks": {"a": {"trips": [(0, 15, 9.)]}}}},
        prices={week: [-100., 50.]},
    )
    monkeypatch.setattr(ss.fc, "_physical_quarters", lambda *_: {})
    data = AnnualBillBounds([period], period.keys, load_network(), {})
    small = ss.Design(1, 20, 0)
    large = ss.Design(1, 30, 0)
    alias = ss.Design(1, 20, 50)
    caps = (20, 0)
    records = [
        WholesaleRecord("2021-10-04", small, caps, 12., "different week"),
        WholesaleRecord(week, ss.Design(1, 10, 0), (10, 0), 11., "smaller hardware"),
        WholesaleRecord(week, large, (10, 0), 10., "smaller cap"),
        WholesaleRecord(week, large, (22, 0), 1., "usable larger scope"),
        WholesaleRecord(week, alias, caps, 2., "held-out alias"),
        WholesaleRecord(week, small, caps, 3., "held-out exact scope"),
    ]
    assert data.annual_kwh == pytest.approx(10. * annual_repeats(data.network))
    assert data.weekly_lower_bound(week, small, caps, records).proof == "held-out exact scope"
    held_out = data.weekly_lower_bound(week, small, caps, records, exclude_scopes=[(small, caps)])
    assert held_out.proof == "usable larger scope"
    assert held_out.lower_eur <= 1.
    fallback = data.weekly_lower_bound(week, large, large.caps, records)
    assert fallback.proof is None
    assert fallback.lower_eur == pytest.approx(-1., abs=2e-6)
