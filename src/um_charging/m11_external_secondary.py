"""Prespecified secondary endpoints and nested-window descriptions."""
from collections import Counter
from copy import deepcopy
from itertools import product

from . import m10_weekly_union, m11_mechanism, m11_rules as rules, site_sizing as ss
from .m11_external_study import (BASES, GRID, bill, diagnostic, matrix, rank, select, service, verdict)


def subset_ref(reference,periods):
    return {tuple(k) for p in periods for k in reference[rules.week(p)]}


def strict_days(days,bounds):
    result=deepcopy(days)
    for day in result:
        for truck in day["vehicles"]:
            v=truck["vehicle_id"]
            before=bounds.get("before_selection",{}).get(v,{})
            after=bounds.get("after_selection",{}).get(v,{})
            for name in ("stops","unmapped_gaps"):
                truck[name]=[s for s in truck[name] if s["arrival_track_id"]!=before.get("track_id")
                             and s["next_track_id"]!=after.get("track_id")]
    return result


def first_design(rows):
    for d in rules.GRID:
        state=service(rows[d.label].values())
        if state!="infeasible":
            return d if state=="feasible" else None
    return None


def margin_rule(train,ref,ledger):
    stressed=[rules.scaled(p,1.2) for p in train]
    kept={}
    for p in stressed:
        w=rules.week(p)
        original=set(map(tuple,ref[w]))
        alternatives=rules.feasible_subsets(p,original,ss.LARGEST)
        feasible=[]
        for choices in product(*alternatives.values()):
            keys={k for group in choices for k in group}
            row=matrix([p],{w:sorted(keys)},[ss.LARGEST.label],ledger,"fixed_service")[ss.LARGEST.label][w]
            if row["physical"]:
                feasible.append(keys)
            elif row["status"]!="infeasible":
                return None,dict(week=w,reason="unresolved",retained=kept)
        if len(feasible)!=1 or (original and not feasible[0]):
            return None,dict(week=w, status="不适用（歧义）",
                             reason="nonunique" if len(feasible)>1 else "empty", retained=kept)
        kept[w]=sorted(feasible[0])
    if not any(kept.values()):
        return None,dict(status="不适用（歧义）",reason="empty",retained=kept)
    rows=matrix(stressed,kept,GRID,ledger,"fixed_service")
    return first_design(rows),dict(retained=kept,service=rows)


def segment_tiers(periods,ref):
    tiers={}
    for p in periods:
        for segment,truck in rules.trucks(p,set(map(tuple,ref[rules.week(p)]))):
            sites={s for a,b,s in truck["windows"] if a<b}
            tier=None
            if len(sites)==1:
                site,=sites
                options=sorted({d.port_kw if site=="PORT" else d.warehouse_kw for d in rules.GRID})
                tier=next((k for k in options if rules.reachable(truck,ss.Design(int(k>0),k,0)
                           if site=="PORT" else ss.Design(0,0,k))),None)
            tiers[(rules.week(p),tuple(segment))]=(tuple(sorted(sites)),tier)
    return tiers


def novelty(tiers,train_weeks,test_weeks):
    known={}
    for (week,_),(sites,tier) in tiers.items():
        if week in train_weeks and tier is not None:
            known[sites]=max(known.get(sites,0),tier)
    rows=[]
    for (week,segment),(sites,tier) in tiers.items():
        if week in test_weeks:
            is_new=tier is not None and tier>known.get(sites,0)
            rows.append(dict(week=week,segment=segment,sites=sites,tier_kw=tier,new=is_new))
    return dict(segments=len(rows),new=sum(r["new"] for r in rows),rows=rows)


