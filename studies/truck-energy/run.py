"""Transfer TUM's simulated payload/auxiliary sensitivity to the UM investment case."""
import argparse
import copy
import csv
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from um_charging.__main__ import checked_output
from um_charging.boundary_cli import facility_details
from um_charging.eligibility_investment import planning_case
from um_charging.eligibility_stress import make_reference
from um_charging.investment_experiment import compare_joint_to_enumeration, enumerate_facilities
from um_charging.model import solve
from um_charging.validation import check_solution

TRACKS_SHA256 = "d92ab77cafe21c1aad3e9be8de1e26b453846a677f91b07ee0ac5f652ec8c50e"
BASE_PAYLOAD_T = 19.3
BASE_AUX_KW = 5.0


def read_tracks(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != TRACKS_SHA256:
        raise ValueError("Expected the pinned upstream CSV bytes; see README.md.")
    energies, hours, distances, vehicles = [], [], [], set()
    rows = 0
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            rows += 1
            if not row["energy_consumption_kwh"]:
                continue
            energy, duration, km = map(float, (row["energy_consumption_kwh"], row["duration_h"], row["distance_km"]))
            if not all(map(math.isfinite, (energy, duration, km))) or duration <= 0 or km <= 0:
                raise ValueError("Invalid nonmissing upstream simulation record")
            energies.append(energy)
            hours.append(duration)
            distances.append(km)
            vehicles.add(row["vehicle_id"])
    return {"source_sha256": TRACKS_SHA256, "published_tracks": rows,
            "tracks_with_original_energy": len(energies), "vehicles_with_original_energy": len(vehicles),
            "excluded_missing_energy": rows - len(energies), "signed_net_kwh": math.fsum(energies),
            "distance_km": math.fsum(distances), "duration_h": math.fsum(hours)}


def coefficient(data, payload_factor, aux_kw):
    energy, hours = data["signed_net_kwh"], data["duration_h"]
    return (payload_factor * energy + aux_kw * hours) / (energy + BASE_AUX_KW * hours)


def evaluate(base, factor, config, evidence=None):
    data = copy.deepcopy(base)
    for truck in data["vehicles"]:
        truck["drive_energy_kwh"] = [energy * factor for energy in truck["drive_energy_kwh"]]
    data["provenance"]["derived"].append("Each synthetic leg is scaled by an external fleet energy ratio.")
    case = planning_case(make_reference(data), 45, config["delayed_vehicle_ids"])
    answer = solve(case)
    checked = check_solution(case, answer)
    if evidence:
        evidence.parent.mkdir(parents=True, exist_ok=True)
        archive = gzip.open(evidence, "xt", encoding="utf-8")
    else:
        archive = None

    def record(index, fixed, result, validation):
        line = {"combination": index, "input": fixed, "result": result, "validation": validation}
        archive.write(json.dumps(line, allow_nan=False) + "\n")

    try:
        if archive:
            record("joint", case, answer, checked)
        menu = enumerate_facilities(case, on_combination=record if archive else None)
    finally:
        if archive:
            archive.close()
    verification = compare_joint_to_enumeration(answer, checked, menu)
    if not verification["passed"] or menu["combination_count"] != 54:
        raise ValueError(f"Facility enumeration and joint model disagree: {verification}")
    return {
        "status": answer["status"], "investment": checked.get("investment_cost"),
        "operating_cost": checked.get("operating_cost"), "objective": answer["objective"],
        "mip_gap": answer["mip_gap"], "physical_checks": checked.get("checks"),
        "feasible_configurations": menu["feasible_count"], "configurations_checked": menu["combination_count"],
        "optima": [[{"site": site["site_id"], "connectors": site["total_interfaces"],
                     "added_kw": site["added_power_kw"]} for site in solution]
                   for solution in facility_details(case, menu["best_hardware"])]
    }


def run(tracks, evidence=None):
    aggregate = read_tracks(tracks)
    config = json.loads((ROOT / "configs/eligibility_stress.json").read_text(encoding="utf-8"))
    base = json.loads((ROOT / config["base_config"]).read_text(encoding="utf-8"))
    if evidence is not None:
        evidence = checked_output(evidence, ROOT)
        evidence.mkdir(parents=True)
    cases = []
    for payload_factor in (0.8, 1.0, 1.2):
        for aux in (3.0, BASE_AUX_KW, 7.0):
            factor = coefficient(aggregate, payload_factor, aux)
            leg = base["vehicles"][0]["drive_energy_kwh"][0] * factor
            payload = round(BASE_PAYLOAD_T * payload_factor, 2)
            log = evidence / f"payload_{payload}_aux_{aux}.jsonl.gz" if evidence else None
            row = evaluate(base, factor, config, log)
            cases.append({"payload_t": payload, "aux_kw": aux,
                          "energy_ratio": factor, "leg_kwh": leg, **row})
    identity = next(x for x in cases if x["payload_t"] == BASE_PAYLOAD_T and x["aux_kw"] == BASE_AUX_KW)
    if (identity["energy_ratio"] != 1 or identity["investment"] != 40
            or not math.isclose(identity["operating_cost"], 400 / 3)):
        raise ValueError("Identity scenario did not recover the registered UM benchmark")
    return {"source": aggregate, "warehouse_delay_minutes": 45, "cases": cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tracks", type=Path, help="Path to the pinned tracks_with_energy.csv")
    parser.add_argument("--evidence", type=Path, help="Fresh directory in the existing offline run Git")
    args = parser.parse_args()
    print(json.dumps(run(args.tracks, args.evidence), ensure_ascii=False, indent=2, allow_nan=False))
