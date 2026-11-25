from types import SimpleNamespace

import pytest

from um_charging import m11_rule_study as study, m11_rules as rules, site_sizing as ss


def test_single_truck_rule_keeps_both_minimum_power_tie_breaks():
    assert rules.order(ss.Design(1,20,40)) > rules.order(ss.Design(1,40,20))
    assert rules.order(ss.Design(2,50,20)) > rules.order(ss.Design(1,50,20))


def test_fixed_service_invoice_rejects_nonzero_cross_year_week():
    period=SimpleNamespace(days=[{"date":"2021-12-31","week_start":"2021-12-27"},{"date":"2022-01-01"}])
    row=dict(status="certified",week="2021-12-27",lower=1.,upper=1.,grid={"PORT":1.,"WAREHOUSE":0.})
    with pytest.raises(ValueError,match="Cross-year"):
        study.settle([period],ss.BASELINE,[row])


def test_no_same_service_bill_for_infeasible_week():
    assert study.settle([None],ss.BASELINE,[dict(status="infeasible")]) == []


def test_fine_point_preserves_terminal_uncertainty_even_with_an_infeasible_week():
    from um_charging.m11_robustness import Point
    point=Point(ss.Design(1,20,20),(15,5))
    point.rows={"week1":{"status":"infeasible"},"week2":{"status":"unresolved","physical":True}}
    assert point.status()=="unresolved"


def test_partial_quarter_cap_applies_to_the_integral():
    from um_charging.m11_robustness import relaxed_segment
    truck={"trips":[(0,1,1.8,"trip")],"windows":[(14,17,ss.PORT)]}
    # One minute plus two minutes at 40 kW gives 2 grid kWh, split across two quarters.
    assert relaxed_segment(truck,ss.Design(1,40,0),(6,0))
    assert not relaxed_segment(truck,ss.Design(1,40,0),(2,0))
