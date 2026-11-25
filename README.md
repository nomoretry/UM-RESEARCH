# 港区与仓库的重卡充电设施规划

[中文](#中文) · [English](#english)

## 中文

本仓库研究**固定运输任务下港区与仓库的双站电动重卡充电设施规划**：在电池上限、站点接入容量、接口数量和充电窗口约束下，比较完成同一运输服务所需的设施投资与运行成本，检验运营灵活性何时能替代扩容。实证案例使用德国单一承运人 5 辆重卡的公开轨迹与模拟能耗数据（DT-CARGO / TUMFTM）及同期 DE-LU 原生日前电价（SMARD），并辅以 4 小时三车合成算例与独立的米兰配送论文缩例复算。

**三项核心结论**：（1）返港集中补电受接口时段制约时，单独扩容无效，须增设接口；（2）300 kWh 德国车队情景下，第二个独立 50 kW 港区接口不能多完成车日，运行节费远低于整机年成本；（3）两次按时间顺序的留出检验中，样本内年费最低的设施均未守住后续运营周的同一组任务，数据已用完，本项目**没有经样本外验证的推荐规模**。文末给出 [Windows 快速复算](#6-windows-快速复算) 与 [研究报告与证据索引](#5-研究报告与证据索引)。

初次访问请先阅读 [仓库导览](docs/GUIDE.md#中文)（5 分钟／半小时／完整复核路线、目录地图与证据等级说明）。

### 1. 什么时候必须增加接口

**结论：当返港补电集中在同一小时、所需接口时段超过现有枪数时，单独扩大电网接入容量无效，必须增加充电接口。**

在 4 小时三车合成算例中，三辆电动重卡从港区出发、到仓库装卸后返港（每车每程耗电 20 kWh、单车充电上限 50 kW；港区/仓库接入 100/75 kW；仓库 1 个接口；每 15 分钟零耗时换车）：

- **45 分钟仓库放行延迟**：前两辆车在仓库等 45 分钟才可插枪，第三辆可用整小时。即使仓库补能安排到最优，返港后仍至少需要 9 个港区接口时段，而 2 个港区接口一小时仅提供 8 个。此时单独扩容无效，增加第 3 个港区接口即可在原有 100 kW 下完成任务。
- **60 分钟仓库放行延迟**：若前两辆车在仓库等满 60 分钟，在相同设备菜单下除增设接口外，还需将港区接入扩至 150 kW。

[任务输入](configs/port_warehouse_investment.json) · [逐档最优设施和费用](results/known_delay_investment_20261111/metrics.json) · [服务范围与约束解释](results/shared_investment_20261112/)

### 2. 第二个港区接口值多少钱

**结论：在 300 kWh 电池情景下，第二个独立 50 kW 港区接口既不能增加完成车日，购电与需量运行价值也远低于独立整机约 €3,724/年的文献成本。**

冻结德国车队案例的接入容量（港区 100 kW、仓库 75 kW）和仓库单接口，在 3 天样本（2021 年 9 月 21–23 日）与随后 6 周上逐项检验港区单接口与双接口的差额：

| 检验情景 | 同服务完成量 | 第二港区接口运行价值 | 结论要点 |
|---|---|---|---|
| 3 天对照（2021-09-21 至 23，同期 DE-LU 日前价） | 8 个车日、45 趟 | 按价调度下再省 €10.62（单口按价相对即充已省 €31.22） | 仅含 3 天电能费 |
| 后 6 周基准（每日回到 150 kWh，等权重复 52 周） | 54/73 个车日 | 6 周省 €32.29，年化约 €331/年（2025 年币值） | 远低于独立 50 kW 整机约 €3,724/年 |
| 跨日电量结转（替代每日回到 150 kWh） | 54/73 个车日 | 6 周省 €38.18，年化约 €391/年（单/双口 6 周电费各降 8.6% / 10.1%） | 完成量与门槛结论不变 |
| 计入 Netze BW 2024 年需量网费 | 54/73 个车日 | 独立第二口约 €2.21/年（同时优化峰值）或 −€773/年（只按电价调度）；既有 50 kW 柜加枪约 €2.15/年 | 需量费大幅压低或逆转电费收益 |
| 正换车时间（2、5 分钟） | 54/73 个车日 | 购电收益仍不足以承担独立第二充电点的年成本 | 未带来新增服务价值 |

- **为何没有服务价值**：逐车检查表明，6 周内未完成的 19 个车日中有 18 个受 300 kWh 电池或缺少充电停靠所限，增加接口、接入容量或单车功率均无法完成，因此第二个接口的价值只体现在电费上。
- **既有柜改造缺口**：能同时给两辆车各供 50 kW 的既有柜增设接口，仍需单独现场报价。

[原始车队来源与停车假设](studies/fleet-service/DATA.md) · [未完成车日归因](studies/fleet-service/service_gap.md) · [完整投资实验](studies/day-ahead/second_port.md) · [跨日电量边界](studies/fleet-service/energy_boundary.md) · [共享柜与需量电费](studies/fleet-service/cabinet_demand.md) · [车队换车时间](studies/fleet-service/changeover.md)

### 3. 两站需要多大功率：选型与两次留出检验

**决定需要多少功率。** 两次按时间顺序的留出检验里，样本内年费最低的设施都没守住随后运营周的同一组运输任务。两段留出各用于一次预定检验（第一折在检验后并入 12 周选型样本，不再作为独立样本）；数据已用完，本项目没有经样本外验证的推荐规模。

| 折次 | 规划 → 留出窗口 | 留出登记 | 选定设施的缺口 | 缺口约束（均在仓库侧） | 事后恢复诊断 |
|---|---|---|---|---|---|
| 第一折 | 6 周（54/73）→ 6 周（2021-11-08 至 12-19） | 52/63 | 港区单站 20/0、40/0（至 50/0）kW 均少 1 个（11-26 车 1） | 行程储备越界 | 仓库 +15 kW 恢复（有价 20 kW） |
| 第二折（预登记） | 12 周（106/136）→ 7 周（2021-12-20 至 2022-02-06） | 49/57 | 40/20 kW 少 1 个（01-19 车 1）；20/20 kW 少 2 个 | 行程可跑完，段末距 150 kWh 差 46.24 kWh | 仓库 30 kW 不可行、40 kW 可行、35 kW 未检验 |

- **12 周重选与策略对照**：合并前 12 周的有价粗网格上，12 个费率与接入口径均选出港区 40 kW 加仓库 20 kW（5 个，含 Netze BW 官方新建与既有）或港/仓各 20 kW（7 个）。第二折中，20/20 kW 另少 1 月 31 日的 4 号车；按 12 周各周最低方案取并集组成的稳健基准，以及按天滚动、到站即充各自选出的设施，也都未保住服务。
- **两折缺口异同**：两折缺口都出现在 1 号车的单日段和仓库一侧，所试港区增容均无效；但约束类型不同——11 月 26 日为首趟行程储备越界，1 月 19 日记录的充电全部在仓库、当天没有港区停靠，行程本身可跑完，缺口来自段末 150 kWh 的模型约定。
- **双站基准与同服务年费**：第二折的 49/57 个登记车日由双站基准（两站各 50 kW 充电机、100/75 kW 接入）按自身可行服务确定，因此它在主情景守住该集合是按构造成立的；耗电增加 10% 时，基准自己也少完成 1 个车日。该基准在第二折的官方网费年费为新建 €22,232.75–22,232.83、既有 €19,895.26–19,895.34（2025 年欧元，按 52/7 年化）。
- **开封后阶梯诊断与口径**：第二折开封后从 40/20 kW 出发按预登记四档有价阶梯诊断，仓库升至 40 kW 恢复服务的额外固定年费为阶梯内最低（新建 €756.91、既有 €489.77，2025 年欧元）；这是看到结果后的诊断，而非样本外验证。设施固定后采用按周全信息离线优化，不是在线策略；年费只在同一留出期内比较（规划期、第一折、第二折 DE-LU 日前均价分别为 €138.23、€206.16、€173.46/MWh）。[规划期选型](studies/fleet-service/site_sizing.md) · [第一折留出](studies/fleet-service/holdout_test.md) · [第二折留出](studies/fleet-service/second_holdout.md)

### 4. 核心假设与结论边界

- **观测与假设分开**：相邻行程记录仅给出停车时长上界；站点映射（基地→港区、非基地工业区→仓库）、仓库 45 分钟放行与可插枪窗口均为情景假设，行程耗电来自上游 BETOS 仿真而非实测。
- **离线排程与同口径比较**：设施固定后采用按周全信息离线优化，不是在线策略；年费仅在同一时期、完成同一组登记服务的设施间比较。
- **样本与推断边界**：实证车队仅覆盖德国单一承运人的 5 辆重卡重复观测，不作统计显著性或跨车队推广声明；可用完整周已全部用完，事后恢复诊断不等于样本外验证，本研究不将任何设施配置列为推荐方案。

### 5. 研究报告与证据索引

| 专题 | 报告与证据 | 内容概要 |
|---|---|---|
| 合成算例与接口瓶颈 | [任务输入](configs/port_warehouse_investment.json) · [逐档最优设施和费用](results/known_delay_investment_20261111/metrics.json) · [服务范围与约束解释](results/shared_investment_20261112/) | 4 小时三车算例中接口时段、放行延迟与接入扩容边界 |
| 车队数据与电价 | [原始车队来源与停车假设](studies/fleet-service/DATA.md) | 德国单承运人 5 车轨迹筛选、空间断点与三期 DE-LU 日前电价 |
| 第二接口门槛与归因 | [完整投资实验](studies/day-ahead/second_port.md) · [未完成车日归因](studies/fleet-service/service_gap.md) | 3 天与 6 周购电收益门槛及 18/19 未完成车日的单车归因 |
| 电量、需量与换车检验 | [跨日电量边界](studies/fleet-service/energy_boundary.md) · [共享柜与需量电费](studies/fleet-service/cabinet_demand.md) · [车队换车时间](studies/fleet-service/changeover.md) | 跨日结转、Netze BW 需量网费与 2/5 分钟换车时间的逐项检验 |
| 两站功率联合选型 | [规划期选型](studies/fleet-service/site_sizing.md) | 6 周规划期 12 个计费口径的粗/细网格选型、下界排除与门槛价 |
| 两次留出检验 | [第一折留出](studies/fleet-service/holdout_test.md) · [第二折留出](studies/fleet-service/second_holdout.md) | 固定设施的两次按时间顺序留出检验、机理诊断与预登记封存核验 |
| 模型与独立论文复算 | [数学模型](docs/model/FORMULATION.md) · [米兰城市配送论文复算](studies/fresia-2025/) | MILP 完整约束公式及独立于 UM 车队的 Fresia 缩例复算 |

### 6. Windows 快速复算

从本研究版本的仓库根目录（含 `requirements-milp.txt`）运行。使用独立 Python 3.12 环境，首次在该环境运行 `python -m pip install -r requirements-milp.txt`。计算使用 SciPy 自带的 HiGHS。输入已随仓库提供。

```powershell
$env:PYTHONPATH = 'src'
python -m um_charging.connector_value
```

成功时，`concurrent` 行显示 `8/8 vehicle-days` 和 `second port saves EUR 10.61522`，`january_replay` 行显示 `6.80206`。项目保留相邻行程推得的停车上界，站点映射与可插枪时间是情景假设。[六周复算与结果](studies/day-ahead/second_port.md) · [数学模型](docs/model/FORMULATION.md) · [米兰城市配送论文复算](studies/fresia-2025/)

---

## English

[中文](#中文)

This repository studies **two-site (port and warehouse) charging infrastructure sizing for heavy-duty electric trucks under fixed transport duties**. Holding service, battery limits, grid connections, connector counts, and charging windows fixed, it compares total investment and operating cost for completing the same service to test when operational flexibility substitutes for capacity expansion. Empirical cases pair recorded German trips and simulated trip energies for five trucks from one carrier (DT-CARGO / TUMFTM) with contemporaneous native DE-LU day-ahead prices (SMARD), alongside a four-hour three-truck synthetic benchmark and a separate Milan urban-delivery paper replication.

**Three headline findings:** (1) when bunched port returns exceed available connector-slots, grid expansion alone fails and an added connector is required; (2) in the 300 kWh German fleet scenario, a second independent 50 kW port connector adds zero vehicle-days and its operating savings fall far short of standalone charger cost; (3) across two chronological holdout tests, the lowest-cost in-sample facilities failed to retain the same service in later weeks—all cohort weeks are exhausted, and the study has **no sizing recommendation validated out of sample**. See [Reproduce in Windows PowerShell](#6-reproduce-in-windows-powershell) and the [Studies and evidence index](#5-studies-and-evidence-index) below.

New readers can start with the [Repository Guide](docs/GUIDE.md#english) (five-minute, half-hour, and full-audit paths, directory map, and evidence tiers).

### 1. When a connector is necessary

**Takeaway: When late-released trucks return and need charging in the same hour, grid expansion alone cannot cover a connector-slot shortage—an extra connector is required.**

In the four-hour synthetic benchmark, three electric trucks leave the port, unload at a warehouse, and return (20 kWh per leg, 50 kW truck charging limit, 100/75 kW port/warehouse grid connections, one warehouse connector, and 15-minute slots with zero changeover time):

- **45-minute warehouse release delay:** Two trucks wait 45 minutes before they can plug in at the warehouse while the third has the full hour. Even the best warehouse schedule leaves at least nine port connector-slots to cover, whereas two port connectors supply only eight. Grid upgrades alone fail; adding a third port connector completes the duty at the existing 100 kW.
- **60-minute warehouse release delay:** If the two trucks wait the entire warehouse hour, the minimum-cost build under the same equipment menu also upgrades the port connection to 150 kW.

[Task and equipment inputs](configs/port_warehouse_investment.json) · [Optimal builds](results/known_delay_investment_20261111/metrics.json) · [Service ranges and constraint evidence](results/shared_investment_20261112/)

### 2. When a second port connector lowers the bill

**Takeaway: In the 300 kWh German fleet scenario, a second independent 50 kW port connector serves no additional vehicle-days, and its operating value remains far below the published €3,724/year standalone charger benchmark.**

Freezing the German fleet’s grid connections (100 kW port, 75 kW warehouse) and one warehouse connector, we compare one versus two port connectors across a three-day benchmark (21–23 September 2021) and six subsequent operating weeks:

| Test case | Matched service | Operating value of 2nd port connector | Key takeaway |
|---|---|---|---|
| Three-day benchmark (21–23 Sep 2021, contemporaneous DE-LU prices) | 8 vehicle-days, 45 trips | Saves a further €10.62 under price optimization (price-optimizing one connector cuts €31.22 vs immediate charging) | Three-day energy bill only |
| Six later weeks (daily reset to 150 kWh, repeated over 52 weeks) | 54/73 vehicle-days | €32.29 over six weeks, supporting about €331/year (2025 euros) | Far below ~€3,724/year standalone 50 kW charger cost |
| Cross-day energy carry-over (instead of daily reset to 150 kWh) | 54/73 vehicle-days | €38.18 over six weeks, about €391/year (six-week bills fall 8.6% with one connector and 10.1% with two) | Service and cost hurdle unchanged |
| Netze BW 2024 demand charges | 54/73 vehicle-days | Independent 2nd connector: about €2.21/year (peak-aware) or −€773/year (energy-only); 2nd cable on existing 50 kW cabinet: about €2.15/year (peak-aware) | Demand charges compress or reverse energy savings |
| Positive plug changeover (2 or 5 minutes) | 54/73 vehicle-days | Energy savings remain below the independent charger’s annual cost | No added service value |

- **Why there is no service gain:** Truck-by-truck checks show that the 300 kWh battery or a lack of charging stops limits 18 of the 19 unserved vehicle-days; extra connectors, grid capacity, or truck charging power cannot serve them, so the second connector’s value is in the bill alone.
- **Retrofit quote gap:** A dispenser retrofit capable of delivering two simultaneous 50 kW sessions from an existing cabinet still requires a site quote.

[Fleet provenance and assumptions](studies/fleet-service/DATA.md) · [Unserved-day attribution](studies/fleet-service/service_gap.md) · [Full investment experiment](studies/day-ahead/second_port.md) · [Energy boundaries](studies/fleet-service/energy_boundary.md) · [Shared cabinets and demand charges](studies/fleet-service/cabinet_demand.md) · [Fleet plug changeover](studies/fleet-service/changeover.md)

### 3. Port and warehouse power sizing across two holdouts

**How much power is needed.** Across two chronological holdouts, the facilities with the lowest in-sample annual cost failed to retain the same transport service in the following weeks. Each holdout was used once for its planned test (the first holdout was merged into the 12-week selection sample after its test and is no longer independent). All cohort weeks have been used, and the study has no sizing recommendation validated out of sample.

| Fold | Selection → holdout window | Register | Gaps for fixed selected builds | Binding constraint (warehouse side) | Post-hoc repair diagnosis |
|---|---|---|---|---|---|
| Fold 1 | 6 wk (54/73) → 6 wk (8 Nov–19 Dec 2021) | 52/63 | Port-only 20/0, 40/0 (up to 50/0) kW missed 1 (26 Nov, vehicle 1) | In-trip reserve breached | Warehouse +15 kW (smallest priced: 20 kW) |
| Fold 2 (preregistered) | 12 wk (106/136) → 7 wk (20 Dec 2021–6 Feb 2022) | 49/57 | 40/20 kW missed 1 (19 Jan, vehicle 1); 20/20 kW missed 2 | Trips finished; terminal SOC 46.24 kWh below 150 kWh | Warehouse 30 kW infeasible, 40 kW feasible, 35 kW untested |

- **12-week reselection and operating policies:** Across the 12 tariff-and-access cases on the 12-week priced coarse grid, five selected 40/20 kW (port/warehouse, including both official Netze BW cases) and seven selected 20/20 kW. In Fold 2, 20/20 kW also missed vehicle 4 on 31 January; the union of weekly least-cost facilities and the designs selected under daily rolling and charge-on-arrival dispatch also failed to complete the register.
- **Common and distinct gap mechanisms:** Both folds had a warehouse-side gap in a single-day segment for vehicle 1 that the tested port upgrades could not close, but the binding constraints differed: on 26 November the in-trip reserve was breached, whereas on 19 January all recorded charging occurred at the warehouse with no port stop that day—the trips completed, and the shortfall came from the modeled 150 kWh terminal requirement.
- **Two-site baseline and same-service bills:** The 49/57 Fold 2 register was defined by the two-site baseline (one 50 kW charger per site on 100/75 kW connections) from its own feasible service, so it retained that register by construction in the main scenario; with 10% higher driving energy, the baseline itself lost one vehicle-day. Its official-tariff annual bill in Fold 2 was €22,232.75–22,232.83 for new connections and €19,895.26–19,895.34 for existing access (2025 euros, 52/7 annualization).
- **Post-opening diagnosis and comparison basis:** In the preregistered four-step priced ladder conducted after opening from 40/20 kW, raising the warehouse to 40 kW restored service at the lowest additional annual fixed cost in the ladder (€756.91 new, €489.77 existing, 2025 euros); this is a post-opening diagnostic, not out-of-sample validation. Fixed-facility scheduling uses weekly full-information offline optimization—not an online policy—and annual bills are compared only within the same holdout (mean DE-LU day-ahead prices: €138.23/MWh in planning, €206.16/MWh in Fold 1, €173.46/MWh in Fold 2). [Planning-period sizing](studies/fleet-service/site_sizing.md) · [First holdout](studies/fleet-service/holdout_test.md) · [Second holdout](studies/fleet-service/second_holdout.md)

### 4. Key assumptions and scope limits

- **Records versus scenario assumptions:** Gaps between adjacent trip recordings bound possible dwell time only; site mapping (home base to port, non-home industrial area to warehouse), the 45-minute warehouse release, and plug eligibility are scenario assumptions, and trip energies come from upstream BETOS simulation rather than metered consumption.
- **Offline dispatch and bill comparability:** Fixed-facility schedules use weekly full-information offline optimization, not an online policy; annual bills are compared only within the same period across facilities completing identical registered service.
- **Sample and inference boundaries:** Empirical fleet results cover repeated observations of five trucks from one German carrier and make no claims of statistical significance or broader generalization. All cohort weeks are exhausted, post-hoc repair diagnostics do not constitute out-of-sample validation, and no build is presented as a recommended facility size.

### 5. Studies and evidence index

| Topic | Reports and evidence | What it covers |
|---|---|---|
| Synthetic connector bottleneck | [Task and equipment inputs](configs/port_warehouse_investment.json) · [Optimal builds](results/known_delay_investment_20261111/metrics.json) · [Service ranges and constraint evidence](results/shared_investment_20261112/) | Four-hour three-truck limits on connector slots, release delays, and grid upgrades |
| Fleet data and prices | [Fleet provenance and assumptions](studies/fleet-service/DATA.md) | One-carrier five-truck filtering, spatial recording gaps, and three-period DE-LU prices |
| Second-connector hurdle | [Full investment experiment](studies/day-ahead/second_port.md) · [Unserved-day attribution](studies/fleet-service/service_gap.md) | Three-day and six-week energy savings plus attribution of 18/19 unserved vehicle-days |
| Energy, demand, changeover | [Energy boundaries](studies/fleet-service/energy_boundary.md) · [Shared cabinets and demand charges](studies/fleet-service/cabinet_demand.md) · [Fleet plug changeover](studies/fleet-service/changeover.md) | Sensitivity to cross-day carry-over, Netze BW demand charges, and 2/5-minute changeover |
| Two-site power sizing | [Planning-period sizing](studies/fleet-service/site_sizing.md) | Six-week coarse/refined grid sizing across 12 billing cases, lower bounds, and price thresholds |
| Two chronological holdouts | [First holdout](studies/fleet-service/holdout_test.md) · [Second holdout](studies/fleet-service/second_holdout.md) | Fixed-facility out-of-sample tests, gap diagnosis, and preregistered sealing checks |
| Model and Milan replication | [Mathematical model](docs/model/FORMULATION.md) · [Separate Milan paper replication](studies/fresia-2025/) | Full MILP formulation and a separate reduced replication of Fresia et al. |

### 6. Reproduce in Windows PowerShell

Start in the research repository root, alongside `requirements-milp.txt`. Use a Python 3.12 environment with the pinned dependencies (`python -m pip install -r requirements-milp.txt` once). SciPy supplies HiGHS. The inputs are included.

```powershell
$env:PYTHONPATH = 'src'
python -m um_charging.connector_value
```

Expect `8/8 vehicle-days` and `second port saves EUR 10.61522` on the `concurrent` line, and `6.80206` on the `january_replay` line. Trip records bound possible dwell; site identity and plug eligibility follow the UM scenario. [Full replay and bills](studies/day-ahead/second_port.md) · [Mathematical model](docs/model/FORMULATION.md) · [Separate Milan paper replication](studies/fresia-2025/)
