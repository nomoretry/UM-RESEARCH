from types import SimpleNamespace

from um_charging.holdout_repair import REPAIRS, dispatch_repairs


class RecordingLog:
    def __init__(self, fail_at=None):
        self.fail_at = fail_at
        self.records = []

    def call(self, sample, period, design, caps, *, fixed):
        self.records.append(dict(file=f"{len(self.records) + 1:04d}.json.gz", sample=sample,
                                 design=design.label, caps=caps, fixed=fixed))
        code = 2 if self.fail_at == len(self.records) else 0
        return {"stats": {"status_code": code}}


def test_rated_contradiction_stops_at_the_first_failing_week():
    weeks = [SimpleNamespace(days=[{"week_start": w}], keys={(w, "1")}) for w in ("week1", "week2")]
    log = RecordingLog(fail_at=2)
    starts = []
    runs = {}
    failure = dispatch_repairs(log, weeks, {("week2", "1")}, runs, lambda _: None, lambda: starts.append(1))
    assert failure == dict(week="week2", design=REPAIRS[0].label, caps_kw=[20, 20], certificate="0002.json.gz")
    assert len(log.records) == 2 and starts == [1]
    assert [r["fixed"] for r in log.records] == [set(), {("week2", "1")}]


def test_dispatch_runs_each_hardware_cap_and_week_only_once():
    weeks = [SimpleNamespace(days=[{"week_start": w}], keys={(w, "1")}) for w in range(6)]
    log = RecordingLog()
    runs = {}
    assert dispatch_repairs(log, weeks, set(), runs, lambda _: None, lambda: None) is None
    assert len(log.records) == 24
    assert set(runs) == {(d.label, (d.port_kw, cap)) for d in REPAIRS for cap in (20, 15)}
    assert all(len(group) == 6 for group in runs.values())
