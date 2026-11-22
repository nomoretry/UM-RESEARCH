from dataclasses import replace
from types import SimpleNamespace

import pytest

from um_charging import m10_warehouse_price as prices


def _option(p, low, high):
    return dict(port_cap_kw=p, warehouse_cap_kw=15, known_lower=low, known_upper=high)


def _old(p, cap, low, high):
    return dict(design=f"p1-{p}-w20", port_cap_kw=str(cap), warehouse_cap_kw="20",
                scenario="official", connection_basis="new",
                status="bounded" if high is not None else "unresolved" if low is not None else "infeasible",
                total_lower="" if low is None else str(low), total_upper="" if high is None else str(high))


def test_unquoted_warehouse_prices_compare_with_their_own_rated_port_and_handle_incomplete_points():
    cases = [dict(scenario="official", connection_basis="new")]
    comps = {(f"p1-{p}-w20", "official", "new"):
             dict(total_lower=low, total_upper=high, caps_kw=[p, 20]) for p,low,high in [(20, 100., 110.),(40, 200.,202.)]}
    old = [_old(20, 20, 100., 110.), _old(20, 10, 112., 114.), _old(40, 40, 201., 202.),
           _old(40, 20, 200., None)]
    choices = {("p1-20-w15", "official", "new"):[_option(20, 75., 80.), _option(10, 78., 81.)],
               ("p1-40-w15", "official", "new"):[_option(40, 170., 172.)]}
    statuses = [dict(design="p1-20-w15", status="settled"), dict(design="p1-40-w15", status="settled"),
                dict(design="p1-40-w15", status="unresolved")]
    a,b = prices._threshold_rows(cases, comps, old, statuses, choices, .2)
    assert a["status"] == "settled" and a["comparison_design"] == "p1-20-w20"
    assert a["net_equipment_lower_eur_2026"] == 100. and a["net_equipment_upper_eur_2026"] == 175.
    assert a["feasible_minimum_points"] == [[20, 15], [10, 15]]
    assert b["status"] == "unresolved" and b["comparison_design"] == "p1-40-w20"
    assert b["comparison_unresolved_caps"] == [[20, 20]] and b["comparison_caps"] == [40, 20]
    assert b["annual_allowance_lower_eur_2025"] == 28 and b["annual_allowance_upper_eur_2025"] is None
    comps["p1-40-w20","official","new"] = dict(total_lower=200., total_upper=None, caps_kw=None)
    old[2] = _old(40, 40, None, None)
    _, b = prices._threshold_rows(cases, comps, old, statuses, choices, .2)
    assert b["comparison_status"] == b["status"] == "unresolved" and b["net_equipment_lower_eur_2026"] is None
    assert prices._comparison(None, [_old(40, 40, None, None)])["comparison_status"] == "infeasible"


def test_only_physical_refinement_exclusions_remove_15kw_grid_point():
    for reason in ("infeasible_superset", "weekly_window_capacity", "infeasible_network_relaxation"):
        proof = dict(week="w", id="proof")
        assert prices._physical_exclusion(dict(reason=reason, exclusion=proof)) == proof
    with pytest.raises(ValueError, match="economic screen"):
        prices._physical_exclusion(dict(reason="priced_above_all_incumbents", exclusion={}))
    with pytest.raises(ValueError, match="requires its registered proof"):
        prices._physical_exclusion(dict(reason="infeasible_network_relaxation", exclusion=None))


def test_replayed_warehouse_purchase_preserves_target_service_caps_and_each_meter(monkeypatch):
    target, donor = prices.ss.Design(1, 20, 15), prices.ss.Design(2, 50, 20)
    caps, fixed = (20, 10), (("date", "1"),)
    req = prices.Request("week", donor, "energy", caps, fixed, ())
    period = SimpleNamespace(days=[{"week_start": "week"}])
    trace = dict(purchase_eur=-1., site_grid_kwh=dict(zip(prices.ss.SITES, (2., 3.))),
                 site_quarter_peak_kw=dict(zip(prices.ss.SITES, (7., 8.))), passed=True)
    result = dict(stats=dict(status="bounded", objective_lower=-1.05, objective_upper=-1.), audit=trace,
                  states=[dict(date="date", vehicle_id="1", served=True)])
    witness = dict(source="fitting_superset_same_caps", site_kwh_floor=[2., 3.], site_peak_floor=[7., 8.],
                   purchase_upper_eur_2021=-1.)
    def replay(p, hw, spec, c, r):
        assert p is period and r is result and hw == target.hardware() and caps == c
        return trace
    monkeypatch.setattr(prices.ss, "meter_replay", replay)
    def check(request=req, evidence=witness):
        return prices._week_meter(period,target,caps,fixed,request,result,evidence)
    assert check() == trace
    with pytest.raises(ValueError, match="witness scope"):
        check(replace(req, caps=(20,15)))
    with pytest.raises(ValueError, match="fixed screening donor"):
        check(evidence={**witness,"source":"identical_request"})
    with pytest.raises(ValueError, match="fixed refinement meter"):
        check(evidence={**witness,"site_kwh_floor":[3.,2.]})
    result["states"] = [dict(date="date", vehicle_id="2", served=True)]
    with pytest.raises(ValueError, match="exact registered vehicle-days"):
        check()
