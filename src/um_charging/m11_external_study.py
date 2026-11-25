"""Registration, interval selection and service endpoints for one rank interval."""
import math

from . import m10_costs, m10_final_bills as fees, m11_rules as rules, site_sizing as ss
from .m11_external_evidence import job


BASES = ("new","existing")
GRID = {d.label:d for d in rules.GRID}


def register(periods,ledger, *, primary=False):
    locked = {rules.week(p):{} for p in periods}
    journal = []
    for i in range(7):
        requests = []
        for p in periods:
            d = p.days[i]["date"]
            w = rules.week(p)
            prior = locked[w]
            if prior is not None and any(k[0]==d for k in p.keys):
                requests.append((p,job(p,ss.BASELINE,"registration",date=d,locked=prior)))
        for (p,spec),row in zip(requests,ledger.batch(requests),strict=True):
            w, day = rules.week(p),spec["request"]["date"]
            journal.append(dict(week=w,date=day,id=row["id"],status=row["status"]))
            if "reason" in row:
                journal[-1]["reason"]=row["reason"]
            if primary and row["status"]=="unresolved":
                longer=dict(spec,seconds=1800)
                row,=ledger.batch([(p,longer)])
                journal.append(dict(week=w,date=day,id=row["id"],status=row["status"],seconds=1800))
            if "reason" in row:
                journal[-1]["reason"]=row["reason"]
            if row["status"] != "certified":
                locked[w] = None
                continue
            selected = set(map(tuple,row["selected"]))
            locked[w].update({k:k in selected for k in p.keys if k[0]==day})
    return {w:(None if keys is None else sorted([list(k) for k,v in keys.items() if v]))
            for w,keys in locked.items()}, journal


def gate(ref,minimum):
    known = sum(len(r) for r in ref.values() if r is not None)
    if any(r is None for r in ref.values()):
        return "unresolved"
    return "passed" if known >= minimum else "not_evaluable"


def matrix(periods,ref,labels,ledger,phase, *, cells=None, existing=None):
    rows = {label:dict((existing or {}).get(label,{})) for label in labels}
    pending = []
    for label in labels:
        d = GRID[label]
        for p in periods:
            w = rules.week(p)
            if w in rows[label] or cells is not None and (label,w) not in cells:
                continue
            fixed = ref[w]
            if fixed is None:
                rows[label][w] = dict(week=w,id=None,status="unresolved",physical=False)
            elif not fixed:
                zero = dict.fromkeys(ss.SITES,0.)
                rows[label][w] = dict(week=w,id=None,status="certified",physical=True,
                                      lower=0.,upper=0.,grid=zero,peak=zero,daily={})
            else:
                pending.append((label,p,job(p,d,phase,fixed=fixed)))
    results = ledger.batch([(p,s) for _,p,s in pending])
    for (label,p,_),row in zip(pending,results,strict=True):
        rows[label][rules.week(p)] = row
    return rows


def retry(periods,ref,rows,labels,phase,ledger):
    lookup = {rules.week(p):p for p in periods}
    requests = [(label,w,lookup[w],job(lookup[w],GRID[label],phase,seconds=1800,fixed=ref[w]))
                for label in labels for w,row in rows.get(label,{}).items()
                if row["status"]=="unresolved" and row["id"] and not row.get("initial_id")
                and not (phase=="fixed_service" and row["physical"])]
    for (label,w,p,_),row in zip(requests,ledger.batch([(p,s) for _,_,p,s in requests]),strict=True):
        rows[label][w] = dict(row,initial_id=rows[label][w]["id"])


def service(rows):
    if any(r["status"]=="infeasible" for r in rows):
        return "infeasible"
    if all(r["physical"] for r in rows):
        return "feasible"
    return "unresolved"


def native_floor(p,design,year=None):
    # Allow both sites to buy up to rated power during every negative-price hour.
    return sum(min(0.,price) * sum(design.caps)/1000 for day,prices in p.prices.items()
               if year is None or day[:4]==year for price in prices)


def purchase(p,d,row):
    years = sorted({day["date"][:4] for day in p.days})
    factors = {y:fees.PRICE_YEAR/fees.PRICE_INDEX[y] for y in years}
    if row is None or row.get("lower") is None:
        lower = sum(native_floor(p,d,y)*factors[y] for y in years)
    elif len(years)==1:
        lower = row["lower"] * factors[years[0]]
    else:
        f = min(factors.values())
        lower = f*row["lower"] + sum((factor-f)*native_floor(p,d,y) for y,factor in factors.items())
    if not row or row.get("status") not in ss.ENERGY_ACCEPTED:
        return lower,None
    high = sum(cost*factors[day[:4]] for day,cost in row["daily"].items())
    return min(lower,high),high


def bill(periods,d,weekly, *, baseline=False):
    net,materials=m10_costs._parameters(periods)
    bounds=[purchase(p,d,weekly.get(rules.week(p))) for p in periods]
    accepted=all(high is not None for _,high in bounds)
    network=0.
    if accepted:
        rows=[weekly[rules.week(p)] for p in periods]
        grid={s:math.fsum(r["grid"][s] for r in rows) for s in ss.SITES}
        peak={s:max(r["peak"][s] for r in rows) for s in ss.SITES}
        settled=ss.settle(net,0.,grid,peak,"official")
        ss.audit_settlement(net,0.,grid,peak,"official",settled)
        network=settled["annual_capacity_eur_2025"]+settled["annual_network_energy_eur_2025"]
    repeat=52/len(periods)
    output={}
    for basis in BASES:
        equipment,connection=fees.capital(d,materials,basis,baseline=baseline)
        fixed=network+equipment+connection
        output[basis]=dict(lower=fixed+repeat*math.fsum(lo for lo,_ in bounds),
                           upper=fixed+repeat*math.fsum(hi for _,hi in bounds) if accepted else None,
                           equipment=equipment,connection=connection,
                           network=network if accepted else None)
    return output


