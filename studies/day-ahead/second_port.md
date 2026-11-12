# 第二个港区接口值多少钱？ · Value of a second port connector

[中文](#中文) · [English](#english) · [首页 / Home](../../README.md)

## 中文

为了单独量出接口的价值，港区从一台 50 kW 接口改为两台可同时各供 50 kW 的接口，港区接入始终是 100 kW，仓库保持一台接口、75 kW 接入。车辆最多取 50 kW，效率 90%，电池容量 300 kWh、储备 30 kWh，每个车日从 150 kWh 开始并回到 150 kWh。仓库按到站后 45 分钟放行，港区到站即可插枪。每 15 分钟预约接口，按实际可用分钟供电，槽边界换车耗时假定为零。六周内按日重新排程，车辆初末电量按日闭合。

**原三日先只换价格。** 2021-09-21 至 23 的 8 个车日、45 趟任务在四种安排中全部完成。同期价格按实际交割小时匹配；旧回放在 2025-01-06 起的交付周选相同当地星期、钟点，即 1 月 7–9 日。日前策略知道当日价格和已公布任务。两种调度支付相同的逐时批发价。表中金额为对应交付年的欧元。

| 三日价格 | 一接口即充 | 一接口日前 | 一接口调度收益 | 双接口即充 | 双接口日前 | 双接口调度收益 | 日前对日前的接口收益 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 同期 | 146.80 | 115.58 | 31.22 | 134.92 | 104.97 | 29.95 | **10.62** |
| 2025 回放 | 99.58 | 88.57 | 11.01 | 89.61 | 81.76 | 7.84 | **6.80** |

**后六周检验。** 使用同一承运人、同一原始五车池，按时间预先选后续六个完整自然周，包括单车日期。与原设计及留出集没有重复行程。42 天中 30 天有可建模任务，4 天只有未通过质量筛选的记录，8 天无记录；共 73 个完整车日、355 趟。每一天先检查全车队，不能全做时分别证明最多能完成的整车日数，再用单接口可完成的最大集合进行同任务结算；同数量时按车辆 ID 选择，选择过程与电价无关。两套设施各有 12/30 个日期完成全部任务，均最多完成 54/73 个车日。可结算的是 28 天、54 个相同车日、281 趟；其余服务仍在结果中，未给未完成任务设定货币价值。

| 周一 | 完成车日 / 可建模车日 | 同期硬件收益（2021 €） | 1 月回放硬件收益（2025 €） |
|---|---:|---:|---:|
| 09-27 | 9/12 | 5.23 | 5.57 |
| 10-04 | 10/13 | 8.06 | 4.43 |
| 10-11 | 9/12 | 2.82 | 1.17 |
| 10-18 | 9/14 | 4.59 | 2.06 |
| 10-25 | 12/16 | 9.74 | 6.72 |
| 11-01 | 5/6 | 1.84 | 1.64 |
| **合计（按未舍入数）** | **54/73** | **32.29** | **21.58** |

同期一接口、双接口按价调度分别支出 €622.44、€590.15。返回调度跨日期的港区最高功率分别为 50、100 kW，仓库均为 50 kW；这些峰值来自最低电费调度。即充与按价调度的比较使用各自能完成相同任务的日期：单接口即充在 9 月 29 日未完成，因此其成对调度收益 €92.53 的分母是 27 天；双接口 €124.79 的分母是 28 天。硬件收益比较的两侧均按价调度，使用相同的 28 天。

**建设门槛。** 六周同期样本平均节省 €5.38/周。假定按相同任务和价差等权重复 52 周，每年最多能承担 €279.82（2021 欧元）；按德国全年 CPI 折为 €330.85（2025 购买力）。相同算法用于 1 月回放得到 €187.06/年（2025 欧元）。这是对已覆盖服务的重复情景。实际年业务量、未完成服务的价值、需求电费和工商业购电合同均未观测。若合同每千瓦时同价，相同购电量产生相同电能费。

Frank、Oebel 与 Gnann 的德国车队研究给出一台独立 50 kW DC 充电机 €20,882，规划安装调试加 30%，合计 €27,146.60。采用 10 年、5% 折现，按设备价计 1% 年维护费，年成本 €3,724.43。两种价格下，样本购电收益都不能负担这一整机。若复用既有柜，必须核实整流容量、并充能力、土建和授权费用；同柜两枪如果只能共享 50 kW，适用的是另一套物理约束。同期零新增维护假设下最高一次性已安装投资为 **€2,554.72**（2025 购买力）。有年度增量开支时，先从 €330.85 中扣除，再除以资本回收系数 0.129505。 [成本参数、CPI 与原始来源](connector_cost.json)

### 复算

从研究分支根目录、使用已装好 [依赖](../../requirements-milp.txt) 的 Python 3.12 环境运行：

```powershell
$env:PYTHONPATH = 'src'
python -m um_charging.connector_value
python -m um_charging.connector_value --full
```

第一条输出两行三日收益；第二条增加两个价格情景的六周门槛。可选 `--output` 接受既有独立无远端记录 Git 中的全新子目录，保存逐车排程与复核。公开结果中的 `days` 逐日列出需求、最大覆盖、失败原因、相同车日的欧元费用和两站峰值，`threshold` 给出年化口径。 [逐日结果](second_port.json) · [算例入口](../../src/um_charging/connector_value.py) · [独立结算](../../src/um_charging/fleet_market.py) · [设施调度与物理检查](../../src/um_charging/fleet_service.py)

### 输入

- **车队。** TUMFTM / DT-CARGO 的行驶时间及 BETOS 模拟能耗，原始德国车队身份保留。相邻轨迹间隔仅是停车上界，基地与工业区域映射为 UM 港区与仓库。新增日期的两个跨轨迹空间断点涉及三个映射停车区间；实际到站、持续在场、作业放行、接枪和开始供电没有独立观测。[谱系、排除与源行核查](../fleet-service/DATA.md) · [原任务](../fleet-service/duties.json) · [六周任务](../fleet-service/operating_weeks.json)
- **价格。** Bundesnetzagentur | SMARD.de，DE-LU 日前批发价，€/MWh，Europe/Berlin。原三日及新增六周共 1,081 个原生小时，无缺值，含 7 个负价，10 月 31 日两个 02:00 以各自 UTC 偏移保存；无合格任务的换时日不进入调度。1 月回放保留原 168 个小时。对每个充电功率段，以与交割小时的重叠时长核算电量，再以每 MWh 报价结算。此次两个时期均采用原生小时价。[同期价格与逐周源哈希](native_2021_source.json) · [同期输入](native_2021_prices.csv) · [一月输入](fleet_week_prices.csv) · [SMARD 下载](https://www.smard.de/en/downloadcenter/download-market-data/) · [数据使用条款](https://www.smard.de/en/datennutzung)
- **设施。** 100/75 kW 是 UM 案例接入条件；资产成本单独取自文献，并未引入配电网潮流、当地接入报价或承运人零售电价。[设施菜单](../../configs/port_warehouse_investment.json)

## English

The trial adds one simultaneous 50 kW port outlet. The port grid limit stays at 100 kW, and the warehouse keeps one outlet and a 75 kW connection. Each truck returns to its initial 150 kWh every day, with a 300 kWh battery and 30 kWh reserve. Warehouse eligibility starts 45 minutes after arrival. Reservations last 15 minutes with zero exchange time and exact eligible minutes inside each slot.

For the same eight truck-days on 21–23 September, the two builds both completed 45 trips. Contemporaneous DE/LU prices put the optimized bills at €115.58 and €104.97. On January 2025 weekday-matched prices those bills were €88.57 and €81.76. Immediate versus optimized dispatch and one versus two connectors are separate comparisons in the first table above.

The next six non-overlapping calendar weeks contained 73 eligible truck-days. Twelve of 30 modeled dates were feasible for the entire fleet under either build. Both builds served at most 54 truck-days. On the same 54 truck-days (281 trips), two connectors saved €32.29 under contemporaneous prices and €21.58 on the January replay. One-connector immediate charging failed on 29 September, so its scheduling comparison covers 27 dates. The optimized hardware comparison retains all 28 dates with common service. Records, simulated energy, assumed access, missing observations and service failures remain separately identifiable in the inputs and results.

Repeating the six-week mix across 52 weeks supports €279.82/year in 2021 euros or €330.85 in 2025 purchasing power. Even with zero extra maintenance that supports €2,554.72 installed capital at 5% over ten years. A published standalone 50 kW unit costs €3,724.43/year under the specified assumptions. An outlet added to an existing cabinet requires its own quote and confirmation of simultaneous 2 × 50 kW delivery. Retail contract exposure, demand charges and the value of unmet service are unknown.

Run the two PowerShell commands above from the repository root. Quick replay prints `10.61522` and `6.80206`; `--full` includes weekly differences and the cost ceilings. TUMFTM supplies the source trip and BETOS energy data; the mapping and release rules are UM scenarios. **Bundesnetzagentur | SMARD.de** supplies the historical wholesale series. [Fleet inputs and provenance](../fleet-service/DATA.md) · [Native DE/LU delivery intervals](native_2021_prices.csv) · [Cost basis](connector_cost.json) · [Results by date, week and price scenario](second_port.json)
