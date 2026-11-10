"""Independent physical/cost recomputation; never imports the MILP matrix."""
from __future__ import annotations

import math

from .model import validate_input


def check_solution(data, result, tolerance=1e-7):
    """Check raw values without rounding occupancy or trusting solver residuals."""
    validate_input(data)  # Shared input schema; no model matrix/residual is consulted.
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance must be finite and positive")
    if not result["has_solution"]:
        return {"applicable": False, "passed": None, "reason": "No primal solution; infeasibility is a solver claim, with analytic certificates for the documented suite."}
    solution = result["solution"]
    V, J, T = len(data["vehicles"]), len(data["sites"]), data["slot_count"]
    expected_shapes = {"occupancy": (V, J, T), "power_kw": (V, J, T), "energy_kwh": (V, T + 1)}
    investing = data["schema_version"] == "capacity-investment-v1"
    expected_keys = set(expected_shapes)
    if investing:
        expected_keys.update(("new_interfaces", "upgrade_selected"))
    def shape_ok(value, shape):
        if not shape:
            return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        return isinstance(value, list) and len(value) == shape[0] and all(shape_ok(x, shape[1:]) for x in value)
    if not isinstance(solution, dict) or set(solution) != expected_keys or any(not shape_ok(solution[key], shape) for key, shape in expected_shapes.items()):
        return {"applicable": True, "passed": False, "errors": ["Malformed or nonfinite solution arrays"]}
    if investing and (not shape_ok(solution["new_interfaces"], (J,))
                      or not isinstance(solution["upgrade_selected"], list)
                      or len(solution["upgrade_selected"]) != J
                      or any(not shape_ok(solution["upgrade_selected"][j], (len(site["upgrade_options"]),))
                             for j, site in enumerate(data["sites"]))):
        return {"applicable": True, "passed": False, "errors": ["Malformed or nonfinite investment arrays"]}
    occupancy, power, energy = solution["occupancy"], solution["power_kw"], solution["energy_kwh"]
    maxima = {name: 0.0 for name in ("C01", "C02", "C03", "C04", "C05", "C06", "C07", "OBJECTIVE")}
    errors, checks = [], 0
    def check(constraint, violation, detail):
        nonlocal checks
        checks += 1
        if not math.isfinite(violation):
            raise ValueError(f"Nonfinite independent recomputation: {constraint}: {detail}")
        violation = max(0.0, float(violation))
        maxima[constraint] = max(maxima[constraint], violation)
        if violation > tolerance:
            errors.append({"constraint": constraint, "violation": violation, "detail": detail})
    effective_interfaces = [site["interfaces"] for site in data["sites"]]
    added_power = [0.0] * J
    interface_cost, expansion_cost = 0.0, 0.0
    if investing:
        for j, site in enumerate(data["sites"]):
            n = solution["new_interfaces"][j]
            check("C01", max(-n, n - site["max_new_interfaces"] * int(site["active"]), abs(n - round(n))), f"{site['id']} added interfaces")
            effective_interfaces[j] += n
            interface_cost += site["interface_cost"] * n
            selected = solution["upgrade_selected"][j]
            check("C01", sum(selected) - int(site["active"]), f"{site['id']} exclusive upgrade")
            for option, u in zip(site["upgrade_options"], selected):
                check("C01", max(-u, u - int(site["active"]), abs(u - round(u))), f"{site['id']}/{option['id']} upgrade binary")
                added_power[j] += option["additional_power_kw"] * u
                expansion_cost += option["cost"] * u
    cost, grid_energy = 0.0, 0.0
    recomputed_energy = []
    for v, vehicle in enumerate(data["vehicles"]):
        current = vehicle["initial_energy_kwh"]
        trace = [current]
        check("C07", abs(energy[v][0] - current), f"{vehicle['id']} initial")
        for t in range(T):
            total_power, occupied = 0.0, 0.0
            for j, site in enumerate(data["sites"]):
                a, p = occupancy[v][j][t], power[v][j][t]
                allowed = int(site["active"] and vehicle["charging_site"][t] == site["id"])
                check("C02", max(-a, a - allowed, abs(a - round(a))), f"{vehicle['id']}/{site['id']}/{t} occupancy")
                check("C03", max(-p, p - vehicle["power_limit_kw"][site["id"]] * a), f"{vehicle['id']}/{site['id']}/{t} power")
                total_power += p; occupied += a
                grid_energy += p * data["slot_hours"]
                cost += data["representative_weight"] * site["price_per_kwh"][t] * p * data["slot_hours"]
            check("C02", occupied - 1.0, f"{vehicle['id']}/{t} mutual exclusion")
            current += vehicle["efficiency"] * data["slot_hours"] * total_power - vehicle["drive_energy_kwh"][t]
            trace.append(current)
            check("C06", abs(energy[v][t + 1] - current), f"{vehicle['id']}/{t + 1} integrated energy")
        for t in range(T + 1):
            for label, value in (("reported", energy[v][t]), ("recomputed", trace[t])):
                check("C07", max(vehicle["energy_min_kwh"] - value, value - vehicle["energy_max_kwh"]), f"{vehicle['id']}/{t} {label} bounds")
        check("C07", vehicle["initial_energy_kwh"] - current, f"{vehicle['id']} terminal recovery")
        recomputed_energy.append(trace)
    site_peak_kw, site_energy_kwh, site_power_kw = {}, {}, {}
    for j, site in enumerate(data["sites"]):
        peak = 0.0
        powers = []
        for t in range(T):
            n = sum(occupancy[v][j][t] for v in range(V))
            p = sum(power[v][j][t] for v in range(V))
            check("C04", n - effective_interfaces[j], f"{site['id']}/{t} interfaces")
            check("C05", p - site["available_power_kw"][t] * int(site["active"]) - added_power[j], f"{site['id']}/{t} grid limit")
            peak = max(peak, p)
            powers.append(p)
        site_peak_kw[site["id"]] = peak
        site_power_kw[site["id"]] = powers
        site_energy_kwh[site["id"]] = sum(powers) * data["slot_hours"]
    investment_cost = interface_cost + expansion_cost
    objective = result.get("objective")
    if isinstance(objective, bool) or not isinstance(objective, (int, float)) or not math.isfinite(objective):
        errors.append({"constraint": "OBJECTIVE", "detail": "Missing or nonfinite objective"})
    else:
        check("OBJECTIVE", abs(objective - cost - investment_cost), "recomputed investment plus weighted operating cost")
    return {"applicable": True, "passed": not errors, "checks": checks, "tolerance": tolerance,
            "max_violation_by_constraint": maxima, "errors": errors,
            "grid_energy_kwh": grid_energy, "operating_cost": cost, "investment_cost": investment_cost,
            "interface_cost": interface_cost, "expansion_cost": expansion_cost,
            "objective_recomputed": cost + investment_cost, "site_peak_kw": site_peak_kw,
            "site_energy_kwh": site_energy_kwh, "site_power_kw": site_power_kw,
            "system_coincident_peak_kw": max(sum(site_power_kw[site['id']][t] for site in data['sites']) for t in range(T)),
            "energy_kwh_recomputed": recomputed_energy,
            "cost_note": ("One modeled cycle: synthetic cycle-equivalent investment plus operating cost; no real or annual economic claim."
                          if investing else "All facilities fixed; sunk investment omitted. Weight is explicit, not a claim of annual coverage.")}
