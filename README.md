# 港区与仓库的重卡充电设施规划
[English](#electric-truck-charging-at-a-port-and-warehouse)

三辆电动重卡从港区出发，到仓库装卸后返港。仓库有一个充电接口。如果两辆车要等 45 分钟才能插枪，应该在港区加一个接口，还是在仓库加？给定运输任务和期末电量，模型同时选择两站的接口数、接入扩容档位和逐车充电功率，以最小化同一周期的设施投资与购电费用。

在四小时合成算例中，港区和仓库的初始接入容量分别为 100 和 75 kW，每车最多以 50 kW 充电。车辆在仓库停车 60 分钟。下表只改变前两辆车的插枪等候，第三辆保留完整窗口。每 15 分钟可以轮换接口，假设换枪不耗时，规划者事先知道本次等候时间。

| 插枪等候（分钟） | 最优总接口（港区 / 仓库） | 付费扩容 | 投资费用 | 总费用 |
|---:|---|---|---:|---:|
| 0、15、30 | 2 / 1 | 无 | 20 | 153.33 |
| 45 | 3 / 1 | 无 | 40 | 173.33 |
| 60 | 3 / 1 | 港区 +50 kW | 75 | 208.33 |

这些费用使用合成周期单位。45 分钟时，两辆车争用仓库的最后一个时段。港区两个接口只能提供 8 个接口时段，而三车至少需要 9 个。港区加到三个接口后，原有 100 kW 已够用。另一种可行配置是港区两个、仓库两个接口，投资为 50，比最低成本方案多 10。[逐车调度](results/known_delay_investment_20261111/dispatch_45.json)

**复算。** 在仓库根目录运行第一条命令，找到 45 分钟这一行，应看到 `min_required_port_plug_slots = 9`、`A_feasible = false`、`B_feasible = true`。第二条核对米兰论文三个情景的设备成本和年度电量。两条均仅需 Python 3。在 Windows 上也可以用 `py -3` 代替 `python`。

```sh
python scripts/check_eligibility_slots.py
python studies/fresia-2025/check_milan.py
```

[任务与设备](configs/port_warehouse_investment.json) · [数学模型](docs/model/FORMULATION.md) · [五档最优配置与费用](results/known_delay_investment_20261111/metrics.json) · [MILP 运行记录](results/known_delay_investment_20261111/reproduction.json) · [论文复算](studies/fresia-2025/)

真实停车记录单独处理。德国 DT-CARGO 样本中，一辆车的两段相邻行驶记录间隔 20 分 30.765 秒；这只能给出可能充电时长的上界，作业放行、插枪和开始供电时刻仍未知。[数据与单事件复算](results/dt_cargo_stop_20261111/event.json)

在固定设施和运输服务下，下一步计划比较到站即充、削峰和按日前价格购电三种策略。价格序列、接入容量和真实可插枪时段的来源将分别记录。

## Electric truck charging at a port and warehouse

Three electric trucks travel from a port to a warehouse, unload and return. If two trucks can plug in only during the last 15 minutes of their warehouse stop, where should an operator add a connector? Given a fixed transport service and terminal battery charge, the mixed-integer model selects connectors, grid connection upgrades and individual charging schedules to minimize investment and electricity cost over the same period.

The four-hour synthetic case starts with 100 kW at the port and 75 kW at the warehouse. Each truck can draw up to 50 kW. All three spend one hour at the warehouse. Two face a known plug-in delay; the third can connect throughout. Connectors can be reassigned at 15-minute boundaries with zero changeover time.

| Plug-in delay (min) | Optimal total connectors (port / warehouse) | Grid upgrade | Investment | Total cost |
|---:|---|---|---:|---:|
| 0, 15, 30 | 2 / 1 | None | 20 | 153.33 |
| 45 | 3 / 1 | None | 40 | 173.33 |
| 60 | 3 / 1 | Port +50 kW | 75 | 208.33 |

Costs are synthetic units for one operating cycle. At 45 minutes, two port connectors provide eight connector-slots, but the trucks need at least nine. A third port connector resolves this with the existing grid connection. Adding a second connector at the warehouse also works and costs ten units more.

Run the two commands above from the repository root with Python 3. The first checks the frozen-facility comparison without a solver. The second reproduces charger-cost and annual energy calculations using published Milan case tables. A separate [German stop record](results/dt_cargo_stop_20261111/event.json) gives an upper bound of 20 minutes 30.765 seconds between driving records. Actual plug-in and charging times are unknown.

[Truck and site inputs](configs/port_warehouse_investment.json) · [Model formulation](docs/model/FORMULATION.md) · [Optimal investments](results/known_delay_investment_20261111/metrics.json) · [MILP run details](results/known_delay_investment_20261111/reproduction.json) · [Milan replication](studies/fresia-2025/)

The planned market study will hold facilities and freight service fixed and compare charging on arrival, peak shaving and day-ahead price scheduling. Each comparison will use the same electricity prices for settlement.
