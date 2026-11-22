# 港区与仓库的重卡充电设施规划

[中文](#中文) · [English](#english)

## 中文

三辆电动重卡从港区出发，到仓库装卸后返港。两辆车作业放行较晚，回来后又在同一小时内需要补电。运营方应该加一个充电接口、扩大电网接入容量，还是把充电移到别的时段就够了？

**先看任务能否完成。** 在四小时合成算例中，每车每程耗电 20 kWh、每车充电上限 50 kW，港区／仓库接入为 100/75 kW。仓库只有一个接口，前两辆车等 45 分钟后才可插枪，第三辆可用整小时。每 15 分钟允许零耗时换车。即使把仓库补能安排得最好，返港后仍至少需要 9 个接口时段，两个港区接口一小时只有 8 个。此时单独扩容无效；增加第三个港区接口即可在原有 100 kW 下完成任务。若前两辆在仓库等满 60 分钟，在相同设备菜单下则还需把港区扩到 150 kW。[任务输入](configs/port_warehouse_investment.json) · [逐档最优设施和费用](results/known_delay_investment_20261111/metrics.json) · [服务范围与约束解释](results/shared_investment_20261112/)

**再看多一个接口值多少钱。** 冻结德国车队案例的接入容量（港区 100 kW、仓库 75 kW）和仓库的一个接口。2021 年 9 月 21–23 日，两种港区配置都完成了 8 个车日、45 趟行程。采用同期德国／卢森堡日前批发价，单接口从到站即充改为按价调度，三天少付 €31.22；在相同按价调度下，第二个港区接口再省 €10.62。后六周两种设施均最多完成 54/73 个车日，同任务的电费差额合计 €32.29。逐车检查表明，其余 19 个车日中有 18 个受 300 kWh 电池或缺少充电停靠所限，增加接口、接入容量或单车功率都无法完成，所以第二个接口的价值只体现在电费上。[未完成车日归因](studies/fleet-service/service_gap.md)按这六周的任务和价差等权重复 52 周，能承担的年费用约 €331（2025 年币值），低于独立 50 kW 充电机约 €3,724/年的文献成本。能同时给两辆车各供 50 kW 的既有柜增设接口，仍需单独报价。[原始车队来源与停车假设](studies/fleet-service/DATA.md) · [完整投资实验](studies/day-ahead/second_port.md) 若车辆相邻两天的电量可以结转，而不是每天回到 150 kWh，完成量不变，一接口和两接口的六周电费分别下降 8.6% 和 10.1%，第二接口的收益变为 €38.18（每年约 €391），结论不变。[跨日电量边界](studies/fleet-service/energy_boundary.md) 按 Netze BW 2024 年网费结算需量后，第二个独立接口的年运行价值约为 €2.21（同时优化峰值）或 −€773（只按电价调度），既有 50 kW 柜加枪在同时优化峰值时约为 €2.15/年。[共享柜与需量电费](studies/fleet-service/cabinet_demand.md) 2、5 分钟换车下，单、双接口仍完成同一组 54/73 个车日，购电收益仍不足以承担独立第二充电点的年成本。[车队换车时间](studies/fleet-service/changeover.md)

**决定需要多少功率。** 两次按时间顺序的留出检验里，样本内年费最低的设施都没守住随后运营周的同一组运输任务。两段留出各用于一次预定检验（第一折在检验后并入 12 周选型样本，不再作为独立样本）；数据已用完，本项目没有经样本外验证的推荐规模。

| 折次 | 规划 → 留出窗口 | 留出登记 | 选定设施的缺口 | 缺口约束（均在仓库侧） | 事后恢复诊断 |
|---|---|---|---|---|---|
| 第一折 | 6 周（54/73）→ 6 周（2021-11-08 至 12-19） | 52/63 | 港区单站 20/0、40/0（至 50/0）kW 均少 1 个（11-26 车 1） | 行程储备越界 | 仓库 +15 kW 恢复（有价 20 kW） |
| 第二折（预登记） | 12 周（106/136）→ 7 周（2021-12-20 至 2022-02-06） | 49/57 | 40/20 kW 少 1 个（01-19 车 1）；20/20 kW 少 2 个 | 行程可跑完，段末距 150 kWh 差 46.24 kWh | 仓库 30 kW 不可行、40 kW 可行、35 kW 未检验 |

- **12 周重选与策略对照**：合并前 12 周的有价粗网格上，12 个费率与接入口径均选出港区 40 kW 加仓库 20 kW（5 个，含 Netze BW 官方新建与既有）或港/仓各 20 kW（7 个）。第二折中，20/20 kW 另少 1 月 31 日的 4 号车；按 12 周各周最低方案取并集组成的稳健基准，以及按天滚动、到站即充各自选出的设施，也都未保住服务。
- **两折缺口异同**：两折缺口都出现在 1 号车的单日段和仓库一侧，所试港区增容均无效；但约束类型不同——11 月 26 日为首趟行程储备越界，1 月 19 日记录的充电全部在仓库、当天没有港区停靠，行程本身可跑完，缺口来自段末 150 kWh 的模型约定。
- **双站基准与同服务年费**：第二折的 49/57 个登记车日由双站基准（两站各 50 kW 充电机、100/75 kW 接入）按自身可行服务确定，因此它在主情景守住该集合是按构造成立的；耗电增加 10% 时，基准自己也少完成 1 个车日。该基准在第二折的官方网费年费为新建 €22,232.75–22,232.83、既有 €19,895.26–19,895.34（2025 年欧元，按 52/7 年化）。
- **开封后阶梯诊断与口径**：第二折开封后从 40/20 kW 出发按预登记四档有价阶梯诊断，仓库升至 40 kW 恢复服务的额外固定年费为阶梯内最低（新建 €756.91、既有 €489.77，2025 年欧元）；这是看到结果后的诊断，而非样本外验证。设施固定后采用按周全信息离线优化，不是在线策略；年费只在同一留出期内比较（规划期、第一折、第二折 DE-LU 日前均价分别为 €138.23、€206.16、€173.46/MWh）。[规划期选型](studies/fleet-service/site_sizing.md) · [第一折留出](studies/fleet-service/holdout_test.md) · [第二折留出](studies/fleet-service/second_holdout.md)

**Windows 快速复算。** 从本研究版本的仓库根目录（含 `requirements-milp.txt`）运行。使用独立 Python 3.12 环境，首次在该环境运行 `python -m pip install -r requirements-milp.txt`。计算使用 SciPy 自带的 HiGHS。输入已随仓库提供。

```powershell
$env:PYTHONPATH = 'src'
python -m um_charging.connector_value
```

成功时，`concurrent` 行显示 `8/8 vehicle-days` 和 `second port saves EUR 10.61522`，`january_replay` 行显示 `6.80206`。项目保留相邻行程推得的停车上界，站点映射与可插枪时间是情景假设。[六周复算与结果](studies/day-ahead/second_port.md) · [数学模型](docs/model/FORMULATION.md) · [米兰城市配送论文复算](studies/fresia-2025/)

## English

[中文](#中文)

Three electric trucks leave the port, unload at a warehouse and return. Two are released late and need to recharge during the same hour back at the port. Should the operator add a connector, upgrade the grid connection, or move charging to another time?

**When a connector is necessary.** In the four-hour synthetic duty, each truck uses 20 kWh per leg and can charge at 50 kW. The port and warehouse have 100 and 75 kW of grid capacity. The warehouse has one connector. Two trucks wait 45 minutes before they can plug in there; the third has the full hour. Trucks can exchange connectors every 15 minutes with zero changeover time. Even the best warehouse schedule leaves at least nine port connector-slots to cover. Two port connectors supply only eight. A third port connector completes the duty at the existing 100 kW. If the two trucks wait the entire warehouse hour, the minimum-cost choice also upgrades the port to 150 kW. [Task and equipment inputs](configs/port_warehouse_investment.json) · [Optimal builds](results/known_delay_investment_20261111/metrics.json) · [Service ranges and constraint evidence](results/shared_investment_20261112/)

**When a connector lowers the bill.** For the German fleet, freeze the port/warehouse connections at 100/75 kW and keep one warehouse connector. On 21–23 September 2021, one and two port connectors both served eight truck-days and 45 trips. Under contemporaneous DE/LU day-ahead prices, moving one-connector charging from immediate to price-optimized cut the bill by €31.22. A second connector saved a further €10.62 under the same optimization. In the next six weeks both builds served at most 54/73 truck-days, with a €32.29 bill difference on identical service. Truck-by-truck checks show that the 300 kWh battery or a lack of charging stops limits 18 of the 19 unserved days. Extra connectors, grid capacity or charging power cannot serve them, so the second connector's value is in the bill alone. [Unserved-day attribution](studies/fleet-service/service_gap.md) Repeating that six-week mix over 52 weeks supports about €331/year in 2025 euros, against a published standalone 50 kW charger benchmark of €3,724/year. A dispenser retrofit capable of delivering two simultaneous 50 kW sessions requires a site quote. [Fleet provenance and assumptions](studies/fleet-service/DATA.md) · [Full investment experiment](studies/day-ahead/second_port.md) If energy carries over between consecutive days instead of resetting to 150 kWh daily, service is unchanged, the six-week bills fall by 8.6% (one connector) and 10.1% (two), and the second connector saves €38.18 (about €391/year); the conclusion holds. [Energy boundaries](studies/fleet-service/energy_boundary.md) With demand charges under the 2024 Netze BW tariff, a second independent connector is worth about €2.21/year with peak-aware dispatch or −€773/year with energy-only dispatch, and adding a connector to the existing 50 kW cabinet is worth about €2.15/year with peak-aware dispatch. [Shared cabinets and demand charges](studies/fleet-service/cabinet_demand.md) With 2 or 5 minutes of plug changeover, both builds still serve the same 54 of 73 truck-days, and energy savings remain below the additional charger's annual cost. [Fleet plug changeover](studies/fleet-service/changeover.md)

**How much power is needed.** Across two chronological holdouts, the facilities with the lowest in-sample annual cost failed to retain the same transport service in the following weeks. Each holdout was used once for its planned test (the first holdout was merged into the 12-week selection sample after its test and is no longer independent). All cohort weeks have been used, and the study has no sizing recommendation validated out of sample.

| Fold | Selection → holdout window | Register | Gaps for fixed selected builds | Binding constraint (warehouse side) | Post-hoc repair diagnosis |
|---|---|---|---|---|---|
| Fold 1 | 6 wk (54/73) → 6 wk (8 Nov–19 Dec 2021) | 52/63 | Port-only 20/0, 40/0 (up to 50/0) kW missed 1 (26 Nov, vehicle 1) | In-trip reserve breached | Warehouse +15 kW (smallest priced: 20 kW) |
| Fold 2 (preregistered) | 12 wk (106/136) → 7 wk (20 Dec 2021–6 Feb 2022) | 49/57 | 40/20 kW missed 1 (19 Jan, vehicle 1); 20/20 kW missed 2 | Trips finished; terminal SOC 46.24 kWh below 150 kWh | Warehouse 30 kW infeasible, 40 kW feasible, 35 kW untested |

- **12-week reselection and operating policies:** Across the 12 tariff-and-access cases on the 12-week priced coarse grid, five selected 40/20 kW (port/warehouse, including both official Netze BW cases) and seven selected 20/20 kW. In Fold 2, 20/20 kW also missed vehicle 4 on 31 January; the union of weekly least-cost facilities and the designs selected under daily rolling and charge-on-arrival dispatch also failed to complete the register.
- **Common and distinct gap mechanisms:** Both folds had a warehouse-side gap in a single-day segment for vehicle 1 that the tested port upgrades could not close, but the binding constraints differed: on 26 November the in-trip reserve was breached, whereas on 19 January all recorded charging occurred at the warehouse with no port stop that day—the trips completed, and the shortfall came from the modeled 150 kWh terminal requirement.
- **Two-site baseline and same-service bills:** The 49/57 Fold 2 register was defined by the two-site baseline (one 50 kW charger per site on 100/75 kW connections) from its own feasible service, so it retained that register by construction in the main scenario; with 10% higher driving energy, the baseline itself lost one vehicle-day. Its official-tariff annual bill in Fold 2 was €22,232.75–22,232.83 for new connections and €19,895.26–19,895.34 for existing access (2025 euros, 52/7 annualization).
- **Post-opening diagnosis and comparison basis:** In the preregistered four-step priced ladder conducted after opening from 40/20 kW, raising the warehouse to 40 kW restored service at the lowest additional annual fixed cost in the ladder (€756.91 new, €489.77 existing, 2025 euros); this is a post-opening diagnostic, not out-of-sample validation. Fixed-facility scheduling uses weekly full-information offline optimization—not an online policy—and annual bills are compared only within the same holdout (mean DE-LU day-ahead prices: €138.23/MWh in planning, €206.16/MWh in Fold 1, €173.46/MWh in Fold 2). [Planning-period sizing](studies/fleet-service/site_sizing.md) · [First holdout](studies/fleet-service/holdout_test.md) · [Second holdout](studies/fleet-service/second_holdout.md)

**Reproduce in Windows PowerShell.** Start in the research repository root, alongside `requirements-milp.txt`. Use a Python 3.12 environment with the pinned dependencies (`python -m pip install -r requirements-milp.txt` once). SciPy supplies HiGHS. The inputs are included.

```powershell
$env:PYTHONPATH = 'src'
python -m um_charging.connector_value
```

Expect `8/8 vehicle-days` and `second port saves EUR 10.61522` on the `concurrent` line, and `6.80206` on the `january_replay` line. Trip records bound possible dwell; site identity and plug eligibility follow the UM scenario. [Full replay and bills](studies/day-ahead/second_port.md) · [Mathematical model](docs/model/FORMULATION.md) · [Separate Milan paper replication](studies/fresia-2025/)
