"""Write each holdout certificate and replay the recorded experiment without optimization."""

import gzip
import json
from time import perf_counter

from . import site_sizing as ss
from .__main__ import digest
from .holdout_service import audit_service_certificate, solve_service_day


class WallLimit(Exception):
    pass


class Certificates:
    def __init__(self, path, deadline, *, replay=False):
        self.path = path
        self.deadline = deadline
        self.replay = replay
        self.records = []
        self.expected = []
        if replay:
            with (path / "solves.jsonl").open(encoding="utf-8") as stream:
                self.expected = [json.loads(line) for line in stream]

    def call(self, sample, period, design, caps, *, fixed=None, day=None, locked=None, reference=()):
        service = day is not None
        number = len(self.records) + 1
        week = period.days[0]["week_start"]
        request = dict(sample=sample, week=week, design=design.label, caps=list(caps),
                       phase="service" if service else "dispatch", day=day,
                       duties=[list(k) for k in sorted(reference if service else fixed)],
                       locked=[[d, v, chosen] for (d, v), chosen in sorted((locked or {}).items())])
        file = self.path / f"{number:04d}.json.gz"
        if self.replay:
            if number > len(self.expected):
                raise WallLimit("End of recorded calls")
            row = self.expected[number - 1]
            if row["request"] != request or row["sha256"] != digest(file) or row["file"] != file.name:
                raise ValueError(f"Changed call or certificate at {file.name}")
            with gzip.open(file, "rt", encoding="utf-8") as stream:
                result = json.load(stream)
        else:
            if perf_counter() >= self.deadline:
                raise WallLimit("Formal wall-clock budget exhausted")
            if service:
                result = solve_service_day(period, design, day, locked, reference, self.deadline)
            else:
                result = ss.solve(period, design, caps=caps, fixed=fixed, deadline=self.deadline)
                stats = result["stats"]
                if (stats["status_code"] == 1 and "time limit" in stats["message"].lower()
                        and result["audit"] is not None and stats["absolute_gap"] is not None
                        and stats["absolute_gap"] <= ss.TIMEOUT_COST_GAP_EUR + 1e-9):
                    stats["status"] = "bounded"
            with gzip.open(file, "xt", encoding="utf-8", compresslevel=1) as stream:
                json.dump(result, stream, allow_nan=False, separators=(",", ":"))
        stats = result["stats"]
        if result["audit"] is not None:
            checked = ss.meter_replay(period, design.hardware(), ss.eb.DEFAULT_SPEC, caps, result, physical=service)
            if json.dumps(checked, sort_keys=True) != json.dumps(result["audit"], sort_keys=True) or not checked["passed"]:
                raise ValueError(f"Independent replay differs for {file.name}")
            selected = ss.eb.selected(result)
            if service:
                audit_service_certificate(period, day, locked, reference, result)
                if any((key in selected) != choice for key, choice in locked.items()):
                    raise ValueError(f"Prior date selection changed at {file.name}")
            elif selected != fixed:
                raise ValueError(f"Dispatch served different duties at {file.name}")
        if not self.replay:
            row = dict(file=file.name, sha256=digest(file), request=request, status=stats["status"],
                       seconds=stats["seconds"], audited=result["audit"] is not None)
            with (self.path / "solves.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, allow_nan=False) + "\n")
            print(f"{number:04d} {sample} {week} {day or 'dispatch'} {design.label} "
                  f"{caps} {stats['status']} {stats['seconds']:.3f}s", flush=True)
        elif row["status"] != stats["status"] or row["audited"] != (result["audit"] is not None):
            raise ValueError(f"Ledger differs at {file.name}")
        self.records.append(row)
        return result
