import json
import math

import pytest

from um_charging import fleet_service, service_gap
from um_charging.day_ahead import read_json
from um_charging.fleet_design import failure_reasons
from um_charging.fleet_service import (
    DEFAULT_SPEC, audit, build_case, dispatch, immediate, max_service, subset_case,
)


def test_default_spec_exact_replay(monkeypatch):
    # Freeze only the elapsed-time clock so the entire result can be compared.
    monkeypatch.setattr(fleet_service, "perf_counter", lambda: 0.)
    days = [d for d in read_json(service_gap.WEEKS)["days"] if d["availability"] == "complete_tasks"]
    hardware = read_json(service_gap.REFERENCE)["hardware"]["one"]
    for day in days[:3]:
        case = build_case(day, 45)
        for solve in (dispatch, max_service, immediate):
            implicit = solve(case, hardware)
            explicit = solve(case, hardware, spec=DEFAULT_SPEC)
            assert json.dumps(implicit) == json.dumps(explicit)
        result = max_service(case, hardware)
        args = subset_case(case, result["selected_ids"]), hardware, result["schedule"]
        assert json.dumps(audit(*args)) == json.dumps(audit(*args, spec=DEFAULT_SPEC))
        assert failure_reasons(case, hardware) == failure_reasons(case, hardware, spec=DEFAULT_SPEC)


def test_analytic_thresholds():
    truck = {"windows": [(0, 60, "PORT")], "trips": [(60, 90, 36, "leg")]}
    # Restoring cyclic SOC requires charging exactly 36 kWh before departure.
    # One hour gives P* = 36 / 0.9. Headroom C - 0.5*C >= 36 gives C* = 72.
    for bracket, exact in ((service_gap.min_truck_kw(truck, DEFAULT_SPEC), 40),
                           (service_gap.min_capacity(truck, 50), 72),
                           (service_gap.min_capacity(truck, math.inf), 72)):
        low, high = bracket
        assert low <= exact <= high + 1e-9
        assert high - low <= 1e-6
    assert service_gap.min_capacity(truck, 39) is None
    truck["windows"] = []
    assert service_gap.min_truck_kw(truck, DEFAULT_SPEC) is None
    assert service_gap.reachable(truck, DEFAULT_SPEC)[1]["cause"] == "single_truck_terminal_energy"


def test_detect_nonmonotone_capacity(monkeypatch):
    def inverted(truck, spec):
        return 300 <= spec.capacity_kwh < 900, None
    monkeypatch.setattr(service_gap, "reachable", inverted)
    with pytest.raises(ValueError, match="Nonmonotone"):
        service_gap.min_capacity({}, 50)


def test_six_week_service_and_proofs():
    result = service_gap.run()
    assert all(result["checks"].values())
    assert result["max_bracket_width"] <= 2e-6
    releases = result["releases"]
    assert releases["45"]["counts"]["served_at_baseline"] == 54
    proof_counts = result["solves"]["counts"]
    rows = [row for release in releases.values() for row in release["rows"]]
    for key, label in (("min_capacity_kwh_50", "capacity"), ("min_truck_kw", "power")):
        finite = sum(row[key] is not None for row in rows)
        assert proof_counts[f"{label}_above.optimal"] == proof_counts[f"{label}_below.infeasible"] == finite
    assert proof_counts["baseline.optimal"] == sum(row["category"] == "served_at_baseline" for row in rows)
    served = {}
    for release, data in releases.items():
        assert sum(data["counts"].values()) == len(data["rows"]) == 73
        served[release] = {(r["date"], r["vehicle_id"]) for r in data["rows"]
                           if r["category"] == "served_at_baseline"}
    assert served["45"] <= served["0"]
    fleet = result["fleet"]
    assert fleet[0]["one"] == fleet[0]["two"] == fleet[0]["goal_total"] == 54
    for key in ("goal_total", "one", "two"):
        values = [r[key] for r in fleet]
        assert values == sorted(values)
    for tier in fleet:
        assert len(tier["goals"]) == 30
        assert len(tier["remaining"]) == 73 - tier["goal_total"]
    assert fleet[-1]["goal_total"] == fleet[-1]["two"] == fleet[-1]["one"] + 1
