"""Frozen-build dispatch of concurrent German vehicle-days in a UM station scenario.

Each quarter reserves at most one truck per physical connector. Split quarters
on exact trip and eligibility boundaries; in each resulting interval the site
and per-truck kW limits hold simultaneously. Charging can cease before a
reservation ends. Positive continuous grid kWh increase battery energy by eta
times that quantity. Each trip's signed BETOS energy is debited at its end.
The data resolve net trip energy, so SOC is checked at departure and arrival;
within-trip SOC is unobserved. Quarter-boundary exchange takes zero minutes.

Every vehicle-day starts and ends at the same assumed SOC. Each civil date is
an independent planning scenario; no energy or uncompleted trips carry over.
The fleet battery size, reserve and cyclic SOC are scenario inputs. Only the
truck charge rate, efficiency, sites and investment menu reuse the UM case.
"""
from collections import defaultdict
from datetime import datetime, timedelta
import math
from time import perf_counter

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .changeover_study import facility_menu
from .day_ahead import ROOT, read_json
from .eligibility_stress import make_reference


# Pre-specified UM heavy-truck scenario; site/menu and charger rating follow the UM baseline.
CAPACITY_KWH = 300.
RESERVE_KWH = 30.
BOUNDARY_KWH = 150.
EFFICIENCY = .9
TRUCK_KW = 50.
EPS = 1e-6
SITES = ("PORT", "WAREHOUSE")


def menu():
    return facility_menu(make_reference(read_json(ROOT / "configs/port_warehouse_investment.json")))


def build_case(day, warehouse_release_min=0):
    """Clip each assumed charging window to its recorded upper bound; keep trip order."""
    if not math.isfinite(warehouse_release_min) or warehouse_release_min < 0:
        raise ValueError("Expected nonnegative warehouse release delay")
    origin = datetime.fromisoformat(day["start"])
    def minute(stamp):
        value = datetime.fromisoformat(stamp)
        if value.utcoffset() is None or origin.utcoffset() is None:
            raise ValueError("Timestamps need explicit offsets")
        return (value - origin) / timedelta(minutes=1)
    horizon = minute(day["end"])
    if horizon != 1440 or (origin.hour, origin.minute, origin.second) != (0, 0, 0):
        raise ValueError("The registered experiment uses complete 24-hour local days without clock changes")
    trucks = {}
    for row in day["vehicles"]:
        v = row["vehicle_id"]
        if v in trucks:
            raise ValueError("Duplicate truck in vehicle-day")
        trips, windows = [], []
        for leg in row["trips"]:
            start, end = minute(leg["start"]), minute(leg["end"])
            energy = float(leg["energy_kwh"])
            if not (0 <= start < end <= horizon) or not math.isfinite(energy) or (trips and trips[-1][1] > start):
                raise ValueError("Invalid trip sequence")
            trips.append((start, end, energy, leg["track_id"]))
        if not trips:
            raise ValueError("A registered vehicle-day must have trips")
        for stop in row["stops"]:
            site = stop["site"]
            start, end = minute(stop["start"]), minute(stop["end"])
            arrival = minute(stop["arrival"])
            if not (arrival <= start < end <= horizon and start >= 0):
                raise ValueError("Stop exceeds recorded bounds")
            if site not in SITES:
                raise ValueError("Unexpected assumed charging site")
            release = max(start, arrival + (warehouse_release_min if site == "WAREHOUSE" else 0))
            if release < end:
                if any(max(a, release) < min(b, end) for a,b,_,_ in trips):
                    raise ValueError("Charging window overlaps driving")
                if any(max(a, release) < min(b, end) for a,b,_ in windows):
                    raise ValueError("Charging windows overlap")
                windows.append((release, end, site))
        trucks[v] = {"trips": trips, "windows": sorted(windows)}
    return {"date": day["date"], "warehouse_release_min": warehouse_release_min, "trucks": trucks}


