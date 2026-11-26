# 固定设施连续SOC：本次结果

> **导读**：本文件记录首个 4 小时三车固定设施连续电量 MILP 回归算例的验证结果（6 情景、37 项测试），运行于 **2026-11-04**。本目录保留基础模型回归证据；现行模型公式请见 [数学模型](../../docs/model/FORMULATION.md)，当前全部研究结论请以 [首页 README](../../README.md) 与 [仓库导览](../../docs/GUIDE.md) 为准。
>
> **Guide:** This file records the **2026-11-04** verification of the initial four-hour three-truck fixed-facility continuous-SOC MILP (6 scenarios, 37 tests). Preserved as baseline regression evidence; for the current formulation see [FORMULATION.md](../../docs/model/FORMULATION.md), and for overall conclusions see [README.md](../../README.md) and the [Repository Guide](../../docs/GUIDE.md).

2026-11-04 在提交 `4d3f3a045cc02ddde35acd69249ff08f78270861` 上正式运行；37项测试通过。新建合成实例，非旧原型结果、德国数据优化或真实港口实证。

| 情景 | 求解状态 | 周期费用（模拟货币） | 独立原始解检查 |
|---|---|---:|---|
| base | optimal | 300.0 | True |
| interface_bottleneck | infeasible | None | None |
| power_bottleneck | infeasible | None | None |
| window_bottleneck | infeasible | None | None |
| higher_power_no_benefit | optimal | 300.0 | True |
| zero_demand | optimal | 0.0 | True |

基准总购电量200kWh、费用300，A/B站峰值66.6667/33.3333kW。每车电量为100→70→100→70→100kWh，初末电量一致。三个可行解各125项独立复核全部通过，最大约束/费用误差为0；求解gap为0。微小的目标/对偶界浮点差异原样保存在 metrics.json。

三种无解都有独立解析能量上界说明，见 [实例说明](../../docs/model/MINIMAL_INSTANCE.md)。无解检查记为null/不适用，不伪造原始解通过。提高A功率仍费用300，保留零收益；零需求费用与购电量均0。

base_schedule.csv 是选出的基准逐车逐站时隙表；同车电量/行驶耗能在不同站点行重复，不可跨站求和。全部完整输入、原始解、stdout/stderr及失败尝试只保存在外部无remote本地Git；reproduction.json提供其摘要hash、精确版本与重跑命令。

仅四个完整一小时时槽、固定设施、给定位置和能耗、线性效率。未做接口投资、离散扩容、真实数据接入、时隙敏感性或潮流。下一步添加接口/扩容决策，并用少量投资组合穷举核对最优费用。
