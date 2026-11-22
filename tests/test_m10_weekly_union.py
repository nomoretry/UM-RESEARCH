from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
import json
from types import SimpleNamespace

import pytest

from um_charging import m10_weekly_union as union


def _ts(h, m, second="00"):
    return f"2021-11-26T{h:02d}:{m:02d}:{second}+01:00"


def test_exact_reachability_resolves_subfloat_deficit_and_does_not_add_warehouse_power():
    day = "2021-11-26"
    key = [(day, "1")]
    trip = dict(start=_ts(8, 0), end=_ts(9, 0), track_id="leg", energy_kwh=Decimal("10.00000000000000001"))
    stop = dict(site=union.ss.PORT, arrival=_ts(9, 0), start=_ts(9, 0),
                end=_ts(9, 13, "20"), arrival_track_id="leg")
    ware = dict(stop, site=union.ss.WAREHOUSE, start=_ts(10, 0), end=_ts(11, 0))
    data = {day: dict(vehicles=[dict(vehicle_id="1", trips=[trip], stops=[stop, ware])])}
    out = union._exact_segment(data, key)
    assert not out["feasible"] and Fraction(out["failure"]["deficit_kwh"]) == Fraction(1, 10**17)
    assert Fraction(out["maximum_available_port_grid_kwh"]) == Fraction(100, 9)
    trip["energy_kwh"] = Decimal("10")
    assert union._exact_segment(data, key)["feasible"]


def test_single_week_network_is_billed_at_52_over_1_and_annual_capacity_once():
    network, material = union._parameters([None])
    d = union.ss.Design(1, 20, 20)
    meter = dict(purchase_eur=3., lower_eur=2.95, site_grid_kwh=dict(zip(union.ss.SITES, (30., 5.))),
                 site_quarter_peak_kw=dict(zip(union.ss.SITES, (10., 4.))))
    one = union._bill(network, material, d, [meter], "official", "new")
    twelve, _ = union._parameters([None] * 12)
    repeat = union._bill(twelve, material, d, [meter] * 12, "official", "new")
    assert one["purchase_upper"] == pytest.approx(3 * 52 * 121.9 / 103.1)
    assert one["purchase_lower"] == pytest.approx(2.95 * 52 * 121.9 / 103.1)
    assert one == pytest.approx(repeat)
    more = [dict(meter, site_quarter_peak_kw=dict(zip(union.ss.SITES, (12., 6.))))] + [meter] * 11
    higher = union._bill(twelve, material, d, more, "official", "new")
    assert higher["demand"] > one["demand"]
    assert higher["connection"] == one["connection"] and higher["equipment"] == one["equipment"]


def _point(week, d, basis, bounds):
    low, high = bounds
    return dict(week=week, design=d.label, scenario="official", connection_basis=basis,
                port_cap_kw=d.port_kw, warehouse_cap_kw=d.warehouse_kw, total_lower=low, total_upper=high,
                status="infeasible" if low is None else "unresolved" if high is None else "bounded",
                missing_ratings_kw="")


def test_weekly_competitors_including_partial_year_service_and_separate_bases():
    a, b, c = union.ss.Design(1, 20, 0), union.ss.Design(1, 20, 40), union.ss.Design(2, 50, 20)
    designs = {d.label: d for d in (a, b, c)}
    rows = []
    for basis in union.BASES:
        rows.extend([_point("w1", a, basis, (9., 10.)),
                     _point("w1", b, basis, (9.5, 10.2) if basis == "new" else (11., 12.)),
                     _point("w1", c, basis, (13., 14.)),
                     _point("w2", a, basis, (None, None)),
                     _point("w2", b, basis, (1., 1.) if basis == "new" else (11., 12.)),
                     _point("w2", c, basis, (5., 6.))])
    minima, membership, complete = union._weekly_choices(rows, designs)
    assert complete and len(minima) == 4
    assert membership == {"new": {a, b}, "existing": {a, c}}
    assert union._union(membership["new"]) == b
    assert union._union(membership["existing"]) == c
    assert union._union(set.union(*membership.values())) == union.ss.Design(2, 50, 40)
    rows.append(_point("w3", a, "new", (8., None)))
    rows.append(_point("w3", b, "new", (9., 10.)))
    minima, _, complete = union._weekly_choices(rows, designs)
    assert not complete and minima[-1]["unresolved_designs"] == [a.label]


def test_week_specific_exclusion_does_not_mask_any_other_week():
    obj = union._WeeklyGrid.__new__(union._WeeklyGrid)
    d = union.ss.Design(1, 20, 0)
    obj.feasible, obj.preferred, obj.impossible = defaultdict(dict), {}, defaultdict(list)
    obj.impossible["w2"].append(union._Scope(union.ss.Design(1, 50, 0), (50, 0), "w2-only"))
    assert obj._observe(("w1", d, d.caps)) is None
    assert obj._observe(("w2", d, d.caps)) == dict(status="infeasible", method="weekly_infeasible_superset", proof="w2-only")


