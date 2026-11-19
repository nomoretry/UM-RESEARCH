from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from um_charging import energy_boundary as eb
from um_charging import fleet_changeover as fc
from um_charging.site_sizing import Design, best_dispatch, meter_replay, solve


def two_sites(energy_kwh=13.5, port_minutes=15):
    origin = datetime(2021, 1, 4, tzinfo=timezone.utc)

    def time(minute):
        return (origin + timedelta(minutes=minute)).isoformat()

    day = dict(
        date=time(0)[:10], start=time(0), end=time(1440), availability="complete_tasks",
        vehicles=[dict(
            vehicle_id="a", unmapped_gaps=[],
            trips=[
                dict(start=time(0), end=time(15), energy_kwh=energy_kwh, track_id="a0"),
                dict(start=time(75), end=time(120), energy_kwh=0., track_id="a1"),
            ],
            stops=[
                dict(site="WAREHOUSE", start=time(15), end=time(75), arrival=time(15),
                     next_departure=time(75), arrival_track_id="a0", next_track_id="a1"),
                dict(site="PORT", start=time(120), end=time(120 + port_minutes), arrival=time(120),
                     next_departure=time(120 + port_minutes), arrival_track_id="a1", next_track_id="a2"),
            ])])
    return eb.Period([day], {day["date"]: [0., 100., 200.] + [0.] * 21})


def test_hand_calculated_minimum_power_and_monotonicity():
    # 13.5 / .9 = 15 kWh across two usable 15-minute windows.
    p = two_sites()
    counts = [solve(p, Design(1, kw, 30), prefer=p.keys)["stats"]["completed_bounds"]
              for kw in (20, 30, 40)]
    assert counts == [[0, 0], [1, 1], [1, 1]]
    bills = [solve(p, Design(1, 30, kw), fixed=p.keys)["audit"]["purchase_eur"] for kw in (30, 40, 50)]
    assert bills == pytest.approx([2.25, 2., 1.75])


def test_zero_draw_even_when_a_charger_is_installed():
    p = two_sites(9)
    design = Design(1, 50, 50)
    result = solve(p, design, caps=(50, 0), fixed=p.keys)
    assert result["audit"]["site_grid_kwh"] == pytest.approx(dict(PORT=10, WAREHOUSE=0))
    assert result["audit"]["purchase_eur"] == pytest.approx(2)
    assert solve(p, Design(0, 0, 0))["stats"]["completed_bounds"] == [0, 0]
    assert solve(p, Design(0, 0, 50), fixed=p.keys)["audit"]["site_grid_kwh"]["PORT"] == 0


def test_meter_cap_is_a_quarter_average_at_both_changeover_delays():
    p = two_sites(4.5, port_minutes=6)
    design = Design(1, 50, 0)
    caps = (20, 0)
    result = solve(p, design, caps=caps, fixed=p.keys)
    assert result["audit"]["site_peak_kw"]["PORT"] == pytest.approx(50)
    assert result["audit"]["site_quarter_peak_kw"]["PORT"] == pytest.approx(20)
    assert solve(p, Design(1, 20, 0), caps=caps, fixed=p.keys)["stats"]["status"] == "infeasible"
    delayed = fc.solve(p, design.hardware(), eb.DEFAULT_SPEC, 5, p.keys,
                       peak_limits=dict(PORT=20, WAREHOUSE=0))
    assert meter_replay(p, design.hardware(), eb.DEFAULT_SPEC, caps, delayed, delay=5)[
        "site_quarter_peak_kw"]["PORT"] == pytest.approx(20)

    forged = deepcopy(result)
    with pytest.raises(ValueError, match="quarter peak cap"):
        meter_replay(p, design.hardware(), eb.DEFAULT_SPEC, (19, 0), forged)


def test_min_over_eligible_runtime_peaks_uses_the_whole_invoice():
    design = Design(1, 50, 30)

    def row(caps, purchase, grid):
        return dict(caps_kw=caps, bills={"official": {"annual_total_eur_2025": purchase + grid}})

    a = row((50, 30), 5, 7)
    b = row((40, 10), 7, 2)
    outside = row((40, 50), 2, 1)
    assert best_dispatch([a, b, outside], design, "official") is b
