# 数学规范—代码—验证对应

更新2026-11-10：`src/um_charging/`支持固定设施v1、投资v1与显式时间/连接政策v2。旧`legacy/truck_charging_v1/`仍为有限方案模型，两者任务/电量边界不同。本轮源码1c4df03c6a6943ce221e09e05a2bce538de304a7，149测试、54情景/840组合、18历史比较及原6回归见[时间粒度结果](../../results/timegrid_20261110/README.md)。上轮源码43e34ca及102测试/140组合保留为[历史结果](../../results/investment_20261110/README.md)。

| 编号 | 已实现位置 | 独立复核/验证入口 | 未覆盖部分 |
|---|---|---|---|
| 数据与窗口 | `scripts/verify_dataset_snapshot.py`；`model.py:validate_input` | 原验证器、原SHA清单、隔离恢复；`test_rejects_invalid_input_without_inference` | 德国数据未接优化；真实窗口/缺口未解决 |
| C01 | `model.py:solve` 新增接口整数及互斥扩容二元；启用仍固定 | `test_upgrade_options_are_alternatives_not_additive`；`test_independent_investment_checker_rejects_corruption`的整数/档位/停站篡改 | 未优化开站；年化投资未实现 |
| C02 | `model.py:solve` 占用上界和单车互斥 | 独立占用检查；行驶充电/错误站点输入和篡改测试 | 不证明给定路线真实；无槽内移动 |
| C03 | `model.py:solve` 功率受占用及车辆/接口共同上限约束 | 独立功率复算；`power_without_interface` 篡改测试 | 无共享功率柜、非线性充电 |
| C04 | `model.py:solve` 原有接口＋新增接口进入并发上限 | `interface_bottleneck`；粗槽三车必占用与细槽2接口见证；`removed_interfaces`篡改 | 槽内不能轮换；槽边界政策需显式 |
| C05 | `model.py:solve` 原可用功率＋选定一档新增kW | `power_bottleneck`；+50/+75档位解析比较；`removed_upgrade`篡改 | 不是潮流或并网证明 |
| C06 | `model.py:solve` 连续电量状态和平衡 | 独立从初值积分；`test_energy_is_not_reset_between_cycles`、`soc` 篡改测试 | 尚无实际多日任务链 |
| C07 | `model.py:solve` 电量界、初值和终端恢复 | `test_initial_soc_cannot_hide_intra_cycle_underflow`、`terminal_energy` 篡改测试 | 仅完整时间槽 |
| C08 | `model.py:solve` v2整次连续插枪窗口占用相等 | `validation.py:check_solution`直接逐对检查；`tests/test_timegrid_model.py`锁定/变功率/资格中断语义 | 不代表真实正换枪耗时；仅两种明确政策 |
| 目标 | `model.py:solve` 周期等效接口/扩容投资＋本周期电费 | `validation.py:check_solution`独立复算；`investment_price`/`operating_price`/`objective`篡改 | 仅合成周期等效成本，年化多日未实现 |
| 零需求/零收益/无解 | `model.py:make_scenarios` 明确测试变换 | 三类解析无解、`test_more_grid_capacity_has_zero_cost_benefit`、`test_zero_demand_requires_no_grid_energy` | 不外推现实阈值或经济结论 |
| 运行与验证 | `src/um_charging/__main__.py` | 原始解、独立检查、目标/界/gap、提交与输入hash | 无可行解时原始解检查不适用，不能记为通过 |
| 闭合位置链 | `model.py:_validate_timeline` | `test_rejects_invalid_investment_input`；`test_transport_and_initial_energy_identical_across_comparisons` | 只校验输入一致性，不验证真实行车时长/窗口 |
| 投资全枚举 | `investment_experiment.py:enumerate_facilities`、`compare_joint_to_enumeration` | 原140组合回归；本轮840组合，v2固定设施保留C08；`test_analytic_two_site_optimum_and_enum_preserve_policy` | 共享原运营模型和HiGHS，非独立求解器 |
| 投资正式入口 | `investment_cli.py:main` | 干净源码要求、原始输入/解/独立检查、枚举/回归清单 | 全日志仅外部本地；单周期模式 |
| 物理链细分 | `timegrid.py:refine_physical_cycle` | `physical_event_ledger`与`audit_physical_equivalence`重新聚合；篡改窗口/设备/能耗/费用拒绝测试 | 只支持本次明确的原一小时链与60/30/15分钟 |
| 时间粒度正式入口 | `timegrid_cli.py:main`、`configs/timegrid_study.json` | 54物理审计、54联合—枚举比较、18历史比较、6回归；原始证据含界限/gap | 不可行解检查不适用，下一轮二维扫描尚未运行 |
| 解析可行见证 | `tests/test_timegrid.py:test_explicit_two_connector_witness_without_extra_parking` | 手工30分钟功率及15分钟复制解；独立C01–C08检查 | 只是最优值见证，不是唯一调度或真实港口排程 |

以上 `model.py`/`validation.py` 指 `src/um_charging/`；测试位于 [test_fixed_facility.py](../../tests/test_fixed_facility.py)。解析预期详见 [MINIMAL_INSTANCE](MINIMAL_INSTANCE.md)，执行证据单独保存在精选结果中。

旧原型和单站脚本证据见 [恢复审计](../research/LEGACY_RECOVERY_20261104.md)。旧原型的每任务独立初始电量、定功率整槽方案和有限路径集合不代表本模型的C06/C07已验证。

正式证据：源码提交 `4d3f3a045cc02ddde35acd69249ff08f78270861`；[新模型结果](../../results/fixed_facility_20261104/README.md)含37项测试与六情景，[旧原型本次结果](../../results/legacy_reproduction_20261104/README.md)含106项测试。数据正式run与失败记录见[数据结果](../../results/data_verification_20261104/README.md)。

2026-11-09文献与代码复核：上述已实现范围未变，未重跑求解。投资、跨节点任务链和换电的建议见[建模衔接说明](../literature/20261109/BASELINE_DESIGN.md)，其公式为计划，不是新增实现。

上段为11月9日历史结论。11月10日投资和跨节点合成链已实现并验证；换电仍未实现。新增测试见[test_investment](../../tests/test_investment.py)和[test_investment_input](../../tests/test_investment_input.py)，精确字段见[输入规范](INVESTMENT_INPUT.md)。原37测试包含在本次102中，不能将原106历史测试算作本次新运行。
