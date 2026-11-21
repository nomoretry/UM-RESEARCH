from copy import deepcopy
from datetime import datetime, timedelta
import math

import pytest

from test_site_sizing import two_sites
from um_charging import energy_boundary as eb
from um_charging import holdout_gap_sensitivity as gap
from um_charging.holdout_evidence import Certificates, WallLimit


def _warehouse(minutes, energy):
    template = two_sites(energy)
    days = deepcopy(template.days)
    d = days[0]
    d["week_start"] = d["date"]
    truck, = d["vehicles"]
    truck["vehicle_id"] = "1"
    stop = truck["stops"][0]
    t = datetime.fromisoformat(d["start"]) + timedelta(minutes=60 + minutes)
    stop.update(end=t.isoformat(), next_departure=t.isoformat())
    return eb.Period(days, template.prices)


def test_actual_hardware_with_software_quarter_cap_round_trips(tmp_path):
    period = _warehouse(6, 1.8)
    design = gap.ss.Design(1, 20, 20)
    # Disable the port to isolate two kWh in the six released warehouse minutes.
    caps = (0, 15)
    log = Certificates(tmp_path, math.inf)
    request = dict(day=min(period.cases), reference=set(), locked={})
    result = log.call("toy", period, design, caps, **request)
    assert result["stats"]["completed_bounds"] == [1, 1]
    assert result["audit"]["site_peak_kw"]["WAREHOUSE"] == pytest.approx(20.)
    assert result["audit"]["site_quarter_peak_kw"]["WAREHOUSE"] == pytest.approx(8.)
    assert log.records[0]["request"]["design"] == "p1-20-w20"
    assert log.records[0]["request"]["caps"] == [0, 15]
    replay = Certificates(tmp_path, math.inf, replay=True)
    assert replay.call("toy", period, design, caps, **request)["stats"] == result["stats"]
    weak = gap.ss.Design(1, 20, 15)
    assert log.call("toy", period, weak, caps, **request)["stats"]["completed_bounds"] == [0, 0]
    full_window = _warehouse(15, 3.6)
    assert log.call("toy", full_window, design, caps, **request)["stats"]["completed_bounds"] == [0, 0]
    assert log.call("toy", full_window, design, (0, 20), **request)["stats"]["completed_bounds"] == [1, 1]


def _previous(periods):
    rows = []
    for p in periods:
        for day in p.days:
            date = day["date"]
            trucks = sorted(v for d, v in p.keys if d == date)
            old = [v for v in trucks if (date, v) != gap.TARGET]
            rows.append(dict(date=date, registered=trucks, facilities={d.label: old for d in gap.PORT_ONLY}))
    starts = {d.label: {"options": [dict(design=gap.ss.Design(1, d.port_kw, 15).label,
                                         fixed_R_status="feasible")]} for d in gap.PORT_ONLY}
    return dict(main=dict(daily=rows, outside=[]), repairs=dict(starts=starts))


def test_window_identity_full_order_and_partial_certificates():
    periods = gap.hi.load_periods()
    before = _previous(periods)
    lost = next(k for k in sorted(periods[0].keys) if k[1] == "5")

    class Log:
        def __init__(self, budget=196):
            self.calls = []
            self.budget = budget

        def call(self, sample, period, design, caps, *, day, locked, reference):
            if len(self.calls) >= self.budget:
                raise WallLimit()
            self.calls.append((design, caps, day))
            states = [dict(date=d, vehicle_id=v, served=(d, v) != lost and
                           (design not in gap.PORT_ONLY or (d, v) != gap.TARGET))
                      for d, v in period.keys]
            return dict(states=states, stats={"status": "certified"}, audit={"passed": True})

    log = Log()
    strict = gap.run_sensitivity(log, before, lambda _: None)
    assert strict["status"] == "complete" and strict["service_calls"] == len(log.calls) == 196
    assert strict["window_audit"]["disabled_intervals"] == 20
    assert strict["window_audit"]["trip_pairs"] == 17 and strict["window_audit"]["vehicle_ids"] == ["5"]
    assert strict["window_audit"]["trip_count"] == 282
    assert strict["registration_lost"] == [list(lost)] and not strict["registration_gained"]
    assert strict["target_gap"]["port_only_gap_persists"] and strict["port_only_insufficient"]
    assert [r["status"] for r in strict["configs"]] == ["service_gap"] * 2 + ["matched"] * 4
    assert all(r["lost_vs_main"] == [list(lost)] for r in strict["configs"])
    assert strict["configs"][-1]["caps_kw"] == [40, 15] and strict["configs"][-1]["design"] == "p1-40-w20"
    assert all((design, caps) == (gap.REPAIRED[1], (40, 15)) for design, caps, _ in log.calls[-28:])
    partial = gap.run_sensitivity(Log(29), before, lambda _: None)
    assert partial["wall_limit_reached"] and partial["status"] == "unresolved"
    assert partial["registered_count"] == 62 and partial["service_calls"] == 29
    assert partial["configs"][0]["served_count"] is None
    assert partial["configs"][0]["certified_count"] > 0
    assert partial["configs"][0]["lost_vs_main"] == [list(lost)]
    assert partial["target_gap"]["port_only_gap_persists"] is None
