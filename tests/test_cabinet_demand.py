from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from um_charging import cabinet_audit, cabinet_model, cabinet_tariff
from um_charging import energy_boundary as eb
from um_charging.cabinet_incumbent import build_incumbent
from um_charging.cabinet_threshold import certify_p2
from um_charging.connector_cost import break_even


def toy_period(grid_kwh, start=480, end=495, day=4):
    origin = datetime(2021, 1, day, tzinfo=timezone.utc)

    def stamp(minutes):
        return (origin + timedelta(minutes=minutes)).isoformat()

    vehicles = []
    for v, energy in grid_kwh.items():
        trip = dict(start=stamp(360), end=stamp(400), energy_kwh=energy*.9, track_id=v)
        stop = dict(site="PORT", start=stamp(start), arrival=stamp(start),
                    end=stamp(end), next_departure=stamp(end),
                    arrival_track_id=v, next_track_id=v+"-next")
        vehicles.append(dict(vehicle_id=v, trips=[trip], stops=[stop], unmapped_gaps=[]))
    d = origin.date().isoformat()
    prices = [100.] * 24
    prices[7] = 10.
    return eb.Period([dict(date=d, availability="complete_tasks", start=stamp(0),
                           end=stamp(1440), vehicles=vehicles)], {d: prices})


def solved(period, equipment, fixed, **weights):
    result = cabinet_model.solve(period, equipment, eb.DEFAULT_SPEC, eb.B, fixed, **weights)
    audit = cabinet_audit.replay(period, equipment, eb.DEFAULT_SPEC, eb.B, result,
                                 fixed=fixed, **weights)
    return result, audit


def test_simultaneous_equal_split_hand_calculation():
    p = toy_period({"3": 6.25, "5": 6.25})
    result, audit = solved(p, "two_shared_rule", p.keys)
    assert sorted(r["power_kw"] for r in result["schedule"]) == pytest.approx([25., 25.])
    assert audit["site_grid_kwh"]["PORT"] == pytest.approx(12.5)
    assert audit["site_peak_kw"]["PORT"] == pytest.approx(50.)
    assert audit["purchase_eur"] == pytest.approx(1.25)
    assert len(solved(p, "one", None)[1]["served"]) == 1


@pytest.mark.parametrize(("end", "cap", "excluded"), [(495, 40., True), (510, 20., False)])
def test_e1_chain_reservation_deficit(end, cap, excluded):
    from um_charging.cabinet_incumbent import screen_e1_peak_sum
    p = toy_period({"3": 5., "5": 5.}, end=end)
    proof = screen_e1_peak_sum(p, eb.DEFAULT_SPEC, eb.B, p.keys, cap)
    assert proof["status_code"] == 0
    assert proof["excluded"] == excluded
    assert proof["minimum_artificial_quarter_deficit"] == pytest.approx(.5 if excluded else 0.)


def test_partial_port_hours_bound_nested_cost_and_preserve_cutoff():
    from um_charging.cabinet_partial import partial_e1_bound
    p = toy_period({"3": 5., "5": 5.}, start=465, end=495)
    weights = dict(energy_weight=1., peak_weights=dict.fromkeys(eb.SITES, .001))
    pool, audited = solved(p, "two_shared_pool", p.keys, **weights)
    single, _ = solved(p, "one", p.keys, **weights)
    # E4 can serve both trucks in the 10 €/MWh quarter. E1 also needs
    # the adjacent 100 €/MWh quarter. Their respective peaks are 40/20 kW.
    assert pool["stats"]["objective"] == pytest.approx(.14)
    assert single["stats"]["objective"] == pytest.approx(.57)
    bound = partial_e1_bound(p, eb.DEFAULT_SPEC, eb.B, p.keys, {**pool, "audit": audited},
                             upgrade_upper=.14, e1_upper=.57, **weights)
    assert bound["lower_bound"] == pytest.approx(.57)
    assert bound["ranked_hours"][0]["shortfall_kwh"] == pytest.approx(5.)
    assert all(s["status_code"] == 0 for t in bound["trials"] for s in t["solves"])


