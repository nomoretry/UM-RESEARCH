from copy import deepcopy
import json

from um_charging import holdout_repair_report as report


def _examples():
    base = {"status": "certified", "annual_total_eur_bounds": [1250.12, 1250.14]}
    fixed = []
    comparison = []
    for tariff in report.TARIFF:
        for basis in report.BASIS:
            fixed.append(dict(scenario=tariff, connection_basis=basis, m8_winner=report.PORT20,
                              recommendation_status="changed", winner=report.BASE,
                              bills={report.PORT20: dict(status="service_gap"),
                                     report.PORT40: dict(status="service_gap"), report.BASE: base},
                              rank_bounds={report.BASE: [1, 1]}))
            policy = "frozen" if tariff == "N0" else "rated_fallback"
            ranges = {report.BASE: [1, 2], report.REPAIRS[0]: [1, 2], report.REPAIRS[1]: [3, 3]}
            repairs = {d: dict(main=dict(**base, policy=policy), reference=dict(**base, policy="service_cap_reference"))
                       for d in report.REPAIRS}
            comparison.append(dict(scenario=tariff, connection_basis=basis, baseline=base, repairs=repairs,
                                   rank_bounds=ranges, ranking_status="overlap"))
    old = dict(stop_reason="recommendation_changed", sensitivity=dict(status="stopped_recommendation_changed"),
               main=dict(service_status={report.BASE: "matched", report.PORT20: "service_gap",
                                         report.PORT40: "service_gap"}), billing=dict(cases=fixed))
    operating = [dict(design=d, caps_kw=[p, 20], week_service_status={"2021-11-08": "feasible"})
                 for d, p in zip(report.REPAIRS, (20, 40))]
    conf = dict(id="p1-20-w20 @ [20,15]", design=report.REPAIRS[0], caps_kw=[20, 15],
                status="matched", served_count=5, missing=[], lost_vs_main=[["2021-11-19", "5"]],
                gained_vs_main=[], diagnostics=[], unresolved_dates=[])
    sensitive = dict(status="complete", registered_count=5, registration_lost=[["2021-11-19", "5"]],
                     registration_gained=[], registration_diagnostics=[], configs=[conf],
                     target_gap=dict(date="2021-11-26", vehicle_id="1", registered=True,
                                     by_config={conf["id"]: "served"}, port_only_gap_persists=True),
                     port_only_insufficient=True)
    new = dict(billing=dict(cases=comparison, operating_points=operating), sensitivity=sensitive,
               source_commit="follow-up-sha", formal_seconds=60, solve_count=7, audited_primals=6,
               stop_reason="completed")
    return old, new


OLD_MD = "\n\n".join(("Original introduction.", report.FIXED_TABLE, "| 网费 / Tariff | 原表 |\n|---|---|",
                     "Baseline fallback note.", report.DAILY, "Original daily evidence and minimum proof.",
                     report.SENSITIVITY, "断点能耗处理。 / Recorded energy assumptions.",
                     "主结果已证实原推荐存在服务缺口，敏感性待核验。", report.REPRODUCTION,
                     "python -m um_charging.holdout --output $fresh\npython -m um_charging.holdout --verify $old"))


def test_public_fields_disambiguate_only_qualified_facility_and_leave_archive_intact():
    old, new = _examples()
    copied = deepcopy(old)
    selected = report.curated(old, new)
    assert old == copied
    assert "changed" not in json.dumps(selected)
    assert len(selected["billing"]["cases"]) == 12
    for row in selected["billing"]["cases"]:
        assert row["m8_winner_retained_service"] is False
        assert row["m8_winner_billed"] is False
        assert row["service_qualified_fixed_facilities"] == [report.BASE]
        assert row["lowest_cost_billed_fixed_facility"] == report.BASE
        assert "winner" not in row and "recommendation_status" not in row
    assert selected["sensitivity"] == new["sensitivity"]
    assert selected["repair_billing"]["cases"] == new["billing"]["cases"]


def test_report_preserves_evidence_and_commands_and_separates_reference_bills_from_ranks():
    selected = report.curated(*_examples())
    md = report.render(OLD_MD, selected)
    assert md.count("Service shortfall, no bill") == 12
    assert md.count("名次 / Ranks (B, 20/20, 40/20)") == 1
    assert md.count("1–2, 1–2, 3") == 12
    assert "1,250.12–1,250.14 (后备 / fallback)" in md
    assert "20/15 服务限峰参照 / Reference" in md
    assert "2021-11-19 (5)" in md and "both port-only facilities still miss this duty" in md
    assert "Baseline fallback note." in md and "Original daily evidence and minimum proof." in md
    assert "python -m um_charging.holdout --output $fresh" in md
    assert "python -m um_charging.holdout --verify $old" in md
    assert "um_charging.holdout_repair --previous $previous --verify" in md


def test_unresolved_sensitivity_is_distinct_from_an_empty_set():
    old, new = _examples()
    sensitive = new["sensitivity"]
    sensitive.update(registered_count=None, registration_gained=None, status="unresolved",
                     port_only_insufficient=None)
    sensitive["target_gap"].update(registered=None, port_only_gap_persists=None)
    sensitive["configs"][0].update(served_count=None, status="unresolved", unresolved_dates=["2021-11-19"])
    md = report.render(OLD_MD, report.curated(old, new))
    assert "Added — ?" in md and "Port-only sufficiency is unresolved" in md
    assert "未定 / open (2021-11-19)" in md
