"""Render the bilingual M9 report from the selected, independently replayed evidence."""
from collections import Counter

from .holdout_bills import FIXED


PORT20, PORT40, BASE = (d.label for d in FIXED)
TARIFF = {"N0": "无 / None", "frank": "Frank 表 / Table 4", "official": "Netze BW",
          "capacity_0": "0", "capacity_22_79": "22.79", "capacity_208_38": "208.38"}
BASIS = {"new": "新建 / New", "existing": "既有 / Existing"}
SERVICE = {"matched": "保留 / retained", "service_gap": "缺口 / gap", "unresolved": "未定 / open"}
RANK = {"unchanged": "一致 / same", "changed": "改变 / changed", "unresolved": "未定 / open"}
FEASIBLE = {"feasible": "可行 / feasible", "infeasible": "不可行 / infeasible",
            "unresolved": "未定 / open"}
CLASS = {
    "infeasible_unlimited_power": "充电功率不限仍不可行 / infeasible with unlimited charging power",
    "truck_power_limit": "单车充电功率限制 / truck charging-power limit",
    "joint_fleet_constraints_or_equal_service_tie": "车队联合约束或同数择优 / shared constraints or service tie",
    "single_truck_infeasible_at_facility": "该设施即使只服务该车也不可行 / infeasible even with exclusive access",
}
REASON = {"trip_exceeds_usable_battery": "单趟超可用电量 / trip exceeds usable battery",
          "no_charging_window": "无可充窗口 / no charging window",
          "trip_soc_boundary": "行程处 SOC 越界 / trip SOC limit",
          "terminal_soc_unreachable": "段末 SOC 无法恢复 / terminal SOC unreachable"}


def _row(*cells):
    return "| " + " | ".join(str(cell) for cell in cells) + " |"


def _ids(values):
    if values is None:
        return "?"
    return ", ".join(sorted(values, key=int)) or "∅"


def _duties(values):
    return ", ".join(f"{day} ({truck})" for day, truck in values) or "∅"


def _bill_cell(bill):
    if "annual_total_eur_bounds" not in bill:
        return SERVICE.get(bill["status"], FEASIBLE.get(bill["status"], bill["status"]))
    lower, upper = bill["annual_total_eur_bounds"]
    lo, hi = f"{lower:,.2f}", f"{upper:,.2f}"
    return hi if lo == hi else f"{lo}–{hi}"


def _cost_section(billing):
    lines = ["## 同服务年费与排名 · Annual cost for the same service", ""]
    if not billing or not billing["cases"]:
        return lines + ["年费比较未完成。 / Annual cost comparisons were not completed.", ""]
    lines.extend([
        "每格为 2025 年欧元/年，区间右端是回放账单，端点显示到分。依据未取整的区间判定名次。"
        "数字 20、40 表示港区单站额定 kW，B 表示基准。排序数字相同或范围重合表示名次仍未分开。", "",
        "Amounts are annual 2025 euros, rounded to cents. The upper endpoint is the replayed bill. "
        "Ranks use unrounded intervals. The port-only facilities are labelled 20 and 40 kW. B is the baseline. "
        "Overlapping rank ranges leave their order open.", "",
        _row("网费 / Tariff", "接入 / Connection", "20 kW", "40 kW", "B",
             "名次 / Ranks (20, 40, B)", "M8 最低 / M8 winner", "结论 / Result"),
        "|---|---|---:|---:|---:|---|---|---|",
    ])
    labels = {PORT20: "20", PORT40: "40", BASE: "B"}
    for case in billing["cases"]:
        ranks = []
        for design in labels:
            rank = case["rank_bounds"].get(design)
            ranks.append("—" if rank is None else str(rank[0]) if rank[0] == rank[1] else f"{rank[0]}–{rank[1]}")
        lines.append(_row(TARIFF[case["scenario"]], BASIS[case["connection_basis"]],
                          *(_bill_cell(case["bills"][d]) for d in labels), ", ".join(ranks),
                          labels[case["m8_winner"]], RANK[case["recommendation_status"]]))
    policies = {}
    for case in billing["cases"]:
        tariff, bill = case["scenario"], case["bills"][BASE]
        if tariff not in policies:
            caps = "/".join(str(k) for k in bill["caps_kw"])
            note = "（额定后备 / rated fallback）" if bill["policy"] == "rated_fallback" else ""
            if "rated_comparator" in bill:
                note += "（封存限峰未定，额定参照另列 / frozen cap unresolved, rated comparator in JSON）"
            policies[tariff] = f"{TARIFF[tariff]} {caps}{note}"
    lines.extend(["", "基准港区/仓库刻钟上限 / Baseline port/warehouse quarter-hour caps (kW) — "
                  + " · ".join(policies.values()) + ".", "",
                  "六周按 52/6 年化。两站分别按六周最大实测刻钟功率选档。购电区间固定回放排程的电表读数。"
                  "基准两站各一台 50 kW 机，接入 100/75 kW。新建按 175 kW 计费，既有的增量接入费用为零。", "",
                  "Each meter uses its six-week maximum quarter-hour demand. The six weeks repeat 52/6 times per year. "
                  "Purchase bounds hold metered energy and peaks at their replayed values. The baseline uses two "
                  "50 kW chargers and 100/75 kW connections. New-build connection costs cover 175 kW, with zero "
                  "incremental capacity under existing access. Wholesale energy (2021), network tariffs (2024) "
                  "and new connection charges (2026) use the M8 CPI conversion to 2025 euros. "
                  "[分项账单及价格口径 / Bill components and price basis](holdout_test.json)", ""])
    return lines


