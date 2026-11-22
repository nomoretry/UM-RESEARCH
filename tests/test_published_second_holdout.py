"""Check the bilingual M10 tables against the sealed publication summary."""
from collections import Counter
from datetime import datetime
from decimal import Decimal
from itertools import groupby
import json
from pathlib import Path
import re


STUDY = Path(__file__).resolve().parents[1] / "studies" / "fleet-service"
REPORT = (STUDY / "second_holdout.md").read_text(encoding="utf-8")
RESULT_PATH = STUDY / "second_holdout.json"


def results():
    return json.loads(RESULT_PATH.read_text(encoding="utf-8"))


def table(header_cell):
    matches = []
    for in_table, lines in groupby(REPORT.splitlines(), lambda line: line.startswith("|")):
        if in_table:
            rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]
            if header_cell in rows[0]:
                assert all(len(row) == len(rows[0]) for row in rows)
                matches.append(rows[2:])
    match, = matches
    return match


def published_interval(cell):
    endpoints = [Decimal(endpoint.replace(",", "")) for endpoint in cell.split("–")]
    assert len(endpoints) in (1, 2)
    return [endpoints[0], endpoints[-1]]


def cents(bounds):
    if isinstance(bounds, (int, float)):
        bounds = [bounds, bounds]
    lower, upper = bounds
    return [Decimal(f"{bound:.2f}") for bound in (lower, upper)]


def published_duties(cell):
    return [list(pair) for pair in re.findall(r"(\d{4}-\d{2}-\d{2}) \((\d+)\)", cell)]


def keyed_costs(rows):
    indexed = {(row["tariff"], row["basis"]): row for row in rows}
    assert len(indexed) == len(rows) == 12
    return indexed


def test_published_second_holdout_register_and_primary_endpoint():
    result = results()
    result_size = RESULT_PATH.stat().st_size
    assert 0 < result_size <= 300_000
    holdout = result["holdout"]
    period = holdout["period"]
    registration = holdout["registration"]
    primary = holdout["primary"]
    f20 = holdout["f20"]
    assert sum(registration["weekly_counts"]) == registration["registered_vehicle_days"]
    assert len(registration["weekly_counts"]) == period["weeks"]
    counts = "/".join(str(count) for count in registration["weekly_counts"])
    assert REPORT.count(counts) == 2
    assert f'{period["start_date"]} 至 {period["end_date"]}' in REPORT
    assert f'{registration["eligible_vehicle_days"]} 个完整车日中登记 {registration["registered_vehicle_days"]} 个' in REPORT
    assert len(primary["missing_duties"]) == 1 and len(f20["missing_duties"]) == 2
    assert primary["classification"] == "failure_independent"
    first, second = table("车日缺口 / Missed duty")
    assert published_duties(second[1]) == primary["missing_duties"]
    assert set(map(tuple, primary["missing_duties"])) < set(map(tuple, f20["missing_duties"]))
    added_date, added_vehicle = next(duty for duty in f20["missing_duties"] if duty not in primary["missing_duties"])
    assert f"{added_date} 的车 {added_vehicle}" in REPORT
    first_evidence = result["first_holdout"]
    assert published_duties(first[1]) == first_evidence["missing_duties"]
    assert f'{first_evidence["pre_trip_shortfall_kwh"]:.3f} kWh' in first[3]
    assert first[2] == "行程储备 / In-trip reserve"
    assert second[2] == "连续段末电量 / Terminal energy"
    assert f'{primary["terminal_upper_kwh"]:.3f} kWh' in second[3]
    assert f'{primary["terminal_shortfall_kwh"]:.3f} kWh' in second[3]
    assert f'{primary["terminal_target_kwh"]:g} kWh' in second[3]


def test_published_second_holdout_selection_bills_and_scope():
    selection = results()["selection"]
    assert f'{selection["registered_vehicle_days"]}/{selection["eligible_vehicle_days"]}' in REPORT
    assert f'{selection["unresolved_fine_grid_points"]} 个点未判定' in REPORT
    assert Counter(row["design"] for row in selection["annual_costs"]) == selection["winner_counts"]
    expected = keyed_costs(selection["annual_costs"])
    rows = table("新建选型年费 / Selection bill, new")
    assert len(rows) == 6
    assert {row[0] for row in rows} == {tariff for tariff, _ in expected}
    roles = {"p1-20-w20": "F20", "p1-40-w20": "F40"}
    for tariff, new_design, new, existing_design, existing in rows:
        for basis, design, bill in (("new", new_design, new), ("existing", existing_design, existing)):
            assert design == roles[expected[tariff, basis]["design"]]
            assert published_interval(bill) == cents(expected[tariff, basis]["annual_cost_eur_2025"])


