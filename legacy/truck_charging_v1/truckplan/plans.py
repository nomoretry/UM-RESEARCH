"""Enumerate finite simple routes and complete-slot charging schedules."""
from itertools import islice
import math

import networkx as nx

from .data import validate_dataset


def generate_plans(data):
    validate_dataset(data)
    settings, vehicle = data["settings"], data["vehicle"]
    graph = nx.DiGraph()
    graph.add_nodes_from(n["node_id"] for n in data["nodes"])
    for edge in data["edges"]:
        graph.add_edge(edge["from_node"], edge["to_node"], **edge)
    by_node = {s["node_id"]: s for s in data["sites"]}
    slots_hour = settings["slot_minutes"] / 60
    plans = []
    for job in data["jobs"]:
        job_count = 0
        try:
            paths = list(islice(nx.shortest_simple_paths(graph, job["origin"], job["destination"], weight="distance_km"), settings["max_paths_per_job"]))
        except nx.NetworkXNoPath:
            paths = []
        for path in paths:
            path_edges = [graph[a][b] for a, b in zip(path, path[1:])]
            distance = sum(e["distance_km"] for e in path_edges)
            consumed = distance * vehicle["consumption_kwh_per_km"]

            def visit(index, arrival, energy, events):
                nonlocal job_count
                if arrival > job["deadline_slot"]:
                    return
                if index == len(path)-1:
                    if energy + 1e-8 < job["terminal_minimum_kwh"]:
                        return
                    job_count += 1
                    if job_count > settings["max_plans_per_job"]:
                        raise ValueError(f"{job['job_id']}: max_plans_per_job exceeded; narrow test size or explicitly raise limit")
                    elapsed = (arrival-job["departure_slot"]) * slots_hour
                    cost = distance*settings["vehicle_cny_per_km"] + consumed/vehicle["charge_efficiency"]*settings["electricity_cny_per_kwh"] + elapsed*settings["driver_cny_per_hour"]
                    plans.append(dict(plan_id=f"P{len(plans):06d}", job_id=job["job_id"], path_nodes=path.copy(), edge_ids=[e["edge_id"] for e in path_edges], distance_km=distance, arrival_slot=arrival, terminal_kwh=energy, events=events, operating_cost_cny=cost, energy_used_kwh=consumed))
                    return
                edge = path_edges[index]
                drive_slots = math.ceil(edge["travel_minutes"]/settings["slot_minutes"])
                drive_energy = edge["distance_km"]*vehicle["consumption_kwh_per_km"]

                def depart(departure, battery, updated_events):
                    if battery-drive_energy >= vehicle["minimum_kwh"]-1e-8:
                        visit(index+1, departure+drive_slots, battery-drive_energy, updated_events)

                depart(arrival, energy, events)
                site = by_node.get(path[index])
                if index == 0 or site is None or site["site_power_kw"] + 1e-8 < site["charger_kw"]:
                    return
                gain = site["charger_kw"]*slots_hour*vehicle["charge_efficiency"]
                max_duration = math.floor((vehicle["battery_kwh"]-energy+1e-8)/gain)
                latest = min(site["close_slot"], job["deadline_slot"])
                for start in range(max(arrival, site["open_slot"]), latest):
                    for duration in range(1, min(max_duration, latest-start)+1):
                        end = start+duration
                        event = dict(site_id=site["site_id"], arrival_slot=arrival, start_slot=start, end_slot=end, energy_before_kwh=energy, energy_after_kwh=energy+gain*duration, grid_energy_kwh=site["charger_kw"]*slots_hour*duration)
                        depart(end, energy+gain*duration, events+[event])
            visit(0, job["departure_slot"], job["initial_kwh"], [])
    return plans
