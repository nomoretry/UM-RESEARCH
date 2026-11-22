"""Rehearse M10 on M9, or execute the committed second-holdout protocol."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic

from . import energy_boundary as eb, holdout_inputs as hi, site_sizing as ss
from .__main__ import checked_output, digest
from .m10_costs import _parameters
from .m10_final_bills import difference, immediate_disclosure, invoice
from .m10_final_evidence import FinalEvidence, FinalRequest, determinism_all
from .m10_final_holdout import (B, BASES, F20, F40, FULL, IMMEDIATE, MAIN, ROLLING, TARIFFS,
                                 VERIFIED_FAILURE, build_plan, execute, point_id, scenario_periods, week_of)
from .m10_final_repairs import physical_repairs, priced_repairs
from .m10_inputs import M9_REGISTRATION, _prices
from .m10_policies import _file_hash, _write
from .site_sizing_screen import without_solver


MATRIX_SHA256 = "1c89315d297715a3a00b7bed99dde23b2e278f25d3d34fc45fe0014d1552c574"
SEALED = {
    hi.WEEKS.with_name("second_holdout_weeks.json"):
        "532e45b1ab51d7940a29bbbf0ec9513bb7ed2a7c2b98e221b8aba81b7da40935",
    hi.PRICES.with_name("native_2022_second_holdout_prices.csv"):
        "bb6ce2edd4482c4c36f0e58a70b3ceef2db71ea264e8e2e7438b23d5035bd704",
}


def forbid_holdout(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        if Path(os.fsdecode(args[0])).name.casefold() in {p.name for p in SEALED}:
            raise PermissionError("The protected second holdout is excluded from rehearsal")


def _registration(path, source, matrix_sha):
    """Authorize input loading only from the committed addendum and frozen source."""
    path = path.resolve()
    if path.name != "PREREG_SECOND_HOLDOUT_ADDENDUM_2.md":
        raise ValueError("Expected the committed second holdout addendum number 2")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(path.parent), *args])
    root = Path(git("rev-parse", "--show-toplevel").decode().strip())
    if git("remote").strip() or not (root / ".git").is_dir() or root == eb.ROOT:
        raise ValueError("The committed addendum must be in the offline archive")
    rel = path.relative_to(root).as_posix()
    commit = git("log", "-1", "--diff-filter=A", "--format=%H", "--", path.name).decode().strip()
    body = path.read_bytes()
    if (not commit or git("show", f"{commit}:{rel}") != body
            or source.encode() not in body or matrix_sha.encode() not in body):
        raise ValueError("The committed addendum does not bind this source or matrix")
    return dict(commit=commit, sha256=hashlib.sha256(body).hexdigest())


def _sealed_periods():
    paths = list(SEALED)
    for path, expected in SEALED.items():
        if digest(path) != expected:
            raise ValueError(f"Protected input changed: {path.name}")
    raw = eb.read_json(paths[0])
    days = raw["days"]
    first = datetime(2021, 12, 20)
    if [d["date"] for d in days] != [(first+timedelta(days=i)).date().isoformat() for i in range(49)]:
        raise ValueError("Expected the complete seven-week sealed calendar")
    curves = _prices(days, paths[1])
    chains, links, _ = eb.calendar(days)
    expected = [8, 0, 6, 14, 10, 9, 10]

    def periods():
        groups = eb.components(days, links)
        if (len(groups) != 7 or any(len(w) != 7 or len({d["week_start"] for d in w}) != 1 for w in groups)
                or [sum(len(d["vehicles"]) for d in w) for w in groups] != expected):
            raise ValueError("Calendar weeks or eligible duties differ from pre-registration")
        return [eb.Period(deepcopy(w), {d["date"]:curves[d["date"]] for d in w}) for w in groups]

    main = periods()
    blocked = raw["parking_bounds"]["mapped_intervals_at_least_1km"]
    hi._exclude_mapped_intervals(days, blocked, expected_count=30, expected_vehicles={"4", "5"})
    if eb.calendar(days)[:2] != (chains, links):
        raise ValueError("Parking eligibility altered registered carry-over links")
    return main, periods(), {p.name: v for p, v in SEALED.items()}, len(blocked)


def _rehearsal_periods():
    main, parking = hi.load_periods(), hi.load_periods(sensitivity=True)
    return main, parking, {p.name: v for p, v in hi.INPUT_HASHES.items()}, 20


def _rehearsal_check(outcome):
    historical = eb.read_json(M9_REGISTRATION)
    previous = {(row["date"], vehicle) for row in historical["main"]["daily"] for vehicle in row["registered"]}
    achieved = set(map(tuple, outcome["reference"]))
    if not outcome["reference_complete"] or len(previous) != 52 or achieved != previous:
        raise ValueError(("Rehearsal disagrees with the published M9 baseline registration",
                          sorted(achieved - previous), sorted(previous - achieved)))
    expected_parking = {(row["date"], vehicle) for row in historical["sensitivity"]["daily"]
                        for vehicle in row["registered"]}
    result = outcome["sensitivities"]["parking_gap"]["reference_by_week"]
    if not all(group is not None for group in result.values()):
        raise ValueError("The rehearsal's parking registration was not certified")
    observed_parking = {tuple(key) for group in result.values() for key in group}
    if observed_parking != expected_parking:
        raise ValueError(("Rehearsal disagrees with M9 parking registration",
                          sorted(observed_parking - expected_parking), sorted(expected_parking - observed_parking)))
    return dict(main_count=len(previous), parking_count=len(expected_parking), matching_exact_vehicle_days=True)


def settle_outcome(periods, outcome):
    points = {p["id"]: p for p in outcome["points"]}
    parameters = _parameters(periods)
    bills, disclosure = [], []
    prepared, surplus = {}, {}
    for alias in outcome["billing_roles"]:
        p = points[alias["point_id"]]
        d = ss.Design(p["port_plugs"], p["port_kw"], p["warehouse_kw"])
        tariff, basis = alias["tariff"], alias["basis"]
        mode = p["policy"]
        key = p["id"], tariff, basis, alias["uses_baseline_assets"]
        if key not in prepared:
            prepared[key] = invoice(periods, d, p["weeks"], scenario=tariff, basis=basis,
                baseline=alias["uses_baseline_assets"], immediate=mode == IMMEDIATE, parameters=parameters
                ) if p["bill_admitted"] else None
        terminal = None
        if mode == IMMEDIATE and (p["id"], tariff) not in surplus:
            if all(w["audit"] is not None for w in p["weeks"]):
                surcharge = immediate_disclosure(periods, p["weeks"], tariff, parameters=parameters)
            else:
                surcharge = dict(status="unregistered_week", annual={"terminal_excess_cost_eur_2025": None},
                                 days=[row for w in p["weeks"] if w["audit"] is not None for row in w["days"]],
                                 missing_weeks=[w["week"] for w in p["weeks"] if w["audit"] is None])
            surplus[p["id"], tariff] = surcharge
            disclosure.append(dict(point_id=p["id"], scenario=tariff, **surplus[p["id"], tariff]))
        if mode == IMMEDIATE:
            terminal = surplus[p["id"], tariff]["annual"]["terminal_excess_cost_eur_2025"]
        elif p["bill_admitted"]:
            terminal = 0.
        ranked = prepared[key]
        rated = alias["rated_counterfactual_point_id"]
        if ranked is None and not alias["fallback"] and rated and rated != p["id"] and points[rated]["bill_admitted"]:
            counterfactual = invoice(periods, d, points[rated]["weeks"], scenario=tariff, basis=basis,
                                     baseline=alias["uses_baseline_assets"], parameters=parameters)
        else:
            counterfactual = None
        bills.append(dict(**alias, design=d.label, service=p["service"], whole_invoice=ranked,
                          terminal_surplus_included_eur_2025=terminal, rated_comparator=counterfactual))
    if len(bills) != len(TARIFFS)*len(BASES)*10:
        raise ValueError("An archived fee policy or role is missing")
    comparisons, ranks = [], []
    for tariff in TARIFFS:
        for basis in BASES:
            group = {r["role"]: r for r in bills if (r["tariff"], r["basis"]) == (tariff, basis)}
            eligible = {name: r["whole_invoice"] for name,r in group.items() if r["whole_invoice"] is not None}
            for role, row in group.items():
                own = row["whole_invoice"]
                ranks.append(dict(tariff=tariff, basis=basis, role=role,
                    strictly_cheaper_roles=sorted(name for name, other in eligible.items()
                        if own and other["annual_total_upper"] < own["annual_total_lower"]),
                    same_service_bill=own is not None))
            if tariff != "official":
                continue
            for role in ("I", "D40"):
                left, right = group[role], group["F40"]
                raw = difference(left["whole_invoice"], right["whole_invoice"])
                adjusted = difference(left["whole_invoice"], right["whole_invoice"],
                                      disclosure=left["terminal_surplus_included_eur_2025"])
                comparisons.append(dict(role=role, comparator="F40", tariff=tariff, basis=basis,
                                        including_surplus=raw, excluding_disclosed_surplus=adjusted,
                                        status="comparable" if raw is not None else "unidentified"))
    return dict(annual=bills, immediate_disclosure=disclosure, official_differences=comparisons, rankings=ranks)


def _repairs(periods, outcome, ledger, billing):
    by_point = {p["id"]:p for p in outcome["points"]}
    observed = {role:by_point[identifier]["service"] for role, identifier in (
        ("S1", point_id(ROLLING,F40,F40.caps)), ("S2", point_id(IMMEDIATE,ss.Design(2,100,20),(100,20))),
        ("S3", point_id(IMMEDIATE,F40,F40.caps)))}
    if not outcome["reference_complete"]:
        return dict(physical={"status":"unregistered_week"}, priced={"status":"unregistered_week"},
                    secondary_service=observed)
    reference = set(map(tuple, outcome["reference"]))
    initial, failures = {}, {}
    for p in outcome["points"]:
        if p["policy"] != FULL:
            continue
        d = ss.Design(p["port_plugs"], p["port_kw"], p["warehouse_kw"])
        if tuple(p["caps_kw"]) != d.caps:
            continue
        for w in p["weeks"]:
            if "fixed_service_status" in w:
                initial[d, w["week"]] = dict(status=w["fixed_service_status"], proof_id=w["proof_id"])
        if d in (F20, F40) and p["failed_weeks"]:
            failures[d] = set(p["failed_weeks"])

    def accept(req, new, stats):
        if stats["status"] == "unresolved" and new:
            ledger.record_unresolved(req)
        ledger.check()

    def call(p, d, enrolled, phase):
        w = week_of(p)
        if not enrolled:
            from .m10_final_holdout import _zero
            return _zero(p)
        req = FinalRequest(MAIN, w, d, phase, d.caps, fixed=enrolled)
        new = ledger.is_new(req)
        (proof, result), = ledger.batch([req])
        stats = result["stats"]
        accept(req, new, stats)
        return dict(week=w, status=stats["status"], proof_id=proof, audit=result["audit"],
                    purchase_lower=stats["objective_lower"], purchase_upper=stats["objective_upper"])

    def daily(p, d, enrolled):
        if not enrolled:
            return dict(status="certified", omitted=[], proof_ids=[])
        locked, ids = {}, []
        for day in sorted({date for date,_ in p.keys}):
            req = FinalRequest(MAIN, week_of(p), d, "registration", d.caps, date=day,
                               locked=locked, reference=enrolled)
            new = ledger.is_new(req)
            (proof, result), = ledger.batch([req])
            stats = result["stats"]
            ids.append(proof)
            accept(req, new, stats)
            if stats["status"] != "certified":
                return dict(status="unresolved", proof_ids=ids)
            selected = eb.selected(result)
            locked.update({key:key in selected for key in p.keys if key[0] == day})
        return dict(status="certified" if all(locked[key] for key in enrolled) else "infeasible",
                    omitted=sorted(key for key in enrolled if not locked[key]), proof_ids=ids)

    physical = physical_repairs(periods, reference, failures, initial,
                                lambda p,d,r:call(p,d,r,"fixed_service"), daily)
    primary = outcome["primary"]["classification"]
    if primary == VERIFIED_FAILURE:
        old = {r["basis"]:r["whole_invoice"] for r in billing["annual"]
               if r["role"] == "F40" and r["tariff"] == "official"}
        priced = priced_repairs(periods, reference, failures[F40], initial,
                                lambda p,d,r:call(p,d,r,"fixed_service"),
                                lambda p,d,r:call(p,d,r,"energy"), complete_reference=old)
    else:
        priced = dict(status="not_triggered", premium_eur_2025=0. if primary == "passed" else None)
    return dict(physical=physical, priced=priced, secondary_service=observed)


def _outputs(target, result, billing, repairs, ledger, rehearsal_check):
    _write(target/"outcome.json", result)
    _write(target/"repairs.json", repairs)
    _write(target/"billing.json", billing)
    _write(target/"new_solves.csv", ledger.records)
    _write(target/"annual.csv", [{**{k:r[k] for k in (
        "role", "policy", "tariff", "basis", "point_id", "frozen_point_id", "fallback", "design", "service")},
        **(r["whole_invoice"] or {}), "terminal_surplus_included_eur_2025":r["terminal_surplus_included_eur_2025"]}
        for r in billing["annual"]])
    _write(target/"official_differences.csv", billing["official_differences"])
    compact = {key:result.get(key) for key in ("status", "primary", "stop_reporting")}
    compact.update(registered_days=len(result["reference"]), native_requests=len(ledger.records),
                   rehearsal_check=rehearsal_check)
    _write(target/"summary.json", compact)
    return compact


def run(matrix_path, folder, *, rehearsal, addendum=None, mode="output", cutoff=None, workers=8,
        breakpoint_archive=None):
    matrix_path, folder = Path(matrix_path).resolve(), Path(folder).resolve()
    matrix_sha = digest(matrix_path)
    if matrix_sha != MATRIX_SHA256:
        raise ValueError("The matrix differs from the one sealed before rehearsal")
    matrix = json.loads(matrix_path.read_bytes())
    build_plan(matrix)
    verify = mode == "verify"
    if cutoff is None and not verify:
        raise ValueError("An explicit offset-aware round deadline is required")
    if cutoff is not None and cutoff.tzinfo is None:
        raise ValueError("The deadline must include its UTC offset")
    deadline = math.inf if cutoff is None else monotonic() + (cutoff-datetime.now(timezone.utc)).total_seconds()
    if deadline <= monotonic():
        raise ss.fc.StudyLimit("The round time has elapsed")
    state = ss.source_state()
    if not verify and state["dirty"]:
        raise ValueError("The execution source must be committed before the formal run")
    binding = dict(matrix_sha256=matrix_sha, mode="M9_rehearsal" if rehearsal else "second_holdout")
    if mode == "output":
        checked_output(folder, eb.ROOT)
    elif not (folder/"binding.json").is_file():
        raise ValueError("A bound output directory is required")
    if mode == "resume" and (folder/"manifest.json").exists():
        raise ValueError("Use read-only verification for a sealed execution")
    repeat_source = None
    if rehearsal:
        sys.addaudithook(forbid_holdout)
        if breakpoint_archive is None:
            raise ValueError("Rehearsal requires the phase B ledger for the joint repeat sample")
        source = Path(breakpoint_archive).resolve()
        repeat_source = source/"certificates"
        seal = source/"summary.json"
        if not repeat_source.is_dir() or not seal.is_file():
            raise ValueError("The sealed breakpoint evidence is missing")
        prior = json.loads(seal.read_bytes())
        if prior["status"] != "complete" or len(list(repeat_source.glob("*.json.gz"))) != prior["native_requests"]:
            raise ValueError("The breakpoint ledger is incomplete")
        binding["breakpoint_summary_sha256"] = digest(seal)
        main, parking, hashes, count = _rehearsal_periods()
    else:
        binding["addendum"] = _registration(addendum, state["commit"], matrix_sha)
        main, parking, hashes, count = _sealed_periods()
    binding.update(input_sha256=hashes, parking_exclusions=count, calendar_weeks=len(main))
    scenarios = scenario_periods(main, parking)
    if mode == "output":
        folder.mkdir()
        _write(folder/"binding.json", dict(**binding, source=state["commit"]))
    saved = json.loads((folder/"binding.json").read_bytes())
    if (saved != dict(**binding, source=saved["source"]) or (not verify and saved["source"] != state["commit"])):
        raise ValueError("The stored execution binding differs from this matrix, source, or data")

    def progress(line):
        print(line, flush=True)
        if not verify:
            with (folder.parent/"PROGRESS.md").open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(f"- {datetime.now().astimezone().isoformat()} {line}\n")

    with FinalEvidence(folder, scenarios, deadline=deadline, verify=verify, workers=workers, scope=binding) as ledger:
        if verify:
            manifest = json.loads((folder/"manifest.json").read_bytes())
            if manifest["binding"] != saved or any(_file_hash(folder/k) != v for k,v in manifest["products"].items()):
                raise ValueError("A sealed product or binding changed")
            with without_solver():
                result = execute(scenarios, matrix, ledger)
                billing = settle_outcome(main, result)
                repairs = _repairs(main, result, ledger, billing)
                repeats = determinism_all([ledger], folder, deadline, breakpoint_dir=repeat_source, verify=True)
            for key, actual in (("outcome", result), ("billing", billing), ("repairs", repairs)):
                if json.loads(json.dumps(actual, ensure_ascii=False, allow_nan=False)) != json.loads((folder/(key+".json")).read_bytes()):
                    raise ValueError(f"Independent replay differs for {key}")
            if repeats != json.loads((folder/"determinism.json").read_bytes()):
                raise ValueError("Independent repeat audit differs")
            if ledger.records != json.loads((folder/"request_inventory.json").read_bytes()):
                raise ValueError("Archived native request inventory changed")
            return dict(status="verified", native_requests=len(ledger.records), audit=ledger.verify_all())
        result = execute(scenarios, matrix, ledger, save=lambda k,v:_write(folder/(k+".json"), v), progress=progress)
        if result["status"] != "complete":
            _write(folder/"new_solves.csv", ledger.records)
            return dict(status="stopped", reason=result["reason"], native_requests=len(ledger.records))
        check = _rehearsal_check(result) if rehearsal else None
        billing = settle_outcome(main, result)
        try:
            repairs = _repairs(main, result, ledger, billing)
        except ss.fc.StudyLimit as exc:
            _write(folder/"new_solves.csv", ledger.records)
            return dict(status="stopped", reason=str(exc), native_requests=len(ledger.records))
        ledger.check()
        summary = _outputs(folder, result, billing, repairs, ledger, check)
        _write(folder/"replay.json", ledger.verify_all())
        _write(folder/"request_inventory.json", ledger.records)
        repeats = determinism_all([ledger], folder, deadline, breakpoint_dir=repeat_source)
        _write(folder/"determinism.json", repeats)
        files = ("outcome.json", "summary.json", "repairs.json", "billing.json", "new_solves.csv", "replay.json",
                 "request_inventory.json", "annual.csv", "official_differences.csv", "determinism.json")
        _write(folder/"manifest.json", dict(binding=saved, products={k:_file_hash(folder/k) for k in files}))
        return {**summary, "repeat_matches": repeats["matched"], "repeats": repeats["sampled"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, type=Path)
    sample = parser.add_mutually_exclusive_group(required=True)
    sample.add_argument("--rehearsal", action="store_true")
    sample.add_argument("--open-registered-holdout", metavar="COMMITTED_ADDENDUM", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    for mode in ("output", "resume", "verify"):
        action.add_argument("--" + mode, type=Path)
    parser.add_argument("--deadline", type=datetime.fromisoformat)
    parser.add_argument("--breakpoint-archive", type=Path)
    args = parser.parse_args(argv)
    mode = next(k for k in ("output","resume","verify") if getattr(args,k) is not None)
    result = run(args.matrix, getattr(args, mode), rehearsal=args.rehearsal, addendum=args.open_registered_holdout,
                 mode=mode, cutoff=args.deadline, breakpoint_archive=args.breakpoint_archive)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
    return 2 if result["status"] == "stopped" else 0


if __name__ == "__main__":
    raise SystemExit(main())
