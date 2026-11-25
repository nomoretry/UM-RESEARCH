"""Run the registered M11 rule study or replay its weekly evidence without optimization."""
import argparse
from datetime import datetime
from pathlib import Path

from . import m10_evidence as e, m11_rule_study as study
from .m11_rule_evidence import Ledger


def archive(folder,name,value,verify):
    content=e._encoded(value)
    path=folder/name
    if verify or path.exists():
        if path.read_bytes()!=content:
            raise ValueError(f"Result differs: {name}")
    else:
        e._publish(path,content)


def execute(runs,folder,stage,deadline,verify=False):
    ledger=Ledger(folder,deadline,verify)
    try:
        model=study.Study(runs,ledger)
        if stage=="rules":
            result=study.rule_phase(model)
        else:
            from . import m11_sensitivity
            result=m11_sensitivity.evaluate(model,stage,folder)
        archive(folder,stage+".json",result,verify)
        print(stage,len(ledger.rows),"weekly requests",len(ledger.unknown),"unresolved groups",flush=True)
        if "stop" in result:
            raise RuntimeError(result["stop"])
        return set(ledger.rows)
    finally:
        ledger.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs",type=Path,required=True)
    parser.add_argument("--folder",type=Path,required=True)
    parser.add_argument("--stage",choices=["rules","sensitivity","fine"],required=True)
    parser.add_argument("--deadline",type=datetime.fromisoformat,required=True)
    args=parser.parse_args()
    execute(**vars(args))
