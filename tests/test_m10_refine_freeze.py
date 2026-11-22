import pytest
from dataclasses import replace
from types import SimpleNamespace

from um_charging import m10_refine_freeze as freeze


CASES = [("N0", "new")]
WEEKS = [f"week-{i}" for i in range(12)]
PRICED = freeze.ss.Design(1, 20, 20)
FOCUS = freeze.PRIORITY[0]
FROZEN = dict(scenario="N0", connection_basis="new", design=PRICED.label, port_cap_kw=20,
              warehouse_cap_kw=20, minimum_lower_eur_2025=1000., minimum_upper_eur_2025=1002.)


def weekly(weeks):
    rows = [dict(week=week, evidence_id=week, status="bounded") for week in weeks]
    return rows, {week: dict(week=week, phase="energy", audited="True", status="bounded") for week in weeks}


def test_freeze_validates_exact_fixed_caps_retains_distinct_minimum_and_point_bounds():
    rows, ledger = weekly(WEEKS)
    point = PRICED.label, PRICED.caps
    win = dict(scenario="N0", connection_basis="new", minimum_lower=1000., minimum_upper=1002.,
               incumbent=dict(design=PRICED.label, caps_kw=[20, 20], missing_ratings_kw="",
                              rank_best=1, rank_worst=1, total_upper=1002.),
               possible_minimum_designs=[PRICED.label])
    annual = {(point, CASES[0]): {"status": "bounded", "missing_ratings_kw": "",
                                  "total_lower": "1001", "total_upper": "1002"}}
    service = {PRICED.label: dict(same_service=True, completed_registered=106,
                                   port_plugs=1, port_kw=20, warehouse_kw=20)}
    out, = freeze._freeze([win], CASES, annual, {point: rows}, ledger, service, WEEKS)
    assert out["minimum_lower_eur_2025"] == 1000 and out["frozen_point_lower_eur_2025"] == 1001
    assert (out["port_cap_kw"], out["warehouse_cap_kw"]) == (20, 20)
    assert out["weekly_proof_ids"].split() == WEEKS
    with pytest.raises(ValueError, match="exact same-service settlement"):
        freeze._freeze([win], CASES, annual, {point: rows[:6]}, ledger, service, WEEKS)
    with pytest.raises(ValueError, match="unique priced"):
        freeze._freeze([{**win, "possible_minimum_designs": [PRICED.label, "another"]}],
                       CASES, annual, {point: rows}, ledger, service, WEEKS)


def test_quote_requires_matching_hardware_caps_and_every_week():
    rows, ledger = weekly(WEEKS)
    high = freeze.ss.Design(1, 20, 20)
    caps = (20, 15)
    point = FOCUS.label, caps
    other = (high.label, caps)
    cap_mismatch = FOCUS.label, (20, 10)
    annual = {(key, CASES[0]): dict(status="bounded", missing_ratings_kw="15",
                                   equipment="120", connection="30", network_energy="10", demand="15",
                                   purchase_lower="300", purchase_upper="305") for key in (other, cap_mismatch)}
    materials = {"annual_charger_eur_2025_by_kw": {20: 120., 40: 200.}, "annual_bkz_eur_2025_per_kw": 1.}
    points = [(FOCUS, caps), (freeze.PRIORITY[1], (40, 15))]
    week_rows = {other: rows, cap_mismatch: rows, point: rows[:6]}
    def evaluate():
        return freeze._quotes(points, [FROZEN], annual, week_rows, ledger, WEEKS, materials, .2)
    inventory, thresholds, priority = evaluate()
    assert not thresholds and len(priority) == 2 and inventory[0]["audited_weeks"] == 6
    assert all(r["settled_points"] == 0 for r in priority)
    annual[point, CASES[0]] = annual[other, CASES[0]]
    with pytest.raises(ValueError, match="twelve-week evidence"):
        evaluate()
    week_rows[point] = rows
    inventory, thresholds, priority = evaluate()
    assert inventory[0]["settled_tariff_cases"] == priority[0]["settled_points"] == 1
    row, = thresholds
    assert (row["annual_allowance_lower_eur_2025"], row["annual_allowance_upper_eur_2025"]) == (520., 527.)
    assert (row["net_equipment_lower_eur_2026"], row["net_equipment_upper_eur_2026"]) == (2600., 2635.)
    assert row["quote_scope"] == "one_net_unit"