def rank(periods,services,energy):
    weeks=[rules.week(p) for p in periods]
    charges={}
    for label,rows in services.items():
        if service([rows[w] for w in weeks])!="infeasible":
            charges[label]=bill(periods,GRID[label],energy.get(label,{}))
    choices={}
    for basis in BASES:
        upper=min((r[basis]["upper"] for r in charges.values() if r[basis]["upper"] is not None),default=math.inf)
        choices[basis]=sorted(label for label,r in charges.items() if r[basis]["lower"]<=upper+1e-8)
    return choices,charges


def select(periods,ledger, *, primary):
    ref,journal=register(periods,ledger,primary=primary)
    state=gate(ref,50)
    result=dict(reference=ref,registration=journal,registration_gate=state)
    if state!="passed":
        return result
    services=matrix(periods,ref,GRID,ledger,"fixed_service")
    feasible=[label for label,rows in services.items() if service(rows.values())=="feasible"]
    energy=matrix(periods,ref,feasible,ledger,"energy")
    choices,charges=rank(periods,services,energy)
    if primary:
        retry(periods,ref,services,choices["new"],"fixed_service",ledger)
        feasible=[label for label,rows in services.items() if service(rows.values())=="feasible"]
        energy=matrix(periods,ref,feasible,ledger,"energy",existing=energy)
        choices,charges=rank(periods,services,energy)
        retry(periods,ref,energy,choices["new"],"energy",ledger)
        choices,charges=rank(periods,services,energy)
    result.update(service=services,energy=energy,choices=choices,bills=charges,
                  unresolved_members={b:[l for l in choices[b] if charges[l][b]["upper"] is None] for b in BASES})
    return result


def verdict(choices,services):
    statuses=[service(services[label].values()) for label in choices]
    if statuses and all(s=="feasible" for s in statuses):
        return "守住"
    if statuses and all(s=="infeasible" for s in statuses):
        return "未守住"
    return "未定"


def annotate(result):
    choices = result.get("choices", [])
    labels = choices.get("new", []) if isinstance(choices, dict) else choices
    baseline = ss.BASELINE.hardware()
    constructed = []
    for label in labels:
        hardware = GRID[label].hardware()
        if all(hardware[site][field] >= value for site,limits in baseline.items()
               for field,value in limits.items()):
            constructed.append(label)
    result["按构造"] = constructed
    if result.get("verdict") == "守住" and labels and len(constructed) == len(labels):
        result["标注"] = "按构造，无信息"
    if result.get("verdict") == "未定":
        states = {service(result["service"][l].values()) for l in labels}
        result["未定原因"] = "多个最低成员结论不同" if {"feasible","infeasible"} <= states else "计算未判出"
    return result


def diagnostic(periods,ref,services):
    from . import service_gap
    output=[]
    for label,rows in services.items():
        design=GRID[label]
        for p in periods:
            w=rules.week(p)
            if rows[w]["status"]!="infeasible":
                continue
            segments=[]
            for segment,truck in rules.trucks(p,set(map(tuple,ref[w]))):
                ok,trace=service_gap.reachable(truck,ss.eb.DEFAULT_SPEC,site_power_kw=dict(zip(ss.SITES,design.caps)))
                if not ok:
                    deficit=(max(150.-trace["high_kwh"],trace["low_kwh"]-150.,0.)
                             if trace["cause"]=="single_truck_terminal_energy" else
                             max(0.,trace["low_kwh"]-trace["high_kwh"]))
                    segments.append(dict(days=segment,sites=sorted({s for _,_,s in truck["windows"]}),
                                         deficit_kwh=deficit,detail=trace))
            output.append(dict(design=label,week=w,failed_segments=segments,
                               joint_only=not segments))
    return output


def evaluate(periods,selection,ledger, *, primary=True):
    ref,journal=register(periods,ledger,primary=primary)
    state=gate(ref,20)
    result=dict(reference=ref,registration=journal,registration_gate=state)
    if state!="passed":
        return dict(result,verdict="不可评" if state=="not_evaluable" else "未定")
    labels=selection["choices"]["new"]
    services=matrix(periods,ref,labels,ledger,"fixed_service")
    if primary:
        # A tie between a known survivor and a known failure already fixes the
        # cohort verdict. Within a hardware, one failed week is decisive.
        for label in labels:
            for p in periods:
                statuses={service(services[l].values()) for l in labels}
                if {"feasible","infeasible"}<=statuses or service(services[label].values())!="unresolved":
                    break
                w=rules.week(p)
                row=services[label][w]
                if row["status"]=="unresolved" and not row["physical"] and row["id"]:
                    extended,=ledger.batch([(p,job(p,GRID[label],"fixed_service",seconds=1800,fixed=ref[w]))])
                    services[label][w]=dict(extended,initial_id=row["id"])
    return dict(result,verdict=verdict(labels,services),choices=labels,service=services,
                diagnostics=diagnostic(periods,ref,services))
