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
    def shape_ok(value, shape):
        if not shape:
            return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        return isinstance(value, list) and len(value) == shape[0] and all(shape_ok(x, shape[1:]) for x in value)
    if not isinstance(solution, dict) or set(solution) != set(expected_shapes) or any(not shape_ok(solution[key], shape) for key, shape in expected_shapes.items()):
        return {"applicable": True, "passed": False, "errors": ["Malformed or nonfinite solution arrays"]}
    occupancy, power, energy = solution["occupancy"], solution["power_kw"], solution["energy_kwh"]
    maxima = {name: 0.0 for name in ("C02", "C03", "C04", "C05", "C06", "C07", "OBJECTIVE")}
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
    site_peak_kw = {}
    for j, site in enumerate(data["sites"]):
        peak = 0.0
        for t in range(T):
            n = sum(occupancy[v][j][t] for v in range(V))
            p = sum(power[v][j][t] for v in range(V))
            check("C04", n - site["interfaces"], f"{site['id']}/{t} interfaces")
            check("C05", p - site["available_power_kw"][t] * int(site["active"]), f"{site['id']}/{t} grid limit")
            peak = max(peak, p)
        site_peak_kw[site["id"]] = peak
    objective = result.get("objective")
    if isinstance(objective, bool) or not isinstance(objective, (int, float)) or not math.isfinite(objective):
        errors.append({"constraint": "OBJECTIVE", "detail": "Missing or nonfinite objective"})
    else:
        check("OBJECTIVE", abs(objective - cost), "recomputed weighted operating cost")
    return {"applicable": True, "passed": not errors, "checks": checks, "tolerance": tolerance,
            "max_violation_by_constraint": maxima, "errors": errors,
            "grid_energy_kwh": grid_energy, "operating_cost": cost, "investment_cost": 0.0,
            "objective_recomputed": cost, "site_peak_kw": site_peak_kw,
            "energy_kwh_recomputed": recomputed_energy,
            "cost_note": "All facilities fixed; sunk investment omitted. Weight is explicit, not a claim of annual coverage."}
