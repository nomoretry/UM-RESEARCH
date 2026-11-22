from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from um_charging import m10_final_bills as billing
from um_charging import site_sizing as ss


def test_cross_year_purchase_and_empty_week_use_all_seven_calendar_weeks():
    first = date(2021, 12, 20)
    periods = []
    weeks = []
    for i in range(7):
        start = first + timedelta(days=7*i)
        dates = [(start + timedelta(days=d)).isoformat() for d in range(7)]
        periods.append(SimpleNamespace(days=[dict(date=d, week_start=dates[0]) for d in dates]))
        value = {0:103.1, 2:110.2}.get(i, 0.)
        bound = {0:51.55, 2:110.2}.get(i, 0.)
        weeks.append(dict(week=dates[0], purchase_lower=bound,
                          audit=dict(passed=True, purchase_eur=value, daily_eur={dates[0]:value},
                                     site_grid_kwh={ss.PORT:10. if value else 0., ss.WAREHOUSE:0.},
                                     site_quarter_peak_kw={ss.PORT:4. if value else 0., ss.WAREHOUSE:0.})))
    spot = billing.procurement(periods, weeks)
    assert spot["by_delivery_year"] == {"2021":103.1, "2022":110.2}
    assert spot["lower"] == pytest.approx(121.9*1.5)
    assert spot["upper"] == pytest.approx(121.9*2)
    new = billing.invoice(periods, ss.BASELINE, weeks, scenario="N0", basis="new", baseline=True)
    old = billing.invoice(periods, ss.BASELINE, weeks, scenario="N0", basis="existing", baseline=True)
    assert new["annualization"] == 52/7
    assert new["parts_eur_2025"]["procurement"] == pytest.approx(121.9*2*52/7)
    assert new["annual_total_upper"] - new["annual_total_lower"] == pytest.approx(121.9*.5*52/7)
    assert new["site_grid_kwh"][ss.PORT] == 20
    assert new["site_quarter_peak_kw"][ss.PORT] == 4
    _, mat = billing._parameters(periods)
    assert new["annual_total_upper"]-old["annual_total_upper"] == pytest.approx(
        175*mat["annual_bkz_eur_2025_per_kw"])
    weeks[1]["audit"]["site_grid_kwh"][ss.PORT] = 1.
    with pytest.raises(ValueError, match="cross-year"):
        billing.procurement(periods, weeks)


def test_difference_keeps_disclosure_off_the_complete_invoice():
    a = dict(annual_total_lower=11., annual_total_upper=12.)
    b = dict(annual_total_lower=8., annual_total_upper=9.)
    assert billing.difference(a, b) == [2., 4.]
    assert billing.difference(a, b, disclosure=.5) == [1.5, 3.5]
    assert billing.difference(a, None) is None
