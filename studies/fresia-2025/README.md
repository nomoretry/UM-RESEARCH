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

## 米兰车辆的班内可用时间 · Time left during the working shift

从仓库根目录运行 `python studies/fresia-2025/route_time.py`。表 6 给出六辆车各自的分区服务需求。按第 3 节的区间行驶时间，枚举从各自基地出发、服务所有必到分区并返回的访问顺序。在这个子问题中，服务可以在各区连续完成。区间时间满足三角不等式，重复访问无法缩短行驶时间。

For each vehicle the 20 half-hour shift slots include 12 mandatory service slots and at least four travel slots. At most four slots (two hours) are left for any other activity during the shift. The program prints one shortest tour for each vehicle. This bound precedes charger availability and SOC constraints. It excludes overnight charging. It is an independently computed subproblem using Section 2.4.3 and Table 6, and does not identify the route or charging schedule chosen by the full energy-cost model.

## 同一组配送任务需要什么设备？ · A two-van equipment decision

表 6 中的 1、2 号车均从基地 1 出发。缩小算例固定两车按 1 → 4 → 5 → 6 → 1 访问，各区服务完成后再驶往下一区。08:00–16:00 的 12 个服务槽与 4 个行驶槽全部排满。两车都在 16:00 返回，并在基地停到 18:00。只改变返场后允许插枪的时段。行驶或服务时不能接枪，每辆车每槽最多占用一台设备，槽边界允许零耗时换枪。

| 两车可插枪时段 | 成本最低的设备 | 初始投资 (€) | 年化投资加维护 (€/年) | 可行设备组合 |
|---|---|---:|---:|---:|
| 16:00–18:00 | 2 AC | 4,000 | 388 | 7/9 |
| 16:30–18:00 | 1 AC + 1 DC | 18,000 | 1,746 | 5/9 |
| 17:00–18:00 | 2 DC | 32,000 | 3,104 | 3/9 |
| 17:30–18:00 | 不可行 | — | — | 0/9 |

表 5 的 Fiat e-Ducato 电池容量为 47 kWh。每车服务耗能 12 × 2.025 kWh，区间行驶耗能 4 × 3.375 kWh，合计 37.8 kWh。式 (2.28) 另扣每半小时 0.0065% 的自放电。算例假定起末电量均为 42.3 kWh。按原文交流 22 kW、直流 50 kW、充电效率 87%，一槽最多补入 9.57 或 21.75 kWh。一台交流设备两小时最多供两车合计 38.28 kWh，两台交流设备则可各供一车。90 分钟内仅有一台直流设备时最多供 65.25 kWh，低于两车的 75.6 kWh 任务耗能，增配一台交流设备后可以轮换。60 分钟内，一辆车各用一槽直流和交流只能获得 31.32 kWh，每车都需要两个直流时段。剩 30 分钟时，即使每车各用一台直流也无法复位。

上表使用可连续调功至铭牌上限、基地供电充足的简化条件。两小时交流方案每车的名牌供电量比任务耗能仅多 0.48 kWh，自放电还会占去其中一部分。四档均未计电费，年费只含设备年化投资和维护。

**加入图 4 的 SOC 功率限制。** 按发表版第 10 页图 4 读取交流与直流的分段线性曲线，分别按每个半小时开始时的 SOC 限制取电功率。车辆、费用、接入窗口和满班任务保持一致。下表使用同一套九种设施组合独立枚举。[图上读取的输入](figure4_power.json) · [分段功率精选结果](figure4_results.json)

| 可插枪分钟 | 图 4 读数下成本最低的设备 | 年费 (€/年) | 可行组合 |
|---:|---|---:|---:|
| 120 | 1 AC + 1 DC | 1,746 | 5/9 |
| 90 | 1 AC + 1 DC | 1,746 | 5/9 |
| 60 | 不可行 | — | 0/9 |
| 30 | 不可行 | — | 0/9 |

返场时电量为 4.474 kWh（9.52% SOC）。按图中交流 10% SOC 达到铭牌的读数，一车独占交流四槽，最高可到 42.2893 kWh，距离 42.3 kWh 目标只差 0.0107 kWh。仅将这个读图拐点改到 9% 时，相同调度窗口的上限升到 42.7492 kWh，两台交流即可完成任务。两小时档的设备选择对该拐点很敏感，须有厂家或作者的数值曲线才能可靠区分。60 分钟档有更大的缺口。即使两车各独占直流设备，逐车班末电量上限也只有 35.3182 kWh。增加接口无法解除这个单车功率与可用时间限制。

Run from the repository root with NumPy and SciPy installed:

```powershell
python studies/fresia-2025/reduced_milan.py
python studies/fresia-2025/reduced_milan.py --power-limit figure4
python -m pytest -q studies/fresia-2025/test_reduced_milan.py
```

The first command prints three proven annual equipment costs, equal lower bounds, zero gaps, and the 30-minute infeasibility. Add `--dispatch "$env:TEMP\milan-dispatch.json"` for individual energy levels and connections. The independent check tests all nine combinations of zero to two AC and DC units. For each vehicle and plug assignment it propagates the reachable energy interval, including self-discharge and battery bounds. Continuous modulation makes that interval exact under the nameplate assumption. Joint assignments must fit the installed units in every slot. The checker also replays the returned dispatch. [Inputs and their provenance](reduced_milan.json) · [MILP](reduced_milan.py) · [Checker](verify_reduced.py) · [Selected results](reduced_results.json)

The second command uses the concave SOC–power curves read from Fig. 4. Under those inputs, 120 and 90 minutes both require one AC and one DC unit (€1,746/year, zero optimality gap). At 60 and 30 minutes all nine configurations fail. For every fixed assignment the independent calculation checks both endpoints and all curve vertices inside the current SOC interval for the highest attainable next energy. This captures taper even when the best next energy comes from an interior SOC. The published chart and its rounded coordinates limit the precision of the two-hour AC decision.

Table 5 supplies charger nameplates, prices, maintenance, battery capacity, efficiencies and withdrawals. Table 6 supplies service counts. Section 3 gives shift length and travel times. The reduced MILP uses the exclusive vehicle states of (2.13), installation and connection limits of (2.23)–(2.27), energy balance of (2.28) and charger cost terms of (2.38)–(2.39). Fixed service placement, 90% boundary SOC and timed release are local assumptions. Missing inputs for a full Milan replication include machine-readable Fig. 4 curve coordinates, chronological site loads/PV and the full-case schedules. The 100 kW limit in section 3.4 describes an internal charging area. This case uses depot 1. UM heavy trucks use the separate [port and warehouse inputs](../../README.md). [Published paper in the authors’ institutional repository](https://hdl.handle.net/11567/1267887)