def _service_section(main):
    lines = ["## 逐日运输服务 · Daily registered service", "",
             "每格列出车辆数值 ID。∅ 表示空集，? 表示未判定。 / Cells list numeric vehicle IDs. "
             "∅ is an empty set and ? is unresolved.", "",
             _row("日期 / Date", "完整 / Eligible", "登记 / Baseline register", "20 kW", "40 kW"),
             "|---|---|---|---|---|"]
    for r in main["daily"]:
        lines.append(_row(r["date"], _ids(r["eligible"]), _ids(r["registered"]),
                          _ids(r["facilities"][PORT20]), _ids(r["facilities"][PORT40])))
    lines.extend(["", "### 登记缺口 · Service gaps", "",
                  _row("设施 / Facility", "服务 / Service", "少完成 (ID) / Missing",
                       "登记外完成 (ID) / Added"), "|---|---|---|---|"])
    for d in (PORT20, PORT40):
        determined = main["service_status"][d] != "unresolved"
        lines.append(_row(d, SERVICE[main["service_status"][d]],
                          _duties(main["missing"][d]) if determined or main["missing"][d] else "?",
                          _duties(main["added"][d]) if determined or main["added"][d] else "?"))
    lines.extend(["", "### 逐车日归因 · Vehicle-day diagnostics", "",
                  "逐个检查包含该车日的所有连续服务段，段首尾电量均为 150 kWh。"
                  "同数量下未选中的车日可能受接口竞争、跨日边界或同数择优影响。", "",
                  "Each diagnostic checks every possible continuous service segment containing the vehicle-day "
                  "with 150 kWh at both ends. Shared plugs, carry-over boundaries and equal-count selection "
                  "can all affect which duties enter a maximum-service register.", "",
                  _row("范围 / Scope", "日期 (ID) / Date (ID)", "判别 / Classification",
                       "单车检验中遇到的限制 / Limits observed", "固定全周集合 / Full weekly register"),
                  "|---|---|---|---|---|"])
    for label, rows in [("登记外 / Outside", main.get("outside", [])), *main.get("fixed_diagnostics", {}).items()]:
        for r in rows:
            reasons = " · ".join(REASON[k] for k in r["reasons"]) or "—"
            lines.append(_row(label, f'{r["date"]} ({r["vehicle_id"]})', CLASS[r["classification"]],
                              reasons, FEASIBLE[r["fixed_R_week"]] if "fixed_R_week" in r else "—"))
    return lines + [""]


