"""Regression tests for the fixed-hardware, asymmetric warehouse delay study."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from um_charging.eligibility_stress import audit_case, build_case, make_reference


ROOT = Path(__file__).resolve().parents[1]
DELAYED = ["V1", "V2"]
FACILITIES = {"A": {"PORT": 2, "WAREHOUSE": 1}, "B": {"PORT": 3, "WAREHOUSE": 1}}


@pytest.fixture
def reference():
    base = json.loads((ROOT / "configs/port_warehouse_investment.json").read_text(encoding="utf-8"))
    return make_reference(base)


@pytest.mark.parametrize("delay", [0, 30, 60])
def test_delay_masks_only_targeted_warehouse_slots(reference, delay):
    original = copy.deepcopy(reference)
    data = build_case(reference, FACILITIES["A"], delay, DELAYED)
    vehicles = {v["id"]: v for v in data["vehicles"]}
    assert set(vehicles) == {"V1", "V2", "V3"}
    for original_vehicle in original["vehicles"]:
        vehicle = vehicles[original_vehicle["id"]]
        closed_slots = delay // 15 if vehicle["id"] in DELAYED else 0
        expected = ([None] * 4 + [None] * closed_slots
                    + ["WAREHOUSE"] * (4 - closed_slots) + [None] * 4 + ["PORT"] * 4)
        assert vehicle["charging_site"] == expected
        assert [event["plug_allowed"] for event in vehicle["timeline"]] == [site is not None for site in expected]
        for old_event, event in zip(original_vehicle["timeline"], vehicle["timeline"], strict=True):
            assert {k: v for k, v in old_event.items() if k != "plug_allowed"} == {
                k: v for k, v in event.items() if k != "plug_allowed"
            }
        fixed_keys = set(original_vehicle) - {"charging_site", "timeline"}
        assert all(vehicle[k] == original_vehicle[k] for k in fixed_keys)
    assert reference == original


@pytest.mark.parametrize("facility", FACILITIES.values(), ids=FACILITIES.keys())
def test_hardware_fixed_for_whole_grid(reference, facility):
    for delay in (0, 15, 30, 45, 60):
        case = build_case(reference, facility, delay, DELAYED)
        sites = {site["id"]: site for site in case["sites"]}
        assert {key: s["interfaces"] for key, s in sites.items()} == facility
        assert sites["PORT"]["available_power_kw"] == [100] * 16
        assert sites["WAREHOUSE"]["available_power_kw"] == [75] * 16
        assert all(site["active"] and site["max_new_interfaces"] == 0 and not site["upgrade_options"]
                   for site in sites.values())
        assert case["connector_policy"] == "slot_boundary_switching"


@pytest.mark.parametrize("mutation", ["V3_window", "warehouse_upgrade", "drive_energy", "port_power"])
def test_input_audit_rejects_uncontrolled_changes(reference, mutation):
    case = build_case(reference, FACILITIES["A"], 45, DELAYED)
    assert audit_case(reference, case, FACILITIES["A"], 45, DELAYED)["passed"]
    vehicles = {v["id"]: v for v in case["vehicles"]}
    sites = {s["id"]: s for s in case["sites"]}
    if mutation == "V3_window":
        vehicles["V3"]["charging_site"][4] = None
        vehicles["V3"]["timeline"][4]["plug_allowed"] = False
    elif mutation == "warehouse_upgrade":
        sites["WAREHOUSE"]["upgrade_options"] = copy.deepcopy(reference["sites"][1]["upgrade_options"])
    elif mutation == "drive_energy":
        vehicles["V1"]["drive_energy_kwh"][0] += 1
    else:
        sites["PORT"]["available_power_kw"][12] += 25
    assert not audit_case(reference, case, FACILITIES["A"], 45, DELAYED)["passed"]


def test_cli_reproduces_costs_and_slot_thresholds(tmp_path):
    # At 45, V3 alone may charge in the first three W slots, but the battery
    # headroom caps its draw at 20/0.9 kWh. At least nine P plug slots remain,
    # more than A's eight. B can use three plugs and meet the 100 kW cap.
    # At 60, W contributes at most 20/0.9; P's 100 kWh cannot fill the rest.
    output_dir = tmp_path / "stress"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env.get("PYTHONPATH", "")])
    proc = subprocess.run(
        [sys.executable, "-m", "um_charging.eligibility_stress", "--config", "configs/eligibility_stress.json",
         "--output", str(output_dir)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=90,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    result = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    rows = {(row["facility"], row["delay_minutes"]): row for row in result["cases"]}
    delays = (0, 15, 30, 45, 60)
    assert len(result["cases"]) == 10
    assert set(rows) == {(label, delay) for label in FACILITIES for delay in delays}
    for label, last in [("A", 30), ("B", 45)]:
        assert len({rows[label, delay]["hardware_sha256"] for delay in delays}) == 1
        for delay in delays:
            row = rows[label, delay]
            assert row["planning_investment"] == (20 if label == "A" else 40)
            if delay <= last:
                assert row["status"] == "optimal"
                assert row["grid_energy_kwh"] == pytest.approx(400 / 3)
                assert row["operating_cost"] == pytest.approx(400 / 3)
                assert row["validation_passed"] is True
            else:
                assert row["status"] == "infeasible"
                assert row["grid_energy_kwh"] is None and row["operating_cost"] is None
                assert row["validation_passed"] is None