def test_published_second_holdout_15_kw_thresholds_and_breakpoints():
    result = results()
    thresholds = {
        (row["design"], row["basis"]): row for row in result["warehouse_15kw"]["official_thresholds"]
    }
    rows = table("新建净价门槛 / Break-even net price, new")
    assert len(rows) * 2 == len(thresholds) == 4
    for point, new, existing in rows:
        design, caps = point.split(" [")
        for basis, cell in (("new", new), ("existing", existing)):
            row = thresholds[design, basis]
            assert caps == ",".join(map(str, row["caps_kw"])) + "]"
            assert published_interval(cell) == cents(row["net_equipment_eur_2026"])
    breakpoint = result["breakpoint_sensitivity"]
    assert f'关闭 {breakpoint["excluded_windows"]} 个已映射的记录断点区间' in REPORT
    assert f'基准重新登记 {breakpoint["registered_vehicle_days"]}/' in REPORT
    assert all(date in REPORT for date, _ in breakpoint["removed_duties"])
    assert breakpoint["f40"]["failed_weeks"] == []
    failed_week, = breakpoint["f20"]["failed_weeks"]
    assert f'F20 在 {failed_week} 起始周不可行' in REPORT


def test_published_second_holdout_annual_bills_and_gaps():
    holdout = results()["holdout"]
    expected = keyed_costs(holdout["annual_costs"])
    rows = table("B 新建留出年费 / Holdout bill, new")
    assert len(rows) == 6
    assert {row[0] for row in rows} == {tariff for tariff, _ in expected}
    labels = {"frozen": "冻结 / Frozen", "rated_fallback": "额定后备 / Rated fallback"}
    for tariff, new, existing, policy in rows:
        for basis, cell in (("new", new), ("existing", existing)):
            row = expected[tariff, basis]
            assert published_interval(cell) == cents(row["annual_cost_eur_2025"])
            assert row["design"] == "p1-50-w50"
            assert row["rank_bounds"] == [1, 1]
            assert labels[row["point_source"]] == policy


def test_published_second_holdout_repair_and_sensitivity_tables():
    holdout = results()["holdout"]
    repairs = holdout["repairs"]
    rows = table("恢复后新建年费 / Restored bill, new")
    priced = {row["design"]: row for row in repairs["priced"]["options"] if row["bills"]}
    assert {row[0] for row in rows} == priced.keys()
    assert len(rows) == len(priced) == 2
    for design, new_fixed, existing_fixed, new, existing in rows:
        for basis, fixed, bill in (("new", new_fixed, new), ("existing", existing_fixed, existing)):
            row = priced[design]["bills"][basis]
            assert published_interval(fixed) == cents(row["extra_fixed_eur_2025"])
            assert published_interval(bill) == cents(row["annual_cost_eur_2025"])
            assert row["added_total_eur_2025"] is None
    physical = repairs["physical"]
    assert len(physical["counted_designs"]) == 6
    assert not physical["warehouse_35_kw_tested"]
    for row in physical["minima"]:
        bound = row["fixed_service"]
        assert f'增容下界均为至少 {bound["minimum_possible_added_kw"]} kW' in REPORT
        assert bound["verified_added_kw"] is None
    assert "仓库 35 kW 未检验" in REPORT
    sensitivity = holdout["sensitivities"]
    parking = sensitivity["parking"]
    assert f'关闭 {parking["excluded_windows"]} 个停车资格区间后，基准重新登记 {parking["registered_vehicle_days"]} 个车日' in REPORT
    assert all(date in REPORT for date, _ in parking["removed_duties"])
    for (margin, duties), evidence in zip(
        table("基准缺口 / Baseline misses"), sensitivity["energy_margins"], strict=True
    ):
        assert margin == f'+{evidence["percent_increase"]}%'
        assert published_duties(duties) == evidence["baseline_missing_duties"]


