"""Publish the follow-up alongside the original fixed-facility service test."""
from copy import deepcopy

from .holdout_report import (
    BASE, BASIS, CLASS, PORT20, PORT40, REASON, SERVICE, TARIFF, _bill_cell, _duties, _row,
)


FIXED_TABLE = "## 同服务年费与排名 · Annual cost for the same service"
DAILY = "## 逐日运输服务 · Daily registered service"
SENSITIVITY = "## 停靠资格敏感性 · Charging eligibility sensitivity"
REPRODUCTION = "## 复现 · Reproduction"
REPAIRS = ("p1-20-w20", "p1-40-w20")
POLICY = {"frozen": "冻结 / frozen", "rated_fallback": "后备 / fallback"}
WEEK_SERVICE = {"feasible": "✓", "infeasible": "×", "unresolved": "?"}
TARGET = {"served": "完成 / served", "missed": "遗漏 / missed",
          "outside_reference": "登记外 / outside register", "unresolved": "未定 / open"}


def curated(previous, new):
    """Keep the original certificate summary intact in its archive; publish service and billing explicitly."""
    selected = deepcopy(previous)
    if selected.pop("stop_reason") != "recommendation_changed":
        raise ValueError("Expected the archived port-only service shortfall")
    selected["original_run_stop_reason"] = "m8_port_only_facilities_missed_registered_service"
    for row in selected["billing"]["cases"]:
        m8 = row["m8_winner"]
        row.pop("recommendation_status")
        row["lowest_cost_billed_fixed_facility"] = row.pop("winner")
        qualified = [d for d, status in selected["main"]["service_status"].items() if status == "matched"]
        row["service_qualified_fixed_facilities"] = qualified
        row["m8_winner_retained_service"] = m8 in qualified
        row["m8_winner_billed"] = "annual_total_eur_bounds" in row["bills"][m8]
    selected["repair_billing"] = deepcopy(new["billing"])
    selected["sensitivity"] = deepcopy(new["sensitivity"])
    selected["repair_run"] = deepcopy({k: v for k, v in new.items() if k not in {"billing", "sensitivity"}})
    return selected


def _rank(bounds):
    if bounds is None:
        return "?"
    low, high = bounds
    return str(low) if low == high else f"{low}–{high}"


def _fixed_section(block, billing):
    before, table = block.split("\n| 网费 / Tariff |", 1)
    _, after = table.split("\n\n", 1)
    labels = {PORT20: "20", PORT40: "40", BASE: "B"}
    lines = [before.rstrip(), "",
             _row("网费 / Tariff", "接入 / Connection", "20 kW", "40 kW", "B",
                  "名次 / Ranks (20, 40, B)", "M8 最低 / M8 winner", "M8 方案的服务与计费 / M8 service and bill"),
             "|---|---|---:|---:|---:|---|---|---|"]
    for case in billing["cases"]:
        if case["m8_winner_retained_service"] or case["m8_winner_billed"]:
            raise ValueError("The fixed-facility register differs from the original service proof")
        ranks = ", ".join(_rank(case["rank_bounds"][d]) if d in case["rank_bounds"] else "—" for d in labels)
        lines.append(_row(TARIFF[case["scenario"]], BASIS[case["connection_basis"]],
                          *(_bill_cell(case["bills"][d]) for d in labels), ranks, labels[case["m8_winner"]],
                          "少完成登记服务，未出账单 / Service shortfall, no bill"))
    lines.extend(["", "B 完成了全部任务，在这三套设施中唯一有同服务账单。仅凭这一排名无法把 B 确定为新的建设推荐。"
                  "下表另列给两套 M8 设施补上仓库机后的比较。"
                  " [修复方案的同服务年费 / Bills after repair](#repair-bills)", "",
                  "B is the only one of the three with a bill for the full register. Its first place alone "
                  "provides no basis for a new build recommendation.", "", after.strip()])
    return "\n".join(lines)


def _repair_intro(costs):
    labels = (BASE, *REPAIRS)
    first = {d: sum(c["rank_bounds"].get(d) == [1, 1] for c in costs["cases"]) for d in labels}
    open_cases = len(costs["cases"]) - sum(first.values())
    return (f"按主运行规则，双站基准、港区 20 kW 加仓库 20 kW、港区 40 kW 加仓库 20 kW "
            f"分别在 {first[BASE]}、{first[REPAIRS[0]]}、{first[REPAIRS[1]]} 个口径确定为最低，"
            f"{open_cases} 个口径最低名次未分开。\n\n"
            f"Under the primary operating rule, the baseline and the 20/20 and 40/20 kW repairs have "
            f"the lowest verified bill in {first[BASE]}, {first[REPAIRS[0]]} and {first[REPAIRS[1]]} cases, "
            f"respectively. First place is unresolved in {open_cases} cases.")


