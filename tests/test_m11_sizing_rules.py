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
