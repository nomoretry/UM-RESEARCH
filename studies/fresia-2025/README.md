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

这四档结果使用可连续调功至铭牌上限、基地供电充足的简化条件。原文图 4 随 SOC 调低充电功率，此处未重建其曲线。两小时交流方案每车的名牌供电量比任务耗能仅多 0.48 kWh，自放电还会占去其中一部分。前三档的可行性与费用最优性仅对给定功率假设成立；30 分钟档在名牌上限下已不可行，进一步降额也无法完成。四档均未计电费，年费只含设备年化投资和维护。

Run from the repository root with NumPy and SciPy installed:

```powershell
python studies/fresia-2025/reduced_milan.py
python -m pytest -q studies/fresia-2025/test_reduced_milan.py
```

The first command prints three proven annual equipment costs, equal lower bounds, zero gaps, and the 30-minute infeasibility. Add `--dispatch "$env:TEMP\milan-dispatch.json"` for individual energy levels and connections. The independent check tests all nine combinations of zero to two AC and DC units. For each vehicle and plug assignment it propagates the reachable energy interval, including self-discharge and battery bounds. Continuous modulation makes that interval exact under the nameplate assumption. Joint assignments must fit the installed units in every slot. The checker also replays the returned dispatch. [Inputs and their provenance](reduced_milan.json) · [MILP](reduced_milan.py) · [Checker](verify_reduced.py) · [Selected results](reduced_results.json)

Table 5 supplies charger nameplates, prices, maintenance, battery capacity, efficiencies and withdrawals. Table 6 supplies service counts. Section 3 gives shift length and travel times. The reduced MILP uses the exclusive vehicle states of (2.13), installation and connection limits of (2.23)–(2.27), energy balance of (2.28) and charger cost terms of (2.38)–(2.39). Fixed service placement, 90% boundary SOC and timed release are local assumptions. Missing inputs for a full Milan replication include machine-readable Fig. 4 curve coordinates, chronological site loads/PV and the full-case schedules. The 100 kW limit in section 3.4 describes an internal charging area. This case uses depot 1. UM heavy trucks use the separate [port and warehouse inputs](../../README.md). [Published paper in the authors’ institutional repository](https://hdl.handle.net/11567/1267887)