def test_multiple_missing_units_only_receive_a_joint_allowance_including_negative_values():
    row = dict(equipment=0., connection=30., network_energy=4., demand=6., purchase_lower=1100., purchase_upper=1102.)
    result = freeze._break_even(FROZEN, row, [15, 25], .2)
    assert result["quote_scope"] == "joint_net_equipment_sum"
    assert result["net_equipment_upper_eur_2026"] < 0
    with pytest.raises(ValueError, match="positive annualization factor"):
        freeze._break_even(FROZEN, row, [15, 25], 0.)


def test_target_transfer_uses_fixed_r_identical_caps_and_all_original_meters(monkeypatch):
    caps = (20, 10)
    periods = {w: SimpleNamespace(keys={(w, "truck")}) for w in WEEKS}
    fixed = set().union(*(p.keys for p in periods.values()))
    source = freeze.ss.Design(1, 40, 20)
    requests = {w: freeze.Request(w, source, "energy", caps, tuple(periods[w].keys), ()) for w in WEEKS}
    records = {w: dict(week=w, phase="energy", design=source.label, port_cap_kw=20, warehouse_cap_kw=10,
                       audited="True", status="bounded", objective_lower=1.99, objective_upper=2.) for w in WEEKS}
    weekly_rows = [dict(week=w, proof=w, source="fitting_superset_same_caps", site_kwh_floor=[2., 3.],
                        site_peak_floor=[4., 7.], purchase_lower_eur_2021=-999., purchase_upper_eur_2021=2.)
                   for w in WEEKS]
    screening = dict(decision="retain", priced=False, weekly=weekly_rows)
    network, materials = freeze._parameters(list(periods.values()))
    cases = [("N0", "new"), ("official", "existing")]
    seen = []
    def replay(period, hardware, spec, requested_caps, result):
        assert hardware == FOCUS.hardware() and requested_caps == caps
        seen.append(result["states"][0]["date"])
        return dict(passed=True, site_grid_kwh=dict(zip(freeze.ss.SITES, [2., 3.])),
                    site_quarter_peak_kw=dict(zip(freeze.ss.SITES, [4., 7.])), purchase_eur=2.)
    monkeypatch.setattr(freeze.ss, "meter_replay", replay)

    def read(w):
        return requests[w], dict(states=[dict(date=w, vehicle_id="truck", served=True)])
    def invoices():
        return freeze._transfer_invoice(FOCUS, caps, screening, periods, fixed, records, read,
                                        network, materials, cases)
    proofs, bills = invoices()
    assert proofs == seen == WEEKS
    assert set(bills) == set(cases)
    assert bills[cases[0]]["purchase_lower"] == pytest.approx(12 * 1.99 * freeze.annual_factors(network)[0])
    assert bills[cases[0]]["purchase_upper"] == pytest.approx(24 * freeze.annual_factors(network)[0])
    assert bills[cases[1]]["network_energy"] > 0 and bills[cases[1]]["demand"] > 0
    transfer = lambda design, c: (proofs, bills) if design == FOCUS else ([], {})
    inventory, thresholds, _ = freeze._quotes([(FOCUS, caps), (freeze.PRIORITY[1], (40, 15))], [FROZEN],
                                              {}, {}, {}, WEEKS, materials, .2, transfer)
    assert inventory[0]["settlement_source"] == thresholds[0]["settlement_source"] == "r013_replayed_meter_settlement"
    assert inventory[1]["settlement_source"] == "unsettled" and thresholds[0]["weekly_proof_ids"].split() == WEEKS
    week = WEEKS[-1]
    weekly_rows[-1]["proof"] = None
    assert invoices() == (WEEKS[:-1], {})
    weekly_rows[-1]["proof"] = week
    original = requests[week]
    for changed in (replace(original, caps=(20, 15)), replace(original, fixed=())):
        requests[week] = changed
        with pytest.raises(ValueError, match="Invalid same-cap fixed-service transfer"):
            invoices()
    requests[week] = original
    weekly_rows[-1]["site_peak_floor"][0] += 1
    with pytest.raises(ValueError):
        invoices()
