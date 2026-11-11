# V1 implementation contract

This is a newly designed JSON interface, not an inferred schema of any external file.
All identifiers are exact and case-sensitive. V1 accepts explicit synthetic fixtures,
not undocumented real-city assumptions. Unknown keys and missing required values must fail.

## Input format

Root keys: `schema_version` ("1.0"), `metadata`, `settings`, `vehicle`, `nodes`,
`edges`, `sites`, `jobs`.

`metadata`: `dataset_id`, `data_kind` ("synthetic" or "research"), `description`,
`sources` (array of {`source_id`, `citation`, `evidence_type`}).
Every node, edge, site and job has `source_id` matching this registry.

`settings`: `slot_minutes` > 0, `horizon_slots` positive integer,
`operating_days_per_year` > 0, `annualization_factor` > 0,
`electricity_cny_per_kwh` >= 0, `driver_cny_per_hour` >= 0,
`vehicle_cny_per_km` >= 0, `max_paths_per_job` positive integer,
`max_plans_per_job` positive integer, `solver_time_limit_seconds` > 0.

`vehicle`: `battery_kwh` > 0, `minimum_kwh` >= 0,
`consumption_kwh_per_km` > 0, `charge_efficiency` in (0,1].

`nodes`: array of {`node_id`, `label`, `source_id`}.
`edges`: array of {`edge_id`, `from_node`, `to_node`, `distance_km` > 0,
`travel_minutes` > 0, `source_id`}. Directed, no parallel edges or self loops.
Missing edges are NOT invented. No assumed reverse direction.

`sites`: array of {`site_id`, `node_id`, `max_bays` positive integer,
`charger_kw` > 0, `site_power_kw` >= 0, `fixed_cost_cny` >= 0,
`bay_cost_cny` >= 0, `open_slot` >= 0, `close_slot` <= horizon,
`source_id`}. At most one site per node. All sites are NEW build options in V1.
Charging draws full `charger_kw` from grid per occupied bay for complete slots;
battery increment per slot is charger_kw * slot_minutes / 60 * charge_efficiency.
The charger_kw value must already be compatible with this one vehicle type.

`jobs`: array of {`job_id`, `origin`, `destination`, `departure_slot`,
`deadline_slot`, `initial_kwh`, `terminal_minimum_kwh`, `source_id`}.
Each job is one independently assigned vehicle trip, NOT a volume or a linked tour.
Origin != destination; initial and terminal minima within battery limits.
Departure fixed; arrivals conservatively rounded to slot boundaries edge by edge.
Deadline inclusive. No charging at origin or destination in V1; initial and terminal
energy are explicit boundary inputs. There is NO implicit full recharge per job chain.

## Modules / API

`truckplan/data.py`: `load_dataset(path)` and `validate_dataset(data)` return
validated unchanged dictionary or raise ValueError. Strict keys, finite numbers,
exact IDs, types, bounds, provenance and referential integrity.

`truckplan/plans.py`: `generate_plans(data)` returns a list of plan dictionaries:
`plan_id`, `job_id`, `path_nodes`, `edge_ids`, `distance_km`, `arrival_slot`,
`terminal_kwh`, `events`, `operating_cost_cny`, `energy_used_kwh`.
Each event: `site_id`, `arrival_slot`, `start_slot`, `end_slot`, `energy_before_kwh`,
`energy_after_kwh`, `grid_energy_kwh`.
Only positive-duration charging events included. Occupancy is [start_slot,end_slot).
Wait permitted before charging at intermediate sites, counted in elapsed time.
Enumerate first max_paths_per_job simple paths sorted by distance using networkx;
for each path enumerate whole-slot charging and waits, including passing without
charging. Stop with explicit error if max_plans_per_job exceeded, never silently
truncate schedules. Route-set restriction is explicitly part of the method.
Operating cost = distance*vehicle_cny_per_km + energy_used_kwh/efficiency*
electricity_cny_per_kwh + elapsed_hours*driver_cny_per_hour.
This accounts for consumed-energy cost, not actual time/location-specific settlement.
No arbitrary unused-terminal-energy credit and no carbon objective.

`truckplan/model.py`: `solve(data, plans, *, enforce_service_capacity=True)` returns
JSON-serializable {`status`, `objective_cny_per_year`, `station_decisions`,
`selected_plan_ids`, `investment_cny_per_year`, `operation_cny_per_year`,
`mip_gap`, `message`}. Use scipy.optimize.milp (HiGHS).
Station decisions array {`site_id`, `build`, `bays`}.
Objective annualized fixed/bay capital + operating_days * selected plan costs.
One plan per job, plan uses only built sites, build <= bays <= max_bays*build,
per-site/per-slot occupied plans <= bays and occupied plans*charger_kw <=
site_power_kw*build. All jobs served; no hidden unmet-demand penalty/slack.
No plan -> status "infeasible" with explanation; no solution vector used if absent.
Service-relaxed variant removes ONLY bay occupancy constraints, not power constraints;
it is a diagnostic lower bound, not a deployable plan. Status must distinguish
optimal, feasible_limit, infeasible, unbounded, solver_error.

`truckplan/verify.py`: independently recompute route adjacency, distance, elapsed
time, energy at each leg/event, station opening, battery bounds and final energy,
deadlines, one plan/job, build/bay/site power constraints, annual objective.
`verify_solution(data, plans, result)` returns {`valid`, `errors`, `metrics`}.
Do NOT trust precomputed energy/cost/arrival fields without recomputation.

## Scope / safety

No real GPS, SOC, OD, grid topology or approved construction permissions are asserted.
JSON and source bytes preserved; no mapping of an unknown schema by case or spelling.
Unit-test fixtures are mathematical inputs, not an empirical Guangdong dataset.
