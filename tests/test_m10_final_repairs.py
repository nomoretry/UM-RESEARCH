from datetime import date, timedelta
from types import SimpleNamespace

from um_charging import m10_final_repairs as repair
from um_charging import site_sizing as ss


def toy_periods():
    first = date(2021,11,8)
    for week in range(6):
        days = [(first+timedelta(days=7*week+n)).isoformat() for n in range(7)]
        yield SimpleNamespace(days=[dict(date=d, week_start=days[0]) for d in days], keys={(days[0],"1")})


def test_priced_staircase_exhausts_four_levels_and_exclusion_spends_no_slot():
    periods = list(toy_periods())
    registered = {key for p in periods for key in p.keys}
    calls = []
    def verification(period, design, fixed):
        assert fixed == period.keys
        return dict(status="certified", proof_id=f"{design.label}/{period.days[0]['date']}")
    def buy(period, design, fixed):
        calls.append(design)
        week = period.days[0]["week_start"]
        return dict(week=week, status="certified", purchase_lower=1.,
                    audit=dict(passed=True, purchase_eur=1., daily_eur={week:1.},
                               site_grid_kwh={ss.PORT:2.,ss.WAREHOUSE:0.},
                               site_quarter_peak_kw={ss.PORT:1.,ss.WAREHOUSE:0.}))
    result = repair.priced_repairs(periods, registered, {"2021-11-08"}, {}, verification, buy)
    assert {r["design"] for r in result["options"]} == {d.label for d in repair.PRICED_STAIRCASE}
    assert set(calls) == set(repair.PRICED_STAIRCASE)
    assert len(calls) == 4*6
    assert len(result["counted_designs"]) == 4
    assert all(result["minima"][k]["status"] == "restored" for k in ("new","existing"))
    larger = ss.Design(1,40,40)
    excluded = repair.priced_repairs(periods, registered, {"2021-11-08"}, {
        (larger,"2021-11-08"): dict(status="infeasible",proof_id="synthetic-proof")}, verification, buy)
    assert excluded["options"][1]["weeks"]["2021-11-08"]["source"] == "inclusion_exclusion"
    assert excluded["options"][1]["design"] not in excluded["counted_designs"]
    assert excluded["options"][3]["counted"]


def test_physical_repair_uses_the_registered_cross_start_order_and_separate_limit():
    starts = [repair.F20,repair.F40]
    assert [r.design.label for r in repair.physical_order(starts)[:6]] == [
        "p1-25-w20", "p1-20-w25", "p1-45-w20", "p1-40-w25", "p1-30-w20", "p1-20-w30"]
    p, *_ = toy_periods()
    both = {b:{"2021-11-08"} for b in starts}
    result = repair.physical_repairs([p], p.keys, both, {},
        lambda *args:dict(status="certified",proof_id="physical-proof"),
        lambda *args:dict(status="certified",proof_ids=["daily-proof"]))
    assert len(result["counted_designs"]) == result["limit"] == 6
    assert any(r["fixed_service"]=="unexamined" for r in result["options"])
    assert {r["both"]["minimum_added_kw"] for r in result["minima"]} == {5}
