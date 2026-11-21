import copy
from datetime import date, timedelta

import pytest

from um_charging import holdout_bills as hb
from um_charging.holdout_report import render
from um_charging import site_sizing as ss


WEEKS = [(date(2021, 11, 8) + timedelta(weeks=i)).isoformat() for i in range(6)]
PORT20, PORT40, BASE = hb.FIXED
POINTS = [(d, d.caps) for d in hb.FIXED] + [(BASE, (50, 0)), (BASE, (20, 0))]


def week(purchase=10., gap=0., *, timeout=False):
    return dict(stats=dict(status="unresolved" if timeout else "certified",
                           status_code=1 if timeout else 0,
                           message="Time limit reached" if timeout else "Optimal",
                           objective_lower=purchase - gap, objective_upper=purchase,
                           relative_gap=gap / purchase),
                audit=dict(passed=True, site_grid_kwh={"PORT": 100., "WAREHOUSE": 0.},
                           site_quarter_peak_kw={"PORT": 15., "WAREHOUSE": 0.},
                           purchase_eur=purchase))


def inputs():
    return ({(d.label, caps): {w: week() for w in WEEKS} for d, caps in POINTS},
            {d.label: "matched" for d in hb.FIXED})


def cases(runs, service):
    result = hb.annual_bills(WEEKS, runs, service, annual_grid_kwh=5200.)
    return {(r["scenario"], r["connection_basis"]): r for r in result["cases"]}


def test_fixed_caps_asset_basis_and_audited_timeout():
    runs, service = inputs()
    runs[PORT20.label, PORT20.caps][WEEKS[0]] = week(gap=.05, timeout=True)
    rows = cases(runs, service)
    assert len(rows) == 12
    expected = {"N0": [50, 50], "official": [50, 0], "frank": [50, 0],
                "capacity_0": [20, 0], "capacity_22_79": [20, 0], "capacity_208_38": [20, 0]}
    network = ss.load_network()
    material = ss._load_costs(ss.CONNECTION_INPUT, network)
    for (scenario, basis), row in rows.items():
        base = row["bills"][BASE.label]
        assert base["caps_kw"] == expected[scenario]
        parts = base["components_eur"]
        assert parts["chargers"] == 2 * material["annual_charger_eur_2025_by_kw"][50]
        assert parts["connection"] == (175 if basis == "new" else 0) * material["annual_bkz_eur_2025_per_kw"]
        small = row["bills"][PORT20.label]
        lo, hi = small["annual_total_eur_bounds"]
        assert hi == pytest.approx(sum(small["components_eur"].values()))
        assert hi - lo == pytest.approx(.05 * hb.annual_factors(network)[0])
        assert small["status"] == "bounded" and row["winner"] == PORT20.label
    assert rows["N0", "new"]["recommendation_status"] == "changed"
    assert rows["frank", "existing"]["recommendation_status"] == "unchanged"


def test_fallback_requires_proven_failure_uses_full_six_weeks():
    runs, service = inputs()
    for w in WEEKS:
        runs[BASE.label, (50, 0)][w] = week(1.)
        runs[BASE.label, BASE.caps][w] = week(11.)
    runs[BASE.label, (50, 0)][WEEKS[0]] = dict(stats=dict(status="infeasible", status_code=2), audit=None)
    runs[BASE.label, (20, 0)][WEEKS[-1]] = week(gap=.05001, timeout=True)
    rows = cases(runs, service)
    base = rows["official", "new"]["bills"][BASE.label]
    assert (base["policy"], base["caps_kw"], base["frozen_caps_kw"]) == ("rated_fallback", [50, 50], [50, 0])
    assert base["purchase_eur_2021_bounds"] == [66., 66.]
    unresolved = rows["capacity_0", "new"]
    row = unresolved["bills"][BASE.label]
    assert row["status"] == "unresolved" and "annual_total_eur" not in row
    assert row["rated_comparator"]["purchase_eur_2021_bounds"] == [66., 66.]
    assert unresolved["winner"] is None and unresolved["recommendation_status"] == "unresolved"


def test_service_gap_has_no_bill_and_unverified_baseline_blocks_comparisons():
    runs, service = inputs()
    service[PORT20.label] = "service_gap"
    del runs[BASE.label, BASE.caps][WEEKS[-1]]
    rows = cases(runs, service)
    for row in rows.values():
        assert row["winner"] is None
        assert "annual_total_eur" not in row["bills"][PORT20.label]
        assert row["recommendation_status"] == (
            "changed" if row["m8_winner"] == PORT20.label else "unresolved")


def test_audit_and_registered_energy_checked():
    runs, service = inputs()
    broken = copy.deepcopy(runs)
    broken[PORT40.label, PORT40.caps][WEEKS[-1]]["audit"]["passed"] = False
    with pytest.raises(ValueError, match="independent replay"):
        cases(broken, service)
    with pytest.raises(ValueError, match="annual grid kWh"):
        hb.annual_bills(WEEKS, runs, service, annual_grid_kwh=5100.)


def test_overlapping_intervals_prevent_winner_and_recommendation():
    bills = {PORT20.label: {"status": "bounded", "annual_total_eur_bounds": [10., 10.1]},
             PORT40.label: {"status": "bounded", "annual_total_eur_bounds": [10.08, 10.2]},
             BASE.label: {"status": "certified", "annual_total_eur_bounds": [99., 99.]}}
    ranking = hb._ranking(bills, PORT20.label, rated_verified=True)
    assert ranking["winner"] is None and ranking["recommendation_status"] == "unresolved"
    assert ranking["rank_bounds"] == {PORT20.label: [1, 2], PORT40.label: [1, 2], BASE.label: [3, 3]}


def test_bilingual_report_uses_cost_intervals_and_survives_partial_archive():
    runs, service = inputs()
    empty = {d.label: [] for d in hb.FIXED}
    partial = dict(source_commit="test-source", formal_seconds=12.3, solve_count=7,
                   main=None, billing=None, repairs=None, sensitivity=dict(status="wall_limit"))
    assert "7." in render(partial) and "wall-clock limit" in render(partial)
    partial["main"] = dict(weekly=[dict(registered=1, eligible=1)],
                           daily=[dict(date=WEEKS[0], eligible=["5"], registered=["5"],
                                       facilities={d.label: ["5"] for d in hb.FIXED})],
                           service_status=service, missing=empty, added=empty)
    assert "? kWh/年" in render(partial)
    partial["main"].update(annual_grid_kwh=5200., m8_annual_grid_kwh=58387.79)
    partial["billing"] = hb.annual_bills(WEEKS, runs, service, annual_grid_kwh=5200.)
    partial["sensitivity"] = dict(status="complete", service_status=service, missing=empty,
                                  registration_lost=[], registration_gained=[])
    result = render(partial)
    assert result.count("新建 / New") == 6 and result.count("既有 / Existing") == 6
    assert f"| {WEEKS[0]} | 5 | 5 | 5 | 5 |" in result and "5,200.00 kWh/年" in result
    assert "--verify (Join-Path $archive 'formal')" in result
