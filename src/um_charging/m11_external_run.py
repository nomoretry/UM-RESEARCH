"""Run one stage of the sealed external fleet study."""
import argparse
from datetime import datetime
import json
from pathlib import Path

from . import m10_evidence as e, m11_external_inputs as inputs, m11_external_secondary as secondary
from . import m11_external_study as study, m11_rule_tables as tables
from .m11_external_evidence import Ledger, utc
from .m11_external_seal import RANKS, authorize, check, committed, digest, git, put, seal


LABELS = ["p1-40-w40","p1-40-w50","p1-50-w40","p1-50-w50",
          "p2-50-w40","p2-50-w50","p2-100-w40","p2-100-w50"]


def prerequisite(archive,cohort,stage,registration,authorization=None):
    authorize(cohort,registration,authorization)
    if cohort!="1-5":
        if committed(registration)!=Path(git(archive,"rev-parse","--show-toplevel").decode().strip()).resolve():
            raise ValueError("Registration and stage output must use the same offline repository")
        if cohort=="16+" or stage==4:
            for name in ("6-10","11-15"):
                check(archive/name/"stage3",name,3)


def expected_rehearsal(archive, stage, result):
    previous=archive.parent.parent/"20261124_m11_external_prep"/"1-5" if archive.name=="rehearsal" else None
    if stage==3:
        if previous:
            check(previous/"stage3","1-5",3)
            reference=inputs.read(previous/"stage3"/"primary.json")["reference"]
            expected=sorted(k for group in reference.values() for k in group)
        else:
            published=inputs.read(archive.parent/"20261123_m10_second_holdout"/"formal"/"outcome.json")
            expected=sorted(published["reference"])
        achieved=sorted(k for group in result.get("reference",{}).values() if group is not None for k in group)
        if len(achieved)!=49 or achieved!=expected:
            raise ValueError("STOP: the 49 original evaluation duties were not reproduced")
    if stage==4:
        if previous:
            check(previous/"stage4","1-5",4)
            expected=sorted(inputs.read(previous/"stage4"/"secondary.json")["evaluation_feasible"])
        else:
            rules=inputs.read(archive.parent/"20261123_m11_rules"/"formal"/"rules.json")
            expected=sorted(row["design"] for row in rules["rated_service"] if row["posthoc"]=="feasible")
        if sorted(result.get("evaluation_feasible",[]))!=expected or expected!=sorted(LABELS):
            raise ValueError("STOP: the eight original rated facilities were not reproduced")
        if not result["f40_check"]:
            raise ValueError("STOP: the Jan 19 F40 service failure was not reproduced")


def main_results(root,stage,days,ledger, *, revised=False):
    if stage==2:
        if days is None:
            return dict(registration_gate="not_evaluable")
        result=study.select(inputs.periods(days),ledger,primary=root.name!="16+")
        return study.annotate(result) if revised else result
    selection=inputs.read(root/"stage2"/"selection.json")
    if stage==3:
        if days is None:
            result=dict(verdict="未定" if selection["registration_gate"]=="unresolved" else "不可评",
                        reason=selection["registration_gate"])
        else:
            result=study.evaluate(inputs.periods(days),selection,ledger,primary=root.name!="16+")
        return study.annotate(result) if revised else result
    endpoint=inputs.read(root/"stage3"/"primary.json")
    if endpoint.get("registration_gate")!="passed":
        return dict(verdict=endpoint["verdict"],reason="previous_gate")
    train_days=inputs.read(root/"stage2"/"tasks.json")
    train=inputs.periods(train_days)
    test=inputs.periods(inputs.read(root/"stage3"/"tasks.json"))
    bounds=inputs.read(root/"stage1"/"boundary.json")
    strict=inputs.periods(secondary.strict_days(train_days,bounds))
    result=secondary.execute(train,test,strict,selection,endpoint,ledger,revised=revised)
    if root.name=="1-5":
        label="p1-40-w20"
        diag=study.diagnostic(test,endpoint["reference"],{label:result["evaluation_service"][label]})
        result["f40_diagnosis"]=diag
        result["f40_check"]=any(r["week"]=="2022-01-17" and any(
            ("2022-01-19","1") in seg["days"] for seg in r["failed_segments"]) for r in diag)
    return result