def execute(train,test,strict,selection,endpoint,ledger, *, revised=False):
    ref={**selection["reference"],**endpoint["reference"]}
    all_periods=train+test
    test_rows=matrix(test,ref,GRID,ledger,"fixed_service",existing=endpoint["service"])
    services={l:{**selection["service"][l],**test_rows[l]} for l in GRID}
    cells={(l,w) for l,rows in services.items() for w,r in rows.items() if r["physical"]}
    energy=matrix(all_periods,ref,GRID,ledger,"energy",cells=cells,existing=selection["energy"])
    recovered=[l for l in GRID if service(test_rows[l].values())=="feasible"]
    train_ok=[l for l in GRID if service(selection["service"][l].values())=="feasible"]
    full_ok=[l for l in GRID if service(services[l].values())=="feasible"]
    test_bills={l:bill(test,GRID[l],energy[l]) for l in recovered}
    strict_selection=select(strict,ledger,primary=False)
    strict_verdict=({"not_evaluable":"不可评","unresolved":"未定"}.get(strict_selection["registration_gate"]))
    if strict_verdict is None:
        strict_verdict=verdict(strict_selection["choices"]["new"],test_rows)
    strict_ref=subset_ref(strict_selection["reference"],strict) if all(
        r is not None for r in strict_selection["reference"].values()) else None
    orig_ref=subset_ref(ref,train)
    contrast=dict(selection=strict_selection,verdict=strict_verdict,
                  added=sorted(strict_ref-orig_ref) if strict_ref is not None else None,
                  removed=sorted(orig_ref-strict_ref) if strict_ref is not None else None,
                  selected_changed=strict_selection.get("choices",{}).get("new")!=selection["choices"]["new"],
                  verdict_changed=strict_verdict!=endpoint["verdict"])
    one,thresholds=rules.single_rules(train,orig_ref)
    two=first_design(selection["service"])
    three=(ss.Design(two.port_plugs,two.port_kw,max([two.warehouse_kw]+[t["warehouse_kw"] for t in thresholds
           if t["warehouse_kw"] is not None])) if two else None)
    four,margin=margin_rule(train,ref,ledger)
    tiers=segment_tiers(all_periods,ref)
    weeks=[rules.week(p) for p in all_periods]
    by_week={w:rank([p],services,energy)[0] for p,w in zip(train,weeks)}
    comparisons=[]
    for basis in BASES:
        members={l for choices in by_week.values() for l in choices[basis]}
        union=m10_weekly_union._union([GRID[l] for l in members]) if members else None
        best=[selection["bills"][l][basis] for l in selection["choices"][basis]]
        for name,d in (("rule1",one),("rule2",two),("rule3",three),("rule4",four),
                       ("weekly_union",union),("dual_site_baseline",ss.BASELINE)):
            label=d.label if d else None
            b=None
            if label in train_ok:
                b=bill(train,d,energy[label],baseline=name=="dual_site_baseline")[basis]
            uppers=[r["upper"] for r in best if r["upper"] is not None]
            premium=([b["lower"]-min(uppers),b["upper"]-min(r["lower"] for r in best)]
                     if b and b["upper"] is not None and uppers else None)
            comparisons.append(dict(method=name,basis=basis,design=label,bill=b,premium=premium,
                                    test=verdict([label],test_rows) if label in test_rows else
                                    margin.get("status","未定") if name=="rule4" else "未定"))
    nested=[]
    for k in (4,6,8,10,12,14,16):
        choices,_=rank(all_periods[:k],services,energy)
        for end in ([12,19] if k==6 else [19]):
            tail={l:{w:services[l][w] for w in weeks[k:end]} for l in choices["new"]}
            nested.append(dict(k=k,end=end,choices=choices["new"],verdict=verdict(choices["new"],tail),
                               novelty=novelty(tiers,weeks[:k],weeks[k:end])))
    census={}
    for name,ps in (("selection",train),("evaluation",test)):
        records=m11_mechanism.census(ps,subset_ref(ref,ps))
        census[name]=dict(Counter(r["site_class"] for r in records))
    failure=diagnostic(test,ref,{l:test_rows[l] for l in selection["choices"]["new"]})
    novel=novelty(tiers,weeks[:12],weeks[12:])
    for row in failure:
        s={tuple(map(tuple,t["days"])) for t in row["failed_segments"]}
        row["prediction_one"]=bool(s)
        row["prediction_two"]=any(tuple(t["segment"]) in s and t["new"] for t in novel["rows"])
    result=dict(evaluation_service=test_rows,weekly_energy=energy,evaluation_bills=test_bills,
                existing_endpoint=verdict(selection["choices"]["existing"],test_rows),
                selection_feasible=train_ok,evaluation_feasible=recovered,all_feasible=full_ok,
                minimum_test_kw={site:min((getattr(GRID[l],attr) for l in recovered),default=None)
                                 for site,attr in (("PORT","port_kw"),("WAREHOUSE","warehouse_kw"))},
                strict=contrast,comparisons=comparisons,margin=margin,warehouse_thresholds=thresholds,
                transfer={l:service(services[l].values()) for l in ("p1-40-w20","p1-40-w40")},
                predictions=failure,site_classes=census,nested=nested,weekly_choices=by_week)
    if revised:
        from . import m11_external_mechanism as mechanism
        detail=mechanism.evaluate(train,test,selection,endpoint,result,revised=True)
        for row in failure:
            row["prediction_two"]=[outcome for outcome in detail["predictions"]
                                   if (outcome["design"],outcome["week"])==(row["design"],row["week"])]
        for row,new in zip(nested,detail["nested"],strict=True):
            row["new_demand"]=new["new_demand"]
    return result
