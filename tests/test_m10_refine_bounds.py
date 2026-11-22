from collections import defaultdict
from copy import deepcopy
from itertools import product
from types import SimpleNamespace

import pytest

from test_site_sizing import two_sites
from um_charging import site_sizing as ss
from um_charging.cabinet_tariff import annual_factors, settle
from um_charging.m10_costs import _parameters
from um_charging.m10_refine_bounds import BACKTEST_COLUMNS, PhysicalWindows, RefinementBounds, Scope, _meter_bounds
from um_charging.site_sizing_bounds import AnnualBillBounds


def test_window_delivery_distinguishes_instantaneous_from_quarter_cap():
    period = two_sites(4.5, port_minutes=6)
    date = period.days[0]["date"]
    period.days[0]["week_start"] = date
    windows = PhysicalWindows([period], period.keys)
    design = ss.Design(1, 50, 0)
    upper, floor, peaks, rejected = windows.envelopes(date, design, (20, 0), 5.)
    # Six minutes at 50 kW fit a 20 kW average over the full quarter.
    assert upper == pytest.approx((5, 0), abs=1e-6) and not rejected
    assert floor == pytest.approx((5, 0), abs=2e-6) and peaks == pytest.approx((20, 0), abs=5e-6)
    assert windows.envelopes(date, design, (15, 0), 5.)[-1]
    assert not windows.envelopes(date, design, (20, 0), 5. + ss.EPS / 2)[-1]


@pytest.mark.parametrize("fully_assigned", [False, True])
def test_physical_termination_of_energy_split_keeps_peaks_free_across_tariff_bands(fully_assigned):
    network = ss.load_network()
    network["annualization"] = dict(weeks_per_year=1, sample_weeks=1)
    network["full_load_hours_boundary"] = 2.
    scenarios = ("N0", *network["tariffs"], *network["capacity_sensitivities_eur_per_kw_year"])
    bounds = SimpleNamespace(network=network, scenarios=scenarios, annual_hours=(4.,4.), annual_kwh=1.,
                             weekly_kwh={"w": 1.})
    kwh = {"PORT": .5, "WAREHOUSE": .5}
    weekly = [dict(week="w", proof=None, site_kwh_floor=(.5, .5 if fully_assigned else .25),
                   site_peak_floor=(.125, .125))]
    result = _meter_bounds(bounds, (1,1), weekly)
    # All pairs are attainable in four hours. Exactly .25 kW is the
    # utilization tariff breakpoint and is assigned differently by the tariffs.
    for (p,w), scenario in product(product((.125,.25,.5,1.),repeat=2), scenarios):
        true = settle(network, 0., kwh, dict(PORT=p, WAREHOUSE=w), scenario)
        assert result[scenario] <= true["annual_total_eur_2025"]


def test_meter_donor_requires_identical_quarter_caps_and_wider_hardware():
    audit = object.__new__(RefinementBounds)
    small, large = ss.Design(1, 40, 20), ss.Design(1, 50, 30)
    caps = (20, 15)
    wide = Scope("w", large, caps, "wide")
    exact = Scope("w", small, caps, "exact")
    audit.at_caps = defaultdict(list, {("w",caps):[wide,exact], ("w",(30,15)):[Scope("w", small, (30,15),"other")]})
    audit._fits = lambda s, d: True
    assert audit._donor("w", small, caps) == exact
    audit.at_caps["w",caps] = [wide]
    assert audit._donor("w", small, caps) == wide
    assert audit._donor("w", large, (30,15)) is None
    assert audit._donor("w", small, (15,15)) is None
    audit._fits = lambda *_: False
    assert audit._donor("w", small, caps) is None


def _two_week_backtest():
    a = two_sites(13.5)
    b = deepcopy(a)
    a.days[0]["week_start"], b.days[0]["week_start"] = "week-1","week-2"
    # Same hand-computable operating task in two distinct sampling weeks.
    # Negative native price in an unoccupied hour must keep its sign in a blind fold.
    b.prices[b.days[0]["date"]][0] = -30.
    periods = [a,b]
    network, materials = _parameters(periods)
    data = object.__new__(RefinementBounds)
    data.by_week = {p.days[0]["week_start"]:p for p in periods}
    data.reference = a.keys
    data.bounds = AnnualBillBounds(periods, a.keys, network, materials)
    data.windows = PhysicalWindows(periods, a.keys)
    data.factor = annual_factors(network)[0]
    data.materials = materials
    d = ss.Design(1,50,50)
    data.builds = {d.label:d}
    data.week_rows = {(d.label,d.caps): {
        w: dict(point_status="certified",week=w,evidence_id="proof-"+w,purchase_lower=1.75,
                port_kwh=2.5,warehouse_kwh=12.5,port_peak_kw=10.,warehouse_peak_kw=50.) for w in data.by_week}}
    equip, _, connections = ss.annual_capital_costs(d, materials)
    data.invoices, data.incumbent = {}, {}
    for scenario in data.bounds.scenarios:
        bill = settle(network,3.5,dict(PORT=5.,WAREHOUSE=25.),dict(PORT=10.,WAREHOUSE=50.),scenario)
        for basis,cost in connections.items():
            net = equip + cost + bill["annual_total_eur_2025"]
            data.invoices[d.label,d.caps,scenario,basis] = net
            data.incumbent[scenario,basis] = net
    data._passed = False
    return data,d


def test_blind_backtest_hides_entire_week_and_locks_screen_on_first_failure():
    audit,d = _two_week_backtest()
    with pytest.raises(RuntimeError, match="backtest"):
        audit.screen()
    rows = list(audit.backtest())
    assert len(rows) == 24 and all(r["passed"] for r in rows) and audit._passed
    assert all(tuple(r) == BACKTEST_COLUMNS for r in rows)
    assert all(r["frozen_proof_ids"] == ["proof-week-2" if r["held_week"] == "week-1" else "proof-week-1"]
               for r in rows)
    holding_second = next(r for r in rows if r["held_week"] == "week-2")
    assert holding_second["purchase_lower_eur_2025"] == pytest.approx((1.75 - .45 - 2*ss.EPS)*audit.factor)
    key = d.label,d.caps,"N0","new"
    first = next(r for r in rows if (r["held_week"],r["scenario"],r["connection_basis"]) == ("week-1","N0","new"))
    audit.invoices[key] = first["annual_lower_eur_2025"] - 1e-9
    failed = list(audit.backtest())
    assert not failed[-1]["passed"] and failed[-1]["margin_eur_2025"] < 0 and not audit._passed
    with pytest.raises(RuntimeError, match="backtest"):
        audit.screen()
