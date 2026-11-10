# 数学规范—代码—验证对应

更新2026-11-10：`src/um_charging/`现支持固定设施和投资两版。旧`legacy/truck_charging_v1/`仍为有限方案模型，两者任务/电量边界不同。正式源码43e34cac0d9ad4268dc54e9aa98fcea25e977320，102测试、9投资情景/140组合及原6情景回归见[结果](../../results/investment_20261110/README.md)。

| 编号 | 已实现位置 | 独立复核/验证入口 | 未覆盖部分 |
|---|---|---|---|
| 数据与窗口 | `scripts/verify_dataset_snapshot.py`；`model.py:validate_input` | 原验证器、原SHA清单、隔离恢复；`test_rejects_invalid_input_without_inference` | 德国数据未接优化；真实窗口/缺口未解决 |
| C01 | `model.py:solve` 新增接口整数及互斥扩容二元；启用仍固定 | `test_upgrade_options_are_alternatives_not_additive`；`test_independent_investment_checker_rejects_corruption`的整数/档位/停站篡改 | 未优化开站；年化投资未实现 |
| C02 | `model.py:solve` 占用上界和单车互斥 | 独立占用检查；行驶充电/错误站点输入和篡改测试 | 不证明给定路线真实；无槽内移动 |
| C03 | `model.py:solve` 功率受占用及车辆/接口共同上限约束 | 独立功率复算；`power_without_interface` 篡改测试 | 无共享功率柜、非线性充电 |
| C04 | `model.py:solve` 原有接口＋新增接口进入并发上限 | `interface_bottleneck`；新算例最终槽三车必补能解析下界；`removed_interfaces`篡改 | 无槽内接口轮换 |
| C05 | `model.py:solve` 原可用功率＋选定一档新增kW | `power_bottleneck`；+50/+75档位解析比较；`removed_upgrade`篡改 | 不是潮流或并网证明 |
| C06 | `model.py:solve` 连续电量状态和平衡 | 独立从初值积分；`test_energy_is_not_reset_between_cycles`、`soc` 篡改测试 | 尚无实际多日任务链 |
| C07 | `model.py:solve` 电量界、初值和终端恢复 | `test_initial_soc_cannot_hide_intra_cycle_underflow`、`terminal_energy` 篡改测试 | 仅完整时间槽 |
| 目标 | `model.py:solve` 周期等效接口/扩容投资＋本周期电费 | `validation.py:check_solution`独立复算；`investment_price`/`operating_price`/`objective`篡改 | 仅合成周期等效成本，年化多日未实现 |
| 零需求/零收益/无解 | `model.py:make_scenarios` 明确测试变换 | 三类解析无解、`test_more_grid_capacity_has_zero_cost_benefit`、`test_zero_demand_requires_no_grid_energy` | 不外推现实阈值或经济结论 |
| 运行与验证 | `src/um_charging/__main__.py` | 原始解、独立检查、目标/界/gap、提交与输入hash | 无可行解时原始解检查不适用，不能记为通过 |
| 闭合位置链 | `model.py:_validate_timeline` | `test_rejects_invalid_investment_input`；`test_transport_and_initial_energy_identical_across_comparisons` | 只校验输入一致性，不验证真实行车时长/窗口 |
| 投资全枚举 | `investment_experiment.py:enumerate_facilities`、`compare_joint_to_enumeration` | `test_analytic_optimum_matches_all_fixed_facility_combinations`，140组合；未解决组合拒绝通过 | 共享原运营模型和HiGHS，非独立求解器 |
| 投资正式入口 | `investment_cli.py:main` | 干净源码要求、原始输入/解/独立检查、枚举/回归清单 | 全日志仅外部本地；单周期模式 |

以上 `model.py`/`validation.py` 指 `src/um_charging/`；测试位于 [test_fixed_facility.py](../../tests/test_fixed_facility.py)。解析预期详见 [MINIMAL_INSTANCE](MINIMAL_INSTANCE.md)，执行证据单独保存在精选结果中。

旧原型和单站脚本证据见 [恢复审计](../research/LEGACY_RECOVERY_20261104.md)。旧原型的每任务独立初始电量、定功率整槽方案和有限路径集合不代表本模型的C06/C07已验证。

正式证据：源码提交 `4d3f3a045cc02ddde35acd69249ff08f78270861`；[新模型结果](../../results/fixed_facility_20261104/README.md)含37项测试与六情景，[旧原型本次结果](../../results/legacy_reproduction_20261104/README.md)含106项测试。数据正式run与失败记录见[数据结果](../../results/data_verification_20261104/README.md)。

2026-11-09文献与代码复核：上述已实现范围未变，未重跑求解。投资、跨节点任务链和换电的建议见[建模衔接说明](../literature/20261109/BASELINE_DESIGN.md)，其公式为计划，不是新增实现。

上段为11月9日历史结论。11月10日投资和跨节点合成链已实现并验证；换电仍未实现。新增测试见[test_investment](../../tests/test_investment.py)和[test_investment_input](../../tests/test_investment_input.py)，精确字段见[输入规范](INVESTMENT_INPUT.md)。原37测试包含在本次102中，不能将原106历史测试算作本次新运行。
