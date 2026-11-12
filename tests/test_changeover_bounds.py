"""Attain the analytical two-plug endpoints with explicit, independently replayed timetables."""
import pytest

from um_charging.changeover_check import replay
from um_charging.facility_month import fixed_cases


def test_endpoint_witnesses_for_two_port_connectors():
    for leg, _, case in fixed_cases():
        if case["sites"][0]["interfaces"] != 2:
            continue
        hardware = {s["id"]: {"interfaces": s["interfaces"], "power_kw": s["available_power_kw"][0]}
                    for s in case["sites"]}
        h = 60 * leg / (50 * .9)
        delay = min(30 - h, 112.5 - 4 * h)
        # Each pair gives the trucks on port plugs 1 and 2 for the next quarter-hour.
        port = [("V1", "V2"), ("V1", "V2"), ("V1", "V3"), ("V2", "V3")]
        rows = []
        for t, pair in enumerate(port):
            for k, v in enumerate(pair):
                start = 180 + 15*t
                loss = delay if t and port[t-1][k] != v else 0
                rows.append({"site": "PORT", "connector": k+1, "slot": 12+t, "vehicle": v,
                             "segments": [[start+loss, start+15, 50]]})
        # Work backwards from the common terminal SOC. V3 releases its
        # warehouse plug at t=90, leaving a full quarter-hour before V1.
        warehouse_minutes = [2*h-45, 2*h-45+delay, 2*h-30+delay]
        for t in (4, 5):
            rows.append({"site": "WAREHOUSE", "connector": 1, "slot": t, "vehicle": "V3",
                         "segments": [[15*t, 15*t+15, 50*warehouse_minutes[2]/30]]})
        for k, truck in enumerate(("V1", "V2")):
            rows.append({"site": "WAREHOUSE", "connector": k+1, "slot": 7, "vehicle": truck,
                         "segments": [[105,120,50*warehouse_minutes[k]/15]]})
        audit = replay(case, hardware, delay, rows)
        assert audit["trip_count"] == 6
        assert all(trace[-1] == pytest.approx(100) for trace in audit["energy_kwh"].values())
        assert [x["gap_minutes"] for x in audit["changes"] if x["site"] == "PORT"] == pytest.approx([delay, delay])
        if leg > 20:
            assert audit["site_peak_kw"]["WAREHOUSE"] == pytest.approx(75)
        else:
            assert audit["energy_kwh"]["V3"][8] == pytest.approx(100)
