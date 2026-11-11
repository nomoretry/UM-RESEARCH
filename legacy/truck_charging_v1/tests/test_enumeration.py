"""Small-fixture exhaustive optimum check, separate from the MILP formulation."""
from collections import Counter
from itertools import product
from pathlib import Path

import pytest

from run import scenario_data
from truckplan.data import load_dataset
from truckplan.model import solve
from truckplan.plans import generate_plans


@pytest.mark.parametrize("scenario", ["base", "no_charge_needed", "site_power_limited", "tight_deadline_one_bay", "reverse_access_blocked"])
def test_milp_matches_exhaustive_enumeration(scenario):
    data = scenario_data(load_dataset(Path(__file__).parents[1]/"data/synthetic/demo.json"), scenario)
    plans = generate_plans(data)
    choices = [[p for p in plans if p["job_id"] == job["job_id"]] for job in data["jobs"]]
    best = float("inf")
    settings = data["settings"]
    for selected in product(*choices):
        occupied = Counter((e["site_id"], t) for p in selected for e in p["events"] for t in range(e["start_slot"], e["end_slot"]))
        investment = 0
        feasible = True
        for site in data["sites"]:
            required_bays = max((count for (site_id, _), count in occupied.items() if site_id == site["site_id"]), default=0)
            if required_bays > site["max_bays"] or required_bays*site["charger_kw"] > site["site_power_kw"]+1e-8:
                feasible = False
                break
            if required_bays:
                investment += site["fixed_cost_cny"] + required_bays*site["bay_cost_cny"]
        if feasible:
            total = investment*settings["annualization_factor"] + sum(p["operating_cost_cny"] for p in selected)*settings["operating_days_per_year"]
            best = min(best, total)
    actual = solve(data, plans)
    if best == float("inf"):
        assert actual["status"] == "infeasible"
    else:
        assert actual["status"] == "optimal"
        assert actual["objective_cny_per_year"] == pytest.approx(best)
