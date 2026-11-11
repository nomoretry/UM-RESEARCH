# 重卡仓库补能与日前购电 · January 2025

同一组港区—仓库运输任务在 2025 年 1 月的 31 条德国/卢森堡日前电价曲线上分别结算。每次从当地 08:00 开始，12:00 结束。港区 3 个接口、150 kW，仓库 1 个接口、75 kW。车辆、插枪资格和行驶耗能沿用合成算例。以下金额是 31 个四小时循环的批发购电费用。

| 策略 / Dispatch | 31 次购电费用 / EUR | 港区峰值 / kW |
|---|---:|---:|
| 到站即充 / First eligible, first served | 485.02222 | 150.00 |
| 削峰 / Minimum peak | 485.02222 | 111.11 |
| 日前最低电费，再削峰 / Least cost, then minimum peak | 469.14533 | 133.33 on 30 days; 111.11 on 25 Jan |

全队每次取电 133.333 kWh。仓库 09:00–10:00 只有一辆车能补电，最多购入 22.222 kWh，其余电量在 11:00–12:00 返港时补足。1 月 25 日两个小时的单价分别为 87.31 和 88.15 EUR/MWh。在仓库补足这 22.222 kWh，比全部回港再充少付 0.01867 欧元；最低可达港区峰值也从 133.33 降至 111.11 kW。另 30 天仓库时段更贵，最低电费方案将电量留到港区，峰值下限为 133.33 kW。最低电费与最低可行峰值之间的最大单日差额出现在 1 月 20 日，约 2.316 欧元。

Each day reuses the fixed service and connection windows in [case.json](case.json). The four input hourly prices settle all policies at 15-minute dispatch resolution. Only the warehouse and return-to-port hours permit charging. Relative to immediate charging, the cost-first schedule with a peak tie-breaker saves EUR 15.87689 over these 31 services. The two objectives minimize the worst individual site peak and the wholesale purchase bill. For the tie-break, solve for minimum cost, constrain spend to that optimum, then minimize the highest site peak. In this case the port determines the maximum. The reported warehouse peak is the value in that dispatch; a price-only solution can have multiple optimal schedules. All schedules complete the same six trips with the same terminal SOC. The result concerns these service hours, fleet and price sample. It excludes retail charges, demand tariffs, equipment investment and balancing-market revenues.

**Reproduction.** From the repository root set the Python import path to `src`, then run:

```powershell
$env:PYTHONPATH = 'src'
python -m um_charging.day_ahead_month
python -m unittest discover -s tests -p test_day_ahead_month.py
```

The first command emits the [daily dispatch comparison](january_2025_results.csv). With `--output PATH` it also saves the schedules and independent feasibility replays in a fresh directory in an existing local-only Git repository. For every date the tests check the energy bill and port-peak bound against an independent calculation using the 20 kWh first-leg deficit and 90% charging efficiency. A negative flat-price fixture checks tie-breaking.

[124 hourly prices](january_2025_prices.csv) · [Original SMARD URLs, file hashes and cross-check](january_2025_source.json). Source: Bundesnetzagentur | SMARD.de, DE-LU 4169. The CSV selects 08:00–12:00 CET. [SMARD’s data-use page](https://www.smard.de/en/datennutzung) gives the market-data attribution terms and notes its ongoing review of wholesale-price licensing. The Energy-Charts API republishes SMARD values; equality at all 124 timestamps checks the extraction against that distribution.

## Fixed builds at 45 minutes

三辆车每天执行相同的六段行驶，期初、期末电量均为每车 100 kWh。V1、V2 只能在 09:45–10:00 于仓库插枪，V3 可用 09:00–10:00。三车均可在 11:00–12:00 返港充电。停车过程、15 分钟无耗时换枪和 100/75 kW 接入容量在两种设施间一致。单程能耗沿用 19.3 t、辅助负荷 5 或 7 kW 的已存情景，后者按未舍入的 20.636628905957647 kWh 计算。每天先最小化购电费，再在同价解中最小化两站较高的峰值。仓库列报告该调度的站点峰值。[能耗来源](../truck-energy/metrics.json) · [31 天逐配置结果](january_2025_facilities.csv)

| 单程 kWh | 港／仓接口 | 投资（合成周期单位） | 可行日 | 31 次购电费（EUR） | 仓价较高 30 天的港／仓峰值 kW | 1 月 25 日的港／仓峰值 kW |
|---:|:---:|---:|---:|---:|:---:|:---:|
| 20.00 | 3/1 | 40 | 31 | 492.95017 | 100.00 / 50.00 | 98.61 / 50.00 |
| 20.00 | 2/2 | 50 | 31 | 492.94492 | 100.00 / 55.56 | 92.36 / 75.00 |
| 20.64 | 3/1 | 40 | 0 | — | — | — |
| 20.64 | 2/2 | 50 | 31 | 510.91080 | 100.00 / 66.87 | 95.94 / 75.00 |

20.00 kWh 时，仓价较高的 30 天，两种设施均把港区一小时的 100 kWh 用足，购电费相同。1 月 25 日，仓价比港价低 0.84 €/MWh，第二个仓库接口允许再转移 6.25 kWh，差额为 6.25 × 0.84 / 1000 = 0.00525 欧元。欧元电费与合成投资分别核算，缺少统一成本口径，无法据此计算投资回收期。

当单程能耗为 E，三车需购电 6E/0.9。仓库一个接口时，V3 最多补 E/0.9 kWh，另外两车在最后一刻钟合计最多补 12.5 kWh。港区最少承担 5E/0.9 − 12.5 kWh。E 超过 20.25 kWh，这一下界就超过返港时段可供的 100 kWh。高能耗输入下短缺 2.14794 kWh，换电价无法改变该物理约束。每组设施先检查一次与价格无关的物理可行性，不可行组的 31 天均保留空账单。

For the higher-energy 2/2 build on 25 January, average port energy would suggest 95.89794 kW. Each delayed truck needs at least three port connector-slots and V3 needs two. In the two slots shared with V3 the delayed trucks can take at most 25 kWh together. In the other half-hour they must take at least 4E/0.9 − 18.75 − 25 kWh. The resulting 95.93670 kW lower bound is attained by the dispatch. Both the warehouse connection limit and truck-level connector occupancy matter.

Run from the repository root in the existing MILP environment. The CSV contains 124 date/build/energy rows, including 31 price-independent infeasibilities. All 186 optimal schedules from the two dispatch stages were independently checked for energy, occupancy, power and settlement. Both stages had zero reported gap throughout. Source commit `6e00777`.

```powershell
$env:PYTHONPATH = 'src'
python -m um_charging.facility_month
```
