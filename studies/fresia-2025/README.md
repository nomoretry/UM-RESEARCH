# Charging investment in the Milan delivery case · 米兰城市配送设施投资

[Fresia et al. (2025)](https://doi.org/10.1016/j.segan.2025.101898) allocate chargers across three depots and three delivery zones, alongside routing, PV and stationary storage decisions. The paper models four representative days at 30-minute resolution. The files in this directory use the Milan case; the UM port and warehouse case has its own inputs.

本文从可由论文表格直接复核的两项计算开始。表 10 给出三个米兰情景各区的设备数量。按表 5 的单价、年维护费和资本回收系数 0.087，独立计算充电设备的初始投资，以及年化投资加维护费。表 11 用来核对全年的电量收支。所有电量单位为 kWh，初始投资单位为欧元，年费用单位为欧元/年。

From the repository root, run `python studies/fresia-2025/check_milan.py`. The script reads the Milan charger counts and annual energy totals in `milan.csv`. It applies the charger terms of equations (2.38) and (2.39) and subtracts annual use and exports from annual supply. The reported installation counts are inputs to this check.

| Milan scenario | Initial charger cost (€) | Annualized chargers + maintenance (€/yr) | Energy residual (kWh/yr) |
|---|---:|---:|---:|
| 1 | 42,000 | 4,074 | 0 |
| 2 | 38,000 | 3,686 | 0 |
| 3 | 12,000 | 1,164 | 0 |

The annualized charger component excludes PV, stationary storage and electricity purchases or sales. Independent replication of the investment optimum requires rebuilding the vehicle and energy constraints and the chronological inputs, including the three sites’ load and PV profiles. The authors offer data on request. Where original inputs are missing, label substitute series and keep their results separate from Milan benchmarks.

下一步可用原文表 6 的物流任务约束和表 5 的设备参数重建一个缩小的投资算例。若改用 UM 港区与仓库的固定运输任务或德国停车记录，应将结果标为重卡适配实验。德国记录提供部分停车上界，插枪资格仍需独立证据。

## 米兰车辆的班内可用时间 · Time left during the working shift

从仓库根目录运行 `python studies/fresia-2025/route_time.py`。表 6 给出六辆车各自的分区服务需求。按第 3 节的区间行驶时间，枚举从各自基地出发、服务所有必到分区并返回的访问顺序。在这个子问题中，服务可以在各区连续完成。区间时间满足三角不等式，重复访问无法缩短行驶时间。

For each vehicle the 20 half-hour shift slots include 12 mandatory service slots and at least four travel slots. At most four slots (two hours) are left for any other activity during the shift. The program prints one shortest tour for each vehicle. This bound precedes charger availability and SOC constraints. It excludes overnight charging. It is an independently computed subproblem using Section 2.4.3 and Table 6, and does not identify the route or charging schedule chosen by the full energy-cost model.
