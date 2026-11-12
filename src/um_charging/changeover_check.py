"""Replay physical connector histories and piecewise constant charging powers."""
from collections import defaultdict
from math import isfinite

from .timegrid import physical_event_ledger


TOL = 1e-6


def require(condition, message):
    if not condition:
        raise ValueError(message)


def replay(case, hardware, delay, schedule):
    """Check the sparse positive-energy rows without using the optimizer's variables."""
    sites = {site["id"]: site for site in case["sites"]}
    vehicles = {v["id"]: v for v in case["vehicles"]}
    ledger = physical_event_ledger(case)
    duration = case["slot_hours"] * 60
    slots = case["slot_count"]
    require(isfinite(delay) and delay >= 0, "Invalid changeover minutes")
    require(set(sites) == set(hardware), "Hardware and case site IDs differ")
    for h in hardware.values():
        require(type(h["interfaces"]) is int and h["interfaces"] >= 0, "Invalid physical connector count")
        require(isfinite(h["power_kw"]) and h["power_kw"] >= 0, "Invalid site power limit")

    occupied = set()
    history = defaultdict(list)
    slot_energy = defaultdict(float)
    power_events = {s: defaultdict(float) for s in sites}
    site_energy = dict.fromkeys(sites, 0.0)
    for row in schedule:
        site, connector, t, v = (row[k] for k in ("site", "connector", "slot", "vehicle"))
        require(site in sites and v in vehicles, "Unknown site or vehicle")
        require(type(connector) is int and 1 <= connector <= hardware[site]["interfaces"], "Invalid connector ID")
        require(type(t) is int and 0 <= t < slots, "Invalid slot")
        truck = vehicles[v]
        event = truck["timeline"][t]
        require(sites[site]["active"] and truck["charging_site"][t] == site
                and event["activity"] == "dwell" and event["plug_allowed"]
                and event["from"] == event["to"] == site, "Charging outside eligible dwell")
        require((v, t) not in occupied, "Vehicle assigned more than once within a slot")
        occupied.add((v, t))
        left, right = duration * t, duration * (t + 1)
        previous_end, first = left, None
        for start, end, power in row["segments"]:
            require(all(isfinite(x) for x in (start, end, power)), "Nonfinite segment")
            require(start >= previous_end and end > start and end <= right, "Segment outside slot or overlapping")
            require(0 <= power <= truck["power_limit_kw"][site] + TOL, "Truck power limit")
            previous_end = end
            if power > 0:
                if first is None:
                    first = start
                kwh = (end - start) * power / 60
                slot_energy[v, t] += kwh
                site_energy[site] += kwh
                power_events[site][start] += power
                power_events[site][end] -= power
        require(first is not None, "Empty positive-energy row")
        history[site, connector].append((t, v, first, right))

    changes = []
    for (site, connector), rows in sorted(history.items()):
        rows.sort()
        for old, new in zip(rows, rows[1:]):
            require(old[0] != new[0], "Physical connector assigned twice within a slot")
            if old[1] != new[1]:
                gap = new[2] - old[3]
                require(gap + TOL >= delay, "Insufficient physical connector changeover gap")
                changes.append({"site": site, "connector": connector, "previous_vehicle": old[1],
                                "next_vehicle": new[1], "release_minute": old[3],
                                "start_minute": new[2], "gap_minutes": gap})
    peaks = {}
    for site, events in power_events.items():
        power = peak = 0.0
        for minute in sorted(events):
            power += events[minute]
            peak = max(peak, power)
            require(power <= hardware[site]["power_kw"] + TOL, "Instantaneous site power limit")
        peaks[site] = peak

    traces = {}
    for v, truck in vehicles.items():
        energy = truck["initial_energy_kwh"]
        trace = [energy]
        for t, demand in enumerate(truck["drive_energy_kwh"]):
            # Within each dwell energy only rises; within each driving segment it only falls.
            energy += truck["efficiency"] * slot_energy[v, t] - demand
            require(truck["energy_min_kwh"] - TOL <= energy <= truck["energy_max_kwh"] + TOL, "SOC bounds")
            trace.append(energy)
        require(energy + TOL >= truck["initial_energy_kwh"], "Terminal SOC recovery")
        traces[v] = trace
    trips = sum(event["activity"] == "drive" for events in ledger.values() for event in events)
    return {"passed": True, "changes": changes, "change_count": len(changes),
            "trip_count": trips, "energy_kwh": traces, "site_peak_kw": peaks, "site_energy_kwh": site_energy}
