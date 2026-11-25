"""Descriptive station-rating thresholds across every registered service segment."""
import argparse
from pathlib import Path

from . import m11_external_inputs as inputs, m11_rules as rules, service_gap, site_sizing as ss
from .m11_external_seal import check, digest, put
from .m11_external_study import GRID


def thresholds(truck, design):
    result = {}
    for site, attr in (("PORT","port_kw"),("WAREHOUSE","warehouse_kw")):
        ratings = sorted({0, *(getattr(d,attr) for d in rules.GRID)})
        power = dict(zip(ss.SITES,design.caps))
        for kw in ratings:
            power[site] = kw
            if service_gap.reachable(truck,ss.eb.DEFAULT_SPEC,site_power_kw=power)[0]:
                result[site] = kw
                break
        else:
            result[site] = None
    return result


def segment_rows(periods, ref, design, *, revised=False):
    rows = []
    for p in periods:
        week = rules.week(p)
        for days,truck in rules.trucks(p,set(map(tuple,ref[week]))):
            rows.append(dict(week=week,days=days,sites=sorted({s for _,_,s in truck["windows"]}),
                             solo_feasible=rules.reachable(truck,design),required=thresholds(truck,ss.LARGEST if revised else design)))
    return rows


def compare(rows, training, evaluation, *, revised=False):
    baseline = [r for r in rows if r["week"] in training]
    maximum = {}
    for site in ss.SITES:
        levels = [r["required"][site] for r in baseline]
        maximum[site] = None if None in levels else max(levels,default=0)
    evaluated = []
    for row in rows:
        if row["week"] not in evaluation:
            continue
        hits = {}
        for site in (ss.SITES if revised else row["sites"]):
            level, old = row["required"][site], maximum[site]
            hits[site] = None if level is None or old is None else level > old
        hit = True if any(v is True for v in hits.values()) else None if None in hits.values() else False
        evaluated.append(dict(**row,higher_by_station=hits,new_requirement=hit))
    return dict(training_segments=len(baseline),training_max_kw=maximum,evaluation_segments=len(evaluated),
                new_proven=sum(r["new_requirement"] is True for r in evaluated),
                unknown=sum(r["new_requirement"] is None for r in evaluated),segments=evaluated)


def per_segment(label,week,failed):
    if not failed:
        return [dict(design=label,week=week,prediction_one="未命中",prediction_two="不适用")]
    outcomes = {True:"命中", False:"未命中", None:"未识别"}
    return [dict(design=label,week=week,days=row["days"],prediction_one="命中",
                 prediction_two=outcomes[row["new_requirement"]],required=row["required"],
                 higher_by_station=row["higher_by_station"]) for row in failed]


def evaluate(train,test,selection,endpoint,secondary, *, revised=False):
    ref={**selection["reference"],**endpoint["reference"]}
    ps=train+test
    weeks=[rules.week(p) for p in ps]
    cache={}
    def comparisons(k,end,labels):
        out={}
        for label in labels:
            if label not in cache:
                cache[label]=segment_rows(ps,ref,GRID[label],revised=revised)
            out[label]=compare(cache[label],set(weeks[:k]),set(weeks[k:end]),revised=revised)
        return out
    main=comparisons(12,19,selection["choices"]["new"])
    predictions=[]
    for label,comparison in main.items():
        for week,row in endpoint["service"][label].items():
            if row["status"]!="infeasible":
                continue
            failed=[r for r in comparison["segments"] if r["week"]==week and not r["solo_feasible"]]
            if revised:
                predictions.extend(per_segment(label,week,failed))
                continue
            hits=[r["new_requirement"] for r in failed]
            two=True if True in hits else None if None in hits or not failed else False
            predictions.append(dict(design=label,week=week,prediction_one=bool(failed),prediction_two=two,
                                    failed=failed))
    nested=[]
    for row in secondary["nested"]:
        k,end=row["k"],row["end"]
        comparison=comparisons(k,end,row["choices"])
        ratios={}
        for label,detail in comparison.items():
            n=detail["evaluation_segments"]
            ratios[label]=dict(denominator=n,new_proven=detail["new_proven"],unknown=detail["unknown"],
                               fraction_lower=detail["new_proven"]/n if n else None,
                               fraction_upper=(detail["new_proven"]+detail["unknown"])/n if n else None,
                               training_max_kw=detail["training_max_kw"])
        nested.append(dict(k=k,end=end,choices=row["choices"],verdict=row["verdict"],new_demand=ratios))
    tails=[r for r in nested if r["end"]==19]
    sustained=next((r["k"] for i,r in enumerate(tails) if all(t["verdict"]=="守住" for t in tails[i:])),None)
    gap={}
    for label in selection["choices"]["new"]:
        gap[label]={s:secondary["minimum_test_kw"][s]-kw if secondary["minimum_test_kw"][s] is not None else None
                    for s,kw in zip(ss.SITES,GRID[label].caps)}
    return dict(primary_members=main,predictions=predictions,nested=nested,all_later_pass_from_k=sustained,
                minimum_proven_rating_gap_kw=gap)


def from_archive(root, *, revised=False):
    selection=inputs.read(root/"stage2"/"selection.json")
    endpoint=inputs.read(root/"stage3"/"primary.json")
    if endpoint.get("registration_gate")!="passed":
        return dict(status="not_evaluable")
    return evaluate(inputs.periods(inputs.read(root/"stage2"/"tasks.json")),
                    inputs.periods(inputs.read(root/"stage3"/"tasks.json")),selection,endpoint,
                    inputs.read(root/"stage4"/"secondary.json"),revised=revised)


def supplement(archive):
    root=archive/"1-5"
    stage4=check(root/"stage4","1-5",4)
    out=root/"secondary_review"
    out.mkdir(exist_ok=True)
    checksum=put(out,"all_segments.json",from_archive(root))
    put(out,"binding.json",dict(stage4=stage4,all_segments=checksum))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rehearsal-archive",type=Path,required=True)
    supplement(parser.parse_args().rehearsal_archive)
