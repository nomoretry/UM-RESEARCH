# 换车时间会给第二个港区接口带来服务价值吗？ · Does plug changeover make a second port outlet valuable?

[中文](#中文) · [English](#english) · [精选结果 / Results](changeover.json) · [首页 / Home](../../README.md)

## 中文

后六周在 0、2、5 分钟和 10、15 分钟压力情景下，两种设施均完成同一组 54/73 个车日。2、5 分钟时，第二个独立港区接口的年电费收益分别约 €396.32、€402.85，均低于 €3,724.43/年整机成本。

### 问题与条件

运输任务、可充电窗口、接入容量和货车规格固定。后六周为 2021-09-27 至 11-07，一个承运人、5 辆货车、30 个完整任务日期的 73 个车日。行程时刻来自 TUMFTM / DT-CARGO，能耗由 BETOS 模拟。停车窗为相邻行程推得的上界，港区到站可插枪，仓库放行延迟固定 45 分钟。S300 的电池／储备／运行段首尾为 300／30／150 kWh，效率 90%，单车取电上限 50 kW。港区接入 100 kW，仓库 75 kW、固定一把枪。双港区接口是各自独立的物理充电点。六周按边界 B 跨日结转，未完成日断开电量链。[车队数据](DATA.md) · [跨日电量边界](energy_boundary.md)

### 换车和独立回放

预约以整刻钟为单位，每把枪同一刻钟至多排一辆车，同一车也只占一把枪。上一刻钟预约给另一辆车时，当前刻钟起点后 δ 分钟内不得取电，实际起充还须等停车窗开放。空闲一刻钟已覆盖本研究的 δ。占同一枪的同一辆车跨午夜连续充电没有额外损失。若 δ=5，一把枪给两车连续两刻钟，后车在完整可用刻钟内最多取电 8.3333 kWh，原上限为 12.5 kWh。独立审计用排程回放逐枪换车，以分钟和实际窗端点复算功率与电费，按行程端点和跨日链复算电量。[模型与审计](../../src/um_charging/fleet_changeover.py)

### 三天对照与单周试跑

9 月 21–23 日的三车对照保留原逐日 150 kWh 首尾条件，共 45 趟行程。两种设施在三档下均完成 8/8 车日，δ=0 的第二接口收益为 €10.61522。正式运行前，10 月 18 日开始的一周按边界 B 和 δ=5 试跑。单、双接口各完成 9 个车日，四次求解用时分别为 0.191, 0.903, 0.300, 3.283 秒。[原三天算例](../day-ahead/second_port.md) · [试跑结果](changeover.json)

| δ 分钟 | 单口／双口车日 | 单口购电 €2021 | 双口购电 €2021 | 电费差 €2021 |
| :---: | :---: | :---: | :---: | :---: |
| 0 | 8/8 · 8/8 | 115.58 | 104.97 | 10.61522 |
| 2 | 8/8 · 8/8 | 115.80 | 104.99 | 10.80969 |
| 5 | 8/8 · 8/8 | 116.04 | 104.99 | 11.05241 |

### 六周共同服务与费用

电费只计 DE-LU 同期日前电能，原生小时报价 €/MWh，欧洲柏林当地时间。调度者在每周建模期已知任务和全部相应小时价格。每周 MILP 先证明最大服务量，再对确定的完成集合优化电费。若两种设施的服务集合不同，以单接口完成集合重算双接口账单，计算同车日节省。5 分钟时服务量保持不变，触发 10、15 分钟压力情景。表中的购电费取自已回放的排程。换车次数为同一把枪连续两次有电预约的车辆变化次数，括号内只数相邻刻钟的变化。次数随返回的电费排程而变。

| δ 分钟 | 单口车日 | 双口车日 | 单口购电 €2021 | 双口购电 €2021 | 换车 单 / 双 | 新增车日 | 同车日年省 €2025 | 回本门槛 €2025/新增车日 |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 0 | 54/73 | 54/73 | 568.85 | 530.67 | 162 (134) / 229 (185) | 0 | 391.24 | — |
| 2 | 54/73 | 54/73 | 569.44 | 530.77 | 63 (33) / 69 (19) | 0 | [395.96, 396.48] | — |
| 5 | 54/73 | 54/73 | 570.22 | 530.90 | 54 (27) / 73 (16) | 0 | [402.54, 403.07] | — |
| 10（压力） | 54/73 | 54/73 | 571.34 | 531.12 | 60 (30) / 58 (7) | 0 | [411.85, 412.26] | — |
| 15（压力） | 54/73 | 54/73 | 572.87 | 531.56 | 58 (0) / 68 (0) | 0 | [423.01, 423.38] | — |

用于年化的电费差按六周等权重复 52 周，再乘已登记 CPI 比值 121.9/103.1。若双接口多完成车日，用 €3,724.43 的整机年费减同车日年节约，再除以六周额外车日 × 52/6，得到每多完成一车日至少需贡献的金额。区间来自两种设施的电费上下界，正换车每周接受相对 gap ≤ 1e-6 **或**绝对 gap ≤ €0.01。表内区间向外取到分。[成本与 CPI](../day-ahead/connector_cost.json)

### 结论与适用范围

所有车日名单相同，基准的 19 个未完成车日依旧未完成。相对 δ=0，每种设施在每个正换车情景的新增、减少均为 0，所以没有需定位到站点、插枪和车辆的新增服务损失，双接口的回本门槛也无新增车日可作分母。完成量对换车时间单调不增，双接口从未少于单接口。



结论适用于登记的停车和放行假设、同站换车规则及 300 kWh 档。运营数据来自重复观测，换车时长没有现场实测校准。Wang 等的公交案例采用包含挪车的 12 分钟固定对照，接近本研究的 10–15 分钟压力档。ABB 的矿卡自动接合约 18 秒、断开约 7 秒，覆盖的是设备动作。Link 等预印本只核查了摘要，正文页码和人工换车用时仍缺。文献核对只用于解释量级。本轮按电能调度和结算。[换车证据与页码](../../docs/literature/20261118/CARDS.md#s2-车队换车时间补查2026-11-19)

### 复算

从仓库根目录用已安装[依赖](../../requirements-milp.txt)的 Python 运行。

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -X utf8 -m um_charging.fleet_changeover --pilot
.\.venv\Scripts\python.exe -X utf8 -m um_charging.fleet_changeover
```

第一条应打印 `8/8 vehicle-days` 和 `second port saves EUR 10.61522`。第二条 δ=0 应为单／双接口 54/73、54/73，六周购电 €568.854676／€530.674001。单次上限 300 秒，六周上限 90 分钟。正式源码 `75125fb0c2b7d3dc4f4a5da369aeaeab9d430af0`，运行时工作树干净。记录用时 501.58 秒，审计 120 份可行排程，未判定周组 0 个。完整日志、逐枪排程和审计见离线记录库 `runs/20261119_changeover/formal_retry/`。[精选与校验值](changeover.json)

## English

At 0, 2 and 5 minutes and in the 10- and 15-minute stress cases, both builds served the same 54 of 73 truck-days. At 2 and 5 minutes the second independent port plug saves about €396.32 and €402.85 per year, below the €3,724.43 annual equipment cost.

### Question and conditions

The later six weeks (27 September–7 November 2021) have 73 complete truck-days across 30 dates, five trucks and one carrier. TUMFTM / DT-CARGO provides trip times and BETOS supplies simulated energy use. Gaps between trips bound dwell. Port access starts on arrival, and warehouse access starts after 45 minutes. The 300 kWh battery has a 30 kWh reserve and 150 kWh endpoints, with 90% charging efficiency and a 50 kW truck limit. Grid limits are 100 kW at the port and 75 kW at the warehouse. The warehouse has one plug. The port has one or two independent plugs. Case B carries energy over linked days, with unserved days splitting a chain. [Data](DATA.md) · [Energy boundary](energy_boundary.md)

### Changeover rule and replay

Each plug takes at most one truck reservation for the whole quarter. A truck cannot occupy two plugs in the same quarter. If the previous quarter belonged to another truck, the next truck may draw power after δ minutes and after its own release. An idle quarter covers every tested δ. The same truck on the same plug may continue across midnight. At 5 minutes a full next quarter offers 10 minutes at up to 50 kW, or 8.3333 kWh versus 12.5 kWh at zero. Replay checks named plugs, minute and within-minute power, the wholesale bill, trip endpoints and the energy chain independently of the solver. [Model and replay](../../src/um_charging/fleet_changeover.py)

### Pilot and six-week comparison

The original 21–23 September pilot keeps daily 150 kWh endpoints, serves all eight truck-days for all three tested times, and replicates €10.61522 of second-plug savings at zero changeover. The 18 October trial week uses carry-over and δ=5, with 9 completed truck-days on one plug and 9 on two. [Pilot and trial data](changeover.json)

The model uses the native DE-LU hourly day-ahead price (€/MWh, Europe/Berlin), with the week's tasks and prices available when dispatching. First it proves maximum weekly service. Then it minimizes energy cost on the selected cohort. If cohorts differ, it reprices the one-plug cohort under both builds. Service holds at 5 minutes, so the study adds 10 and 15 minutes as stress cases. Bills come from the replayed schedules. Changes count a different truck after the preceding positive reservation on the same plug. Counts in parentheses cover consecutive quarters only.

| δ min | One plug days | Two plug days | One plug €2021 | Two plugs €2021 | Changes one / two | Extra days | Annual matched saving €2025 | Break-even €2025/extra day |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 0 | 54/73 | 54/73 | 568.85 | 530.67 | 162 (134) / 229 (185) | 0 | 391.24 | — |
| 2 | 54/73 | 54/73 | 569.44 | 530.77 | 63 (33) / 69 (19) | 0 | [395.96, 396.48] | — |
| 5 | 54/73 | 54/73 | 570.22 | 530.90 | 54 (27) / 73 (16) | 0 | [402.54, 403.07] | — |
| 10 (stress) | 54/73 | 54/73 | 571.34 | 531.12 | 60 (30) / 58 (7) | 0 | [411.85, 412.26] | — |
| 15 (stress) | 54/73 | 54/73 | 572.87 | 531.56 | 58 (0) / 68 (0) | 0 | [423.01, 423.38] | — |

The energy bill covers the six weeks in 2021 euros. For the annual saving, repeat the six weeks equally over 52 weeks and multiply by 121.9/103.1 to express 2025 euros. If the two-plug build adds truck-days, divide the €3,724.43 annual charger cost less matched energy savings by the annualized increase in truck-days. The cost criterion is a relative gap of 1e-6 or an absolute weekly gap of €0.01. The intervals propagate the weekly bounds and round outward. [Costs and CPI](../day-ahead/connector_cost.json)

### Findings and scope

Both builds keep the same truck-day set across all delays. The 19 already unserved truck-days remain unserved. Relative to zero delay there are zero additions and zero removals, so there are no additional losses to attribute to trucks or plugs and no extra days to use in a break-even calculation. The completion count is non-increasing with delay and weakly increasing with the number of port plugs.

This is a fixed-service electricity comparison using the registered charging windows and one repeated carrier sample. Wang et al.'s bus case uses a 12-minute fixed benchmark including vehicle movement. ABB's automated mining-truck sequence reports seconds for mating and disconnection, with vehicle manoeuvres separate. Link et al.'s abstract does not give changeover times. The external evidence contextualizes the time grid. [Source pages and reading scope](../../docs/literature/20261118/CARDS.md#s2-车队换车时间补查2026-11-19)

### Reproduce

Set `PYTHONPATH=src` and run `python -m um_charging.fleet_changeover --pilot` and `python -m um_charging.fleet_changeover` from the repository root. Expect an 8/8 pilot and €10.61522 of zero-delay savings. In the six-week zero-delay row expect 54/73 for each build, with €568.854676 and €530.674001 of electricity. Logs and full schedules are in the offline archive at `runs/20261119_changeover/formal_retry/`. [Selected results](changeover.json)
