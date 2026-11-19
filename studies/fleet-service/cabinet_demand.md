# 第二个港区接口能省下多少运行费？ · What is a second port outlet worth?

[中文](#中文) · [English](#english) · [精选结果 / Results](cabinet_demand.json) · [跨日边界 / Energy boundary](energy_boundary.md) · [首页 / Home](../../README.md)

## 中文

同样完成 54 个车日，€22.79/kW·年下，只按电价调度使港区峰值翻倍，独立第二充电点年价值 **−€773.10**。调度计入需量后为 **€2.21/年**，低于整机年成本 €3,724.43。既有柜加枪约省 **€2.15/年**。[结果][results]

### 问题与条件

2021-09-27 至 11-07，一个承运人、5 辆车、30 个完整任务日期共 73 车日。TUMFTM / DT-CARGO 提供行程时间，BETOS 模拟能耗。行程间隔是停车上界，假定港区即到即充、仓库 45 分钟放行。港 / 仓接入 100 / 75 kW，仓库单口。单车 50 kW、效率 90%，整刻钟预约、换车零耗时。S300 容量 / 储备 / 首尾 300 / 30 / 150 kWh。B 跨日结转，未服务日断链。六周任务和同期 DE-LU 小时价均已知，时区 Europe/Berlin。[数据][data] · [电量边界][boundary]

| 港区设备 | 接口 / 柜数 | 单车和两车的取电规则 | 增量成本依据 |
|---|---|---|---|
| E1 单接口 | 1 / 1 | 一车至多 50 kW | 现有设备，作为基准 |
| E2 独立第二充电点 | 2 / 2 | 两路各 50 kW，合计至多 100 kW | Frank 等表 2，新增整机 €20,882 |
| E3 共享柜、双车各限 25 kW | 2 / 1 | 一车至多 50 kW，并充时每车至多 25 kW | Alpitronic HYC50 规格已核实，加枪改造无报价 |
| E4 共享柜、连续分配 | 2 / 1 | 两车可任意分配合计 50 kW | UM 敏感性假设，改造无报价 |

HYC50 标称直流输出，UM 沿用为取电上限。E2 加 30% 安装规划费，10 年、5% 年化，年维护费为原价 1%。10 月 26 日 03:00，E3 两车各取 25 kW，15 分钟各购电 6.25 kWh。[设备成本][cost] · [小实验][pilot]

### 同一运输服务的主结果

P1 先最小化批发费再结算网费。P2 联合优化批发费与两站容量费，电量网费按实际档位计。c（2024 €/kW·年）仅替换容量价，c = 0 仍收 Frank 电量网费。各组均完成相同的 54/73 车日。年账单含三项费用，年价值为 E1 减升级账单（2025 €）。P1/P2 栏只有一个数时，两者相同。[结果][results] · [图][peak]

| c | 设备 | 六周购电费 €2021，P1/P2 | P1 港 / 仓 kW | P2 港 / 仓 kW | 年账单 €，P1/P2 | 年运行价值 €，P1/P2 |
|---|---|---:|---:|---:|---:|---:|
| 0 | E1 | 568.85 | 50 / 50 | 50 / 50 | 11,198.48 | 0.00 |
| 0 | E2 | 530.67 | 100 / 50 | 100 / 50 | 10,807.25 | 391.24 |
| 0 | E3 | 568.69 | 50 / 50 | 50 / 50 | 11,196.81 | 1.67 |
| 0 | E4 | 568.66 | 50 / 50 | 50 / 50 | 11,196.49 | 2.00 |
| 22.79 | E1 | 568.85 / 571.78 | 50 / 50 | 50 / 0 | 13,527.15 / 12,392.75 | 0.00 / 0.00 |
| 22.79 | E2 | 530.67 / 572.68 | 100 / 50 | 49.51 / 0 | 14,300.25 / 12,390.54 | −773.10 / 2.21 |
| 22.79 | E3 | 568.69 / 572.98 | 50 / 50 | 49.38 / 0 | 13,525.48 / 12,390.60 | 1.67 / 2.15 |
| 22.79 | E4 | 568.66 / 572.68 | 50 / 50 | 49.51 / 0 | 13,525.16 / 12,390.54 | 2.00 / 2.21 |

两站分表、只计车队，港区可独立供电。同价下使用仓库另增需量。c = 22.79 的 P2 解仓库峰值为零，c = 0 沿用 P1，为 50 kW。若合表按同时总负荷取峰，错峰使用仓库可能改变峰值和档位，此处仅定性讨论。

E2 扣整机年费为 −€3,722.22/年。E3 零新增维护时，年收益除以资本回收系数 0.129505，投资上限约 €16.59（求解区间端点取到分为 €16.58、€16.59）。E4 约 €17.08。[成本基准][cost]

### 敏感性与临界容量价

| 升级 | 208.38 下 P1 年价值（€） | 208.38 下 P2 年价值（€） | P1 临界 c | P2 购电费加容量费目标的临界 c |
|---|---:|---:|---|---|
| E2 | −10,254.83 | [0.809778, 1.974919] | 7.6579 | 所有 c ≥ 0 均为正 |
| E3 | 1.67 | [0.809778, 1.974919] | 非负区间无零点 | 部分区间未判定 |
| E4 | 2.00 | [0.809778, 1.974919] | 非负区间无零点 | 部分区间未判定 |

P1 下 E2 六周购电收益 €38.180675（2021 币值），重复 52/6 倍，折为 €391.237733/年（乘 121.9/103.1）。港区增 50 kW，仓库峰值不变。临界 c = 391.237733 ÷ (50 × 121.9/119.3) = **€7.6579/kW·年**。c = 22.79 时多付容量费 €1,164.334032，电量网费差为零，年价值为 **−€773.10**。Destatis 年度总 CPI（2020 = 100）已核实，2021/2024/2025 为 103.1/119.3/121.9。[CPI 与费率出处][tariff]

P2 随 c 重排。208.38 时 E1 调度目标为 €[11,964.444554, 11,965.334824]/年，界差 €0.890269，故相对价值报区间。此时港区进入高小时档。表末列限购电与容量费目标。完整账单还受电量价分档影响。三个登记价格的账单价值均为正，其他费率仍有未决区间。

| 2024 网费口径 | 低档容量 / 电量价 | 高档容量 / 电量价 | 2,500 h |
|---|---:|---:|---|
| Frank 等（2025）表 4，PDF 第 6 页 | 22.79 / 0.0900 | 208.38 / 0.0100 | 低档 |
| Netze BW 原表，中压负荷曲线计量，印刷第 2 页 | 22.79 / 0.0876 | 208.38 / 0.0133 | 高档 |

单位为 €/kW·年及 €/kWh。年需量取六周最大整刻钟平均功率，年 kWh 除以需量得满负荷小时。两套容量价相同，原表已核实为中压。主合同均落低档，原表使各组年账单降低 €143.18（P2 的 E1 从 €12,392.75 降至 €12,249.57），接口价值不变。[网费原表][tariff]

### 哪些结论保持，哪些需要改写

**保持。** S300 有 19 个车日仍无法完成，购电收益负担不起独立整机。**改写。** 需量计费会扭转只按批发电价调度的价值，加枪与增柜的服务能力也不同。900 kWh 下，S900a（储备 / 初值 30 / 150 kWh）四组均为 64/73。S900b（30 / 450）依 E1–E4 为 65、66、65、65。S900c（90 / 450）为 64、65、64、64。后两档在 10 月 18 日只有 E2 能完成车 1、3、5 三辆车当天的任务。E1 服务 1、5，共享柜服务 3、5。[服务缺口][gaps] · [精选结果][results]

**适用范围。** 5 辆车重复观测，六周等权年化属于情景假设。实际全年任务、基础负荷、站点电压与合同、加枪报价均未知。

### 复算

从仓库根目录运行，先只读核对精选摘要（48 行、1 行 bounded），再列原始求解命令。小实验 E3 预期 €26.104882、50 kW。全套 Frank / P2 / E2 为 54/73、六周 €572.679872、年账单 €12,390.54。原运行耗时 3,887.49 秒。[结果][results] · [CLI][cli]

```powershell
.venv\Scripts\python.exe -c "import json; r=json.load(open('studies/fleet-service/cabinet_demand.json', encoding='utf-8'))['main']; print(len(r), sum(x['status']=='bounded' for x in r))"
$env:PYTHONPATH = 'src'
.venv\Scripts\python.exe -X utf8 -m um_charging.cabinet_demand --pilot
.venv\Scripts\python.exe -X utf8 -m um_charging.cabinet_demand
```

逐组合排程、回放与证明见[离线记录定位](#offline-record)。

## English

At €22.79/kW/year, energy-only dispatch doubles the port peak. For 54 matched truck-days, the independent charger’s annual value is **−€773.10**. Pricing demand in dispatch gives **€2.21/year**, against €3,724.43 annual equipment cost. A second cable on the existing cabinet saves **€2.15/year**. [Results][results]

### Question and conditions

One carrier, five trucks, 30 dates and 73 complete truck-days, 27 September–7 November 2021. TUMFTM / DT-CARGO records trip times, BETOS simulates energy. Trip gaps bound parking. Port access on arrival and warehouse release after 45 minutes are assumed. Port/warehouse connections are 100/75 kW, with one warehouse outlet. Trucks draw up to 50 kW at 90% efficiency on quarter-hour reservations with zero changeover. S300 capacity/reserve/endpoints are 300/30/150 kWh. B carries energy across linked duties, split by unserved days. Six-week tasks and native DE-LU hourly prices are known, in Europe/Berlin time. [Data][data] · [Boundary][boundary]

| Port build | Outlets / cabinets | Power allocation | Incremental cost basis |
|---|---|---|---|
| E1 single | 1 / 1 | Up to 50 kW | Existing |
| E2 independent | 2 / 2 | 50 kW each, up to 100 kW total | Frank et al., Table 2, €20,882 |
| E3 shared | 2 / 1 | One up to 50 kW, two up to 25 kW each | HYC50 specification, no retrofit quote |
| E4 pooled | 2 / 1 | Continuous split of 50 kW | UM sensitivity, no quote |

UM uses HYC50 DC ratings as grid-draw limits. E2 adds 30% for planning and installation, with ten years at 5% and 1% annual maintenance on equipment price. At 03:00 on 26 October two E3 trucks each draw 25 kW, buying 6.25 kWh per quarter. [Costs][cost] · [Pilot][pilot]

### Main results on identical service

P1 minimizes wholesale cost before billing. P2 prices wholesale energy and both meter peaks in dispatch. Each meter’s band sets its volumetric fee. Fixed c (2024 €/kW/year) retains Frank’s volumetric fee at zero. All builds serve the same 54/73. Annual bills include all three charges in 2025 euros. Value is E1 less the upgrade. One entry in a P1/P2 column applies to both. WH is warehouse. [Results][results] · [Figure][peak]

| c | Build | 6-week €2021, P1/P2 | P1 port/WH kW | P2 port/WH kW | Bill €/yr, P1/P2 | Value €/yr, P1/P2 |
|---|---|---:|---:|---:|---:|---:|
| 0 | E1 | 568.85 | 50 / 50 | 50 / 50 | 11,198.48 | 0.00 |
| 0 | E2 | 530.67 | 100 / 50 | 100 / 50 | 10,807.25 | 391.24 |
| 0 | E3 | 568.69 | 50 / 50 | 50 / 50 | 11,196.81 | 1.67 |
| 0 | E4 | 568.66 | 50 / 50 | 50 / 50 | 11,196.49 | 2.00 |
| 22.79 | E1 | 568.85 / 571.78 | 50 / 50 | 50 / 0 | 13,527.15 / 12,392.75 | 0.00 / 0.00 |
| 22.79 | E2 | 530.67 / 572.68 | 100 / 50 | 49.51 / 0 | 14,300.25 / 12,390.54 | −773.10 / 2.21 |
| 22.79 | E3 | 568.69 / 572.98 | 50 / 50 | 49.38 / 0 | 13,525.48 / 12,390.60 | 1.67 / 2.15 |
| 22.79 | E4 | 568.66 / 572.68 | 50 / 50 | 49.51 / 0 | 13,525.16 / 12,390.54 | 2.00 / 2.21 |

With separate fleet-only meters, the port can cover the duties at the same prices and avoid a second peak. All displayed P2 warehouse peaks are 0 kW at 22.79 and 50 kW at zero. Under a joint meter, off-peak warehouse use could change coincident demand and tariff band. This is qualitative.

E2 loses €3,722.22/year after equipment cost. At zero extra maintenance, divide E3’s saving by the 0.129505 capital recovery factor, giving about €16.59 installed (bound endpoints round to €16.58 and €16.59). E4 supports €17.08. [Costs][cost]

### Sensitivity, break-even and tariff evidence

| Upgrade | P1 value at 208.38 (€ / year) | P2 value at 208.38 (€ / year) | P1 break-even c | P2 wholesale + capacity break-even c |
|---|---:|---:|---|---|
| E2 | −10,254.83 | [0.809778, 1.974919] | 7.6579 | Positive for c ≥ 0 |
| E3 | 1.67 | [0.809778, 1.974919] | No zero for c ≥ 0 | Unresolved in part |
| E4 | 2.00 | [0.809778, 1.974919] | No zero for c ≥ 0 | Unresolved in part |

Under P1, E2 saves €38.180675 in six-week 2021 euros. Multiplying by 52/6 × 121.9/103.1 yields €391.237733/year. The port adds 50 kW; warehouse demand stays level. Break-even c = 391.237733 ÷ (50 × 121.9/119.3) = **€7.6579/kW/year**. At 22.79 the extra annual demand charge is €1,164.334032 with equal volumetric charges, giving **−€773.10/year**. Verified Destatis annual CPI (2020 = 100) is 103.1, 119.3 and 121.9 for 2021, 2024 and 2025. [CPI and sources][tariff]

P2 reschedules as c changes. At 208.38 E1’s annual dispatch objective is €[11,964.444554, 11,965.334824], a €0.890269 gap, hence the intervals. The port enters the high-hours band. The final column covers wholesale plus demand. Full bills also depend on volumetric bands. Positive savings are certified at the three registered prices, with unresolved intervals elsewhere.

| 2024 tariff | Low demand / energy | High demand / energy | Band at exactly 2,500 h |
|---|---:|---:|---|
| Frank et al. (2025), Table 4, PDF p. 6 | 22.79 / 0.0900 | 208.38 / 0.0100 | Low |
| Netze BW, metered medium-voltage supply, printed p. 2 | 22.79 / 0.0876 | 208.38 / 0.0133 | High |

Rates are €/kW/year and €/kWh. The peak is the maximum aligned quarter-hour mean. Annual kWh divided by peak gives full-load hours. Demand rates match the verified medium-voltage sheet. Main bills settle in the low band. The operator’s rates cut each bill by €143.18 (P2 E1 falls from €12,392.75 to €12,249.57). Outlet values hold. [Original sheets][tariff]

### What holds, what changes and where it applies

**What holds.** S300 leaves 19 truck-days unserved. Energy savings cannot fund the independent charger. **What changes.** Demand charges can reverse the value of price-only dispatch. A second cable and an independent cabinet also differ in service. At 900 kWh, S900a (reserve/start 30/150 kWh) serves 64/73 with every build. E1–E4 serve 65, 66, 65, 65 in S900b (30/450) and 64, 65, 64, 64 in S900c (90/450). On 18 October in the latter two, only E2 completes all three trucks’ duties (1, 3, 5). E1 serves 1 and 5, the shared builds 3 and 5. [Service gaps][gaps] · [Results][results]

**Scope.** Five trucks repeat across six equally weighted weeks. Actual annual service, other meter loads, site voltage, contracts and retrofit prices remain unknown.

### Reproduce

In the repository root, the first command reads the existing file (48 rows, one bounded dispatch). The next two solve the pilot and full case. Expect E3 €26.104882 and 50 kW in the pilot. Frank / P2 / E2 gives 54/73, €572.679872 over six weeks, €12,390.54/year. Recorded time 3,887.49 s. [CLI][cli]

```powershell
.venv\Scripts\python.exe -c "import json; r=json.load(open('studies/fleet-service/cabinet_demand.json', encoding='utf-8'))['main']; print(len(r), sum(x['status']=='bounded' for x in r))"
$env:PYTHONPATH = 'src'
.venv\Scripts\python.exe -X utf8 -m um_charging.cabinet_demand --pilot
.venv\Scripts\python.exe -X utf8 -m um_charging.cabinet_demand
```

See the offline record for schedules, per-combination results and proofs.

### Offline record

离线记录库 / Offline records `runs/20261119_cabinet_demand_retry1/summary.json`

[results]: cabinet_demand.json
[data]: DATA.md
[boundary]: energy_boundary.md
[tariff]: ../day-ahead/network_charges.json
[cost]: ../day-ahead/connector_cost.json
[peak]: figures/cabinet_demand_peak_value.svg
[pilot]: figures/cabinet_demand_pilot.svg
[gaps]: service_gap.md
[cli]: ../../src/um_charging/cabinet_demand.py