def export_tables(folder,stage,result):
    exports={}
    if stage==2 and "bills" in result:
        exports["rated_bills.csv"]=[dict(design=l,basis=b,**r) for l,bases in result["bills"].items()
                                    for b,r in bases.items()]
    if stage in (2,3) and "service" in result:
        exports["weekly_service.csv"]=[dict(design=l,week=w,status=r["status"],witness=r["physical"],
                                           proof=r["id"]) for l,rows in result["service"].items() for w,r in rows.items()]
    if stage==4 and "comparisons" in result:
        exports["methods.csv"]=result["comparisons"]
        exports["nested_windows.csv"]=[]
        for row in result["nested"]:
            key="novelty" if "novelty" in row else "same_site_description"
            exports["nested_windows.csv"].append({**row,key:{k:v for k,v in row[key].items() if k!="rows"}})
    for name,rows in exports.items():
        raw=tables.table(rows)
        path=folder/name
        if not path.exists():
            e._publish(path,raw)
        elif path.read_bytes()!=raw:
            raise ValueError("CSV differs on replay")
    return list(exports)


def execute(archive,cohort,stage,source,registration,deadline,authorization=None):
    begin=utc()
    if deadline.tzinfo is None or begin>=deadline:
        raise ValueError("Original deadline has expired or lacks timezone")
    prerequisite(archive,cohort,stage,registration,authorization)
    root=archive/cohort
    folder=root/f"stage{stage}"
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/"manifest.json").exists():
        raise ValueError("Stage is already sealed")
    head=git(inputs.STUDY,"rev-parse","HEAD").decode().strip()
    if git(inputs.STUDY,"status","--porcelain").strip():
        raise ValueError("Execution requires a clean committed research tree")
    if registration is not None:
        from .m11_external_seal import execution_binding
        execution_binding(registration,head,inputs.STUDY)
    if stage==1:
        inputs.first(folder,source,cohort,registration,head=head,begin=begin,authorization=authorization)
        return
    if inputs.read(root/"stage1"/"execution.json")["source_commit"]!=head:
        raise ValueError("Execution commit changed between stages")
    if stage in (2,3):
        days,last,previous=inputs.prepare_phase(root,source,cohort,stage,registration,authorization)
    else:
        previous=check(root/"stage3",cohort,3)
        for i in (2,3):
            if inputs.read(root/f"stage{i}"/"manifest.json")["previous"]!=check(root/f"stage{i-1}",cohort,i-1):
                raise ValueError("Broken stage ancestry")
        days=last=None
    names=[]
    if days is not None:
        put(folder,"tasks.json",days)
        names.append("tasks.json")
    if last is not None:
        put(folder,"last_selection_arrivals.json",last)
        names.append("last_selection_arrivals.json")
    ledger=Ledger(root/"evidence",deadline)
    starts=set(p.stem for p in (ledger.folder/"starts").glob("*.json"))
    try:
        result=main_results(root,stage,days,ledger,revised=True)
    finally:
        ledger.close()
    key={2:"selection.json",3:"primary.json",4:"secondary.json"}[stage]
    put(folder,key,result)
    if cohort=="1-5":
        expected_rehearsal(archive,stage,result)
    names.extend([key,*export_tables(folder,stage,result)])
    if stage==4 and (root/"stage3"/"tasks.json").is_file():
        put(folder,"operating_19_weeks.json",dict(days=inputs.read(root/"stage2"/"tasks.json")
                                                   +inputs.read(root/"stage3"/"tasks.json")))
        names.append("operating_19_weeks.json")
    if stage==4:
        from . import m11_external_mechanism
        put(folder,"all_segments.json",m11_external_mechanism.from_archive(root,revised=True))
        names.append("all_segments.json")
        from . import m11_external_audit
        put(folder,"request_manifest.json",m11_external_audit.inventory(ledger.folder))
        names.append("request_manifest.json")
    proofs=proof_inventory(ledger)
    put(folder,"proofs.json",proofs)
    put(folder,"execution.json",dict(source_commit=head,started=begin.isoformat(),finished=utc().isoformat(),
                                     seconds=(utc()-begin).total_seconds(),requests_used=len(proofs),
                                     requests_started=len(set(proofs)-starts)))
    seal(folder,cohort,stage,[*names,"proofs.json","execution.json"],previous)


