"""Post-opening sensitivity of registration, rated facility selection and service."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from copy import copy
from datetime import datetime, timedelta
from functools import partial
import gzip
import math
import os
from pathlib import Path
import random
import subprocess
import sys
from time import monotonic
from unittest.mock import patch

from . import m10_evidence as evidence, m10_final_evidence as final, m11_boundary
from . import m11_external_evidence as native, m11_external_inputs as inputs
from . import m11_external_study as study, m11_rules as rules, service_gap, site_sizing as ss
from .m10_policy_evidence import _equals, _meter_summary
from .m11_external_evidence import Ledger, utc
from .m11_external_seal import put
from .m11_rule_evidence import period_digest


ORDER = ("L0", "W", "L30", "L15", "E110", "E90", "L60")
COHORTS = {"1-5": "rehearsal/1-5", "6-10": "formal/6-10", "11-15": "formal/11-15"}
RELEASE = {"L0": 0, "L15": 15, "L30": 30, "L60": 60}
FACTORS = {"E90": .9, "E110": 1.1}


def sealed_selection(root):
    """Rebuild the original selection exclusively from its native certificates."""
    root = Path(root)
    periods = inputs.periods(inputs.read(root / "stage2" / "tasks.json"))
    ledger = Ledger(root / "evidence", None, verify=True)
    result = study.select(periods, ledger, primary=True)
    sealed = inputs.read(root / "stage2" / "selection.json")
    for field in ("reference", "choices", "bills"):
        if result[field] != sealed[field]:
            raise ValueError(f"S0 regression differs in {field}")
    return {basis: {label: [result["bills"][label][basis][bound] for bound in ("lower", "upper")]
                    for label in labels} for basis, labels in result["choices"].items()}


def periods_for(root, code):
    def convert(period):
        if code in RELEASE:
            return ss.eb.Period(period.days, period.prices, warehouse_release_min=RELEASE[code])
        if code in FACTORS:
            return rules.scaled(period, FACTORS[code])
        if code not in ("S0", "W"):
            raise ValueError(code)
        return period
    return [[convert(p) for p in inputs.periods(inputs.read(root / stage / "tasks.json"))]
            for stage in ("stage2", "stage3")]


@contextmanager
def boundary(code):
    if code != "W":
        yield
        return
    physical_replay = ss.fc.replay

    def weekly_replay(period, hardware, spec, delay, result, *, physical=False):
        audited = physical_replay(period, hardware, spec, delay, result, rule="weekly", physical=physical)
        m11_boundary._segments(period, "weekly", result)
        return audited

    # Each worker handles one specification at a time; model and independent audit
    # both use the previously registered weekly convention for the same request.
    with patch.object(ss, "_levels", partial(m11_boundary._levels, "weekly")), patch.object(ss.fc, "replay", weekly_replay):
        yield


def variant_work(folder, period, job, deadline):
    with boundary(job["specification"]):
        return native.work(folder, period, job, deadline)


class SpecLedger(Ledger):
    def __init__(self, folder, deadline, code):
        super().__init__(folder, deadline, worker=variant_work)
        self.code = code

    def batch(self, pairs):
        bound = [(p, {**s, "specification": self.code}) for p, s in pairs]
        with boundary(self.code):
            return super().batch(bound)


def failure_rows(periods, ref, services, code):
    if code != "W":
        diagnostics = study.diagnostic(periods, ref, services)
    else:
        diagnostics = []
        from .holdout_inputs import _segment_truck
        for label, rows in services.items():
            for p in periods:
                w = rules.week(p)
                if rows[w]["status"] != "infeasible":
                    continue
                groups = {}
                for day, vehicle in sorted(ref[w]):
                    groups.setdefault(vehicle, []).append((day, vehicle))
                failed = []
                for days in groups.values():
                    truck = _segment_truck(p, days)
                    ok, trace = service_gap.reachable(truck, ss.eb.DEFAULT_SPEC,
                                                       site_power_kw=dict(zip(ss.SITES, study.GRID[label].caps)))
                    # The final reserve is a lower bound. Excess energy is admissible.
                    if ok or (trace["cause"] == "single_truck_terminal_energy" and trace["high_kwh"] >= 150):
                        continue
                    gap = (150 if trace["cause"] == "single_truck_terminal_energy" else trace["low_kwh"]) - trace["high_kwh"]
                    failed.append(dict(days=days, detail=trace, deficit_kwh=gap))
                diagnostics.append(dict(week=w, design=label, failed_segments=failed))
    result = []
    for row in diagnostics:
        common = dict(week=row["week"], design=row["design"])
        if not row["failed_segments"]:
            result.append(dict(**common, constraint="joint_service", dates=None, upper_kwh=None, deficit_kwh=None))
        for seg in row["failed_segments"]:
            detail = seg["detail"]
            result.append(dict(**common, dates=[d for d, _ in seg["days"]], constraint=detail["cause"],
                               upper_kwh=detail["high_kwh"], deficit_kwh=seg["deficit_kwh"]))
    return result


def interval_bills(selection):
    return {basis: {name: [selection["bills"][name][basis][k] for k in ("lower", "upper")]
                    for name in names} for basis, names in selection.get("choices", {}).items()}


def calculate(code, cohort, source, directory, deadline):
    train, test = periods_for(source, code)
    ledger = SpecLedger(directory / "evidence", deadline, code)
    try:
        selection = study.select(train, ledger, primary=False)
        ref, journal = study.register(test, ledger)
        gate = study.gate(ref, 20)
        out = dict(spec=code, cohort=cohort, registered=[sum(map(len, x.values())) if None not in x.values() else None
                  for x in (selection["reference"], ref)], choices=interval_bills(selection), failures=[],
                  evaluation_feasible=None, evaluation_unresolved=None, construction_members=[])
        gates = [selection["registration_gate"], gate]
        if "unresolved" in gates or "not_evaluable" in gates:
            out["verdict"] = "未定" if "unresolved" in gates else "不可评"
        else:
            table = study.matrix(test, ref, study.GRID, ledger, "fixed_service")
            states = [study.service(rows.values()) for rows in table.values()]
            labels = selection["choices"]["new"]
            endpoint = study.annotate(dict(choices=labels, service=table, verdict=study.verdict(labels, table)))
            out.update(verdict=endpoint["verdict"], construction_members=endpoint["按构造"],
                       evaluation_feasible=states.count("feasible"), evaluation_unresolved=states.count("unresolved"),
                       failures=failure_rows(test, ref, {k:table[k] for k in labels}, code))
            put(directory, "test_service.json", table)
        put(directory, "selection.json", selection)
        put(directory, "registration.json", dict(reference=ref, journal=journal))
        return out
    finally:
        ledger.close()


def restricted(period, keys):
    p = copy(period)
    p.keys = set(map(tuple, keys))
    if not p.keys <= period.keys:
        raise ValueError("Unregistered input duty")
    return p


def max_request(period, label):
    return evidence.Request.make(period, study.GRID[label], "max_registered", study.GRID[label].caps)


def baseline_row(cohort, root, folder, deadline):
    train, test = periods_for(root, "S0")
    selection = inputs.read(root / "stage2" / "selection.json")
    endpoint = inputs.read(root / "stage3" / "primary.json")
    secondary = inputs.read(root / "stage4" / "secondary.json")
    labels = selection["choices"]["new"]
    label, = labels
    failed = failure_rows(test, endpoint["reference"], endpoint["service"], "S0")
    gaps = []
    for p in test:
        w = rules.week(p)
        if endpoint["service"][label][w]["status"] != "infeasible":
            continue
        keys = endpoint["reference"][w]
        scope = restricted(p, keys)
        req = max_request(scope, label)
        job = dict(input=period_digest(p), design=label, week=w, registered=keys, seconds=300)
        ident = evidence._hash(job)
        put(folder / "starts", ident + ".json", job)
        raw = evidence._solve(scope, req, monotonic() + (deadline-utc()).total_seconds())
        evidence.replay(scope, req, raw)
        body = dict(job=job, result=raw)
        evidence._publish(folder / "certificates" / (ident+".json.gz"),
                          gzip.compress(evidence._encoded(dict(body=body, sha256=evidence._hash(body))), mtime=0))
        gaps.append(dict(week=w, registered=len(keys), completed_bounds=raw["stats"]["completed_bounds"]))
    n = sum(map(len, endpoint["reference"].values()))
    missing = sum(g["registered"] - g["completed_bounds"][0] for g in gaps) if all(
        g["completed_bounds"][0] == g["completed_bounds"][1] for g in gaps) else None
    bills = interval_bills(selection)
    builds = inputs.read(ss.eb.ROOT / "studies/fleet-service/external_designs.json")["cohorts"][cohort]["designs"]
    viable = [(d["selection_bill"]["new"], name) for name, d in builds.items() if d["selection_bill"]
              and all(s == "feasible" for s in d["evaluation"].values())]
    best, other = min(viable)
    lo, hi = bills["new"][label]
    conversion = [(best[0]-hi)/(missing*52/7), (best[1]-lo)/(missing*52/7)] if missing else None
    return dict(spec="S0", cohort=cohort, registered=[sum(map(len,selection["reference"].values())),n],
                choices=bills, failures=failed, evaluation_feasible=len(secondary["evaluation_feasible"]),
                evaluation_unresolved=sum(study.service(rs.values()) == "unresolved" for rs in secondary["evaluation_service"].values()),
                verdict=endpoint["verdict"], construction_members=endpoint["按构造"], failed_weeks=gaps,
                completed=None if missing is None else n-missing, least_survivor=other, eur_per_additional_duty=conversion)


def sample_requests(archive):
    rng = random.Random(20261122)
    pool, mandatory = [], []
    for cohort in ("6-10", "11-15"):
        root = archive / COHORTS[cohort]
        stages = {}
        for i in (2,3,4):
            for ident in inputs.read(root / f"stage{i}/proofs.json"):
                stages.setdefault(ident,i)
        sel = inputs.read(root / "stage2/selection.json")
        cheapest = sorted(sel["bills"], key=lambda k: sel["bills"][k]["new"]["lower"])[:2]
        train, test = periods_for(root, "S0")
        normal = {period_digest(p) for p in train+test}
        rows = [r for r in inputs.read(root / "stage4/request_manifest.json")
                if r["input"] in normal and r["budget_s"] == 300 and r["id"] in stages]
        for name in cheapest:
            mandatory.append((cohort, rng.choice(sorted(r["id"] for r in rows if r["phase"]=="energy"
                              and stages[r["id"]]==2 and ss.Design(**r["design"]).label==name))))
        for stage, phase in [(3,"registration"), (4,"fixed_service")]:
            mandatory.append((cohort, rng.choice(sorted(r["id"] for r in rows if r["phase"]==phase and stages[r["id"]]==stage))))
        pool.extend((cohort, r["id"]) for r in rows)
    return mandatory + rng.sample(sorted(set(pool)-set(mandatory)), 20-len(mandatory))


def repeats(archive, directory, deadline):
    sample = sample_requests(archive)
    put(directory, "sample.json", sample)
    periods = {cohort: {period_digest(p): p for period in periods_for(archive/COHORTS[cohort],"S0") for p in period}
               for cohort in ("6-10","11-15")}
    checks = []
    for i in range(0,len(sample),8):
        with ProcessPoolExecutor(max_workers=8, max_tasks_per_child=1) as pool:
            jobs = []
            for cohort, ident in sample[i:i+8]:
                original = native.proof(archive/COHORTS[cohort]/"evidence", ident)
                job = original["job"]
                p = periods[cohort][job["input"]]
                folder = directory/cohort
                for sub in ("starts","certificates"):
                    (folder/sub).mkdir(parents=True,exist_ok=True)
                f = pool.submit(native.work,folder,p,job,deadline)
                jobs.append((cohort,ident,original,p,folder,f))
            for cohort,ident,orig,p,folder,f in jobs:
                f.result()
                new = native.proof(folder,ident)
                req = native.unpack(orig["job"])
                a,b = [_meter_summary(final._effective(p,req,item["result"])) for item in (orig,new)]
                checks.append(dict(cohort=cohort,id=ident,week=req.week,phase=req.phase,design=req.design.label,
                                   original=a,repeated=b,match=all(a[k]==b[k] for k in ("status","status_code","schedule_sha256"))
                                   and all(_equals(a[k],b[k]) for k in ("objective_lower","objective_upper","meter"))))
    put(directory,"comparison.json",checks)
    return checks


def verify_all(archive, output):
    counts = {}
    for folder in sorted((output/"cases").glob("*/*")):
        code,cohort = folder.parent.name,folder.name
        train,test = periods_for(archive/COHORTS[cohort],code)
        weeks = {rules.week(p):p for p in train+test}
        evidence_dir = folder/"evidence"
        finished = set()
        for file in sorted((evidence_dir/"certificates").glob("*.json.gz")):
            ident = file.name.split(".")[0]
            body = native.proof(evidence_dir,ident)
            job,raw = body["job"],body["result"]
            marker = inputs.read(evidence_dir/"starts"/(ident+".json"))
            if code=="S0":
                p = weeks[job["week"]]
                if job != marker or job["input"]!=period_digest(p):
                    raise ValueError("Maximum-service binding differs")
                evidence.replay(restricted(p,job["registered"]),max_request(p,job["design"]),raw)
            else:
                if marker["job"]!=job or job["specification"]!=code:
                    raise ValueError("Variant binding differs")
                with boundary(code):
                    native.replay(weeks[job["request"]["week"]],job,raw)
            finished.add(ident)
        starts = {f.stem for f in (evidence_dir/"starts").glob("*.json")}
        if not finished <= starts:
            raise ValueError("Missing request start")
        counts[code+"/"+cohort] = dict(replayed=len(finished),interrupted=sorted(starts-finished))
    for cohort in ("6-10","11-15"):
        folder = output/"repeats"/cohort
        lookup = {period_digest(p):p for phase in periods_for(archive/COHORTS[cohort],"S0") for p in phase}
        for file in (folder/"certificates").glob("*.json.gz"):
            body = native.proof(folder,file.name.split(".")[0])
            native.replay(lookup[body["job"]["input"]],body["job"],body["result"])
    put(output,"replay.json",counts)


def run(archive, output, deadline):
    os.environ.update(evidence.WORKER_ENV)
    put(output,"s0_regression.json",sealed_selection(archive/COHORTS["6-10"]))
    repeats_dir=output/"repeats"
    repeats_dir.mkdir()
    repeats(archive,repeats_dir,deadline)
    # Duration of native verification, the full tests and archive publication is
    # separate from the 300 seconds required to admit each new weekly request.
    solve_until = deadline-timedelta(minutes=9)
    stop = False
    for code in ("S0",*ORDER):
        for cohort,sub in COHORTS.items():
            folder=output/"cases"/code/cohort
            folder.mkdir(parents=True)
            try:
                if code=="S0":
                    for name in ("starts","certificates"):
                        (folder/"evidence"/name).mkdir(parents=True)
                    row=baseline_row(cohort,archive/sub,folder/"evidence",solve_until)
                else:
                    row=calculate(code,cohort,archive/sub,folder,solve_until)
            except ss.fc.StudyLimit as exc:
                put(folder,"stopped.json",dict(reason=str(exc),at=utc().isoformat()))
                stop = True
                break
            put(folder,"result.json",row)
            print(code,cohort,row["verdict"],utc().isoformat(),flush=True)
        if stop:
            break
    subprocess.run([sys.executable,"-B","-m",__spec__.name,"--archive",str(archive),
                    "--output",str(output),"--verify"],check=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--deadline",type=datetime.fromisoformat)
    parser.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    if args.verify:
        verify_all(args.archive,args.output)
    elif args.deadline and args.deadline.tzinfo:
        run(args.archive,args.output,args.deadline)
    else:
        parser.error("Supply an absolute timezone-aware deadline")
