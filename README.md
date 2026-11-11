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

米兰双车缩例固定配送任务、访问顺序和班末电量。按原文图 4 读取的充电曲线，120 和 90 分钟窗口均选一台交流加一台直流，年化设备费 €1,746；60 和 30 分钟均不可行。两小时档对曲线读数敏感，两台交流设备每车仅差约 0.011 kWh 就能达标。仅施加铭牌限制会在两小时档选两台交流，并将一小时档判为可行。[设备枚举、曲线读数与复算命令](studies/fresia-2025/)

真实停车记录单独处理。德国 DT-CARGO 样本中，一辆车的两段相邻行驶记录间隔 20 分 30.765 秒；这只能给出可能充电时长的上界，作业放行、插枪和开始供电时刻仍未知。[数据与单事件复算](results/dt_cargo_stop_20261111/event.json)

### 固定设施后，省电费与削峰怎样取舍？

固定上表 60 分钟档的设施（港区 3 个接口、150 kW；仓库 1 个接口、75 kW）。前两辆车只能返港充电，第三辆在仓库有一小时的合成插枪窗口。将同一任务链放在 2025-01-06 柏林时间 08:00–12:00，三种策略均完成六段行驶，三车期末各 100 kWh，总购电量 133.333 kWh。以德国／卢森堡同一条日前批发价格曲线结算，仅计电能费。

| 调度策略 | 四小时购电费（€） | 港区峰值（kW） | 仓库峰值（kW） |
|---|---:|---:|---:|
| 到站即充 | 4.45578 | 150.00 | 50.00 |
| 最小化两站中较高的峰值 | 4.45578 | 111.11 | 50.00 |
| 最小化日前购电费 | 4.37733 | 150.00 | 0.00 |

仓库窗口所在小时的电价为 36.36 €/MWh，返港小时为 32.83 €/MWh。削峰把仓库能容纳的 22.222 kWh 用足，使港区在剩余一小时恰好达到 111.11 kW 的下界。电费最优解把电量全部留到返港后购买。表中为求解器返回的峰值；三车各以 44.444… kW 充满最后一小时，也能达到同一最低费用，港区峰值为 133.333… kW。[固定情景](studies/day-ahead/case.json) · [同价结算结果](studies/day-ahead/metrics.json) · [原始报价与署名](studies/day-ahead/prices.json)

从仓库根目录用 PowerShell 复算。输出中 `purchase_eur` 为四小时购电费，`site_peak_kw` 为两站各自的峰值。

```powershell
python -m pip install -r requirements-milp.txt
$env:PYTHONPATH = 'src'
python -m um_charging.day_ahead
```

在相同的 45 分钟插枪延迟下，以 TUM 车队行程的模拟能耗变化构造重卡情景。单程从 20.00 增至 20.64 kWh 后，最低费用配置从港区三个、仓库一个接口变为两地各两个。在另一组固定设施实验中，用 2025 年 1 月每天相同四个时段的 DE-LU 日前电价结算，31 次任务按电价调度共花 €469.15，削峰调度共花 €485.02。[载荷与接口配置](studies/truck-energy/) · [逐日费用和峰值](studies/day-ahead/january_2025.md)

## Electric truck charging at a port and warehouse

Three electric trucks travel from a port to a warehouse, unload and return. If two trucks can plug in only during the last 15 minutes of their warehouse stop, where should an operator add a connector? Given a fixed transport service and terminal battery charge, the mixed-integer model selects connectors, grid connection upgrades and individual charging schedules to minimize investment and electricity cost over the same period.

The four-hour synthetic case starts with 100 kW at the port and 75 kW at the warehouse. Each truck can draw up to 50 kW. All three spend one hour at the warehouse. Two face a known plug-in delay; the third can connect throughout. Connectors can be reassigned at 15-minute boundaries with zero changeover time.

| Plug-in delay (min) | Optimal total connectors (port / warehouse) | Grid upgrade | Investment | Total cost |
|---:|---|---|---:|---:|
| 0, 15, 30 | 2 / 1 | None | 20 | 153.33 |
| 45 | 3 / 1 | None | 40 | 173.33 |
| 60 | 3 / 1 | Port +50 kW | 75 | 208.33 |

Costs are synthetic units for one operating cycle. At 45 minutes, two port connectors provide eight connector-slots, but the trucks need at least nine. A third port connector resolves this with the existing grid connection. Adding a second connector at the warehouse also works and costs ten units more.

In the separate two-van Milan study, the SOC-dependent power curves read from Figure 4 select one AC and one DC charger (€1,746/year) for both 120 and 90 minutes of depot charging. No build works at 60 or 30 minutes. At 120 minutes two AC chargers miss the target by only about 0.011 kWh per van, so this choice is sensitive to the plotted curve. Nameplate limits alone select two AC chargers at 120 minutes and permit charging within 60 minutes. [Equipment enumeration, curve inputs and replay](studies/fresia-2025/)

Run the two commands above from the repository root with Python 3. The first checks the frozen-facility comparison without a solver. The second reproduces charger-cost and annual energy calculations using published Milan case tables. A separate [German stop record](results/dt_cargo_stop_20261111/event.json) gives an upper bound of 20 minutes 30.765 seconds between driving records. Actual plug-in and charging times are unknown.

[Truck and site inputs](configs/port_warehouse_investment.json) · [Model formulation](docs/model/FORMULATION.md) · [Optimal investments](results/known_delay_investment_20261111/metrics.json) · [MILP run details](results/known_delay_investment_20261111/reproduction.json) · [Milan replication](studies/fresia-2025/)

### Energy cost and peak power with fixed facilities

Freeze the 60-minute-delay build (three port connectors at 150 kW, one warehouse connector at 75 kW). Only the third truck can plug in during the warehouse dwell. All three policies complete six legs, return all three trucks to 100 kWh each, and buy 133.333 kWh. The assumed UM cycle runs from 08:00 to 12:00 Berlin time on 6 January 2025. Every policy pays the same DE-LU day-ahead wholesale price for each delivery hour. The comparison covers energy purchases only.

| Dispatch policy | Four-hour purchase cost (€) | Port peak (kW) | Warehouse peak (kW) |
|---|---:|---:|---:|
| Charge on arrival | 4.45578 | 150.00 | 50.00 |
| Minimize the higher site peak | 4.45578 | 111.11 | 50.00 |
| Minimize day-ahead purchase cost | 4.37733 | 150.00 | 0.00 |

The warehouse can deliver up to 22.222 kWh before the return trip. Using that energy leaves 111.111 kWh to deliver in the final port hour, which explains the peak lower bound. That port hour is cheaper (€32.83/MWh versus €36.36/MWh at the warehouse). Buying everything at the port minimizes the bill. The table reports the returned schedules. A flat 44.444… kW per truck during the final hour also attains the lowest cost, at a port peak of 133.333… kW. Run the PowerShell commands above to reproduce the table. [Fixed case](studies/day-ahead/case.json) · [Verified results](studies/day-ahead/metrics.json) · [SMARD price inputs](studies/day-ahead/prices.json)

With the same 45-minute plug-in delay, trip-energy scenarios derived from TUM fleet simulations change the optimal build from three port connectors and one warehouse connector at 20.00 kWh per leg to two at each site at 20.64 kWh. In the separate frozen-facility study, settling 31 four-hour services on January 2025 DE-LU day-ahead prices gives €469.15 for price-aware dispatch and €485.02 for peak shaving. [Payload and facility sizing](studies/truck-energy/) · [Daily costs and peaks](studies/day-ahead/january_2025.md)
