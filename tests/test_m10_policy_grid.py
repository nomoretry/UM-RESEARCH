from types import SimpleNamespace

import pytest

from test_m10_immediate import PORT, period, truck
from um_charging import m10_policy_grid as study


class FixtureEvidence:
    """Issue hand-built traces; do not invoke an optimizer."""
    def __init__(self, *, wide=False, bad_day=None):
        self.requests = []
        self.weeks = []
        self.wide = wide
        self.bad_day = bad_day

    def check(self):
        pass

    def record_rolling_week(self,row):
        self.weeks.append((row["design"],tuple(row["caps_kw"]),row["week"],row["status"]))

    def batch(self,reqs):
        pairs = []
        for req in reqs:
            self.requests.append(req)
            day,vehicle = req.fixed[0]
            label = f"{day}-{req.design.label}-{req.caps}"
            if not req.caps[0] or day==self.bad_day:
                pairs.append((label,dict(stats=dict(status="infeasible",objective_lower=None,objective_upper=None),
                                         schedule=[],states=[],audit=None)))
                continue
            # Same procurement price and same service; two admissible optimal
            # witnesses have different peaks on physically equivalent daily regions.
            kw = 20 if req.design.warehouse_kw else 10
            rows = [dict(date=day,vehicle_id=vehicle,site=PORT,plug=1,reservation_slot=q,
                         start_min=15*q,end_min=15*q+15,power_kw=float(kw))
                    for q in range(4,4+40//kw)]
            value = 1.
            stats = dict(status="unresolved" if self.wide else "certified",objective=value,
                         objective_lower=value-(.11 if self.wide else 0.),objective_upper=value)
            pairs.append((label,dict(stats=stats, schedule=rows, states=[dict(date=day,vehicle_id=vehicle,
                served=True,x=150.,y=150.)],audit=dict(purchase_eur=value))))
        return pairs


def fixture_inputs(n=1):
    p = period([{"1":truck([(0,60,9)],[(60,120,PORT)])} for _ in range(n)])
    return SimpleNamespace(periods=[p],registered=frozenset(p.keys))


def test_full_grid_and_each_disclosure_is_counted_once():
    inputs = fixture_inputs()
    evidence = FixtureEvidence()
    saved = []
    output = study.policy_grid(inputs,evidence,checkpoint=lambda name,row:saved.append((name,row)))
    assert set(output) == set(study.TABLES)
    points = output["policy_points"]
    assert len({p["design"] for p in points if p["policy"]=="immediate"}) == 35
    assert len({p["design"] for p in points if p["policy"]=="rolling"}) == 35
    assert len(output["policy_cross_checks"]) == 5
    assert len(saved) == len(points) == len(output["policy_schedules"])
    assert len(evidence.weeks) == sum(p["policy"]=="rolling" for p in points)
    assert len(output["policy_annual"]) == 12*len(points)
    assert len(output["policy_comparison"]) == 24*len(points)
    official = [r for r in output["policy_comparison"] if r["policy"]=="immediate"
                and r["design"]=="p1-20-w20" and r["scenario"]=="official" and r["connection_basis"]=="new"]
    bill,disclosure = official
    assert bill["item"]=="whole_invoice" and disclosure["item"]=="terminal_surplus_included"
    assert bill["invoice_lower_eur_2025_per_year"] == bill["invoice_upper_eur_2025_per_year"]
    assert disclosure["invoice_upper_eur_2025_per_year"] is None
    assert disclosure["terminal_excess_kwh"] == pytest.approx(9.)
    assert disclosure["annual_terminal_excess_kwh"] == pytest.approx(9.*52)
    # No warehouse window is available on either request. A prior design's
    # matching feasible region cannot select the actual target's meter trace.
    traces = {r["design"]:r for r in output["policy_schedules"] if r["policy"]=="rolling"
              and r["design"] in ("p1-20-w0","p1-20-w20")}
    assert traces["p1-20-w0"]["audit"]["site_quarter_peak_kw"][PORT] == 10.
    assert traces["p1-20-w20"]["audit"]["site_quarter_peak_kw"][PORT] == 20.
    assert {r.design.label for r in evidence.requests} >= set(traces)
    failed = next(r for r in points if r["policy"]=="rolling" and r["design"]=="p0-0-w0")
    assert not failed["same_service"] and failed["completed_vehicle_days"] is None
    assert not any(r["total_upper"] is not None for r in output["policy_annual"]
                   if r["policy"]=="rolling" and r["design"]=="p0-0-w0")
    output["policy_days"][-1] = output["policy_days"][0]
    with pytest.raises(ValueError,match="vehicle-day"):
        study._verify_coverage(output,inputs,study.ss.design_grid(study.ss.COARSE_KW),
                               study._parameters(inputs.periods))


def test_overwide_observation_is_separate_from_admitted_minimum(monkeypatch):
    design = study.ss.Design(1,20,20)
    monkeypatch.setattr(study.ss,"design_grid",lambda grid:[design])
    output = study.policy_grid(fixture_inputs(),FixtureEvidence(wide=True))
    for row in output["policy_annual"]:
        if row["policy"] == "rolling":
            assert row["same_service"] and row["status"]=="unresolved"
            assert row["witness_conditioned_upper"] is not None
            assert row["total_upper"] is None and row["total_lower"] is None
    for row in output["policy_minima"]:
        if row["policy"] == "rolling":
            assert row["status"]=="unresolved" and row["minimum_upper"] is None
    for row in output["policy_design_ranks"]:
        if row["policy"] == "rolling":
            assert row["rank_best"] is None and row["rank_worst"] is None
            assert row["conditional_rank_best"] == row["conditional_rank_worst"] == 1


def test_conditionally_solved_future_day_is_not_a_realized_trace():
    inputs = fixture_inputs(4)
    p, = inputs.periods
    keys = sorted(p.keys)
    p.chains = [keys[:3],keys[3:]]
    design = study.ss.Design(1,20,20)
    w = study._dispatch_week(p,design,design.caps,inputs.registered,FixtureEvidence(bad_day=keys[0][0]))
    days = study._rolling_days(p,w,design,design.caps)
    assert [r["status"] for r in days] == [
        "joint_day_infeasible","conditional_after_unobserved_day","conditional_after_unobserved_day","complete"]
    assert all(r["completed"] is None and r["site_grid_kwh"] is None for r in days[:3])
    assert {r["date"] for r in w["conditional_schedule"]} == {keys[1][0],keys[2][0]}
    assert {r["date"] for r in w["schedule"]} == {keys[3][0]}
