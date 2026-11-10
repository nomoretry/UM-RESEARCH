"""C01-C07 for fixed transport; optional interface and discrete power investment."""
from __future__ import annotations

import copy
import math

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix


def _keys(value, expected, path):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{path}: exact keys required: {sorted(expected)}")


def _number(value, path, lower=0.0, strictly_positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path}: finite number required")
    if not math.isfinite(value) or value < lower or (strictly_positive and value <= 0):
        raise ValueError(f"{path}: invalid numeric value")


def _identifier(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: nonempty string required")


def _validate_investment_site(site, path):
    if type(site["max_new_interfaces"]) is not int or site["max_new_interfaces"] < 0:
        raise ValueError(f"{path}.max_new_interfaces: nonnegative integer required")
    _number(site["interface_cost"], f"{path}.interface_cost")
    if not isinstance(site["upgrade_options"], list):
        raise ValueError(f"{path}.upgrade_options: list required")
    option_ids = []
    for m, option in enumerate(site["upgrade_options"]):
        option_path = f"{path}.upgrade_options[{m}]"
        _keys(option, {"id", "additional_power_kw", "cost"}, option_path)
        _identifier(option["id"], f"{option_path}.id")
        option_ids.append(option["id"])
        _number(option["additional_power_kw"], f"{option_path}.additional_power_kw", strictly_positive=True)
        _number(option["cost"], f"{option_path}.cost")
    if len(set(option_ids)) != len(option_ids):
        raise ValueError(f"{path}.upgrade_options: duplicate option id")


def _validate_timeline(vehicle, site_ids, T, path):
    timeline = vehicle["timeline"]
    if not isinstance(timeline, list) or len(timeline) != T:
        raise ValueError(f"{path}.timeline: exactly slot_count entries required")
    for t, slot in enumerate(timeline):
        slot_path = f"{path}.timeline[{t}]"
        _keys(slot, {"from", "to", "activity", "plug_allowed"}, slot_path)
        for field in ("from", "to"):
            if not isinstance(slot[field], str) or slot[field] not in site_ids:
                raise ValueError(f"{slot_path}.{field}: exact site id required")
        if type(slot["plug_allowed"]) is not bool:
            raise ValueError(f"{slot_path}.plug_allowed: boolean required")
        energy = vehicle["drive_energy_kwh"][t]
        charging_site = vehicle["charging_site"][t]
        if slot["activity"] == "drive":
            if slot["from"] == slot["to"] or energy <= 0 or slot["plug_allowed"] or charging_site is not None:
                raise ValueError(f"{slot_path}: drive requires distinct endpoints, positive energy and no charging")
        elif slot["activity"] == "dwell":
            if slot["from"] != slot["to"] or energy != 0:
                raise ValueError(f"{slot_path}: dwell requires identical endpoints and zero drive energy")
            expected_site = slot["to"] if slot["plug_allowed"] else None
            if charging_site != expected_site:
                raise ValueError(f"{slot_path}: charging_site must match explicit plug eligibility")
        else:
            raise ValueError(f"{slot_path}.activity: exact drive or dwell required")
        if t and timeline[t - 1]["to"] != slot["from"]:
            raise ValueError(f"{slot_path}: discontinuous fixed route")
    if timeline[-1]["to"] != timeline[0]["from"]:
        raise ValueError(f"{path}.timeline: complete closed cycle required")


def validate_input(data):
    """Reject missing slots, unknown keys, aliases and nonfinite physical inputs."""
    if not isinstance(data, dict) or data.get("schema_version") not in ("fixed-facility-v1", "capacity-investment-v1"):
        raise ValueError("unsupported schema_version")
    investment = data["schema_version"] == "capacity-investment-v1"
    top_keys = {"schema_version", "instance_id", "description", "provenance", "units",
                "slot_hours", "slot_count", "representative_weight", "sites", "vehicles"}
    _keys(data, top_keys | ({"cost_basis"} if investment else set()), "input")
    _identifier(data["instance_id"], "instance_id")
    _identifier(data["description"], "description")
    _keys(data["provenance"], {"observed", "derived", "assumed", "simulated"}, "provenance")
    for label, items in data["provenance"].items():
        if not isinstance(items, list) or any(not isinstance(x, str) for x in items):
            raise ValueError(f"provenance.{label}: list of strings required")
    if data["units"] != {"energy": "kWh", "power": "kW", "time": "hour",
                         "price": "synthetic_currency/kWh", "objective": "synthetic_currency"}:
        raise ValueError("units: use the documented explicit units")
    _number(data["slot_hours"], "slot_hours", strictly_positive=True)
    _number(data["representative_weight"], "representative_weight", strictly_positive=True)
    if investment and (data["cost_basis"] != "synthetic_cycle_equivalent" or data["representative_weight"] != 1):
        raise ValueError("capacity-investment-v1 requires synthetic_cycle_equivalent costs and representative_weight=1")
    T = data["slot_count"]
    if type(T) is not int or T <= 0:
        raise ValueError("slot_count: positive integer required")
    for group in ("sites", "vehicles"):
        if not isinstance(data[group], list) or not data[group]:
            raise ValueError(f"{group}: nonempty list required")

    site_ids = []
    for j, site in enumerate(data["sites"]):
        path = f"sites[{j}]"
        site_keys = {"id", "active", "interfaces", "available_power_kw", "price_per_kwh"}
        _keys(site, site_keys | ({"max_new_interfaces", "interface_cost", "upgrade_options"} if investment else set()), path)
        _identifier(site["id"], f"{path}.id")
        site_ids.append(site["id"])
        if type(site["active"]) is not bool:
            raise ValueError(f"{path}.active: boolean required")
        if type(site["interfaces"]) is not int or site["interfaces"] < 0:
            raise ValueError(f"{path}.interfaces: nonnegative integer required")
        if investment:
            _validate_investment_site(site, path)
        for field in ("available_power_kw", "price_per_kwh"):
            if not isinstance(site[field], list) or len(site[field]) != T:
                raise ValueError(f"{path}.{field}: exactly slot_count entries required")
            for value in site[field]:
                _number(value, f"{path}.{field}")
    if len(set(site_ids)) != len(site_ids):
        raise ValueError("duplicate site id")

    vehicle_ids = []
    for v, vehicle in enumerate(data["vehicles"]):
        path = f"vehicles[{v}]"
        vehicle_keys = {"id", "energy_min_kwh", "energy_max_kwh", "initial_energy_kwh",
                        "efficiency", "power_limit_kw", "drive_energy_kwh", "charging_site"}
        _keys(vehicle, vehicle_keys | ({"timeline"} if investment else set()), path)
        _identifier(vehicle["id"], f"{path}.id")
        vehicle_ids.append(vehicle["id"])
        for field in ("energy_min_kwh", "energy_max_kwh", "initial_energy_kwh"):
            _number(vehicle[field], f"{path}.{field}")
        if not vehicle["energy_min_kwh"] <= vehicle["initial_energy_kwh"] <= vehicle["energy_max_kwh"]:
            raise ValueError(f"{path}: energy_min <= initial_energy <= energy_max required")
        _number(vehicle["efficiency"], f"{path}.efficiency", strictly_positive=True)
        if vehicle["efficiency"] > 1:
            raise ValueError(f"{path}.efficiency: must be <= 1")
        _keys(vehicle["power_limit_kw"], set(site_ids), f"{path}.power_limit_kw")
        for value in vehicle["power_limit_kw"].values():
            _number(value, f"{path}.power_limit_kw")
        for field in ("drive_energy_kwh", "charging_site"):
            if not isinstance(vehicle[field], list) or len(vehicle[field]) != T:
                raise ValueError(f"{path}.{field}: exactly slot_count explicit entries required")
        for t, energy in enumerate(vehicle["drive_energy_kwh"]):
            _number(energy, f"{path}.drive_energy_kwh[{t}]")
            site_id = vehicle["charging_site"][t]
            if site_id is not None and (not isinstance(site_id, str) or site_id not in site_ids):
                raise ValueError(f"{path}.charging_site[{t}]: exact site id or null required")
            if energy > 0 and site_id is not None:
                raise ValueError(f"{path}: C02 prohibits charging in a driving slot")
        if investment:
            _validate_timeline(vehicle, site_ids, T, path)
    if len(set(vehicle_ids)) != len(vehicle_ids):
        raise ValueError("duplicate vehicle id")
    return data


def make_scenarios(base):
    """Documented deterministic perturbations; no inferred historical fields."""
    validate_input(base)
    # The suite is a test of this physical fixture, not a general scenario generator.
    expected_sites = [
        {"id": "A", "active": True, "interfaces": 2, "available_power_kw": [100.0] * 4, "price_per_kwh": [1.0, 1.0, 2.0, 2.0]},
        {"id": "B", "active": True, "interfaces": 1, "available_power_kw": [50.0] * 4, "price_per_kwh": [1.0, 1.0, 2.0, 2.0]},
    ]
    expected_vehicles = [
        {"id": vehicle_id, "energy_min_kwh": 20.0, "energy_max_kwh": 100.0,
         "initial_energy_kwh": 100.0, "efficiency": 0.9, "power_limit_kw": {"A": 50.0, "B": 50.0},
         "drive_energy_kwh": [30.0, 0.0, 30.0, 0.0], "charging_site": [None, site_id, None, site_id]}
        for vehicle_id, site_id in (("V1", "A"), ("V2", "A"), ("V3", "B"))
    ]
    if (base["instance_id"] != "minimal_three_trucks" or base["slot_count"] != 4
            or base["slot_hours"] != 1.0 or base["representative_weight"] != 1.0
            or base["sites"] != expected_sites or base["vehicles"] != expected_vehicles):
        raise ValueError("the six-case suite requires the documented minimal_three_trucks input")
    cases = {"base": copy.deepcopy(base)}
    for name in ("interface_bottleneck", "power_bottleneck", "window_bottleneck", "higher_power_no_benefit", "zero_demand"):
        cases[name] = copy.deepcopy(base)
        cases[name]["instance_id"] = name
    cases["interface_bottleneck"]["sites"][0]["interfaces"] = 1
    cases["power_bottleneck"]["sites"][0]["available_power_kw"] = [60.0] * base["slot_count"]
    cases["window_bottleneck"]["vehicles"][2]["charging_site"][3] = None
    cases["higher_power_no_benefit"]["sites"][0]["available_power_kw"] = [150.0] * base["slot_count"]
    for vehicle in cases["zero_demand"]["vehicles"]:
        vehicle["drive_energy_kwh"] = [0.0] * base["slot_count"]
    return cases


def solve(data, *, display=False, time_limit=60.0):
    """Solve fixed transport with fixed or investable capacity; retain raw values."""
    validate_input(data)
    _number(time_limit, "time_limit", strictly_positive=True)
    V, J, T = len(data["vehicles"]), len(data["sites"]), data["slot_count"]
    investment = data["schema_version"] == "capacity-investment-v1"
    block = V * J * T
    operational_size = 2 * block + V * (T + 1)
    # Additional variables follow the original a/p/e blocks without changing them.
    upgrade_indices = []
    size = operational_size + (J if investment else 0)
    if investment:
        for site in data["sites"]:
            upgrade_indices.append(list(range(size, size + len(site["upgrade_options"]))))
            size += len(site["upgrade_options"])
    def a(v, j, t): return (v * J + j) * T + t
    def p(v, j, t): return block + a(v, j, t)
    def e(v, t): return 2 * block + v * (T + 1) + t
    def n(j): return operational_size + j
    lower, upper = np.zeros(size), np.full(size, np.inf)
    integer, objective = np.zeros(size), np.zeros(size)
    rows, cols, values, lb, ub = [], [], [], [], []
    counts = {f"C{k:02d}": 0 for k in range(1, 8)}

    def row(terms, low, high, constraint):
        idx = len(lb)
        for col, val in terms.items():
            rows.append(idx); cols.append(col); values.append(val)
        lb.append(low); ub.append(high); counts[constraint] += 1

    # C01: activation remains supplied; new interfaces and upgrades can be optimized.
    if investment:
        for j, site in enumerate(data["sites"]):
            upper[n(j)] = site["max_new_interfaces"] * int(site["active"])
            integer[n(j)] = 1
            objective[n(j)] = site["interface_cost"]
            counts["C01"] += 1  # Integer variable upper bound, including active-site link.
            for m, idx in enumerate(upgrade_indices[j]):
                upper[idx] = int(site["active"])
                integer[idx] = 1
                objective[idx] = site["upgrade_options"][m]["cost"]
            if upgrade_indices[j]:
                row({idx: 1.0 for idx in upgrade_indices[j]}, -np.inf, int(site["active"]), "C01")
    else:
        counts["C01"] = J
    for v, vehicle in enumerate(data["vehicles"]):
        for t in range(T + 1):
            lower[e(v, t)], upper[e(v, t)] = vehicle["energy_min_kwh"], vehicle["energy_max_kwh"]
        lower[e(v, 0)] = upper[e(v, 0)] = vehicle["initial_energy_kwh"]
        lower[e(v, T)] = vehicle["initial_energy_kwh"]  # C07 terminal recovery.
        counts["C07"] += T + 3
        for t in range(T):
            row({a(v, j, t): 1.0 for j in range(J)}, -np.inf, 1.0, "C02")
            balance = {e(v, t + 1): 1.0, e(v, t): -1.0}
            for j, site in enumerate(data["sites"]):
                upper[a(v, j, t)] = float(site["active"] and vehicle["charging_site"][t] == site["id"])
                integer[a(v, j, t)] = 1
                row({p(v, j, t): 1.0, a(v, j, t): -vehicle["power_limit_kw"][site["id"]]}, -np.inf, 0.0, "C03")
                balance[p(v, j, t)] = -vehicle["efficiency"] * data["slot_hours"]
                objective[p(v, j, t)] = data["representative_weight"] * site["price_per_kwh"][t] * data["slot_hours"]
            row(balance, -vehicle["drive_energy_kwh"][t], -vehicle["drive_energy_kwh"][t], "C06")
    for j, site in enumerate(data["sites"]):
        for t in range(T):
            interfaces = {a(v, j, t): 1.0 for v in range(V)}
            power = {p(v, j, t): 1.0 for v in range(V)}
            if investment:
                interfaces[n(j)] = -1.0
                for m, idx in enumerate(upgrade_indices[j]):
                    power[idx] = -site["upgrade_options"][m]["additional_power_kw"]
            row(interfaces, -np.inf, site["interfaces"], "C04")
            row(power, -np.inf, site["available_power_kw"][t] * int(site["active"]), "C05")
    matrix = coo_matrix((values, (rows, cols)), shape=(len(lb), size)).tocsr()
    result = milp(objective, integrality=integer, bounds=Bounds(lower, upper),
                  constraints=LinearConstraint(matrix, lb, ub),
                  options={"disp": display, "time_limit": time_limit, "mip_rel_gap": 0.0})
    status = {0: "optimal", 1: "limit_reached", 2: "infeasible", 3: "unbounded", 4: "solver_error"}[result.status]
    def finite_or_none(value):
        return float(value) if value is not None and math.isfinite(value) else None
    output = {
        "instance_id": data["instance_id"], "status": status, "status_code": int(result.status),
        "message": str(result.message), "has_solution": result.x is not None,
        "objective": finite_or_none(result.fun),
        "dual_bound": finite_or_none(getattr(result, "mip_dual_bound", None)),
        "mip_gap": finite_or_none(getattr(result, "mip_gap", None)),
        "mip_node_count": finite_or_none(getattr(result, "mip_node_count", None)),
        "constraint_counts": counts, "solution": None,
        "limitations": ("Fixed closed transport timeline; interface and discrete power investment with synthetic cycle-equivalent costs; no routing, siting or power flow."
                        if investment else "Fixed facilities and supplied complete synthetic timeline; no routing, investment or power flow."),
    }
    if result.x is not None:
        output["solution"] = {
            "occupancy": result.x[:block].reshape(V, J, T).tolist(),
            "power_kw": result.x[block:2 * block].reshape(V, J, T).tolist(),
            "energy_kwh": result.x[2 * block:operational_size].reshape(V, T + 1).tolist(),
        }
        if investment:
            output["solution"]["new_interfaces"] = result.x[operational_size:operational_size + J].tolist()
            output["solution"]["upgrade_selected"] = [[float(result.x[idx]) for idx in indices] for indices in upgrade_indices]
    return output