def _repair_section(repairs):
    lines = ["## 单站恢复 · Single-site service restoration", ""]
    if not repairs or not repairs["starts"]:
        return lines + ["没有单站修复结果。 / No single-site restoration result was recorded.", ""]
    lines.extend(["恢复标准是在六周内完成全部登记车日。按相对原设施增加的额定 kW 比较，"
                  "固定全周登记集合的物理可行性与逐日优先级选出的车日分别记录。", "",
                  "Restoration requires the entire register across all six weeks. Increments are rated kW "
                  "relative to the starting facility. Weekly register feasibility and daily selection are checked separately.",
                  "", _row("原设施 / Start", "方向 / Site", "恢复条件 / Restoration requirement", "最小增量 / Minimum kW",
                           "下界 / Lower kW", "已验证 / Verified kW", "达到上界 / Witness"),
                  "|---|---|---|---:|---:|---:|---|"])
    for d, r in repairs["starts"].items():
        for site, scope in [("综合 / Both", r), *r["directions"].items()]:
            for requirement, proof in (("固定集合 / Fixed register", scope),
                                       ("逐日顺序 / Daily selection", scope["daily_policy"]),
                                       ("两者共同 / Both requirements", scope["joint"])):
                cells = [proof[k] if proof[k] is not None else "—" for k in
                         ("minimum_added_kw", "minimum_possible_added_kw", "verified_added_kw")]
                lines.append(_row(d, site, requirement, *cells, ", ".join(proof["ways_at_verified_kw"]) or "—"))
    lines.extend(["", _row("原设施 / Start", "恢复设计 / Restoration", "新增 kW / Added kW",
                           "全周物理可行 / Fixed register", "逐日顺序 / Daily selection",
                           "逐日策略保留周数 / Weeks retaining R"), "|---|---|---:|---|---|---:|"])
    policies = {"retained": "六周保留 / retained", "omitted": "有车日遗漏 / omissions",
                "unresolved": "未定 / open", "unchecked": "未查 / unchecked"}
    for start, r in repairs["starts"].items():
        witnesses = {d for scope in (r, *r["directions"].values()) for d in scope["ways_at_verified_kw"]}
        for option in r["options"]:
            if option["design"] in witnesses or option["daily_policy_weeks"]:
                kept = sum(s == "feasible" for s in option["daily_policy_weeks"].values())
                lines.append(_row(start, option["design"], option["added_kw"], FEASIBLE[option["fixed_R_status"]],
                                  policies[option["daily_policy_status"]], f"{kept}/6"))
    lines.extend(["", "新增核验设施 / Additional designs checked — " +
                  (", ".join(repairs["extra_designs"]) or "∅") + f' ({len(repairs["extra_designs"])}/{repairs["limit"]}).',
                  "", "[逐周证据、已排除的小档位与逐日服务 / Weekly proofs, smaller ratings and daily service](holdout_test.json)", ""])
    return lines


def _sensitivity_section(main, sensitivity):
    lines = ["## 停靠资格敏感性 · Charging eligibility sensitivity", "",
             "留出期 20 个两端相距至少 1 km 的已映射停靠区间均属 5 号车，源自 17 对相邻行程。"
             "主情景允许在这些窗口充电。敏感性关闭窗口，保留跨日衔接，重新登记并只检验服务。"
             "断点之间未记录的行驶能耗不计入模型。", "",
             "All 20 mapped date-clipped intervals with endpoints at least 1 km apart belong to vehicle 5 "
             "and span 17 track pairs. The main run permits charging. The sensitivity removes those windows, "
             "preserves cross-day links, registers service anew and evaluates service only. Energy consumed "
             "during unrecorded travel between the endpoints is outside the model.", ""]
    state = sensitivity["status"]
    if state != "complete":
        messages = {"stopped_recommendation_changed": "主结果触发推荐改变停止条件 / main result triggered the recommendation stop",
                    "wall_limit": "达到墙钟上限 / wall-clock limit",
                    "unresolved": "服务未判定 / service unresolved"}
        return lines + [f"未完成 / Incomplete — {messages[state]}.", ""]
    lost, gained = sensitivity["registration_lost"], sensitivity["registration_gained"]
    lines.extend([f"登记移出 / Removed — {_duties(lost)}.  登记新增 / Added — {_duties(gained)}.", "",
                  _row("设施 / Facility", "主结果 / Main", "敏感性 / Sensitivity", "结论改变 / Changed",
                       "少完成 (ID) / Missing"), "|---|---|---|---|---|"])
    for d in (PORT20, PORT40):
        original, revised = main["service_status"][d], sensitivity["service_status"][d]
        changed = "?" if "unresolved" in (original, revised) else "是 / yes" if original != revised else "否 / no"
        lines.append(_row(d, SERVICE[original], SERVICE[revised], changed, _duties(sensitivity["missing"][d])))
    return lines + [""]


