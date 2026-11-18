# 跨日电量结转会改变什么？ · What changes when energy carries over between days?

[中文](#中文) · [English](#english) · [服务缺口 / Service gaps](service_gap.md) · [第二个港区接口 / Second port connector](../day-ahead/second_port.md) · [首页 / Home](../../README.md)

## 中文

此前的车队模型把每个日历日当作独立情景：每辆车 00:00 从 150 kWh 开始，24:00 必须回到 150 kWh。夜里停在港区的同一段停车因此被午夜切成两段。本页在其他条件全部不变的情况下，比较三种电量边界。不变的条件包括：后六周 30 个日期、73 个完整车日、仓库 45 分钟放行、单车 50 kW、效率 90%、港区一接口或两接口（100 kW）、仓库一接口（75 kW）、2021 年同期 DE-LU 原生小时价，以及每 15 分钟预约接口、换车零耗时。

- **A 逐日固定**：现行规则，每天起止都等于 E0。
- **B 跨日结转**：同一辆车的连续日之间电量直接结转，只在一段连续运行的首尾要求等于 E0。
- **C 逐日自由循环**：每天起止相等但取值自由，天与天之间不连接。它相当于把每天当成一个重复的代表日，不是物理上的连续运行，只单列作对照。

**连续运行怎样认定。** 两天能连起来，当且仅当同一辆车两天都是完整车日，并且前一天最后一段停车或未映射停留的下一条行程，正是后一天的第一条行程。没有记录的日期和被质量规则排除的日期，一律不拼接。按此规则得到 34 段连续运行，最长 5 天。39 处跨午夜衔接中，33 处是港区停车，3 处是仓库停车，3 处停在未映射地点（不能充电，但电量连续）；另有 29 处断开。夜间可充电的时间，仍然是相邻行驶记录之间的停车上界。某天没有完成时，这段运行在该日断开，两侧各自以 E0 起止，这是情景假设。电价方面，B 假定调度者已知整段运行各日的价格，A 只需知道当天价格。

**两段可以手算的小实验**（300 kWh，港区一接口，单车）：

| 车辆与日期 | A 电费 | B 电费 | C 电费 | B 的午夜电量（kWh） |
|---|---:|---:|---:|---|
| 车 5，9 月 27–29 日 | €47.347502 | €47.150054 | €47.347502 | 109.03、130.23 |
| 车 3，10 月 20–22 日 | €8.364301 | €6.125763 | €7.683315 | 192.22、89.74 |

三种规则的购电量相同（分别为 501.864 kWh 和 422.905 kWh），只改变充电时段。A 与现有逐日调度逐日求和的差值在 1e-14 € 量级；能量守恒残差不超过 2.3e-13 kWh。另用一个不调用本模块的单车线性规划独立复算，结果与上表一致。

**300 kWh：完成量不变，电费下降。** 两种设施在 A、B、C 三种规则下都完成 54/73 个车日，名单完全相同，所以此前未完成的 19 个车日不是逐日边界造成的。在同样的 54 个车日上：

| 设施 | A | B | C | B − A |
|---|---:|---:|---:|---:|
| 港区一接口 | €622.44 | €568.85 | €619.37 | −€53.58（−8.6%） |
| 港区两接口 | €590.15 | €530.67 | €580.64 | −€59.48（−10.1%） |

B 规则下，同一车辆连续两天之间的 27 个午夜，电量从 30 kWh 到 300 kWh 不等，中位数约 122 kWh：充电被移到午夜以后价格更低的时段。站点峰值不变（一接口 50/50 kW，两接口 100/50 kW）。第二个港区接口在六周内的电费收益，A 为 €32.29，B 为 €38.18，C 为 €38.73。按原方法等权重复 52 周，B 下的年化上限为 €391.24（2025 年购买力），零新增维护时可承受的投资为 €3,021.03，仍远低于独立 50 kW 充电机每年 €3,724.43。

**900 kWh：先分开容量和初始库存。** 固定 50% SOC 时，初值会从 150 kWh 变成 450 kWh，所以分四档比较。完成量（车日）如下：

| 情景 | 容量 / 储备 / 初值（kWh） | 一接口 A / B / C | 两接口 A / B / C |
|---|---|---|---|
| S300 | 300 / 30 / 150 | 54 / 54 / 54 | 54 / 54 / 54 |
| S900a 只放大容量 | 900 / 30 / 150 | 58 / 64 / 63 | 59 / 64 / 64 |
| S900b 再提高初值 | 900 / 30 / 450 | 63 / 65 / 63 | 64 / 66 / 64 |
| S900c 现行缩放 | 900 / 90 / 450 | 62 / 64 / 63 | 63 / 65 / 64 |

- 在 A 下，900 kWh 带来的新增完成量多半来自更高的初值：从 S900a 到 S900b，一接口由 58 增至 63。
- 在 B 下，只放大容量就能到 64；提高初值只再多 1 个。原因是车辆可以把前一晚多充的电带到第二天，跨日结转替代了“额外的初始库存”。
- S900c 下，B 相对 A 新增 9 月 30 日车 3 和 10 月 11 日车 1。10 月 18 日三车在港区争用接口的瓶颈仍在，第二接口在 A、B 下都多完成 1 个车日（62→63、64→65）。
- S900a 的 B 下，一接口和两接口都是 64，第二接口没有服务收益。所以“900 kWh 时第二接口多完成 1 个车日”这一结论，取决于初值设定。
- 900 kWh 的各组合在一接口和两接口之间完成的车日集合不同，不能直接相减得出接口的电费收益，这里不报。

**哪些结论保持，哪些需要改写。**

- **保持**：300 kWh 下的 19 个未完成车日，原因是车辆本身，不是日界设定。第二港区接口的购电收益负担不起独立整机。站点峰值不变。
- **需要改写**：
  - 原研究的电费（例如一接口 €622.44）是在“每天回到 150 kWh”的条件下得到的。在同样的完成任务上，跨日结转会使六周电费低 8.6%–10.1%。
  - 在 A 下，大电池的服务收益多半是更高初值的作用。在 B 下，只放大容量就能获得大部分收益。
  - 900 kWh 时第二接口带来的服务收益，取决于初值设定。

**适用范围。** 一个承运人，5 辆车反复观测；单个车日的计数不是独立样本。连续运行最长 5 天，周末没有记录，因此不跨周末结转。每段首尾等于 E0 以及“未完成日断开运行”都是情景假设。电池容量变大时行程能耗不变。B 的电价信息假设比 A 更强。共享柜、需量费和换车时间都没有改动，留待分别检验。

### 复算

从研究分支根目录，用已安装[依赖](../../requirements-milp.txt)（含 Windows 上的 `tzdata`）的 Python 3.12 环境运行：

```powershell
$env:PYTHONPATH = 'src'
python -m um_charging.energy_boundary --pilot
python -m um_charging.energy_boundary
```

第一条打印两段小实验的逐日表，`P1 carry_over` 一行总电费为 `47.150054`，`P2 carry_over` 为 `6.125763`。第二条约需数分钟，第二行应为 `S300 one carry_over served=54/73 common=54 common_EUR=568.854676 delta_EUR=-53.584008`。可选 `--output` 只接受独立无 remote 本地 Git 中的新目录，并要求源码已提交、工作树干净。[链、逐车日名单与各组合结果](energy_boundary.json) · [算例入口](../../src/um_charging/energy_boundary.py) · [车队任务来源](DATA.md)

## English

The fleet model so far treated each calendar day separately. Every truck started at 150 kWh at midnight and had to be back at 150 kWh by the next midnight, so one overnight port stay was split in two. This page changes only that boundary. Everything else stays fixed: the six later weeks (30 dates, 73 complete truck-days), the 45-minute warehouse release, 50 kW per truck, 90% efficiency, one or two port connectors (100 kW), one warehouse connector (75 kW), native 2021 DE-LU hourly prices, and 15-minute connector reservations with zero exchange time.

- **A daily_fixed**: the current rule; every day starts and ends at E0.
- **B carry_over**: energy carries across linked midnights; each continuous run starts and ends at E0.
- **C daily_cyclic_free**: each day starts and ends at the same, freely chosen level, and days are not linked. It is a repeated representative day, not continuous operation.

Two days link only when both are complete truck-days of the same vehicle and the overnight stop or unmapped stay ends with that vehicle's first trip of the next day. Missing or excluded days are never bridged. The result is 34 runs of up to five days. Of the 39 links, 33 are port stays, 3 are warehouse stays and 3 are unmapped stays. Overnight charging access is the recorded parking upper bound. An unserved day splits its run, and each remaining part starts and ends at E0; this is a scenario assumption. Under B the dispatcher knows every day's prices within the run.

At 300 kWh, all three rules complete the same 54 of 73 truck-days with both builds. The 19 unserved days therefore do not stem from the daily boundary. On those same 54 days, carry-over cuts the six-week bill from €622.44 to €568.85 with one connector and from €590.15 to €530.67 with two. That is 8.6% and 10.1% respectively, with unchanged site peaks. Across the 27 linked midnights, carried energy ranges from 30 to 300 kWh, with a median near 122 kWh. The second connector's six-week bill gain is €32.29 under A and €38.18 under B. Repeated over 52 weeks, B supports €391.24/year in 2025 purchasing power. That is still far below the €3,724.43/year of an independent 50 kW charger.

At 900 kWh, a fixed 50% start would raise initial energy from 150 to 450 kWh, so the comparison separates capacity from starting inventory. Under A, most of the large-battery service gain comes from the higher start (one connector: 58 with a 150 kWh start, 63 with 450). Under B, capacity alone reaches 64, because trucks carry the previous night's energy forward. With the current scaling (S900c), carry-over adds 30 September (truck 3) and 11 October (truck 1). The 18 October port contention remains, and a second connector adds one truck-day under both A and B. With a 150 kWh start under B it adds none.

Run `python -m um_charging.energy_boundary --pilot` and `python -m um_charging.energy_boundary` from the repository root with `PYTHONPATH=src`. The pilot prints `47.150054` and `6.125763` for the two carry-over runs; the full run's second line reads `S300 one carry_over served=54/73 common=54 common_EUR=568.854676 delta_EUR=-53.584008`. [Runs, truck-day lists and results](energy_boundary.json)