def proof_inventory(ledger):
    inventory={}
    for label in sorted(ledger.used):
        path=ledger.folder/"certificates"/(label+".json.gz")
        if path.is_file():
            inventory[label]=digest(path.read_bytes())
        else:
            marker=ledger.folder/"starts"/(label+".json")
            inventory[label]=dict(interrupted=digest(marker.read_bytes()))
    return inventory


def verify(archive,cohort="1-5"):
    root=archive/cohort
    revised=(root/"stage1"/"roster.json").is_file()
    previous=None
    totals=[]
    for stage in range(1,5):
        folder=root/f"stage{stage}"
        doc=inputs.read(folder/"manifest.json")
        if doc["previous"]!=previous:
            raise ValueError("Broken stage ancestry")
        previous=check(folder,cohort,stage)
        if stage==1:
            continue
        days=inputs.read(folder/"tasks.json") if (folder/"tasks.json").exists() else None
        ledger=Ledger(root/"evidence",None,verify=True)
        result=main_results(root,stage,days,ledger,revised=revised)
        key={2:"selection.json",3:"primary.json",4:"secondary.json"}[stage]
        if e._encoded(result)+b"\n"!=(folder/key).read_bytes():
            raise ValueError("Decision replay differs from archived result")
        if cohort=="1-5":
            expected_rehearsal(archive,stage,result)
        inventory=inputs.read(folder/"proofs.json")
        if inventory!=proof_inventory(ledger):
            raise ValueError("Certificate inventory mismatch")
        totals.append(len(inventory))
    from . import m11_external_mechanism
    detail=root/"stage4"/"all_segments.json"
    if not detail.exists():
        # The rehearsal's pre-review stage-four seal is immutable. Its
        # companion binds the full-segment calculation to that same seal.
        detail=root/"secondary_review"/"all_segments.json"
        binding=root/"secondary_review"/"binding.json"
        committed(binding)
        if inputs.read(binding)!={"stage4":previous,"all_segments":digest(detail.read_bytes())}:
            raise ValueError("Mechanism supplement is not bound to stage four")
    if detail.read_bytes()!=e._encoded(m11_external_mechanism.from_archive(root,revised=revised))+b"\n":
        raise ValueError("Full-segment mechanism replay differs")
    repeat_count=0
    if revised:
        from . import m11_external_audit
        m11_external_audit.check_inventory(root)
    elif cohort=="1-5":
        from . import m11_external_audit
        repeat_count=len(m11_external_audit.execute(archive,None,verify=True)["checks"])
    return dict(stages=4,replayed=totals,manifest=previous,independent_repeats=repeat_count)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive",required=True,type=Path)
    parser.add_argument("--cohort",required=True,choices=RANKS)
    parser.add_argument("--stage",required=True,type=int,choices=(1,2,3,4))
    parser.add_argument("--source",type=Path)
    parser.add_argument("--registration",type=Path)
    parser.add_argument("--authorization",type=Path)
    parser.add_argument("--deadline",required=True,type=datetime.fromisoformat)
    args=parser.parse_args()
    if args.stage<4 and args.source is None:
        parser.error("Stages 1 to 3 require the pinned source path")
    execute(args.archive,args.cohort,args.stage,args.source,args.registration,args.deadline,args.authorization)


if __name__=="__main__":
    main()