def _reproduction(summary):
    return ["## 复现 · Reproduction", "",
            f'正式运行源码 / Source — `{summary["source_commit"]}`. '
            f'墙钟 / Wall time — {summary["formal_seconds"]:.2f} s. '
            f'求解 / Solver calls — {summary["solve_count"]}.', "",
            "从仓库根执行。下列两条 Python 命令分别重新求解至新目录和独立回放已有正式归档。 / "
            "From the repository root, the two Python commands reproduce the solves in a fresh directory "
            "and independently replay the existing formal archive.", "",
            "```powershell", "$env:PYTHONPATH = 'src'",
            r"$archive = 'C:\Users\27788\UM-local-records\conversations\0001_records\runs\20261121_holdout_weeks'",
            "$fresh = Join-Path $archive ('reproduction-' + [guid]::NewGuid().ToString('N'))",
            r".\.venv\Scripts\python.exe -m um_charging.holdout --output $fresh",
            r".\.venv\Scripts\python.exe -m um_charging.holdout --verify (Join-Path $archive 'formal')", "```", ""]


def render(summary):
    """Render a report without reading files or running a solver."""
    lines = ["# 固定充电设施的六周留出检验 · Six-week holdout of fixed charging facilities", "",
             "[运输样本 / Sample](DATA.md#six-holdout-weeks-for-the-fixed-m8-facilities) · "
             "[留出结果 / Holdout data](holdout_test.json) · [规划期 / M8 study](site_sizing.md)", ""]
    main, bills = summary["main"], summary["billing"]
    if main is None:
        lines += ["达到墙钟上限，主登记集合未完成。 / The wall-clock limit was reached during registration.", ""]
        return "\n".join(lines + _reproduction(summary))
    aggregate = Counter(c["recommendation_status"] for c in bills["cases"]) if bills else Counter()
    registered = [r["registered"] for r in main["weekly"]]
    count_text = "?" if any(n is None for n in registered) else str(sum(registered))
    eligible = sum(r["eligible"] for r in main["weekly"])
    e, old = main.get("annual_grid_kwh"), main.get("m8_annual_grid_kwh", 58387.79)
    consumption = "?" if e is None else f"{e:,.2f}"
    lines.extend([f"2021-11-08 至 2021-12-19，基准登记 **{count_text}/{eligible}** 个完整车日。"
             f"登记任务的网侧年电量为 **{consumption} kWh/年**，M8 为 **{old:,.2f} kWh/年**。"
             "两者按各自六周任务重复至 52 周，反映运输任务量的差别。", "",
             f"Over 8 November–19 December 2021 the baseline registered **{count_text}/{eligible}** complete "
             f"vehicle-days. Registered grid energy is **{consumption} kWh/year** in the holdout and "
             f"**{old:,.2f} kWh/year** in M8. Each annualization repeats its own six-week transport workload.", ""])
    if bills:
        lines.extend([f"与 M8 最低方案相比，{aggregate['unchanged']} 个口径一致，{aggregate['changed']} 个改变，"
                      f"{aggregate['unresolved']} 个未定。 / Among the predeclared facilities, the M8 recommendation "
                      f"holds in {aggregate['unchanged']} cases, changes in {aggregate['changed']} and remains "
                      f"unresolved in {aggregate['unresolved']}.", ""])
    lines.extend(["留出期仅比较三套事先固定的设施。设施固定后按周全信息优化，调度时已知一周全部任务和原生 DE-LU "
                  "日前小时价格。留出期没有重新选型，排名即使保持，也可能有更便宜的其他设计。", "",
                  "Only the three prespecified facilities enter this comparison. With facilities fixed, each weekly "
                  "schedule uses all tasks and native DE-LU day-ahead hourly prices for that week. Designs were "
                  "not reselected in the holdout, so even an unchanged ranking allows for a cheaper untested design.", ""])
    lines += _cost_section(bills) + _service_section(main) + _repair_section(summary["repairs"])
    lines += _sensitivity_section(main, summary["sensitivity"])
    lines += _reproduction(summary)
    return "\n".join(lines)