def test_published_second_holdout_sealing_chronology():
    chronology = results()["chronology"]
    timeline = {(commit, datetime.fromisoformat(time)) for _, commit, time in table("提交 / Commit")}
    archived = {
        ((event.get("commit") or "—")[:8], datetime.fromisoformat(event["time"]).replace(tzinfo=None))
        for event in chronology.values()
    }
    assert timeline == archived


def test_published_second_holdout_operating_costs():
    policies = results()["operating_policies"]
    union_costs = keyed_costs(policies["robust_union"]["annual_costs"])
    rows = table("官方新建年费 / Selection-period official new bill")
    assert len(rows) == 4
    names = (
        "全信息 / Full information",
        "按天滚动 / Daily rolling",
        "到站即充 / Charge-on-arrival",
        "各周最低方案的设施并集 / Union of weekly least-cost facilities",
    )
    sources = ("full_information", "rolling", "immediate", "robust_union")
    for (label, design, caps, new, existing), name, key in zip(rows, names, sources, strict=True):
        assert label == name
        for basis, cell in (("new", new), ("existing", existing)):
            item = (
                union_costs["official", basis]
                if key == "robust_union"
                else policies[f"official_{basis}"][key]
            )
            assert design == item["design"]
            assert caps == "/".join(map(str, item["caps_kw"]))
            assert published_interval(cell) == cents(item["annual_cost_eur_2025"])
    for basis in ("new", "existing"):
        surplus = policies[f"official_{basis}"]["immediate"]["terminal_surplus_eur_2025_per_year"]
        assert f"{surplus:,.2f} 欧元/年" in REPORT
    for row in policies["robust_union"]["ex_ante_premiums"]:
        low, high = row["annual_premium_eur_2025"]
        assert f"{low:.2f} 至 {high:.2f}".replace("-", "−") in REPORT


def test_published_second_holdout_secondary_outcomes_and_unidentified_differences():
    holdout = results()["holdout"]
    union = holdout["robust_union"]
    summary = {r["endpoint"]: r for r in holdout["secondary"]}
    summary["U"] = union
    rows = table("证据等级 / Evidence class")
    classifications = {
        "只有求解器证明 / Solver-only failure": "failure_solver_only",
        "独立回放确证失败 / Failure confirmed by independent replay": "failure_independent",
        "独立复核确证失败 / Failure independently corroborated": "failure_independent",
    }
    assert [row[0] for row in rows] == ["S1", "S2", "S3", "U"]
    for endpoint, _, dates, evidence in rows:
        assert dates.split(", ") == summary[endpoint]["failed_weeks"]
        assert classifications[evidence] == summary[endpoint]["classification"]
    assert union["annual_cost_eur_2025"] is None
    differences = {(row["basis"], row["role"]): row for row in holdout["official_differences"]}
    assert differences.keys() == {(basis, role) for basis in ("new", "existing") for role in ("I", "D40")}
    for row in differences.values():
        assert row["comparator"] == "F40" and row["classification"] == "unidentified"
        assert row["including_surplus_eur_2025"] is None
        assert row["excluding_surplus_eur_2025"] is None
    assert "I−F40 和 D40−F40 的官方年费差均不可识别" in REPORT


def test_published_second_holdout_timestamp_manifests_and_replay_totals():
    result = results()
    older, newer = result["external_timestamps"]
    for entry in (older, newer):
        assert f'覆盖 {entry["files"]} 个文件' in REPORT
        assert REPORT.count(entry["sha256"]) == 2
    assert older["bitcoin_proof_at_opening"]
    heights = list(map(str, older["bitcoin_block_heights"]))
    assert "、".join(heights) in REPORT
    assert ", ".join(heights[:-1]) + " and " + heights[-1] in REPORT
    assert newer["calendar_pending_at_opening"] and not newer["bitcoin_proof_at_opening"]
    assert "Any block attestation for the second manifest postdates opening." in REPORT
    replay = result["verification"]
    assert replay["native_requests"] == replay["feasible_replayed"] + replay["infeasible_certificates"]
    assert f'{replay["native_requests"]} 个原生请求' in REPORT
    assert f'{replay["feasible_replayed"]} 个可行结果' in REPORT
    assert f'{replay["infeasible_certificates"]} 个不可行证书' in REPORT
    assert replay["unresolved_weekly_groups"] == 0 and "无未定周组" in REPORT
    repeat = replay["determinism"]
    assert f'种子 {repeat["seed"]}' in REPORT
    assert f'{repeat["matched"]}/{repeat["sampled"]} 匹配' in REPORT
