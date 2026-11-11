"""Minimum travel time to serve Table 6 and return to each Milan home depot."""
import csv
from itertools import permutations
from pathlib import Path

SHIFT_SLOTS = 20  # 08:00–18:00, half-hour intervals in Section 3.


def travel_slots(start, end):
    if start == end:
        return 0
    if {start, end} in ({1, 2}, {1, 3}):
        return 2
    return 1


def shortest_tour(home, demand):
    stops = [zone for zone, slots in demand.items() if slots and zone != home]
    best = None
    for order in permutations(stops):
        tour = (home, *order, home)
        duration = sum(travel_slots(a, b) for a, b in zip(tour, tour[1:]))
        candidate = (duration, tour)
        if best is None or candidate < best:
            best = candidate
    return best


def main():
    print("vehicle,service_slots,min_travel_slots,max_spare_shift_slots,example_tour")
    with Path(__file__).with_name("service_slots.csv").open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            demand = {i: int(row[f"zone_{i}"]) for i in range(1, 7)}
            service = sum(demand.values())
            travel, route = shortest_tour(int(row["home_depot"]), demand)
            spare = SHIFT_SLOTS - service - travel
            print(f"{row['vehicle']},{service},{travel},{spare},{'-'.join(map(str, route))}")


if __name__ == "__main__":
    main()
