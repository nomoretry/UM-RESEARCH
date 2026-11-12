import pytest

from um_charging.changeover_check import replay
from um_charging.changeover_study import hardware_key
from um_charging.day_ahead import ROOT, read_json
from um_charging.shared_investment import PRIOR, equipment, physical_cases, relax_schedule, shared_minimum


def test_shared_choice_intersects_feasible_sets_and_preserves_ties():
    menu = [(k, {"PORT": {"interfaces": n, "power_kw": 100}}) for k, n in ((1, 1), (2, 2), (3, 3), (3, 4))]
    a, b, c, d = [hardware_key(hw) for _, hw in menu]
    feasible = {(s, build): build in choices for s, choices in ((0, [a, c, d]), (1, [b, c, d]), (2, []))
                for build in [a, b, c, d]}
    assert shared_minimum(menu, [0], feasible) == (1, [a])
    assert shared_minimum(menu, [1], feasible) == (2, [b])
    assert shared_minimum(menu, [0, 1], feasible) == (3, [c, d])
    assert shared_minimum(menu, [0, 2], feasible) == (None, [])


def test_transferred_witness_replays_on_actual_easier_duty_and_new_turnaround():
    cases = physical_cases()
    high = max(leg for leg, _ in cases)
    row, = [r for r in read_json(PRIOR)["baseline_and_sensitivity"]
            if r["leg_kwh"] == high and r["hardware"]["PORT"]["interfaces"] == 2]
    changed = relax_schedule(row["critical_schedule"], high, 20, 2)
    checked = replay(cases[20, 30], row["hardware"], 2, changed)
    assert checked["passed"] and checked["trip_count"] == 6
    assert all(trace[-1] == pytest.approx(100) for trace in checked["energy_kwh"].values())
    for assigned in changed:
        ((start, end, power),) = assigned["segments"]
        assert start - 15 * assigned["slot"] in (0, 2)
        assert end == 15 * (1 + assigned["slot"])
        assert 0 < power <= 50 + 1e-6


def test_selected_corner_schedules_and_hand_computable_lower_bounds():
    result = read_json(ROOT / "results/shared_investment_20261112/metrics.json")
    cases = physical_cases()
    primary = [r for r in result["table"] if r["grid"] == "primary"]
    assert len(primary) == len({(r["max_leg_kwh"], r["max_release_min"], r["max_turnaround_min"])
                               for r in primary}) == 40
    mixed = result["nonrectangular_shared_plan"]
    assert mixed["individual_minima"] == [40, 50] and mixed["shared_investment"] == 70
    opts = {"warehouse_upgrade": (60, (("PORT", 2, 100), ("WAREHOUSE", 2, 100))),
            "port_capacity": (75, (("PORT", 3, 150), ("WAREHOUSE", 1, 75)))}
    for name, (cost, build) in opts.items():
        cert = result["certificates"][name]
        schedule, = cert["witnesses"].values()
        leg, release, tau = cert["service"]
        check = replay(cases[leg, release], equipment(build), tau, schedule)
        assert cert["investment"] == cost and check["passed"] and check["trip_count"] == 6
        warehouse_bound = leg / 0.9 + (12.5 if release == 45 else 0)
        assert 6 * leg / 0.9 - warehouse_bound > 100
