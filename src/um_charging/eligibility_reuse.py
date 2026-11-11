"""Reuse the published fixed A/B operating optima for exactly matched inputs."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .eligibility_stress import audit_case, build_case


HISTORY = "results/eligibility_stress_20261111"
TOLERANCE = 1e-7


def _published_digest(data):
    # __main__.write_json on the original Linux run used UTF-8 and LF.
    text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _model_fields(data):
    return {key: val for key, val in data.items() if key not in {"instance_id", "provenance"}}


def _check_operating(row, frozen):
    quantities = ("operating_cost", "grid_energy_kwh", "dual_bound", "mip_gap")
    if row["status"] == "infeasible":
        if any(row[k] is not None for k in (*quantities, "validation_checks", "validation_passed")):
            raise ValueError("Infeasible fixed case must have no solution or primal check")
        return
    if row["status"] != "optimal" or row["validation_passed"] is not True or not row["validation_checks"]:
        raise ValueError("An optimal fixed case needs its historical independent checks")
    if any(not math.isfinite(row[k]) for k in quantities):
        raise ValueError("Fixed optimum lacks a finite cost, grid energy or certificate")
    need = sum(sum(v["drive_energy_kwh"]) / v["efficiency"] for v in frozen["vehicles"])
    prices = {price for site in frozen["sites"] for price in site["price_per_kwh"]}
    if len(prices) != 1:
        raise ValueError("This delay study requires the registered uniform energy price")
    for actual, expected in ((row["grid_energy_kwh"], need), (row["operating_cost"], need * prices.pop()),
                             (row["operating_cost"], row["dual_bound"])):
        if not math.isclose(actual, expected, abs_tol=TOLERANCE, rel_tol=0):
            raise ValueError("Published fixed-case energy, operating fee or bound is inconsistent")
    if not 0 <= row["mip_gap"] <= TOLERANCE:
        raise ValueError("Published fixed-case gap exceeds tolerance")


def frozen_operating_reuse(reference, study, frozen_metrics, delay_minutes):
    """Build the enumeration callback from the published fixed-facility study."""
    receipt = Path(__file__).resolve().parents[2] / HISTORY / "reproduction.json"
    provenance = json.loads(receipt.read_text(encoding="utf-8"))
    if _published_digest(frozen_metrics) != provenance["raw_metrics_sha256"]:
        raise ValueError("Frozen metrics do not match the published run digest")
    if delay_minutes not in (15, 30, 45, 60):
        raise ValueError("Fixed A/B reuse is for the positive delay levels")
    rows = {row["facility"]: row for row in frozen_metrics["cases"] if row["delay_minutes"] == delay_minutes}
    cached = {}
    for name, facility in study["facilities"].items():
        row = rows[name]
        frozen = build_case(reference, facility, delay_minutes, study["delayed_vehicle_ids"])
        if _published_digest(frozen) != row["input_sha256"]:
            raise ValueError(f"{name}/{delay_minutes}: fixed input differs from its historical hash")
        audit = audit_case(reference, frozen, facility, delay_minutes, study["delayed_vehicle_ids"])
        if not audit["passed"] or audit["hardware_sha256"] != row["hardware_sha256"]:
            raise ValueError(f"{name}/{delay_minutes}: fixed hardware or service audit failed")
        _check_operating(row, frozen)
        key = tuple((s["id"], facility[s["id"]] - s["interfaces"], None) for s in reference["sites"])
        cached[key] = (_model_fields(frozen), row)

    def reuse(fixed, allocations, investment_cost):
        key = tuple((a["site_id"], a["new_interfaces"], a["upgrade_id"]) for a in allocations)
        if key not in cached:
            return None
        expected, row = cached[key]
        if _model_fields(fixed) != expected or investment_cost != row["planning_investment"]:
            raise ValueError("A/B hardware matches but operating inputs or cycle investment differ")
        operating = row["operating_cost"]
        return {"status": row["status"], "operating_cost": operating, "operating_dual_bound": row["dual_bound"],
                "operating_mip_gap": row["mip_gap"], "validation_passed": row["validation_passed"],
                "validation_checks": row["validation_checks"],
                "total_cost": None if operating is None else investment_cost + operating,
                "reused_from": {"metrics": HISTORY + "/metrics.json", "source_commit": provenance["source_commit"],
                                "facility": row["facility"], "delay_minutes": delay_minutes,
                                "input_sha256": row["input_sha256"]}}
    return reuse