def _repair_section(costs):
    lines = ['<a id="repair-bills"></a>', "", "## 修复方案的同服务年费 · Annual bills after repair", "",
             "两套最低有报价的修复都在仓库安装 20 kW 充电机，保留原港区额定功率。15 kW 硬件缺少报价。"
             "两列服务限峰参照使用同一台已计价的 20 kW 仓库机，仅把仓库刻钟平均电表限到 15 kW。"
             "15 kW 来自留出期服务检验，参照只作比较。主排名包括 B 及两个按冻结策略运行的修复。", "",
             "Each repair keeps its original port rating and installs the smallest priced warehouse charger "
             "that restores service, 20 kW. The 15 kW hardware has no quoted price. The two reference bills "
             "keep the installed 20 kW unit and restrict the warehouse quarter-hour meter to 15 kW. This cap "
             "comes from holdout service evidence. The primary ranking includes B and the two repairs under "
             "their frozen-policy rule.", "",
             _row("网费 / Tariff", "接入 / Access", "B", "20/20 主 / Primary", "40/20 主 / Primary",
                  "20/15 服务限峰参照 / Reference", "40/15 服务限峰参照 / Reference",
                  "名次 / Ranks (B, 20/20, 40/20)"),
             "|---|---|---:|---:|---:|---:|---:|---|"]
    for case in costs["cases"]:
        rows = [case["repairs"][d] for d in REPAIRS]
        main = [f'{_bill_cell(r["main"])} ({POLICY[r["main"]["policy"]]})' for r in rows]
        lines.append(_row(TARIFF[case["scenario"]], BASIS[case["connection_basis"]], _bill_cell(case["baseline"]),
                          *main, *(_bill_cell(r["reference"]) for r in rows),
                          ", ".join(_rank(case["rank_bounds"].get(d)) for d in (BASE, *REPAIRS))))
    lines.extend(["", "金额为 2025 年欧元/年。无网费的冻结点等于各自额定点。其余网费的冻结点将仓库限到零，"
                  "使它与同样港区硬件及限峰的港区单站拥有相同的充电机会。原归档中更宽松的单枪港区 "
                  "50/0 kW 运行点在 11 月 22 日当周已证不可行，因而这些更小的港区功率及限峰同样失败，"
                  "因此这些费率对整个六周采用额定后备。各分项及上下界见精选结果。", "",
                  "Amounts are annual 2025 euros. With no network charge each frozen point equals its rated "
                  "point. Every other frozen policy closes the warehouse meter, leaving only the port station. "
                  "The archived 50/0 kW point with one port plug already failed in the week of 22 November. "
                  "Its feasible set contains every smaller port rating and meter cap tested here. Each failed policy "
                  "therefore uses rated fallback for all six weeks. "
                  "[费用分项与区间 / Components and bounds](holdout_test.json)", "",
                  "额定运行点逐周固定原登记集合 R。原样本中登记外 11 个车日即使单车独占、功率不限也无法完成，"
                  "故一旦证明整周可完成 R，逐日优先规则选出的也恰好是 R。", "",
                  "Each rated point is checked against the fixed weekly register R. The eleven duties outside "
                  "the register were independently infeasible even with unlimited charging power, so a proved "
                  "weekly extension covering R also yields exactly R under daily selection.", "",
                  _row("额定点 / Rated kW", "逐周保留 R / Weekly service status"), "|---|---|"])
    for d in REPAIRS:
        rated, = [p for p in costs["operating_points"] if p["design"] == d and p["caps_kw"][1] == 20]
        weeks = ", ".join(f'{week[5:]} {WEEK_SERVICE[status]}' for week, status in sorted(rated["week_service_status"].items()))
        lines.append(_row(d, weeks))
    lines.extend(["", "✓ 已证明可服务 / proved feasible · × 已证明不可行 / infeasible · ? 未判定 / open.", "",
                  "这些账单衡量 M8 单站方案加上最低有价修复的费用。留出期未重新选择设施，更便宜的其他设计仍有可能。", "",
                  "These bills price the smallest quoted repairs to the M8 facilities. The holdout did not "
                  "repeat facility selection, so other designs could cost less."])
    return "\n".join(lines)


def _listed(duties):
    return "?" if duties is None else _duties(duties)


