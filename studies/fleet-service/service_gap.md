# 六周未完成车日由什么决定？ · What limits the unserved truck-days?

[中文](#中文) · [English](#english) · [第二个港区接口 / Second port connector](../day-ahead/second_port.md) · [首页 / Home](../../README.md)

## 中文

[第二个港区接口](../day-ahead/second_port.md)的六周检验中，港区一接口与两接口两种设施（港区 100 kW、仓库一接口 75 kW）都最多完成 73 个车日中的 54 个。本页回答：剩下的 19 个车日，增加接口、扩大接入或提高单车充电功率能否完成？如果换成更大的电池，设施需求会不会改变？

**设施菜单无法补上这 19 个车日。** 每个车日单独检查，不与其他车争用接口或接入，站点功率不设上限。在 45 分钟仓库放行下，只有 10 月 1 日车 3 能靠提高单车功率完成，需要 92.19 kW，超过现行 50 kW。其余 18 个车日即使单车功率无限也完成不了：9 个在 50 kW 下需要更大电池，8 个需要同时提高功率和电池，10 月 21 日车 1 当天没有任何映射到港区或仓库的停车窗口。这 18 个车日中，11 个有单段行程的模拟耗电超过 270 kWh，即 300 kWh 电池扣除 30 kWh 储备后的可用量；最大的一段为 399.31 kWh（10 月 7 日车 1）。其余 7 个车日的单程最高为 93–254 kWh，但两次可插枪停车之间累计的行驶耗电超出电池可用量，或当天的可插枪窗口不足以补回全天耗电。仓库提前到 0 分钟放行，基准可完成 55/73，只多出 10 月 1 日车 3。

| 电池档（kWh） | 菜单上界（车日） | 一接口 | 两接口 | 达到上界的最低新增投资 |
|---:|---:|---:|---:|---|
| 300（原情景） | 54 | 54 | 54 | 0，各站一接口 |
| 450 | 57 | 57 | 57 | 0 |
| 600 | 58 | 58 | 58 | 0 |
| 750 | 62 | 62 | 62 | 0 |
| 900 | 63 | 62 | **63** | **20**，第二个港区接口 |

**只有电池扩到 900 kWh 时，第二个港区接口才多完成一个车日。** 电池档按原情景同比例缩放：储备为 0.1·C，日初与日末电量为 0.5·C，单车 50 kW，效率 90%，仓库按 45 分钟放行。菜单上界由菜单内最大的设施逐日求得，即港区三接口 175 kW、仓库三接口 100 kW。在 300–750 kWh 各档，现有各站一接口的设施已经达到这个上界，所剩车日的失败原因全部是单车行程或期末电量边界，没有一项是接口或接入容量争用。900 kWh 时，10 月 18 日车 1、车 3 都要在凌晨出车前于港区预先补电，与车 5 在港区重叠。一个接口最多完成 2 辆，两个接口在 100 kW 下完成 3 辆。按同一合成周期菜单，这是唯一的最低投资方案，新增 20 个合成单位。这一结果是对六周已知任务的回顾性评估，不是事前设计。600 kWh 与在售长途电动重卡的装机容量同一量级，例如 eActros 600 为三组 207 kWh 电池包。[车型参数报道](https://www.wardsauto.com/news/archive-wards-mercedes-unveils-heavy-duty-bev-truck/797497/)

**由此调整的判断。** 在原 300 kWh 情景下，第二个港区接口的价值只来自已完成任务上的购电差额，原[投资门槛](../day-ahead/second_port.md)没有遗漏它的服务价值。设施投资不能提高这六周的完成量。若要提高完成量，先要改变车辆情景：电池容量、日初电量，或未映射停车点的补能。另外，每天从午夜独立开始、日初为半电的设定，使 900 kWh 档的早间港区补电成为必需，10 月 18 日的接口收益依赖这一时序假设。

### 证明与复核

- 每个车日用闭区间电量递推求单车功率阈值 P* 和电池阈值 C*，二分精度 1e-6，夹逼宽度最大 9.54e-7。每个有限阈值都用车队 MILP 双向证明：上方 +0.001 求得可行排程并通过独立回放审计，下方 −0.001 不可行。两种放行共 111 个功率阈值和 129 个 50 kW 下的电池阈值，全部通过。复核时另用原有的 `failure_reasons` 重算了全部 146 行逐车日记录，结果无一处不一致。
- 五档电池共 30 个日期 × 54 种设施，求解 1,102 次，HiGHS 报告的 gap 均为 0。默认规格下 dispatch、max_service、即充与审计的结果与原代码逐位相同；`connector_value` 仍输出 10.61522 与 6.80206。
- 正式运行源码 `2064bea`，运行时工作树干净。逐次求解与审计保存在离线记录库的 `20261118_service_gap`，319 项测试通过。

### 复算

从研究分支根目录，用已安装 [依赖](../../requirements-milp.txt) 的 Python 3.12 环境运行。Windows 上还需安装 `tzdata`，读取 Europe/Berlin 时区。

```powershell
$env:PYTHONPATH = 'src'
python -m um_charging.service_gap
```

第一行应包含 `served_at_baseline=54 truck_power_recoverable=1 ... battery_recoverable=9 battery_and_power_recoverable=8 no_um_charging_window=1`。最后一行应为 `C=900 kWh goals=63 one=62 two=63 six_week_min_period_investment=20`。可选 `--output` 只接受独立无 remote 本地 Git 中的新目录，且要求源码已提交、工作树干净。[逐车日阈值与各档结果](service_gap.json) · [算例入口](../../src/um_charging/service_gap.py) · [车队调度与审计](../../src/um_charging/fleet_service.py) · [任务来源](DATA.md)

## English

In the [second port connector](../day-ahead/second_port.md) study, one and two port connectors both served at most 54 of 73 truck-days in six later weeks. The port has 100 kW, and the warehouse has one 75 kW connector. This page tests whether more connectors, more grid capacity or faster truck charging could serve the remaining 19. It also checks whether a larger battery changes the facility requirement.

**The facility menu cannot recover them.** Each truck-day was checked alone, with no connector or site-power contention. With the 45-minute warehouse release, only truck 3 on 1 October becomes feasible through faster charging, at 92.19 kW instead of 50 kW. The other 18 stay infeasible even with unlimited charging power. Nine need a larger battery at 50 kW, eight need a larger battery and more power, and truck 1 on 21 October has no mapped port or warehouse stop. Eleven of the 18 have a single leg above 270 kWh, the 300 kWh battery's usable energy above the 30 kWh reserve. The largest uses 399.31 kWh (truck 1, 7 October). In the other seven, legs between charging stops add up to more than the usable battery energy, or the eligible stops cannot restore the day's driving energy. With immediate warehouse release, baseline service rises from 54 to 55/73, adding only truck 3 on 1 October.

Battery tiers scale the original ratios: reserve 0.1·C, start and end energy 0.5·C, 50 kW, 90% efficiency, 45-minute warehouse release. From 300 to 750 kWh, the existing one-connector build reaches the menu maximum of 54, 57, 58 and 62 truck-days. Every remaining failure is a single-truck leg or end-of-day energy limit, never contention for connectors or grid capacity. At 900 kWh, the menu maximum is 63. Trucks 1 and 3 must recharge at the port before their early departures on 18 October, while truck 5 is also there. One connector serves two of the three trucks; two connectors at 100 kW serve all three. The unique cheapest build adds a second port connector for 20 synthetic cycle units. This is a retrospective evaluation of six known weeks, not a design made in advance. The 600 kWh tier is comparable to the installed capacity of current long-haul electric trucks, such as the eActros 600's three 207 kWh packs. [Vehicle report](https://www.wardsauto.com/news/archive-wards-mercedes-unveils-heavy-duty-bev-truck/797497/)

**What changes.** With the original 300 kWh trucks, the second connector's value comes only from bills on completed duties. The existing cost hurdle therefore omits no service value. More of these six weeks can be served only by changing the vehicle scenario: battery size, starting energy, or charging at unmapped stops. Each day starts independently at midnight with half-full batteries, which forces the morning port charging behind the 900 kWh connector gain.

Every finite threshold was confirmed by a fleet MILP feasible 0.001 above it, with an independent replay audit, and infeasible 0.001 below. The 1,102 solves report zero gap. Default-parameter results match the previous code exactly. The formal run used clean commit `2064bea`; complete solve records are in the offline archive. Run `python -m um_charging.service_gap` from the repository root with `PYTHONPATH=src` and `tzdata` installed on Windows. Its last line should read `C=900 kWh goals=63 one=62 two=63 six_week_min_period_investment=20`. [Thresholds and tier results](service_gap.json)