def _toy_period(origin, consumption):
    def stamp(minutes):
        return (origin + timedelta(minutes=minutes)).isoformat()
    date = origin.date().isoformat()
    truck = dict(vehicle_id="1", unmapped_gaps=[], trips=[
        dict(start=stamp(0), end=stamp(15), energy_kwh=consumption, track_id="out")],
        stops=[dict(site=union.ss.PORT, arrival=stamp(15), start=stamp(15), end=stamp(45),
                    next_departure=stamp(45), arrival_track_id="out", next_track_id="next")])
    return union.ss.eb.Period([dict(date=date, week_start=date, start=stamp(0), end=stamp(1440),
                                  availability="complete_tasks", vehicles=[truck])], {date: [10.] * 24})


def test_public_weekly_union_replays_sealed_minima_without_seeing_later_requests(tmp_path, monkeypatch):
    small, large = union.ss.Design(1,20,0), union.ss.Design(1,40,0)
    periods = [_toy_period(datetime(2001,1,d,tzinfo=timezone.utc), kwh) for d,kwh in ((1,9.),(8,14.4))]
    inputs = SimpleNamespace(periods=periods, registered=set.union(*(p.keys for p in periods)),
                             source_sha256={"synthetic-calendar": "toy"})
    # Invent tariff and equipment values. The real bill, independent audit,
    # physical model and interval ranking are used throughout this test.
    materials = dict(annual_charger_eur_2025_by_kw={20: 100.,40: 200.}, annual_bkz_eur_2025_per_kw=.1)
    rate = dict(capacity_eur_per_kw_year=1., energy_eur_per_kwh=.01)
    def parameters(periods):
        return dict(annualization={"sample_weeks":len(periods), "weeks_per_year":52},
                    price_level={"cpi":{"2021":100., "2024":100., "2025":100.}}, metering={"sites":union.ss.SITES},
                    full_load_hours_boundary=2500, capacity_sensitivities_eur_per_kw_year={"c0":0.,"c1":1.,"c2":2.},
                    tariffs={k:dict(low_includes_boundary=k=="frank", bands={"low":rate,"high":rate})
                             for k in ("frank","official")}), materials
    monkeypatch.setattr(union,"_parameters",parameters)
    monkeypatch.setattr(union.ss,"design_grid",lambda _: [small,large])
    monkeypatch.setattr(union.ss.DispatchGrid,"options",lambda self,design,grid:[design.caps])
    by_week = {p.days[0]["week_start"]:p for p in periods}
    class Evidence:
        def __init__(self):
            self.results, self.requests, self.order = {}, {}, []
            self.verify = False
        def check(self):
            pass
        @property
        def records(self):
            return [dict(id=k,phase="energy",status=r["stats"]["status"],objective_lower=r["stats"]["objective_lower"])
                    for k,r in self.results.items()]
        def request_for(self, label):
            return self.requests[label]
        def get(self, label):
            return self.results[label]
        def batch(self, requests):
            output = []
            for req in requests:
                label = req.week + req.design.label
                self.order.append(label)
                if label not in self.results:
                    assert not self.verify
                    self.requests[label] = req
                    self.results[label] = union.ss.solve(by_week[req.week],req.design,caps=req.caps,fixed=set(req.fixed))
                output.append((label,self.results[label]))
            return output
    evidence = Evidence()
    old, = evidence.batch([union.Request.make(periods[0],large,"energy",large.caps,fixed=periods[0].keys)])
    label = old[0]
    evidence.order.clear()
    def save(name, value):
        (tmp_path/name).write_text(json.dumps(value),encoding="utf-8")
    (tmp_path/"solves.csv").write_text(f"id,phase\n{label},energy\n",encoding="utf-8")
    (tmp_path/"operating_points.csv").write_text(
        "design,port_cap_kw,warehouse_cap_kw,week,status,evidence_id\n"
        f"{large.label},40,0,2001-01-01,certified,{label}\n",encoding="utf-8")
    save("service_summary.json", {d.label:dict(weeks=[]) for d in (small,large)})
    save("selection.json", dict(winners=[dict(scenario="official",connection_basis=b,minimum_lower=199.,
        minimum_upper=200.,incumbent=dict(design=large.label,caps_kw=large.caps)) for b in union.BASES]))
    save("run_manifest.json",dict(inputs=dict(planning=inputs.source_sha256,fixed_service=sorted(inputs.registered)),
                                  timeout_interval_eur_2021=.1))
    save("seal.json",dict(products={p.name:union.digest(p) for p in tmp_path.iterdir() if p.is_file()}))
    formal = union.weekly_union(inputs,tmp_path,evidence)
    assert [r["possible_minimum_designs"] for r in formal["weekly_minima"]] == [
        [small.label], [small.label], [large.label], [large.label]]
    assert len(formal["union_costs"]) == 12 and len(formal["ex_ante_premiums"]) == 2
    assert all(r["design"] == large.label and r["status"] == "settled" for r in formal["union_costs"])
    for row in formal["ex_ante_premiums"]:
        assert row["premium_lower"] == pytest.approx(row["union_lower"]-200)
        assert row["premium_upper"] == pytest.approx(row["union_upper"]-199)
    observed_visits = evidence.order[:]
    assert observed_visits
    evidence.verify = True
    evidence.order.clear()
    assert union.weekly_union(inputs,tmp_path,evidence) == formal
    assert evidence.order == observed_visits
