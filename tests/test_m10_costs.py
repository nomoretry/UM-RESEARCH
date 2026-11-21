from types import SimpleNamespace

import pytest

from test_site_sizing import two_sites
from um_charging import m10_costs as costs
from um_charging import site_sizing as ss
from um_charging.cabinet_tariff import annual_factors
from um_charging.site_sizing_bounds import AnnualBillBounds


def test_twelve_week_factor_preserves_equipment_benchmark():
    twelve, materials = costs._parameters(range(12))
    six = ss.load_network()
    assert annual_factors(twelve)[0] == pytest.approx((52 / 12) * 121.9 / 103.1)
    assert annual_factors(twelve)[1] == annual_factors(six)[1]
    assert six["annualization"]["sample_weeks"] == 6
    assert materials == ss._load_costs(ss.CONNECTION_INPUT, six)


class ToyEvidence:
    trial = False

    def __init__(self, period):
        self.period = period
        self.solved = {}

    def batch(self, requests):
        output = []
        for request in requests:
            result = ss.solve(self.period, request.design, caps=request.caps, fixed=request.fixed)
            label = str(len(self.solved))
            self.solved[label] = result
            output.append((label, result))
        return output

    def get(self, label):
        return self.solved[label]


def test_weekly_proof_reuse_and_one_year_bill():
    period = two_sites(13.5)
    day = period.days[0]["date"]
    period.days[0]["week_start"] = day
    inputs = SimpleNamespace(periods=[period], registered=period.keys)
    large, small = ss.Design(2, 100, 50), ss.Design(1, 50, 50)
    no_warehouse = ss.Design(2, 100, 0)
    service = {no_warehouse: dict(weeks=[dict(week=day, status="shortfall", evidence_id="service-proof")])}
    network, materials = costs._parameters(inputs.periods)
    evidence = ToyEvidence(period)
    dispatch = costs.CoarseDispatch(inputs, service, network, evidence)
    bounds = AnnualBillBounds(inputs.periods, inputs.registered, network, materials)

    original = dispatch.dispatch(large, (50, 50))
    narrow = dispatch.dispatch(small, (50, 50))
    assert original["status"] == narrow["status"] == "certified"
    assert narrow["weeks"][0]["method"] == "larger_hardware_schedule"
    assert narrow["weeks"][0]["solve"] == original["weeks"][0]["solve"]
    rows = list(costs._invoice_rows(small, narrow, bounds, dispatch.records))
    assert len(rows) == 12
    n0 = next(r for r in rows if (r["scenario"], r["connection_basis"]) == ("N0", "existing"))
    assert n0["purchase_upper"] == pytest.approx(1.75 * 52 * 121.9 / 103.1)
    assert n0["total_upper"] == pytest.approx(n0["purchase_upper"] + n0["equipment"])
    assert set(n0) == costs.ANNUAL_COLUMNS.keys()
    assert set(next(costs._weekly_table(bounds, small, narrow))) == costs.OPERATING_COLUMNS.keys()
    assert costs._hold_one_week_out({small: [narrow]}, dispatch, bounds)["annual_comparisons"] == 12

    pending = dict(narrow, status="unresolved")
    incomplete = next(costs._invoice_rows(small, pending, bounds, dispatch.records))
    assert incomplete["total_upper"] is None
    assert incomplete["witness_upper"] >= incomplete["total_lower"]

    excluded = dispatch.dispatch(small, (50, 0))
    assert excluded["status"] == "infeasible"
    assert excluded["weeks"][0]["solve"] == "service-proof"
    assert len(evidence.solved) == 1


def test_partial_ranking_considers_each_hardware_once_and_keeps_unresolved_competitor():
    def row(label, cap, low, high, missing=""):
        return dict(design=label, port_cap_kw=cap, warehouse_cap_kw=0, scenario="N0", connection_basis="new",
                    total_lower=low, total_upper=high, missing_ratings_kw=missing, rank_best=None, rank_worst=None)
    annual = [row("a", 20, 10, 11), row("a", 30, 9.5, 25), row("b", 20, 9, None),
              row("c", 30, 12, 13), row("d", 30, 2, None, "15")]
    ranks, winners = costs._rank_designs(annual)
    ranks = {r["design"]: r for r in ranks}
    assert ranks["a"]["rank_best"] == 1 and ranks["a"]["rank_worst"] == 2
    assert ranks["b"]["rank_best"] == 1 and ranks["b"]["rank_worst"] == 3
    assert ranks["c"]["rank_best"] == 2
    assert ranks["d"]["rank_best"] is None
    assert winners[0]["incumbent"]["caps_kw"] == [20, 0]
    assert winners[0]["possible_minimum_designs"] == ["a", "b"]
