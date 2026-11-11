"""Solver-free check for the fixed A/B warehouse plug-eligibility experiment.

Each truck consumes 40 battery kWh and charges at 90% efficiency. On warehouse
arrival it has room for 20 battery kWh. All four warehouse and all four port
slots last 15 min; each truck accepts at most 50 kW and can switch at boundaries.
One warehouse plug can serve one truck per slot, so the 75 kW warehouse cap
never limits this experiment. V3 is always eligible; only V1 and V2 are delayed.

All energy calculations use integer units of 1/72 grid kWh. For each admissible
warehouse assignment we take the maximum energy each assigned truck can accept.
This choice can only decrease its port requirement and respects all warehouse
limits. Thus testing this residual is exact for feasibility in this instance.

A has two 50 kW plugs under a 100 kW port limit. A residual fits when no truck
needs more than four plug-slots and their total is at most eight. To see
sufficiency, fill two rows of four slots with each truck's requested slot count
in order. Each count is at most four, so a truck straddling rows occupies
disjoint time slots. The site cap holds even when both plugs run at 50 kW.

B has three plugs and a 100 kW port limit. All trucks have the same one-hour
port window; serve them concurrently at constant power equal to their residual
grid kWh divided by one hour. The port and per-truck energy bounds are then
necessary and sufficient. Reported counts concern four-slot warehouse plug
assignments only; several may map to the same physical charging schedule.
"""
from itertools import product
import json


UNITS_PER_KWH = 72
PORT_SLOTS = 4
TRUCKS = (1, 2, 3)
GRID_NEED = 40 * 10 * UNITS_PER_KWH // 9       # 40 / 0.9 kWh
WAREHOUSE_ROOM = 20 * 10 * UNITS_PER_KWH // 9  # 20 / 0.9 kWh
ENERGY_PER_PLUG_SLOT = 50 * UNITS_PER_KWH // 4  # 50 kW for 0.25 h
PORT_SITE_ENERGY = 100 * UNITS_PER_KWH          # 100 kW for 1 h


def check_delay(delay_min):
    delayed_slots = delay_min // 15
    choices = [(0, 3)] * delayed_slots + [(0, 1, 2, 3)] * (4 - delayed_slots)
    assignments = a_count = b_count = 0
    min_required_port_slots = 12
    for schedule in product(*choices):  # 0 = unoccupied
        port_need = [
            GRID_NEED - min(schedule.count(truck) * ENERGY_PER_PLUG_SLOT, WAREHOUSE_ROOM)
            for truck in TRUCKS
        ]
        plug_slots = [
            (need + ENERGY_PER_PLUG_SLOT - 1) // ENERGY_PER_PLUG_SLOT
            for need in port_need
        ]
        min_required_port_slots = min(min_required_port_slots, sum(plug_slots))
        a_count += max(plug_slots) <= PORT_SLOTS and sum(plug_slots) <= 2 * PORT_SLOTS
        b_count += max(port_need) <= ENERGY_PER_PLUG_SLOT * PORT_SLOTS and sum(port_need) <= PORT_SITE_ENERGY
        assignments += 1
    return {
        "delay_min": delay_min,
        "warehouse_assignments": assignments,
        "extendable_warehouse_assignments_A": a_count,
        "extendable_warehouse_assignments_B": b_count,
        "A_feasible": a_count > 0,
        "B_feasible": b_count > 0,
        "min_required_port_plug_slots": min_required_port_slots,
    }


if __name__ == "__main__":
    print(json.dumps([check_delay(delay) for delay in range(0, 61, 15)], indent=2))
