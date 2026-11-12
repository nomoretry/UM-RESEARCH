import pytest

from um_charging.fleet_service import audit, immediate


def truck(energy, windows, start=20, end=30):
    return {"trips": [(start, end, energy, "leg")],
            "windows": [(a, b, "PORT") for a, b in windows]}


def hardware(interfaces=2):
    return {"PORT": {"interfaces": interfaces, "power_kw": 75.},
            "WAREHOUSE": {"interfaces": 1, "power_kw": 75.}}


def spans(result, vehicle):
    return [(r["start_min"], r["end_min"], r["power_kw"])
            for r in result["schedule"] if r["vehicle_id"] == vehicle]


def test_small_purchase_at_rated_power_with_hourly_settlement():
    case = {"trucks": {"A": truck(1.125, [(59.5, 75)], start=80, end=90)}}
    prices = [100., 200.] + [0.] * 22
    result = immediate(case, hardware(), prices)
    assert spans(result, "A") == [(59.5, 60, 50), (60, 61, 50)]
    replay = audit(case, hardware(), result["schedule"], prices)
    assert replay["passed"]
    assert replay["terminal_kwh"] == {"A": 150}
    assert replay["site_peak_kw"]["PORT"] == 50
    assert replay["site_energy_kwh"]["PORT"] == pytest.approx(1.25)
    assert replay["purchase_eur"] == pytest.approx((.5 * 100 + 1 * 200) * 50 / 60 / 1000)


def test_capacity_freed_mid_quarter_but_connector_reservation_persists():
    case = {"trucks": {"A": truck(1.125, [(0, 15)]), "B": truck(9, [(0, 15)])}}
    result = immediate(case, hardware(), [120.] * 24)
    assert spans(result, "A") == [(0, 1.5, 50)]
    assert spans(result, "B") == [(0, 1.5, 25), (1.5, 12.75, 50)]
    assert result["audit"]["site_peak_kw"]["PORT"] == 75
    assert result["audit"]["purchase_eur"] == pytest.approx((1.25 + 10) * 120 / 1000)
    assert result["audit"]["passed"]
    one = immediate(case, hardware(1), [120.] * 24)
    assert spans(one, "A") == [(0, 1.5, 50)]
    assert spans(one, "B") == []
    assert one["audit"]["completed_ids"] == ["A"]


def test_full_battery_mid_quarter_stops_until_after_the_trip():
    case = {"trucks": {"A": truck(200, [(0, 201), (210, 300)], start=201, end=210)}}
    result = immediate(case, hardware(), [100.] * 24)
    trace = spans(result, "A")
    assert result["audit"]["passed"]
    # 150 kWh of initial battery headroom at 45 battery kW lasts 200 minutes.
    assert max(end for start, end, _ in trace if start < 201) == pytest.approx(200)
    assert min(start for start, _, _ in trace if start >= 201) == 210
    assert max(end for _, end, _ in trace) == pytest.approx(210 + 50 / 45 * 60)
    assert result["audit"]["terminal_kwh"]["A"] == pytest.approx(150)
