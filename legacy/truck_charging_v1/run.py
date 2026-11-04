"""Run, verify and preserve exact inputs for the V1 prototype."""
import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import platform

from truckplan.data import load_dataset, validate_dataset
from truckplan.plans import generate_plans
from truckplan.model import solve
from truckplan.verify import verify_solution

ROOT = Path(__file__).resolve().parent
SCENARIOS = ("base", "no_charge_needed", "site_power_limited", "tight_deadline_one_bay", "reverse_access_blocked", "relaxed_service")


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def scenario_data(base, scenario):
    data = deepcopy(base)
    if scenario != "base" and data["metadata"]["dataset_id"] != "TEST_ONLY_4NODES_2TRIPS":
        raise ValueError("Built-in scenario transformations apply ONLY to the exact bundled synthetic fixture")
    if scenario == "no_charge_needed":
        data["vehicle"]["consumption_kwh_per_km"] = 0.5
    elif scenario == "site_power_limited":
        next(s for s in data["sites"] if s["site_id"] == "SA")["site_power_kw"] = 75
    elif scenario == "tight_deadline_one_bay":
        for job in data["jobs"]: job["deadline_slot"] = 4
        next(s for s in data["sites"] if s["site_id"] == "SA")["max_bays"] = 1
    elif scenario == "reverse_access_blocked":
        edge = next(e for e in data["edges"] if e["edge_id"] == "OA")
        edge["from_node"], edge["to_node"] = "A", "O"
    data["metadata"]["description"] += f" 测试情景：{scenario}。"
    return validate_dataset(data)


def run_case(data, output, *, relaxed=False):
    save_json(output/"input.json", data)
    plans = generate_plans(data)
    result = solve(data, plans, enforce_service_capacity=not relaxed)
    verification = verify_solution(data, plans, result) if result["selected_plan_ids"] else {"valid": False, "errors": ["No selected solution; no feasibility claim."], "metrics": {}}
    counts = {j["job_id"]: sum(p["job_id"] == j["job_id"] for p in plans) for j in data["jobs"]}
    manifest = {
        "data_kind": data["metadata"]["data_kind"],
        "dataset_id": data["metadata"]["dataset_id"],
        "input_sha256": hashlib.sha256((output/"input.json").read_bytes()).hexdigest(),
        "python": platform.python_version(),
        "packages": {x: importlib.metadata.version(x) for x in ("scipy", "networkx", "numpy")},
        "code_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ("run.py", "truckplan/data.py", "truckplan/plans.py", "truckplan/model.py", "truckplan/verify.py")},
        "plan_count": len(plans), "plans_by_job": counts,
        "route_scope": "At most max_paths_per_job shortest simple directed paths; whole-slot schedules only.",
        "relaxed_service_diagnostic": relaxed,
        "restriction": "Not a real Guangdong planning result. Synthetic scenarios must not be presented as measured data." if data["metadata"]["data_kind"] == "synthetic" else "Real-world validity depends on independently audited data and assumptions."
    }
    save_json(output/"plans.json", plans)
    save_json(output/"solution.json", result)
    save_json(output/"verification.json", verification)
    save_json(output/"manifest.json", manifest)
    by_id = {p["plan_id"]: p for p in plans}
    selected = [by_id[x] for x in result["selected_plan_ids"]]
    save_json(output/"selected_plans.json", selected)
    return {"status": result["status"], "objective_cny_per_year": result["objective_cny_per_year"], "valid_under_full_constraints": verification["valid"], "station_decisions": result["station_decisions"], "plan_count": len(plans), "output": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT/"data/synthetic/demo.json")
    parser.add_argument("--output", type=Path, default=ROOT/"results")
    parser.add_argument("--scenario", choices=SCENARIOS+("all",), default="base")
    args = parser.parse_args()
    base = load_dataset(args.data)
    scenarios = SCENARIOS if args.scenario == "all" else (args.scenario,)
    summary = {}
    for scenario in scenarios:
        data = scenario_data(base, scenario)
        summary[scenario] = run_case(data, args.output/scenario, relaxed=scenario == "relaxed_service")
        print(json.dumps({scenario: summary[scenario]}, ensure_ascii=False))
    save_json(args.output/"comparison.json", summary)
    names = {"base": "完整基础模型", "no_charge_needed": "无需途中充电", "site_power_limited": "场站总功率收紧", "tight_deadline_one_bay": "紧时限且仅一个充电位", "reverse_access_blocked": "接入道路方向反转", "relaxed_service": "取消充电位约束的诊断"}
    lines = ["# 本次模型运行结果", "", "数据性质："+base["metadata"]["data_kind"], "", "模拟输入的结果只证明相应测试条件下的程序行为，不能作为广东实际规划或论文实证结论。", "", "| 情景 | 求解状态 | 年度目标（元） | 完整约束校验 | 站点配置 |", "|---|---|---:|---|---|"]
    for name, result in summary.items():
        cost = "不适用" if result["objective_cny_per_year"] is None else f"{result['objective_cny_per_year']:,.2f}"
        decisions = "；".join(f"{s['site_id']}：{s['bays']}位" for s in result["station_decisions"] if s["build"]) or "无建站方案"
        valid = "通过" if result["valid_under_full_constraints"] else ("没有可验证解" if result["status"] == "infeasible" else "未通过")
        lines.append(f"| {names[name]} | {result['status']} | {cost} | {valid} | {decisions} |")
    lines += ["", "最优性与无解均限定在本次生成的路径和充电安排集合内。服务约束放松只用于诊断，不能作为可执行方案。", "", "每个情景目录保留input、plans、solution、selected_plans、verification和manifest；修改输入后重新运行，不能直接改写结果。", ""]
    (args.output/"RESULTS.zh.md").write_text("\n".join(lines), encoding="utf-8")
    if any(r["status"] in ("solver_error", "unbounded") for r in summary.values()):
        return 2
    if any(not r["valid_under_full_constraints"] and name != "relaxed_service" and r["status"] in ("optimal", "feasible_limit") for name, r in summary.items()):
        return 3
    if args.scenario != "all" and next(iter(summary.values()))["status"] == "infeasible":
        return 4
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as exc:
        print(f"Input/model error: {exc}", file=sys.stderr)
        sys.exit(2)
