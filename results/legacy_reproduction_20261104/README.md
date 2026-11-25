# 旧原型本次复现：2026-11-04

> **导读**：本文件记录按字节恢复的早期有限方案原型 `legacy/truck_charging_v1/` 的独立复现结果（106 项测试、6 组合成情景），运行于 **2026-11-04**。该原型与现行连续电量固定任务模型边界不同，仅作历史溯源；当前模型与研究结论请以 [数学模型](../../docs/model/FORMULATION.md) 及 [首页 README](../../README.md) 为准。
>
> **Guide:** This summary documents the **2026-11-04** independent rerun of the recovered finite-plan prototype `legacy/truck_charging_v1/` (106 tests, 6 synthetic scenarios). Preserved for historical provenance only; for the active continuous-SOC model and current conclusions see [FORMULATION.md](../../docs/model/FORMULATION.md) and [README.md](../../README.md).

这是恢复源码后的新运行，不是历史JSON的重命名。106项测试全部通过，六情景与历史摘要一致。源码版本、输入hash及完整本地证据索引见 reproduction.json。

| 情景 | 状态 | 年目标（模拟CNY） | 完整约束校验 |
|---|---|---:|---|
| base | optimal | 462000.0 | True |
| no_charge_needed | optimal | 315000.0 | True |
| site_power_limited | optimal | 491000.0 | True |
| tight_deadline_one_bay | infeasible | None | False |
| reverse_access_blocked | optimal | 608000.0 | True |
| relaxed_service | optimal | 461000.0 | False |

`relaxed_service` 用一个接口同时服务两车，独立校验正确拒绝；不是可执行调度。无解只针对生成的有限方案集。全部任务、成本和路网均为合成设置，每任务独立初始电量，不是连续任务链或真实建站结果。原始日志、方案集合与完整解只在外部本地Git。
