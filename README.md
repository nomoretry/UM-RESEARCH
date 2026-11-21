# 港区与仓库的重卡充电设施规划

[中文](#中文) · [English](#english)

## 中文

三辆电动重卡从港区出发，到仓库装卸后返港。两辆车作业放行较晚，回来后又在同一小时内需要补电。运营方应该加一个充电接口、扩大电网接入容量，还是把充电移到别的时段就够了？

**先看任务能否完成。** 在四小时合成算例中，每车每程耗电 20 kWh、每车充电上限 50 kW，港区／仓库接入为 100/75 kW。仓库只有一个接口，前两辆车等 45 分钟后才可插枪，第三辆可用整小时。每 15 分钟允许零耗时换车。即使把仓库补能安排得最好，返港后仍至少需要 9 个接口时段，两个港区接口一小时只有 8 个。此时单独扩容无效；增加第三个港区接口即可在原有 100 kW 下完成任务。若前两辆在仓库等满 60 分钟，在相同设备菜单下则还需把港区扩到 150 kW。[任务输入](configs/port_warehouse_investment.json) · [逐档最优设施和费用](results/known_delay_investment_20261111/metrics.json) · [服务范围与约束解释](results/shared_investment_20261112/)

**再看多一个接口值多少钱。** 冻结德国车队案例的接入容量（港区 100 kW、仓库 75 kW）和仓库的一个接口。2021 年 9 月 21–23 日，两种港区配置都完成了 8 个车日、45 趟行程。采用同期德国／卢森堡日前批发价，单接口从到站即充改为按价调度，三天少付 €31.22；在相同按价调度下，第二个港区接口再省 €10.62。后六周两种设施均最多完成 54/73 个车日，同任务的电费差额合计 €32.29。逐车检查表明，其余 19 个车日中有 18 个受 300 kWh 电池或缺少充电停靠所限，增加接口、接入容量或单车功率都无法完成，所以第二个接口的价值只体现在电费上。[未完成车日归因](studies/fleet-service/service_gap.md)按这六周的任务和价差等权重复 52 周，能承担的年费用约 €331（2025 年币值），低于独立 50 kW 充电机约 €3,724/年的文献成本。能同时给两辆车各供 50 kW 的既有柜增设接口，仍需单独报价。[原始车队来源与停车假设](studies/fleet-service/DATA.md) · [完整投资实验](studies/day-ahead/second_port.md) 若车辆相邻两天的电量可以结转，而不是每天回到 150 kWh，完成量不变，一接口和两接口的六周电费分别下降 8.6% 和 10.1%，第二接口的收益变为 €38.18（每年约 €391），结论不变。[跨日电量边界](studies/fleet-service/energy_boundary.md) 按 Netze BW 2024 年网费结算需量后，第二个独立接口的年运行价值约为 €2.21（同时优化峰值）或 −€773（只按电价调度），既有 50 kW 柜加枪在同时优化峰值时约为 €2.15/年。[共享柜与需量电费](studies/fleet-service/cabinet_demand.md) 2、5 分钟换车下，单、双接口仍完成同一组 54/73 个车日，购电收益仍不足以承担独立第二充电点的年成本。[车队换车时间](studies/fleet-service/changeover.md)

**决定需要多少功率**　规划期六周，港区单站保住同一组 54/73 个车日，官方网费下有价方案以新建 20 kW、既有 40 kW 最省。随后六周，港区增至 50 kW 仍漏掉 11 月 26 日的 1 号车，仓库加 15 kW 可补回，有报价的最小档为 20 kW。按预登记运行规则，两套有价修复在留出期 12 个口径下的年费都低于双站基准。修复源自这次留出，网费影响排序，5 号车断点期间能否充电影响服务，选型留待独立样本检验。设施固定后按整周已知任务和电价离线排程，年费只在留出期内比较，日前均价为 €206.16/MWh，规划期为 €138.23/MWh。[规划期功率选型](studies/fleet-service/site_sizing.md) · [留出服务与年费](studies/fleet-service/holdout_test.md)

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

**How much power is needed**　One port charger served 54/73 truck-days in six planning weeks, with 20 kW cheapest for new access and 40 kW for existing access among priced designs under the official tariff. In the next six weeks even 50 kW at the port missed vehicle 1 on 26 November, while adding 15 kW at the warehouse restored service (smallest priced unit 20 kW). Under preregistered rules both priced repairs cost less annually than the two-site baseline in all 12 holdout cases. Choosing between these holdout-derived repairs requires independent data because tariffs affect cost rankings and charging eligibility during vehicle 5’s recording gaps affects service. Schedules used offline, full-week knowledge of tasks and prices for fixed facilities, and bills are compared within the holdout (mean day-ahead price €206.16/MWh, versus €138.23/MWh in planning). [Planning-period sizing](studies/fleet-service/site_sizing.md) · [Holdout service and bills](studies/fleet-service/holdout_test.md)

**Reproduce in Windows PowerShell.** Start in the research repository root, alongside `requirements-milp.txt`. Use a Python 3.12 environment with the pinned dependencies (`python -m pip install -r requirements-milp.txt` once). SciPy supplies HiGHS. The inputs are included.

```powershell
$env:PYTHONPATH = 'src'
python -m um_charging.connector_value
```

Expect `8/8 vehicle-days` and `second port saves EUR 10.61522` on the `concurrent` line, and `6.80206` on the `january_replay` line. Trip records bound possible dwell; site identity and plug eligibility follow the UM scenario. [Full replay and bills](studies/day-ahead/second_port.md) · [Mathematical model](docs/model/FORMULATION.md) · [Separate Milan paper replication](studies/fresia-2025/)
