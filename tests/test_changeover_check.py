"""Small constructive connector schedules and targeted replay failures."""
from copy import deepcopy

import pytest

from um_charging.changeover_check import replay
from um_charging.facility_month import fixed_cases


@pytest.fixture
def port_schedule():
    _, _, case = next(fixed_cases())
    hardware = {"PORT": {"interfaces": 3, "power_kw": 150}, "WAREHOUSE": {"interfaces": 1, "power_kw": 75}}
    rows = [{"site": "PORT", "connector": i, "slot": t, "vehicle": v["id"],
             "segments": [[15 * t, 15 * (t + 1), 40 / .9]]}
            for i, v in enumerate(case["vehicles"], start=1) for t in range(12, 16)]
    return case, hardware, rows


def test_one_truck_per_connector_needs_no_change(port_schedule):
    case, hardware, rows = port_schedule
    audit = replay(case, hardware, 240, rows[::-1])
    assert audit["passed"] and audit["change_count"] == 0 and audit["trip_count"] == 6
    assert audit["site_peak_kw"]["PORT"] == pytest.approx(120 / .9)
    assert audit["site_energy_kwh"]["PORT"] == pytest.approx(120 / .9)
    for trace in audit["energy_kwh"].values():
        assert trace[4] == pytest.approx(80)
        assert trace[12] == pytest.approx(60)
        assert trace[-1] == pytest.approx(100)


def test_two_independent_changeovers_can_overlap(port_schedule):
    case, hardware, rows = port_schedule
    for r in rows:
        if r["connector"] in (1, 2):
            seg = r["segments"][0]
            seg[2] *= 60 / 58
            if r["slot"] >= 14:
                r["connector"] = 3 - r["connector"]
            if r["slot"] == 14:
                seg[0] += 2
    checked = replay(case, hardware, 2, rows)
    assert [e["gap_minutes"] for e in checked["changes"]] == [2, 2]
    with pytest.raises(ValueError, match="changeover gap"):
        replay(case, hardware, 2.1, rows)
    # Cutting off power early in the previous slot does not end physical occupancy.
    for r in rows:
        if r["vehicle"] != "V3" and r["slot"] == 13:
            r["segments"][0][1] -= 3
    with pytest.raises(ValueError, match="changeover gap"):
        replay(case, hardware, 5, rows)


def test_unused_slot_counts_toward_gap(port_schedule):
    case, hardware, rows = port_schedule
    hardware["PORT"]["interfaces"] = 4
    for r in rows:
        if r["vehicle"] == "V1" and r["slot"] >= 13:
            r["connector"] = 4
        if r["vehicle"] == "V2" and r["slot"] >= 14:
            r["connector"] = 1
    assert replay(case, hardware, 15, rows)["changes"][0]["gap_minutes"] == 15
    with pytest.raises(ValueError, match="changeover gap"):
        replay(case, hardware, 15.5, rows)


def test_power_limit_at_an_interior_event(port_schedule):
    case, hardware, rows = port_schedule
    hardware["PORT"]["power_kw"] = 136
    rows[0]["segments"] = [[180, 187.5, 50], [187.5, 195, 80 / .9 - 50]]
    with pytest.raises(ValueError, match="Instantaneous site power"):
        replay(case, hardware, 0, rows)


@pytest.mark.parametrize("fault,reason", [
    ("out_of_window", "eligible dwell"), ("double_plug", "Vehicle assigned"),
    ("double_connector", "Physical connector assigned"), ("wrong_id", "Invalid connector ID"),
    ("undercharge", "Terminal SOC"), ("overlap", "Segment outside slot"),
    ("overpower", "Truck power"), ("nonfinite", "Nonfinite"),
])
def test_reject_corrupt_schedule(port_schedule, fault, reason):
    case, hardware, rows = port_schedule
    row = rows[0]
    if fault == "out_of_window":
        row.update(slot=4, site="WAREHOUSE", segments=[[60, 75, 40 / .9]])
    elif fault == "double_plug":
        rows.append({**deepcopy(row), "connector": 2})
    elif fault == "double_connector":
        row["connector"] = 2
    elif fault == "wrong_id":
        row["connector"] = 0
    elif fault == "undercharge":
        rows.pop()
    elif fault == "overlap":
        row["segments"].append([183, 185, 5])
    elif fault == "overpower":
        row["segments"][0][2] = 51
    elif fault == "nonfinite":
        row["segments"][0][2] = float("nan")
    with pytest.raises(ValueError, match=reason):
        replay(case, hardware, 0, rows)
