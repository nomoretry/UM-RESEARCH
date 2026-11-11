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