def subset_case(case, selected_ids):
    ids = set(selected_ids)
    if not ids <= set(case["trucks"]):
        raise ValueError("Unknown vehicle in service subset")
    return {**case, "trucks": {v: t for v,t in case["trucks"].items() if v in ids}}


def _events(case):
    cuts = set(range(0, 1441, 15))
    for t in case["trucks"].values():
        for a,b,_ in t["windows"]:
            cuts.update((a,b))
        for a,b,_,_ in t["trips"]:
            cuts.update((a,b))
    ticks = sorted(cuts)
    for a,b in zip(ticks, ticks[1:]):
        available = {s: [] for s in SITES}
        for v,truck in case["trucks"].items():
            for start,end,site in truck["windows"]:
                if start <= a and b <= end:
                    available[site].append(v)
        yield a,b,available


def audit(case, hardware, schedule, hourly_prices=None):
    """Replay positive powers against physical intervals, reservations, trips and daily SOC."""
    prices = [0.] * 24 if hourly_prices is None else hourly_prices
    site_energy = dict.fromkeys(SITES, 0.)
    peaks = dict.fromkeys(SITES, 0.)
    changes = {s: defaultdict(float) for s in SITES}
    assigned = defaultdict(set)
    by_v = defaultdict(list)
    bill = 0.
    errors = []
    for r in schedule:
        v,s,a,b,p = (r[k] for k in ("vehicle_id","site","start_min","end_min","power_kw"))
        q = r["reservation_slot"]
        if not (v in case["trucks"] and s in hardware and all(math.isfinite(x) for x in (a,b,p))
                and 15*q <= a < b <= 15*(q+1) and 0 < p <= TRUCK_KW+EPS):
            raise ValueError("Invalid dispatch row")
        if not any(site == s and left <= a and b <= right for left,right,site in case["trucks"][v]["windows"]):
            raise ValueError("Dispatch outside released dwell")
        assigned[s,q].add(v)
        changes[s][a] += p
        changes[s][b] -= p
        kwh = p*(b-a)/60
        site_energy[s] += kwh
        bill += kwh * prices[int(a//60)] / 1000
        by_v[v].append((a,b,kwh))
    for (s,q),vs in assigned.items():
        if len(vs) > hardware[s]["interfaces"]:
            errors.append(f"{s}: too many designated trucks in quarter {q}")
    for s,events in changes.items():
        load = 0.
        for t in sorted(events):
            load += events[t]
            peaks[s] = max(peaks[s], load)
        if peaks[s] > hardware[s]["power_kw"]+EPS:
            errors.append(f"{s}: site capacity exceeded")
    terminals, passed_ids, trips_completed = {}, [], 0
    for v,truck in case["trucks"].items():
        power = sorted(by_v[v])
        if any(x[1] > y[0] for x,y in zip(power,power[1:])):
            raise ValueError("Two simultaneous connections on a vehicle")
        # Driving is checked on leg boundaries; longitudinal within-leg SOC is unavailable.
        events = [(b,EFFICIENCY*kwh) for _,b,kwh in power]
        events.extend((b,-e) for _,b,e,_ in truck["trips"])
        level = BOUNDARY_KWH
        good = True
        for t,delta in sorted(events):
            level += delta
            if level < RESERVE_KWH-EPS or level > CAPACITY_KWH+EPS:
                good = False
        terminals[v] = level
        if good and abs(level-BOUNDARY_KWH) <= EPS:
            passed_ids.append(v)
            trips_completed += len(truck["trips"])
        else:
            errors.append(f"{v}: battery bounds or terminal energy")
    return {"passed": not errors, "errors": errors, "terminal_kwh": terminals,
            "site_peak_kw": peaks, "site_energy_kwh": site_energy, "purchase_eur": bill if hourly_prices is not None else None,
            "completed_ids": passed_ids, "vehicles_completed": len(passed_ids), "trips_completed": trips_completed}


def _solve(case, hardware, prices, partial):
    t0 = perf_counter()
    if prices is not None and (len(prices)!=24 or not all(math.isfinite(r) for r in prices)):
        raise ValueError("Provide 24 finite local delivery-hour prices")
    for s in SITES:
        if type(hardware[s]["interfaces"]) is not int or hardware[s]["interfaces"]<0 or not math.isfinite(hardware[s]["power_kw"]) or hardware[s]["power_kw"]<0:
            raise ValueError("Invalid frozen site")
    trucks = case["trucks"]
    obj, maxval, integers = [], [], []
    def variable(upper, c=0., binary=False):
        i = len(obj); obj.append(c); maxval.append(upper); integers.append(int(binary)); return i
    ri,ci,values,lb,ub = [],[],[],[],[]
    def constraint(terms, low=-np.inf, high=np.inf):
        i = len(lb)
        for col,val in terms:
            ri.append(i); ci.append(col); values.append(val)
        lb.append(low); ub.append(high)
    # A reservation belongs to one truck for the entire quarter; a subslot only
    # clips it to true availability and enforces capacity when trucks overlap.
    events = list(_events(case))
    quarters = defaultdict(set)
    for a,b,available in events:
        for s,vs in available.items(): quarters[s,int(a//15)].update(vs)
    reservations = {}
    for (s,q),vs in quarters.items():
        n = hardware[s]["interfaces"]
        if 0 < n < len(vs):
            for v in sorted(vs):
                reservations[s,q,v] = variable(1,binary=True)
            constraint([(reservations[s,q,v],1) for v in vs],high=n)
    service = {v: variable(1,-1,True) for v in trucks} if partial else {}
    by_v = defaultdict(list)
    decisions = []
    for a,b,available in events:
        duration = (b-a)/60
        for s,vehicles in available.items():
            if not vehicles or not hardware[s]["interfaces"] or not hardware[s]["power_kw"]:
                continue
            max_grid = min(TRUCK_KW, hardware[s]["power_kw"])*duration
            terms = []
            for v in vehicles:
                i = variable(max_grid, 0. if prices is None else prices[int(a//60)]/1000)
                by_v[v].append((b,i))
                decisions.append((v,s,a,b,i))
                terms.append((i,1))
                key = s,int(a//15),v
                if key in reservations:
                    constraint([(i,1),(reservations[key],-max_grid)],high=0)
            constraint(terms,high=hardware[s]["power_kw"]*duration)
    for v,t in trucks.items():
        # The battery increases monotonically in a parking spell and changes by
        # the signed simulated net demand of each trip. Leg endpoints suffice.
        def balance(time,draw,low,high):
            terms = [(i,EFFICIENCY) for end,i in by_v[v] if end<=time]
            if partial:
                terms.append((service[v],-draw))
            else:
                low += draw; high += draw
            constraint(terms,low-BOUNDARY_KWH,high-BOUNDARY_KWH)
        draw = 0.
        for a,b,e,_ in t["trips"]:
            balance(a,draw,RESERVE_KWH,CAPACITY_KWH)
            draw += e
            balance(b,draw,RESERVE_KWH,CAPACITY_KWH)
        balance(1440,draw,BOUNDARY_KWH,BOUNDARY_KWH)
    if not obj:
        variable(0)
    matrix = coo_matrix((values,(ri,ci)),shape=(len(lb),len(obj))).tocsr()
    res = milp(obj,integrality=integers,bounds=Bounds(np.zeros(len(obj)),maxval),
               constraints=LinearConstraint(matrix,lb,ub),options={"mip_rel_gap":0.,"time_limit":60.})
    status = {0:"optimal",1:"limit",2:"infeasible"}.get(res.status,"unresolved")
    raw = {"status":status,"objective":None,"dual_bound":None,"mip_gap":None,"seconds":perf_counter()-t0,
           "schedule":[],"audit":None,"selected_ids":[],"completed_count":0}
    if status != "optimal":
        if status != "infeasible":
            raise RuntimeError(f"Fleet solve unresolved: {res.message}")
        return raw
    ids = sorted(v for v in trucks if not partial or res.x[service[v]]>.5)
    rows = [{"vehicle_id":v,"site":s,"reservation_slot":int(a//15),"start_min":a,"end_min":b,
             "power_kw":float(res.x[i])*60/(b-a)} for v,s,a,b,i in decisions if res.x[i]>1e-9]
    checked = audit(subset_case(case,ids),hardware,rows,prices)
    if not checked["passed"]:
        raise ValueError(f"Independent fleet audit failed: {checked['errors']}")
    proof = -len(ids) if partial else (checked["purchase_eur"] or 0.)
    if abs(proof-res.fun)>EPS:
        raise ValueError("Objective mismatch")
    # LP-only SciPy results omit MIP metadata; optimal termination gives the LP bound.
    bound = getattr(res, "mip_dual_bound", None)
    raw.update(objective=float(res.fun),dual_bound=float(bound if bound is not None else res.fun),
               mip_gap=float(getattr(res, "mip_gap", None) or 0.), selected_ids=ids,completed_count=len(ids),schedule=rows,audit=checked)
    return raw


def dispatch(case, hardware, hourly_prices=None):
    return _solve(case,hardware,hourly_prices,False)


def max_service(case, hardware):
    return _solve(case,hardware,None,True)


def immediate(case, hardware, hourly_prices=None):
    """Reserve by first eligibility then ID, use maximal power, ignore future prices.

    The aggregate purchase budget is set by the announced service energy and
    cyclic SOC. Stop at the instant a truck becomes full or exhausts that
    budget. Redistribute freed grid power, retaining every connector's truck
    reservation until the quarter ends. Prices only enter the settlement.
    """
    t0 = perf_counter()
    required = {v:sum(e for _,_,e,_ in t["trips"])/EFFICIENCY for v,t in case["trucks"].items()}
    level = {v:BOUNDARY_KWH for v in required}
    arrivals = {v:{b:-e for _,b,e,_ in t["trips"]} for v,t in case["trucks"].items()}
    reservations = defaultdict(set)
    rows = []
    for a,b,available in _events(case):
        for v in level:
            level[v] += arrivals[v].get(a,0.)
        q = int(a//15)
        for site, vehicles in available.items():
            reserved = reservations[site, q]
            interfaces = hardware[site]["interfaces"]
            releases = {
                v: next(left for left, right, station in case["trucks"][v]["windows"]
                        if station == site and left <= a < b <= right)
                for v in vehicles
            }
            now = a
            while vehicles and now < b:
                power_left = hardware[site]["power_kw"]
                powers = {}
                next_event = b
                for v in sorted(vehicles, key=lambda v: (v not in reserved, releases[v], v)):
                    if power_left <= 0:
                        break
                    if v not in reserved and len(reserved) >= interfaces:
                        continue
                    headroom = (CAPACITY_KWH - level[v]) / EFFICIENCY
                    grid_kwh = min(required[v], headroom)
                    if grid_kwh <= 1e-9:
                        continue
                    kw = min(TRUCK_KW, power_left)
                    powers[v] = kw
                    power_left -= kw
                    reserved.add(v)
                    next_event = min(next_event, now + 60 * grid_kwh / kw)
                if not powers:
                    break
                for v, kw in powers.items():
                    energy = kw * (next_event - now) / 60
                    rows.append({"vehicle_id": v, "site": site, "reservation_slot": q,
                                 "start_min": now, "end_min": next_event, "power_kw": kw})
                    required[v] -= energy
                    level[v] += EFFICIENCY * energy
                now = next_event
    checked = audit(case,hardware,rows,hourly_prices)
    return {"status":"dispatched" if checked["passed"] else "incomplete","schedule":rows,"audit":checked,
            "selected_ids":checked["completed_ids"],"completed_count":checked["vehicles_completed"],
            "objective":None,"dual_bound":None,"mip_gap":None,"seconds":perf_counter()-t0}
