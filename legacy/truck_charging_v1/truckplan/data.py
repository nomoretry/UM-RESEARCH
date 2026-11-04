"""Strict input validation; never infer external field mappings."""
import json
import math
from pathlib import Path


def _keys(obj, expected, location):
    if not isinstance(obj, dict):
        raise ValueError(f"{location}: expected object")
    expected = set(expected.split())
    if set(obj) != expected:
        raise ValueError(f"{location}: missing={sorted(expected-set(obj))}; unknown={sorted(set(obj)-expected)}")


def _number(value, location, *, minimum=0, positive=False, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{location}: expected finite number")
    if integer and not isinstance(value, int):
        raise ValueError(f"{location}: expected integer")
    if value < minimum or (positive and value <= minimum):
        raise ValueError(f"{location}: value outside allowed bounds")


def _text(value, location):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location}: expected nonempty string")


def _rows(data, name, keys, id_key):
    rows = data[name]
    if not isinstance(rows, list):
        raise ValueError(f"{name}: expected list")
    seen = set()
    for i, row in enumerate(rows):
        _keys(row, keys, f"{name}[{i}]")
        _text(row[id_key], f"{name}.{id_key}")
        if row[id_key] in seen:
            raise ValueError(f"{name}: duplicate {id_key} {row[id_key]}")
        seen.add(row[id_key])
    return rows, seen


def validate_dataset(data):
    _keys(data, "schema_version metadata settings vehicle nodes edges sites jobs", "root")
    if data["schema_version"] != "1.0":
        raise ValueError("schema_version: must equal 1.0")
    meta = data["metadata"]
    _keys(meta, "dataset_id data_kind description sources", "metadata")
    for key in ("dataset_id", "description"):
        _text(meta[key], f"metadata.{key}")
    if meta["data_kind"] not in ("synthetic", "research"):
        raise ValueError("metadata.data_kind: expected synthetic or research")
    _, source_ids = _rows(meta, "sources", "source_id citation evidence_type", "source_id")
    for row in meta["sources"]:
        _text(row["citation"], "sources.citation")
        _text(row["evidence_type"], "sources.evidence_type")
    st = data["settings"]
    _keys(st, "slot_minutes horizon_slots operating_days_per_year annualization_factor electricity_cny_per_kwh driver_cny_per_hour vehicle_cny_per_km max_paths_per_job max_plans_per_job solver_time_limit_seconds", "settings")
    for key in st:
        _number(st[key], f"settings.{key}", positive=key not in ("electricity_cny_per_kwh", "driver_cny_per_hour", "vehicle_cny_per_km"), integer=key in ("horizon_slots", "max_paths_per_job", "max_plans_per_job"))
    v = data["vehicle"]
    _keys(v, "battery_kwh minimum_kwh consumption_kwh_per_km charge_efficiency", "vehicle")
    for key in v:
        _number(v[key], f"vehicle.{key}", positive=key != "minimum_kwh")
    if v["minimum_kwh"] >= v["battery_kwh"] or v["charge_efficiency"] > 1:
        raise ValueError("vehicle: invalid battery bounds or efficiency")
    nodes, node_ids = _rows(data, "nodes", "node_id label source_id", "node_id")
    if len(nodes) < 2:
        raise ValueError("nodes: at least two nodes required")
    for row in nodes:
        _text(row["label"], "nodes.label")
    edges, _ = _rows(data, "edges", "edge_id from_node to_node distance_km travel_minutes source_id", "edge_id")
    pairs = set()
    for e in edges:
        _text(e["from_node"], "edges.from_node")
        _text(e["to_node"], "edges.to_node")
        pair = (e["from_node"], e["to_node"])
        if any(n not in node_ids for n in pair) or pair[0] == pair[1] or pair in pairs:
            raise ValueError(f"edges: invalid, duplicate, or unregistered connection {pair}")
        pairs.add(pair)
        for key in ("distance_km", "travel_minutes"):
            _number(e[key], f"edges.{key}", positive=True)
    sites, _ = _rows(data, "sites", "site_id node_id max_bays charger_kw site_power_kw fixed_cost_cny bay_cost_cny open_slot close_slot source_id", "site_id")
    occupied_nodes = set()
    for s in sites:
        _text(s["node_id"], "sites.node_id")
        if s["node_id"] not in node_ids or s["node_id"] in occupied_nodes:
            raise ValueError("sites: node absent or more than one site per node")
        occupied_nodes.add(s["node_id"])
        for key in ("max_bays", "charger_kw", "site_power_kw", "fixed_cost_cny", "bay_cost_cny", "open_slot", "close_slot"):
            _number(s[key], f"sites.{key}", positive=key in ("max_bays", "charger_kw"), integer=key in ("max_bays", "open_slot", "close_slot"))
        if not s["open_slot"] < s["close_slot"] <= st["horizon_slots"]:
            raise ValueError("sites: invalid opening interval")
    jobs, _ = _rows(data, "jobs", "job_id origin destination departure_slot deadline_slot initial_kwh terminal_minimum_kwh source_id", "job_id")
    if not jobs:
        raise ValueError("jobs: at least one explicit trip required")
    for j in jobs:
        _text(j["origin"], "jobs.origin")
        _text(j["destination"], "jobs.destination")
        if j["origin"] not in node_ids or j["destination"] not in node_ids or j["origin"] == j["destination"]:
            raise ValueError("jobs: invalid origin/destination")
        for key in ("departure_slot", "deadline_slot", "initial_kwh", "terminal_minimum_kwh"):
            _number(j[key], f"jobs.{key}", integer=key.endswith("_slot"))
        if not j["departure_slot"] < j["deadline_slot"] <= st["horizon_slots"]:
            raise ValueError("jobs: invalid timing bounds")
        for key in ("initial_kwh", "terminal_minimum_kwh"):
            if not v["minimum_kwh"] <= j[key] <= v["battery_kwh"]:
                raise ValueError(f"jobs.{key}: outside battery bounds")
    for name in ("nodes", "edges", "sites", "jobs"):
        for row in data[name]:
            _text(row["source_id"], f"{name}.source_id")
            if row["source_id"] not in source_ids:
                raise ValueError(f"{name}: unknown source_id {row['source_id']}")
    return data


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON contains duplicate key: {key}")
        result[key] = value
    return result


def load_dataset(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        data = json.load(stream, object_pairs_hook=_unique_object)
    return validate_dataset(data)
