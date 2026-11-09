# 数学规范—代码—验证对应

2026-11-04：旧工程已在用户工作目录实物定位并恢复至 `legacy/truck_charging_v1/`。新固定设施模型位于 `src/um_charging/`；两者的任务与电量边界不同。实际执行状态见 [STATUS](../research/STATUS.md)。

| 编号 | 已实现位置 | 独立复核/验证入口 | 未覆盖部分 |
|---|---|---|---|
| 数据与窗口 | `scripts/verify_dataset_snapshot.py`；`model.py:validate_input` | 原验证器、原SHA清单、隔离恢复；`test_rejects_invalid_input_without_inference` | 德国数据未接优化；真实窗口/缺口未解决 |
| C01 | `model.py:solve` 固定设施参数 | `test_inactive_site_cannot_charge` | 新增接口、站点投资、离散扩容未实现 |
| C02 | `model.py:solve` 占用上界和单车互斥 | 独立占用检查；行驶充电/错误站点输入和篡改测试 | 不证明给定路线真实；无槽内移动 |
| C03 | `model.py:solve` 功率受占用及车辆/接口共同上限约束 | 独立功率复算；`power_without_interface` 篡改测试 | 无共享功率柜、非线性充电 |
| C04 | `model.py:solve` 每站每槽接口数 | `interface_bottleneck` 解析上界与求解；`interface_limit` 篡改测试 | 无槽内接口轮换 |
| C05 | `model.py:solve` 每站每槽可用接入功率 | `power_bottleneck` 解析上界与求解；`grid_limit` 篡改测试 | 不是潮流或并网证明 |
| C06 | `model.py:solve` 连续电量状态和平衡 | 独立从初值积分；`test_energy_is_not_reset_between_cycles`、`soc` 篡改测试 | 尚无实际多日任务链 |
| C07 | `model.py:solve` 电量界、初值和终端恢复 | `test_initial_soc_cannot_hide_intra_cycle_underflow`、`terminal_energy` 篡改测试 | 仅完整时间槽 |
| 目标 | `model.py:solve` 时变价格乘购电量与明确权重 | `test_hand_calculated_two_cycle_energy_and_cost`；独立 `OBJECTIVE` 复算 | 固定沉没成本省略，新增年化投资未实现 |
| 零需求/零收益/无解 | `model.py:make_scenarios` 明确测试变换 | 三类解析无解、`test_more_grid_capacity_has_zero_cost_benefit`、`test_zero_demand_requires_no_grid_energy` | 不外推现实阈值或经济结论 |
| 运行与验证 | `src/um_charging/__main__.py` | 原始解、独立检查、目标/界/gap、提交与输入hash | 无可行解时原始解检查不适用，不能记为通过 |

以上 `model.py`/`validation.py` 指 `src/um_charging/`；测试位于 [test_fixed_facility.py](../../tests/test_fixed_facility.py)。解析预期详见 [MINIMAL_INSTANCE](MINIMAL_INSTANCE.md)，执行证据单独保存在精选结果中。

旧原型和单站脚本证据见 [恢复审计](../research/LEGACY_RECOVERY_20261104.md)。旧原型的每任务独立初始电量、定功率整槽方案和有限路径集合不代表本模型的C06/C07已验证。

正式证据：源码提交 `4d3f3a045cc02ddde35acd69249ff08f78270861`；[新模型结果](../../results/fixed_facility_20261104/README.md)含37项测试与六情景，[旧原型本次结果](../../results/legacy_reproduction_20261104/README.md)含106项测试。数据正式run与失败记录见[数据结果](../../results/data_verification_20261104/README.md)。

2026-11-09文献与代码复核：上述已实现范围未变，未重跑求解。投资、跨节点任务链和换电的建议见[建模衔接说明](../literature/20261109/BASELINE_DESIGN.md)，其公式为计划，不是新增实现。