def test_shared_rule_rejects_unequal_simultaneous_power():
    # Both energy requests fit the shared 50 kW total, but 30 + 20 is
    # impossible under simultaneous equal sharing within one exact event.
    p = toy_period({"3": 7.5, "5": 5.})
    result, _ = solved(p, "two_shared_pool", p.keys)
    assert sorted(r["power_kw"] for r in result["schedule"]) == pytest.approx([20., 30.])
    assert len(solved(p, "two_shared_rule", None)[1]["served"]) == 1
    with pytest.raises(ValueError, match="25 kW"):
        cabinet_audit.replay(p, "two_shared_rule", eb.DEFAULT_SPEC, eb.B, result, fixed=p.keys)
    tampered = deepcopy(result)
    tampered["schedule"][0]["power_kw"] += 2
    with pytest.raises(ValueError, match="cabinet kW"):
        cabinet_audit.replay(p, "two_shared_pool", eb.DEFAULT_SPEC, eb.B, tampered, fixed=p.keys)


def test_shared_witness_replays_real_assignments_and_rejects_unattainable_caps():
    from um_charging.cabinet_shared import shared_peak_witness

    caps = {"PORT": 50., "WAREHOUSE": 0.}
    fee = {"PORT": 2., "WAREHOUSE": 2.}
    feasible = toy_period({"3": 6.25, "5": 6.25})
    witness = shared_peak_witness(feasible, [feasible], eb.DEFAULT_SPEC, eb.B,
                                  feasible.keys, caps, 1., fee)
    assert witness["audit"]["passed"]
    assert witness["objective_upper"] == pytest.approx(101.25)
    blocked = toy_period({"3": 7.5, "5": 5.})
    witness = shared_peak_witness(blocked, [blocked], eb.DEFAULT_SPEC, eb.B,
                                  blocked.keys, caps, 1., fee)
    assert not witness["feasible"]
    assert all(t["stats"]["objective"] == pytest.approx(1.) for t in witness["weeks"][0]["trials"])


def test_shared_cabinet_three_trucks_partial_half_shares():
    # Two identical quarters contain four half-shares of 6.25 kWh. Trucks
    # 1/3/5 need one/two/one shares, respectively. Dispatching (20,18) kW
    # then (18,16) kW is a feasible constructive schedule for all three.
    needs = {"1": 5., "3": 9., "5": 4.}
    p = toy_period(needs, end=510)
    result, audit = solved(p, "two_shared_rule", p.keys)
    assert len(audit["served"]) == 3
    measured = defaultdict(float)
    for row in result["schedule"]:
        measured[row["vehicle_id"]] += row["power_kw"]*(row["end_min"]-row["start_min"])/60
    assert measured == pytest.approx(needs)
    assert audit["site_peak_kw"]["PORT"] <= 50. + 1e-6
    assert audit["purchase_eur"] == pytest.approx(1.8)
    assert len(solved(p, "one", None)[1]["served"]) == 2


def test_independent_cabinets_equivalent_to_two_legacy_ports():
    p = toy_period({"3": 12.5, "5": 12.5})
    legacy_hw = {"PORT": dict(interfaces=2, power_kw=100), "WAREHOUSE": dict(interfaces=1, power_kw=75)}
    legacy = eb.solve(p, legacy_hw, eb.DEFAULT_SPEC, eb.B, p.keys)
    _, audit = solved(p, "two_independent", p.keys)
    assert audit["site_peak_kw"]["PORT"] == pytest.approx(100.)
    assert audit["purchase_eur"] == pytest.approx(legacy["audit"]["purchase_eur"])
    with pytest.raises(ValueError, match="cabinet kW"):
        cabinet_audit.replay(p, "two_shared_rule", eb.DEFAULT_SPEC, eb.B, legacy, fixed=p.keys)


def test_aligned_meter_quarters_and_native_hour_settlement():
    # 50 kW in a 15-minute dwell spanning two delivery hours: 5 minutes
    # land in one meter quarter, 10 in the next. Maximum meter demand is
    # 50*10/15 rather than the instantaneous or rolling 15-minute peak.
    p = toy_period({"5": 12.5}, start=475, end=490)
    _, audit = solved(p, "two_shared_rule", p.keys, peak_weights={"PORT": 22.79})
    assert audit["site_peak_kw"]["PORT"] == pytest.approx(50*10/15)
    assert audit["site_instant_peak_kw"]["PORT"] == pytest.approx(50)
    assert audit["purchase_eur"] == pytest.approx((5*10 + 10*100)*50/60/1000)


