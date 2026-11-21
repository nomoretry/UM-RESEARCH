from datetime import date, timedelta

import pytest

from um_charging import holdout_repair_costs as rc
from um_charging import site_sizing as ss


WEEKS = [(date(2021, 11, 8) + timedelta(weeks=i)).isoformat() for i in range(6)]
SMALL, LARGE = rc.REPAIRS


def dispatch(w, price):
    return dict(stats=dict(status="certified", status_code=0, objective_lower=price, objective_upper=price,
                           relative_gap=0., message="Optimal"),
                states=[dict(date=w, vehicle_id="5", served=True)],
                audit=dict(passed=True, purchase_eur=price, site_grid_kwh={"PORT": 50., "WAREHOUSE": 50.},
                           site_quarter_peak_kw={"PORT": 10., "WAREHOUSE": 10.}))


def inputs():
    cases = [dict(scenario=s, connection_basis=b, bills={ss.BASELINE.label: dict(
        status="certified", caps_kw=[50, 50], annual_total_eur=100000., annual_total_eur_bounds=[100000., 100000.])})
             for s in ("N0", "frank", "official", "capacity_0", "capacity_22_79", "capacity_208_38")
             for b in ("new", "existing")]
    source = dict(design=ss.BASELINE.label, caps_kw=[50, 0], status="infeasible",
                  week_status={w: "infeasible" if w == WEEKS[2] else "certified" for w in WEEKS})
    main = dict(annual_grid_kwh=5200.,
                weekly=[dict(week=w, registered=1) for w in WEEKS],
                daily=[dict(date=w, registered=["5"], eligible=["3", "5"]) for w in WEEKS],
                outside=[dict(date=w, vehicle_id="3", classification="infeasible_unlimited_power") for w in WEEKS])
    prior = dict(main=main, billing=dict(cases=cases, operating_points=[source]))
    runs = {(d.label, (d.port_kw, wh)): {w: dispatch(w, 10. if wh == 20 else 15.) for w in WEEKS}
            for d in rc.REPAIRS for wh in (15, 20)}
    return runs, prior


def test_frozen_whole_period_fallback_and_separate_service_cap_reference():
    runs, prior = inputs()
    out = rc.costs(WEEKS, runs, prior, annual_kwh=5200.)
    assert len(out["cases"]) == 12 and len(out["operating_points"]) == 4
    expected = {(SMALL.label, (20, 0)), (LARGE.label, (20, 0)), (LARGE.label, (40, 0))}
    assert {(p["design"], tuple(p["caps_kw"])) for p in out["zero_warehouse_proofs"]} == expected
    assert all(p["source_caps_kw"] == [50, 0] and p["infeasible_weeks"] == [WEEKS[2]]
               for p in out["zero_warehouse_proofs"])
    network = ss.load_network()
    equipment = ss._load_costs(ss.CONNECTION_INPUT, network)
    for r, old in zip(out["cases"], prior["billing"]["cases"], strict=True):
        assert r["baseline"] == old["bills"][ss.BASELINE.label]
        assert r["ranking_status"] == "determined"
        assert r["rank_bounds"] == {SMALL.label: [1, 1], LARGE.label: [2, 2], ss.BASELINE.label: [3, 3]}
        for d in rc.REPAIRS:
            main, ref = (r["repairs"][d.label][key] for key in ("main", "reference"))
            assert main["policy"] == ("frozen" if r["scenario"] == "N0" else "rated_fallback")
            assert main["caps_kw"] == list(d.caps)
            assert main["frozen_caps_kw"] == (
                list(d.caps) if r["scenario"] == "N0" else
                [d.port_kw, 0] if r["scenario"] in {"frank", "official"} else [20, 0])
            assert ref["caps_kw"] == [d.port_kw, 15] and ref["policy"] == "service_cap_reference"
            assert main["purchase_eur_2021_bounds"] == [60., 60.] and ref["purchase_eur_2021_bounds"] == [90., 90.]
            assert main["components_eur"]["chargers"] == ref["components_eur"]["chargers"]
            rated_kw = sum(d.caps) if r["connection_basis"] == "new" else 0
            assert ref["components_eur"]["connection"] == rated_kw * equipment["annual_bkz_eur_2025_per_kw"]


def test_gaps_preserve_service_and_unknown_ranks_without_switching_to_reference():
    runs, prior = inputs()
    for d, gap in ((SMALL, .050001), (LARGE, .05)):
        stats = runs[d.label, d.caps][WEEKS[0]]["stats"]
        stats.update(status="unresolved", status_code=1, message="Time limit reached",
                     objective_lower=stats["objective_upper"] - gap)
    out = rc.costs(WEEKS, runs, prior, 5200.)
    small = next(p for p in out["operating_points"] if p["design"] == SMALL.label and p["caps_kw"] == list(SMALL.caps))
    assert small["week_service_status"][WEEKS[0]] == "feasible" and small["week_status"][WEEKS[0]] == "unresolved"
    for r in out["cases"]:
        assert r["ranking_status"] == "unresolved" and r["rank_bounds"][SMALL.label] == [1, 3]
        assert r["rank_bounds"][LARGE.label] == [1, 2] and r["rank_bounds"][ss.BASELINE.label] == [2, 3]
        assert "annual_total_eur" not in r["repairs"][SMALL.label]["main"]
        assert r["repairs"][SMALL.label]["reference"]["status"] == "certified"
        large = r["repairs"][LARGE.label]["main"]
        assert large["status"] == "bounded" and large["annual_total_eur_bounds"][0] < large["annual_total_eur"]


def test_rated_infeasibility_stops_and_different_register_is_rejected():
    runs, prior = inputs()
    result = runs[SMALL.label, SMALL.caps][WEEKS[0]]
    result["states"][0]["vehicle_id"] = "3"
    with pytest.raises(ValueError, match="different register"):
        rc.costs(WEEKS, runs, prior, 5200.)
    result.update(stats=dict(status="infeasible", status_code=2), audit=None, states=[])
    with pytest.raises(rc.RatedServiceFailure, match=SMALL.label):
        rc.costs(WEEKS, runs, prior, 5200.)


def test_unproven_old_frozen_limit_does_not_authorize_rated_fallback():
    runs, prior = inputs()
    source = prior["billing"]["operating_points"][0]
    source["status"] = source["week_status"][WEEKS[2]] = "unresolved"
    rows = rc.costs(WEEKS, runs, prior, 5200.)["cases"]
    for row in rows:
        main = row["repairs"][LARGE.label]["main"]
        assert main["policy"] == "frozen"
        assert main["status"] == ("certified" if row["scenario"] == "N0" else "unresolved")


def test_overlapping_bills_limit_exact_ranks():
    bills = {k: dict(status="certified", annual_total_eur_bounds=v)
             for k, v in zip((ss.BASELINE.label, LARGE.label, SMALL.label), ([70., 80.], [65., 70.], [60., 60.]),
                             strict=True)}
    status, ranks = rc._ranks(bills)
    assert status == "overlap"
    assert ranks == {ss.BASELINE.label: [2, 3], LARGE.label: [2, 3], SMALL.label: [1, 1]}