def _sensitivity_section(context, result):
    # Retain the bilingual definition of the intervention from the original report.
    method, _ = context.split("\n主结果已证实原推荐存在服务缺口", 1)
    if result is None:
        return method.rstrip() + "\n\n未运行。 / Service sensitivity was not run."
    count = result["registered_count"]
    lines = [method.rstrip(), "",
             f"重新登记 / Reregistered — {count if count is not None else '?'} 个车日 / vehicle-days. "
             f'移出 / Removed — {_listed(result["registration_lost"])}. '
             f'新增 / Added — {_listed(result["registration_gained"])}.', "",
             "下表“移出／新增”比较同一配置在主情景与敏感性中的实际选择。“少完成”逐项对照重新登记的集合。", "",
             "Removed and added duties compare each configuration with its own main result. Missing duties "
             "are measured against the sensitivity register. This sensitivity evaluates service only.", "",
             _row("硬件 / Hardware", "港/仓限峰 / Meter kW", "逐日完成 / Served", "保留新集合 / Register",
                  "少完成 / Missing", "移出 / Removed", "新增 / Added", "11-26 车 1 / Vehicle 1"),
             "|---|---|---:|---|---|---|---|---|"]
    target = result["target_gap"]
    for r in result["configs"]:
        config_caps = "/".join(str(k) for k in r["caps_kw"])
        lines.append(_row(r["design"], config_caps, r["served_count"] if r["served_count"] is not None else "?",
                          SERVICE[r["status"]], _listed(r["missing"]), _listed(r["lost_vs_main"]),
                          _listed(r["gained_vs_main"]), TARGET[target["by_config"][r["id"]]]))
        if r["unresolved_dates"]:
            lines[-1] = lines[-1].replace(SERVICE[r["status"]], SERVICE[r["status"]] + " (" +
                                            ", ".join(r["unresolved_dates"]) + ")", 1)
    notes = [("新登记 / Register", r) for r in result["registration_diagnostics"]]
    notes += [(r["id"], proof) for r in result["configs"] for proof in r["diagnostics"]]
    if notes:
        lines.extend(["", _row("范围 / Scope", "车日 / Duty", "原因 / Diagnosis", "单车证据 / Single-truck limits"),
                      "|---|---|---|---|"])
        for label, proof in notes:
            lines.append(_row(label, f'{proof["date"]} ({proof["vehicle_id"]})', CLASS[proof["classification"]],
                              " · ".join(REASON[k] for k in proof["reasons"]) or "—"))
    register_flag = {True: "仍在新登记集合 / retained in the new register",
                     False: "移出新登记集合 / outside the new register", None: "登记未定 / register unresolved"}
    gap_flag = {True: "两套单站仍遗漏该车日 / both port-only facilities still miss this duty",
                False: "两套单站共同遗漏该车日的情况未再出现 / the original joint omission does not recur",
                None: "该车日的服务差异未定 / service for this duty is unresolved"}
    overall = {True: "两套港区单站仍不能保留全部登记任务。 / Both port-only facilities still fall short.",
               False: "至少一套港区单站保留全部新登记任务。 / At least one port-only facility retains the register.",
               None: "单站结论未定。 / Port-only sufficiency is unresolved."}
    lines.extend(["", f'{target["date"]} ({target["vehicle_id"]}) — {register_flag[target["registered"]]}'
                  f'；{gap_flag[target["port_only_gap_persists"]]}。 {overall[result["port_only_insufficient"]]}'])
    return "\n".join(lines)


def _new_commands(run):
    return "\n".join(["### 修复与敏感性复现 · Repair and sensitivity reproduction", "",
                      f'源码 / Source — `{run["source_commit"]}`. '
                      f'墙钟 / Wall time — {run["formal_seconds"]:.2f} s. '
                      f'求解 / Solver calls — {run["solve_count"]}. '
                      f'已回放可行排程 / Replayed feasible schedules — {run["audited_primals"]}.', "",
                      "从仓库根执行。 / Run from the repository root.", "",
                      "```powershell", "$env:PYTHONPATH = 'src'",
                      r"$runs = Join-Path $env:USERPROFILE 'UM-local-records\conversations\0001_records\runs'",
                      r"$previous = Join-Path $runs '20261121_holdout_weeks\formal'",
                      "$repairArchive = Join-Path $runs '20261121_holdout_repair_bills'",
                      "$fresh = Join-Path $repairArchive ('reproduction-' + [guid]::NewGuid().ToString('N'))",
                      r".\.venv\Scripts\python.exe -m um_charging.holdout_repair --previous $previous --output $fresh",
                      r".\.venv\Scripts\python.exe -m um_charging.holdout_repair --previous $previous --verify (Join-Path $repairArchive 'formal')",
                      "```"])


def render(previous_markdown, selected):
    """Update the four named report sections and preserve the original service evidence and commands."""
    intro, rest = previous_markdown.split(FIXED_TABLE)
    fixed, rest = rest.split(DAILY)
    service, rest = rest.split(SENSITIVITY)
    sensitivity, reproduction = rest.split(REPRODUCTION)
    intro = intro.replace("留出期仅比较三套事先固定的设施。", "最初的留出检验比较三套事先固定的设施。")
    intro = intro.replace("Only the three prespecified facilities enter this comparison.",
                          "The original holdout comparison covers three prespecified facilities.")
    service = service.replace("本轮只评估其服务", "该次检验只评估其服务")
    service = service.replace("The repairs were assessed for service only.",
                              "The original 15 kW hardware checks assessed service only.")
    costs = selected["repair_billing"]
    first = _repair_intro(costs) if costs else "修复账单未完成。 / Repair billing was not completed."
    return "\n\n".join((intro.rstrip(), first, _fixed_section(FIXED_TABLE + fixed, selected["billing"]),
                        _repair_section(costs) if costs else first, (DAILY + service).rstrip(),
                        _sensitivity_section(SENSITIVITY + sensitivity, selected["sensitivity"]),
                        (REPRODUCTION + reproduction).rstrip(), _new_commands(selected["repair_run"]))) + "\n"
