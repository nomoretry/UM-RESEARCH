import math

import pytest

from test_holdout_service import overnight
from um_charging import holdout
from um_charging.holdout_bills import FIXED
from um_charging.holdout_evidence import Certificates


def test_register_round_trip_replays_each_day_and_rejects_modified_file(tmp_path, monkeypatch):
    p = overnight({"1": 4.5, "2": 4.5})
    for day in p.days:
        day["week_start"] = min(p.cases)
    log = Certificates(tmp_path, math.inf)
    registered, ref = holdout.register(log, "toy", [p], lambda _: None)
    assert len(registered["daily"]) == 2 and len(log.records) == len(FIXED) * 2
    assert ref and registered["service_status"][holdout.ss.BASELINE.label] == "matched"

    def forbid_solver(*args, **kwargs):
        raise AssertionError("Certificate verification invoked a solver")
    monkeypatch.setattr("um_charging.holdout_evidence.solve_service_day", forbid_solver)
    archive = Certificates(tmp_path, math.inf, replay=True)
    assert holdout.register(archive, "toy", [p], lambda _: None) == (registered, ref)
    first = tmp_path / archive.records[0]["file"]
    first.write_bytes(first.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="certificate"):
        holdout.register(Certificates(tmp_path, math.inf, replay=True), "toy", [p], lambda _: None)