def test_weekly_row_keeps_exact_original_window_endpoint():
    days = eb.read_json(eb.WEEKS)["days"]
    group, = [g for g in eb.components(days, eb.calendar(days)[1]) if g[0]["date"] == "2021-10-04"]
    local, full = eb.Period(group, {}), eb.Period(days, {})
    d = "2021-10-05"
    right, = [b for _, b, s in local.cases[d]["trucks"]["4"]["windows"]
              if s == "PORT" and 342 < b < 343]
    left = (right//15)*15
    row = dict(date=d, vehicle_id="4", site="PORT", start_min=local.offset[d]+left,
               end_min=local.offset[d]+right, reservation_slot=int((local.offset[d]+left)//15), power_kw=50.)
    shifted, = cabinet_audit.schedule_on_clock(full, local, [row])
    assert shifted["end_min"] == full.offset[d] + right
    assert shifted["reservation_slot"] == int((full.offset[d]+left)//15)


def test_one_demand_charge_across_two_weeks():
    # Week 1 sets a mandatory 30 kW peak. Week 2 can use that headroom at
    # the cheap price: 30 kW for 15 min, then 20 kW for 15 min at EUR 100/MWh.
    # Separate weekly peaks would incorrectly smooth the second week to 25 kW.
    first = toy_period({"3": 7.5})
    second = toy_period({"3": 12.5}, start=465, end=495, day=11)
    p = eb.Period(first.days + second.days, {**first.prices, **second.prices})
    network = cabinet_tariff.load_network()
    energy_weight, fee_weight = cabinet_tariff.annual_factors(network)
    weights = dict(energy_weight=energy_weight, peak_weights={"PORT": 22.79*fee_weight})
    _, p1 = solved(p, "one", p.keys)
    p2_result, p2 = solved(p, "one", p.keys, **weights)
    assert p1["site_peak_kw"]["PORT"] == pytest.approx(50.)
    assert p2["site_peak_kw"]["PORT"] == pytest.approx(30.)
    assert sorted(r["power_kw"] for r in p2_result["schedule"] if r["date"] == second.days[0]["date"]) == pytest.approx([20., 30.])
    assert p2["purchase_eur"] == pytest.approx(.75 + .075 + .5)
    settlements = []
    for audit in (p1, p2):
        settlement = cabinet_tariff.settle(network, audit["purchase_eur"], audit["site_grid_kwh"],
                                           audit["site_peak_kw"], "frank")
        cabinet_audit.audit_settlement(network, audit["purchase_eur"], audit["site_grid_kwh"],
                                       audit["site_peak_kw"], "frank", settlement)
        settlements.append(settlement["annual_total_eur_2025"])
    assert settlements[0] - settlements[1] == pytest.approx(20*22.79*fee_weight - .45*energy_weight)
    assert settlements[1] < settlements[0]
    upper = build_incumbent(p, [first, second], eb.DEFAULT_SPEC, eb.B, p.keys, **weights)
    assert upper["audit"]["passed"]
    assert upper["objective_upper"] >= p2_result["stats"]["objective"] - 1e-6
    assert upper["site_peak_kw"]["PORT"] == pytest.approx(30.)


@pytest.mark.parametrize("basis,at", [("frank", "low"), ("official", "high")])
def test_meter_band_and_invoice_at_boundary(basis, at):
    network = cabinet_tariff.load_network()
    assert cabinet_tariff.select_band(network, 2499., basis) == "low"
    assert cabinet_tariff.select_band(network, 2500., basis) == at
    assert cabinet_tariff.select_band(network, 2501., basis) == "high"
    # Exactly 65,000 kWh/year. Rounding 52/6 before multiplication would
    # incorrectly put this invoice below the threshold in binary double.
    energy = {"PORT": 7500., "WAREHOUSE": 0.}
    peak = {"PORT": 26., "WAREHOUSE": 0.}
    settlement = cabinet_tariff.settle(network, 10., energy, peak, basis)
    cabinet_audit.audit_settlement(network, 10., energy, peak, basis, settlement)
    assert settlement["sites"]["PORT"]["band"] == at
    settlement["annual_capacity_eur_2025"] += 1.
    with pytest.raises(ValueError, match="annual_capacity_eur_2025"):
        cabinet_audit.audit_settlement(network, 10., energy, peak, basis, settlement)


def test_registered_a_b_energy_service_peaks_and_break_even():
    days = eb.read_json(eb.WEEKS)["days"]
    native = eb.csv_rows(eb.NATIVE)
    prices = {d["date"]: eb.hourly_curve(native, d) for d in days if d["availability"] == "complete_tasks"}
    reference = eb.read_json(eb.WEEKS.with_name("energy_boundary.json"))["full"]
    periods = [eb.Period(g, prices) for g in eb.components(days, eb.calendar(days)[1])]
    week = {d["date"]: d["week_start"] for d in days}
    paired = {}
    for rule in (eb.A, eb.B):
        for equipment, facility in (("one", "one"), ("two_independent", "two")):
            row, = (r for r in reference if (r["spec"], r["facility"], r["rule"]) == ("S300", facility, rule))
            keys = set(map(tuple, row["selected"]))
            assert len(keys) == row["common_count"] == row["completed"] == 54
            bills = defaultdict(float)
            peaks = dict.fromkeys(eb.SITES, 0.)
            for p in periods:
                fixed = keys & p.keys
                result = cabinet_model.solve(p, equipment, eb.DEFAULT_SPEC, rule, fixed)
                audit = cabinet_audit.replay(p, equipment, eb.DEFAULT_SPEC, rule, result, fixed=fixed)
                assert set(audit["served"]) == fixed
                for d, euro in audit["daily_eur"].items():
                    bills[week[d]] += euro
                for s in eb.SITES:
                    peaks[s] = max(peaks[s], audit["site_peak_kw"][s])
            assert sum(bills.values()) == pytest.approx(row["common_eur"], abs=1e-6, rel=0)
            assert peaks == pytest.approx(row["site_peak_kw"], abs=1e-6, rel=0)
            paired[rule, equipment] = bills
        weekly = [paired[rule, "one"][w] - paired[rule, "two_independent"][w] for w in sorted(set(week.values()))]
        ceilings = break_even(weekly)
        euro, capex = ((330.85, 2554.72) if rule == eb.A else (391.24, 3021.03))
        assert round(ceilings["annual_cost_ceiling_2025_eur"], 2) == euro
        assert round(ceilings["capital_ceiling_zero_maintenance_2025_eur"], 2) == capex


def test_optimized_price_threshold_with_zero_tail():
    def choices(name):
        base = [(2., 4.), (5., 3.), (8., 2.)]
        return base if name == "one" else [*base, (1., 5.)]

    def point(name, rate):
        energy, peak = min(choices(name), key=lambda x: (x[0]+rate*x[1], x[1]))
        return dict(energy=energy, peak=peak)

    def min_peak(name):
        energy, peak = min(choices(name), key=lambda x: (x[1], x[0]))
        return dict(energy=energy, peak=peak)

    intervals = certify_p2(point, min_peak, 1., (0., 1., 4.))["intervals"]
    for regions in intervals.values():
        verified = [r for r in regions if r["status"] == "zero_to_tolerance"]
        assert any(r["from_rate"] <= 1. <= r["to_rate"] for r in verified)
        assert all(r["from_rate"] >= 1. for r in verified)


@pytest.mark.parametrize("separate_weeks", [False, True])
def test_port_normalization_matches_unscaled_quarters(separate_weeks):
    first = toy_period({"3": 9., "5": 4.5}, start=465, end=510)
    second = toy_period({"3": 4., "5": 6.}, start=475, end=511, day=11)
    days = first.days+second.days
    if separate_weeks:
        days = [{**day, "week_start": day["date"]} for day in days]
    p = eb.Period(days, {**first.prices, **second.prices})
    weights = dict(energy_weight=9.5, peak_weights={"PORT": 15., "WAREHOUSE": 16.})
    original = cabinet_model.solve(p, "one", eb.DEFAULT_SPEC, eb.B, p.keys, force_exact=True, **weights)
    normalized = cabinet_model.solve(p, "one", eb.DEFAULT_SPEC, eb.B, p.keys,
                                     objective_upper=original["stats"]["objective"]+.1, **weights)
    physical = cabinet_audit.replay(p, "one", eb.DEFAULT_SPEC, eb.B, normalized, fixed=p.keys, **weights)
    if separate_weeks:
        assert normalized["stats"]["weekly_support"]
    else:
        assert normalized["stats"]["normalization_kw"] == 50.
    assert original["stats"]["objective"] == pytest.approx(284.915)
    assert normalized["stats"]["objective"] == pytest.approx(original["stats"]["objective"], abs=1e-7, rel=0)
    assert normalized["stats"]["dual_bound"] == pytest.approx(original["stats"]["objective"], abs=1e-7, rel=0)
    assert physical["site_peak_kw"] == pytest.approx({"PORT": 18., "WAREHOUSE": 0.})

@pytest.mark.parametrize("base_energy, upgrade_energy", [(10., 10.), (10.0004, 10.)])
def test_threshold_reports_unresolved_primal_dual_overlap(base_energy, upgrade_energy):
    # Coinciding incumbents and a small apparent saving can both be inconclusive.
    # A 0.001 EUR dual gap also cannot support an unbounded tariff extrapolation.
    def point(name, rate):
        energy = base_energy if name == "one" else upgrade_energy
        return dict(energy=energy, peak=2., lower=energy+2.*rate-0.001)

    def min_peak(name):
        return dict(energy=10., peak=2., lower=1.999)

    results = certify_p2(point, min_peak, 1., (0., 1., 4.))
    for regions in results["intervals"].values():
        assert all(r["status"].startswith("unresolved") for r in regions)
        assert regions[-1]["to_rate"] is None
        assert regions[-1]["bounds_at_start_2025_eur"][1] >= 0.001-1e-10


def test_threshold_positive_certificate_uses_dual_lower():
    def point(name, rate):
        energy = 11. if name == "one" else 10.
        return dict(energy=energy, peak=2., lower=energy+2.*rate-0.001)

    def min_peak(name):
        return dict(energy=11. if name == "one" else 10., peak=2., lower=2.)

    result = certify_p2(point, min_peak, 1., (0., 1., 4.))
    for regions in result["intervals"].values():
        assert all(r["status"]=="strictly_positive" for r in regions)
        assert regions[0]["lower_bound_2025_eur"] == pytest.approx(0.999)
        assert regions[-1]["lower_bound_at_start_2025_eur"] == pytest.approx(0.999)


def test_capacity_savings_certificate_accounts_for_both_banded_volume_charges():
    from um_charging.cabinet_demand import bill_intervals

    low = dict(from_rate=0., to_rate=20., all_sites_low_proved=True, annual_grid_kwh=1000.)
    high = dict(intervals=[dict(from_rate=40.,to_rate=50.,
                    max_abs_annual_volumetric_difference_eur_2025={"frank":1.25})])
    raw = {"two_shared_rule":[dict(from_rate=0.,to_rate=None,status="strictly_positive",
                                  lower_bound_at_start_2025_eur=2.,lower_slope_2025=0.)]}
    pieces=bill_intervals(raw,low,high,cabinet_tariff.load_network())["two_shared_rule"]
    assert [(v["from_rate"],v["to_rate"],v["status"]) for v in pieces]==[
        (0.,20.,"strictly_positive"),(20.,40.,"unresolved_across_meter_bands"),
        (40.,50.,"strictly_positive"),(50.,None,"unresolved_across_meter_bands")]
    assert pieces[2]["billed_lower_eur_2025"]==pytest.approx(.75)


def test_finite_gain_chord_keeps_the_upgrade_line_intersection():
    from um_charging.cabinet_threshold import gain_interval

    def point(name,rate):
        profiles = [(10.,2.)] if name=="one" else [(9.,2.),(10.,1.)]
        energy,peak=min(profiles,key=lambda x:x[0]+rate*x[1])
        return dict(energy=energy,peak=peak,lower=energy+rate*peak)

    bounds=gain_interval("two_shared_rule",0.,4.,point,1.)
    assert bounds["lower_bound_2025_eur"]==pytest.approx(1.)
    assert bounds["uniform_objective_gain_upper_eur_2025"]>=4.
