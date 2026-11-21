# 固定充电设施的六周留出检验 · Six-week holdout of fixed charging facilities

[运输样本 / Sample](DATA.md#six-holdout-weeks-for-the-fixed-m8-facilities) · [留出结果 / Holdout data](holdout_test.json) · [规划期 / M8 study](site_sizing.md)

2021-11-08 至 2021-12-19，基准登记 **52/63** 个完整车日。登记任务的网侧年电量为 **59,335.60 kWh/年**，M8 为 **58,387.79 kWh/年**。两者按各自六周任务重复至 52 周，反映运输任务量的差别。

Over 8 November–19 December 2021 the baseline registered **52/63** complete vehicle-days. Registered grid energy is **59,335.60 kWh/year** in the holdout and **58,387.79 kWh/year** in M8. Each annualization repeats its own six-week transport workload.

**两套港区单站方案都少完成 11 月 26 日的 1 号车。** 两者各完成 51 个登记车日。双站基准完成全部 52 个，因此是三套固定设施中唯一可列入 12 个口径年费比较的设施。在原港区保留 20 或 40 kW 的条件下，仓库增加 15 kW 均恢复六周全部服务。留出期比 M8 少登记 2 个车日，但按 52 周重复后，所需网侧电量多 947.81 kWh（1.62%）。

**Both port-only facilities missed vehicle 1 on 26 November.** Each served 51 registered vehicle-days. Only the two-site baseline served all 52 and qualified for annual billing under all twelve cases. Adding 15 kW at the warehouse restored the full six-week service with either original port rating. The holdout registered two fewer vehicle-days than M8 and required 947.81 more grid kWh per year (1.62%).

最初的留出检验比较三套事先固定的设施。设施固定后按周全信息优化，调度时已知一周全部任务和原生 DE-LU 日前小时价格。留出期没有重新选型，排名即使保持，也可能有更便宜的其他设计。

The original holdout comparison covers three prespecified facilities. With facilities fixed, each weekly schedule uses all tasks and native DE-LU day-ahead hourly prices for that week. Designs were not reselected in the holdout, so even an unchanged ranking allows for a cheaper untested design.

仓库安装 20 kW 充电机后，两套有价修复均保留全部 52 个登记车日。按主运行规则，20/20 kW 在 7 个口径年费最低，40/20 kW 在另 5 个口径最低，双站基准均为第三。Netze BW 官方网费下，40/20 kW 新建和既有接入的回放年费分别为 €19,708.03 和 €18,906.61。

Both priced warehouse repairs served the full register of 52 vehicle-days. Under the primary operating rule, the 20/20 kW repair had the lowest annual bill in seven cases and the 40/20 kW repair in the other five. The baseline ranked third throughout. Under the official Netze BW tariff, the 40/20 kW repair's replayed bills were €19,708.03 with new connections and €18,906.61 with existing access.

## 同服务年费与排名 · Annual cost for the same service

每格为 2025 年欧元/年，区间右端是回放账单，端点显示到分。依据未取整的区间判定名次。数字 20、40 表示港区单站额定 kW，B 表示基准。排序数字相同或范围重合表示名次仍未分开。

Amounts are annual 2025 euros, rounded to cents. The upper endpoint is the replayed bill. Ranks use unrounded intervals. The port-only facilities are labelled 20 and 40 kW. B is the baseline. Overlapping rank ranges leave their order open.

| 网费 / Tariff | 接入 / Connection | 20 kW | 40 kW | B | 名次 / Ranks (20, 40, B) | M8 最低 / M8 winner | M8 方案的服务与计费 / M8 service and bill |
|---|---|---:|---:|---:|---|---|---|
| 无 / None | 新建 / New | 缺口 / gap | 缺口 / gap | 19,637.40–19,637.72 | —, —, 1 | 40 | 少完成登记服务，未出账单 / Service shortfall, no bill |
| 无 / None | 既有 / Existing | 缺口 / gap | 缺口 / gap | 17,299.92–17,300.23 | —, —, 1 | 40 | 少完成登记服务，未出账单 / Service shortfall, no bill |
| Frank 表 / Table 4 | 新建 / New | 缺口 / gap | 缺口 / gap | 27,422.66–27,422.97 | —, —, 1 | 20 | 少完成登记服务，未出账单 / Service shortfall, no bill |
| Frank 表 / Table 4 | 既有 / Existing | 缺口 / gap | 缺口 / gap | 25,085.17–25,085.48 | —, —, 1 | 20 | 少完成登记服务，未出账单 / Service shortfall, no bill |
| Netze BW | 新建 / New | 缺口 / gap | 缺口 / gap | 27,277.15–27,277.46 | —, —, 1 | 20 | 少完成登记服务，未出账单 / Service shortfall, no bill |
| Netze BW | 既有 / Existing | 缺口 / gap | 缺口 / gap | 24,939.66–24,939.98 | —, —, 1 | 40 | 少完成登记服务，未出账单 / Service shortfall, no bill |
| 0 | 新建 / New | 缺口 / gap | 缺口 / gap | 25,093.99–25,094.30 | —, —, 1 | 20 | 少完成登记服务，未出账单 / Service shortfall, no bill |
| 0 | 既有 / Existing | 缺口 / gap | 缺口 / gap | 22,756.50–22,756.82 | —, —, 1 | 20 | 少完成登记服务，未出账单 / Service shortfall, no bill |
| 22.79 | 新建 / New | 缺口 / gap | 缺口 / gap | 27,422.66–27,422.97 | —, —, 1 | 20 | 少完成登记服务，未出账单 / Service shortfall, no bill |
| 22.79 | 既有 / Existing | 缺口 / gap | 缺口 / gap | 25,085.17–25,085.48 | —, —, 1 | 20 | 少完成登记服务，未出账单 / Service shortfall, no bill |
| 208.38 | 新建 / New | 缺口 / gap | 缺口 / gap | 46,386.13–46,386.44 | —, —, 1 | 20 | 少完成登记服务，未出账单 / Service shortfall, no bill |
| 208.38 | 既有 / Existing | 缺口 / gap | 缺口 / gap | 44,048.64–44,048.96 | —, —, 1 | 20 | 少完成登记服务，未出账单 / Service shortfall, no bill |

B 完成了全部 52 个登记车日，是原三套设施中唯一取得同服务账单的设施。建设选择还取决于修复设施完成这些任务的成本。[修复方案的同服务年费 / Bills after repair](#repair-bills)

B is the only one of the three with a bill for the full register. Its first place alone provides no basis for a new build recommendation.

无网费沿用基准的 50/50 kW 运行点。其余五种网费原定的 50/0 或 20/0 kW 限峰都在 11 月 22 日当周被证实无法保留服务，因此按预登记对整个六周采用 50/50 kW 额定后备。表中三个固定需量价的单位为 €/kW·年。

The no-network-charge case kept its frozen 50/50 kW setting. The other five tariffs used a frozen 50/0 or 20/0 kW cap. Both failed the registered service in the week of 22 November, so the prespecified 50/50 kW rated fallback covers all six weeks for those tariffs. Fixed demand prices are in €/kW per year.

六周按 52/6 年化。两站分别按六周最大实测刻钟功率选档。购电区间固定回放排程的电表读数。基准两站各一台 50 kW 机，接入 100/75 kW。新建按 175 kW 计费，既有的增量接入费用为零。

Each meter uses its six-week maximum quarter-hour demand. The six weeks repeat 52/6 times per year. Purchase bounds hold metered energy and peaks at their replayed values. The baseline uses two 50 kW chargers and 100/75 kW connections. New-build connection costs cover 175 kW, with zero incremental capacity under existing access. Wholesale energy (2021), network tariffs (2024) and new connection charges (2026) use the M8 CPI conversion to 2025 euros. [分项账单及价格口径 / Bill components and price basis](holdout_test.json)

<a id="repair-bills"></a>

## 修复方案的同服务年费 · Annual bills after repair

两套最低有报价的修复都在仓库安装 20 kW 充电机，保留原港区额定功率。15 kW 硬件缺少报价。两列服务限峰参照使用同一台已计价的 20 kW 仓库机，仅把仓库刻钟平均电表限到 15 kW。15 kW 来自留出期服务检验，参照只作比较。主排名包括 B 及两个按冻结策略运行的修复。

Each repair keeps its original port rating and installs the smallest priced warehouse charger that restores service, 20 kW. The 15 kW hardware has no quoted price. The two reference bills keep the installed 20 kW unit and restrict the warehouse quarter-hour meter to 15 kW. This cap comes from holdout service evidence. The primary ranking includes B and the two repairs under their frozen-policy rule.

| 网费 / Tariff | 接入 / Access | B | 20/20 主 / Primary | 40/20 主 / Primary | 20/15 服务限峰参照 / Reference | 40/15 服务限峰参照 / Reference | 名次 / Ranks (B, 20/20, 40/20) |
|---|---|---:|---:|---:|---:|---:|---|
| 无 / None | 新建 / New | 19,637.40–19,637.72 | 14,287.12–14,287.27 (冻结 / frozen) | 12,999.55–12,999.75 (冻结 / frozen) | 14,336.08–14,336.33 | 13,028.15–13,028.36 | 3, 2, 1 |
| 无 / None | 既有 / Existing | 17,299.92–17,300.23 | 13,752.84–13,752.99 (冻结 / frozen) | 12,198.12–12,198.33 (冻结 / frozen) | 13,801.80–13,802.04 | 12,226.72–12,226.93 | 3, 2, 1 |
| Frank 表 / Table 4 | 新建 / New | 27,422.66–27,422.97 | 19,827.01–19,827.16 (后备 / fallback) | 19,853.34–19,853.54 (后备 / fallback) | 19,734.16–19,734.40 | 19,765.50–19,765.71 | 3, 1, 2 |
| Frank 表 / Table 4 | 既有 / Existing | 25,085.17–25,085.48 | 19,292.73–19,292.88 (后备 / fallback) | 19,051.91–19,052.12 (后备 / fallback) | 19,199.87–19,200.12 | 18,964.08–18,964.29 | 3, 2, 1 |
| Netze BW | 新建 / New | 27,277.15–27,277.46 | 20,012.16–20,012.31 (后备 / fallback) | 19,707.83–19,708.03 (后备 / fallback) | 19,921.12–19,921.36 | 19,619.99–19,620.20 | 3, 2, 1 |
| Netze BW | 既有 / Existing | 24,939.66–24,939.98 | 19,477.88–19,478.03 (后备 / fallback) | 18,906.40–18,906.61 (后备 / fallback) | 19,386.83–19,387.08 | 18,818.57–18,818.78 | 3, 2, 1 |
| 0 | 新建 / New | 25,093.99–25,094.30 | 15,102.85–15,103.00 (后备 / fallback) | 18,456.14–18,456.34 (后备 / fallback) | 15,126.43–15,126.67 | 18,484.73–18,484.95 | 3, 1, 2 |
| 0 | 既有 / Existing | 22,756.50–22,756.82 | 14,568.56–14,568.71 (后备 / fallback) | 17,654.71–17,654.92 (后备 / fallback) | 14,592.15–14,592.39 | 17,683.31–17,683.52 | 3, 1, 2 |
| 22.79 | 新建 / New | 27,422.66–27,422.97 | 16,034.31–16,034.46 (后备 / fallback) | 19,853.34–19,853.54 (后备 / fallback) | 15,941.46–15,941.71 | 19,765.50–19,765.71 | 3, 1, 2 |
| 22.79 | 既有 / Existing | 25,085.17–25,085.48 | 15,500.03–15,500.18 (后备 / fallback) | 19,051.91–19,052.12 (后备 / fallback) | 15,407.18–15,407.42 | 18,964.08–18,964.29 | 3, 1, 2 |
| 208.38 | 新建 / New | 46,386.13–46,386.44 | 23,619.70–23,619.85 (后备 / fallback) | 31,231.42–31,231.63 (后备 / fallback) | 22,578.68–22,578.92 | 30,195.41–30,195.62 | 3, 1, 2 |
| 208.38 | 既有 / Existing | 44,048.64–44,048.96 | 23,085.42–23,085.57 (后备 / fallback) | 30,430.00–30,430.20 (后备 / fallback) | 22,044.39–22,044.64 | 29,393.99–29,394.20 | 3, 1, 2 |

金额为 2025 年欧元/年。无网费的冻结点等于各自额定点。其余网费的冻结点将仓库限到零，只剩港区单站可用。即使港区单枪的额定功率和刻钟上限都放宽到 50 kW，11 月 22 日当周仍无法完成登记服务。原先更低的港区额定功率或限峰也无法保留该周服务，因此这五种网费均对整个六周采用额定后备。

Amounts are annual 2025 euros. With no network charge each frozen point equals its rated point. Every other frozen policy closes the warehouse meter, leaving only the port station. The archived 50/0 kW point with one port plug already failed in the week of 22 November. Its feasible set contains every smaller port rating and meter cap tested here. Each failed policy therefore uses rated fallback for all six weeks. [费用分项与区间 / Components and bounds](holdout_test.json)

额定运行点逐周固定原登记集合 R。原样本中登记外 11 个车日即使单车独占、功率不限也无法完成，故一旦证明整周可完成 R，逐日优先规则选出的也恰好是 R。

Each rated point is checked against the fixed weekly register R. The eleven duties outside the register were independently infeasible even with unlimited charging power, so a proved weekly extension covering R also yields exactly R under daily selection.

| 额定点 / Rated kW | 逐周保留 R / Weekly service status |
|---|---|
| p1-20-w20 | 11-08 ✓, 11-15 ✓, 11-22 ✓, 11-29 ✓, 12-06 ✓, 12-13 ✓ |
| p1-40-w20 | 11-08 ✓, 11-15 ✓, 11-22 ✓, 11-29 ✓, 12-06 ✓, 12-13 ✓ |

✓ 已证明可服务 / proved feasible · × 已证明不可行 / infeasible · ? 未判定 / open.

这些账单衡量 M8 单站方案加上最低有价修复的费用。留出期未重新选择设施，更便宜的其他设计仍有可能。

These bills price the smallest quoted repairs to the M8 facilities. The holdout did not repeat facility selection, so other designs could cost less.

## 逐日运输服务 · Daily registered service

每格列出车辆数值 ID。∅ 表示空集，? 表示未判定。 / Cells list numeric vehicle IDs. ∅ is an empty set and ? is unresolved.

| 日期 / Date | 完整 / Eligible | 登记 / Baseline register | 20 kW | 40 kW |
|---|---|---|---|---|
| 2021-11-08 | 1, 5 | 5 | 5 | 5 |
| 2021-11-09 | ∅ | ∅ | ∅ | ∅ |
| 2021-11-10 | 3, 4, 5 | 3, 4, 5 | 3, 4, 5 | 3, 4, 5 |
| 2021-11-11 | 3, 5 | 3, 5 | 3, 5 | 3, 5 |
| 2021-11-12 | 3, 5 | 5 | 5 | 5 |
| 2021-11-13 | ∅ | ∅ | ∅ | ∅ |
| 2021-11-14 | ∅ | ∅ | ∅ | ∅ |
| 2021-11-15 | 1, 3, 4, 5 | 3, 5 | 3, 5 | 3, 5 |
| 2021-11-16 | 3, 4, 5 | 3, 4, 5 | 3, 4, 5 | 3, 4, 5 |
| 2021-11-17 | 1, 3, 4, 5 | 3, 4, 5 | 3, 4, 5 | 3, 4, 5 |
| 2021-11-18 | 4, 5 | 4, 5 | 4, 5 | 4, 5 |
| 2021-11-19 | 1, 4, 5 | 1, 4, 5 | 1, 4, 5 | 1, 4, 5 |
| 2021-11-20 | ∅ | ∅ | ∅ | ∅ |
| 2021-11-21 | ∅ | ∅ | ∅ | ∅ |
| 2021-11-22 | 1, 3, 5 | 3, 5 | 3, 5 | 3, 5 |
| 2021-11-23 | 1, 3 | 3 | 3 | 3 |
| 2021-11-24 | 1, 3, 4 | ∅ | ∅ | ∅ |
| 2021-11-25 | 1, 3, 4 | 3, 4 | 3, 4 | 3, 4 |
| 2021-11-26 | 1, 3 | 1, 3 | 3 | 3 |
| 2021-11-27 | ∅ | ∅ | ∅ | ∅ |
| 2021-11-28 | ∅ | ∅ | ∅ | ∅ |
| 2021-11-29 | 1, 4 | 1, 4 | 1, 4 | 1, 4 |
| 2021-11-30 | 3 | 3 | 3 | 3 |
| 2021-12-01 | 3, 4 | 3, 4 | 3, 4 | 3, 4 |
| 2021-12-02 | 3 | 3 | 3 | 3 |
| 2021-12-03 | 2, 3 | 2, 3 | 2, 3 | 2, 3 |
| 2021-12-04 | ∅ | ∅ | ∅ | ∅ |
| 2021-12-05 | ∅ | ∅ | ∅ | ∅ |
| 2021-12-06 | 3, 4 | 3, 4 | 3, 4 | 3, 4 |
| 2021-12-07 | 5 | 5 | 5 | 5 |
| 2021-12-08 | 2, 3, 5 | 2, 3, 5 | 2, 3, 5 | 2, 3, 5 |
| 2021-12-09 | ∅ | ∅ | ∅ | ∅ |
| 2021-12-10 | 3, 4 | 3, 4 | 3, 4 | 3, 4 |
| 2021-12-11 | ∅ | ∅ | ∅ | ∅ |
| 2021-12-12 | ∅ | ∅ | ∅ | ∅ |
| 2021-12-13 | 5 | 5 | 5 | 5 |
| 2021-12-14 | 4 | 4 | 4 | 4 |
| 2021-12-15 | 3, 4, 5 | 3, 4, 5 | 3, 4, 5 | 3, 4, 5 |
| 2021-12-16 | 3, 4, 5 | 3, 4, 5 | 3, 4, 5 | 3, 4, 5 |
| 2021-12-17 | 4 | 4 | 4 | 4 |
| 2021-12-18 | ∅ | ∅ | ∅ | ∅ |
| 2021-12-19 | ∅ | ∅ | ∅ | ∅ |

### 登记缺口 · Service gaps

| 设施 / Facility | 服务 / Service | 少完成 (ID) / Missing | 登记外完成 (ID) / Added |
|---|---|---|---|
| p1-20-w0 | 缺口 / gap | 2021-11-26 (1) | ∅ |
| p1-40-w0 | 缺口 / gap | 2021-11-26 (1) | ∅ |

### 逐车日归因 · Vehicle-day diagnostics

基准未登记的 11 个车日即使没有枪数、站点或单车功率限制，仍会在行程中越过电池可行范围。逐个检查包含这些车日的 52 个连续段组合，每段首尾电量均取 150 kWh。

11 月 26 日的 1 号车可以由双站基准服务。单独检查当天时，首趟行程 787 于柏林时间 10:14 出发，耗电 204.58 kWh；从 150 kWh 起点到 30 kWh 储备线可用 120 kWh。出发前只有仓库停靠，首次港区停靠在 15:23 后。把之前的连续日期也纳入时，两套港区单站设施各自的五种允许连续段也全部失败。

All eleven vehicle-days outside the baseline register violated a trip energy bound even with unlimited station and vehicle power and unrestricted connector access. All 52 combinations of an omitted duty and a continuous segment containing it were checked with 150 kWh at each segment boundary. On 26 November, vehicle 1's first trip (787) left at 10:14 Berlin time and used 204.58 kWh. A standalone day starts with 120 kWh available above reserve. Only the warehouse was available before departure, and the first port stop began after 15:23. All five possible continuous segments containing this day also failed at both port-only facilities.

| 范围 / Scope | 日期 (ID) / Date (ID) | 判别 / Classification | 单车检验中遇到的限制 / Limits observed | 固定全周集合 / Full weekly register |
|---|---|---|---|---|
| 登记外 / Outside | 2021-11-08 (1) | 充电功率不限仍不可行 / infeasible with unlimited charging power | 行程处 SOC 越界 / trip SOC limit | — |
| 登记外 / Outside | 2021-11-12 (3) | 充电功率不限仍不可行 / infeasible with unlimited charging power | 行程处 SOC 越界 / trip SOC limit | — |
| 登记外 / Outside | 2021-11-15 (1) | 充电功率不限仍不可行 / infeasible with unlimited charging power | 行程处 SOC 越界 / trip SOC limit | — |
| 登记外 / Outside | 2021-11-15 (4) | 充电功率不限仍不可行 / infeasible with unlimited charging power | 单趟超可用电量 / trip exceeds usable battery | — |
| 登记外 / Outside | 2021-11-17 (1) | 充电功率不限仍不可行 / infeasible with unlimited charging power | 行程处 SOC 越界 / trip SOC limit | — |
| 登记外 / Outside | 2021-11-22 (1) | 充电功率不限仍不可行 / infeasible with unlimited charging power | 单趟超可用电量 / trip exceeds usable battery | — |
| 登记外 / Outside | 2021-11-23 (1) | 充电功率不限仍不可行 / infeasible with unlimited charging power | 单趟超可用电量 / trip exceeds usable battery | — |
| 登记外 / Outside | 2021-11-24 (1) | 充电功率不限仍不可行 / infeasible with unlimited charging power | 单趟超可用电量 / trip exceeds usable battery · 行程处 SOC 越界 / trip SOC limit | — |
| 登记外 / Outside | 2021-11-24 (3) | 充电功率不限仍不可行 / infeasible with unlimited charging power | 单趟超可用电量 / trip exceeds usable battery | — |
| 登记外 / Outside | 2021-11-24 (4) | 充电功率不限仍不可行 / infeasible with unlimited charging power | 行程处 SOC 越界 / trip SOC limit | — |
| 登记外 / Outside | 2021-11-25 (1) | 充电功率不限仍不可行 / infeasible with unlimited charging power | 单趟超可用电量 / trip exceeds usable battery · 行程处 SOC 越界 / trip SOC limit | — |
| p1-20-w0 | 2021-11-26 (1) | 该设施即使只服务该车也不可行 / infeasible even with exclusive access | 单趟超可用电量 / trip exceeds usable battery · 行程处 SOC 越界 / trip SOC limit | 不可行 / infeasible |
| p1-40-w0 | 2021-11-26 (1) | 该设施即使只服务该车也不可行 / infeasible even with exclusive access | 单趟超可用电量 / trip exceeds usable battery · 行程处 SOC 越界 / trip SOC limit | 不可行 / infeasible |

## 单站恢复 · Single-site service restoration

恢复标准是在六周内完成全部登记车日。按相对原设施增加的额定 kW 比较，固定全周登记集合的物理可行性与逐日优先级选出的车日分别记录。

**两套原设施的最小单站改动都是仓库增加 15 kW。** 仓库增加 10 kW、或仅将港区增至网格上限 50 kW，均无法完成登记集合。下表保留只用直接逐日记录得到的界。对本样本，登记外 11 个车日全部独立不可行，因此任何覆盖登记集合的逐日方案都只能恰好完成该集合。由此也可排除全部更小档位的逐日恢复可能性。两种 15 kW 修复均通过六周逐日核验，该次检验只评估其服务。

**The minimum single-site change from either port-only design is a 15 kW warehouse charger.** The 10 kW warehouse step and every port-only increase through 50 kW fail the fixed register. The table retains the bounds available from direct daily-selection records. In this sample all eleven outside duties are independently infeasible, so every daily selection covering the register must equal it. The fixed-register exclusions therefore rule out daily restoration at every smaller step. Both 15 kW warehouse designs also passed direct daily selection across all six weeks. The original 15 kW hardware checks assessed service only.

Restoration requires the entire register across all six weeks. Increments are rated kW relative to the starting facility. Weekly register feasibility and daily selection are checked separately.

| 原设施 / Start | 方向 / Site | 恢复条件 / Restoration requirement | 最小增量 / Minimum kW | 下界 / Lower kW | 已验证 / Verified kW | 达到上界 / Witness |
|---|---|---|---:|---:|---:|---|
| p1-20-w0 | 综合 / Both | 固定集合 / Fixed register | 15 | 15 | 15 | p1-20-w15 |
| p1-20-w0 | 综合 / Both | 逐日顺序 / Daily selection | — | 5 | 15 | p1-20-w15 |
| p1-20-w0 | 综合 / Both | 两者共同 / Both requirements | 15 | 15 | 15 | p1-20-w15 |
| p1-20-w0 | PORT | 固定集合 / Fixed register | — | — | — | — |
| p1-20-w0 | PORT | 逐日顺序 / Daily selection | — | 5 | — | — |
| p1-20-w0 | PORT | 两者共同 / Both requirements | — | — | — | — |
| p1-20-w0 | WAREHOUSE | 固定集合 / Fixed register | 15 | 15 | 15 | p1-20-w15 |
| p1-20-w0 | WAREHOUSE | 逐日顺序 / Daily selection | — | 10 | 15 | p1-20-w15 |
| p1-20-w0 | WAREHOUSE | 两者共同 / Both requirements | 15 | 15 | 15 | p1-20-w15 |
| p1-40-w0 | 综合 / Both | 固定集合 / Fixed register | 15 | 15 | 15 | p1-40-w15 |
| p1-40-w0 | 综合 / Both | 逐日顺序 / Daily selection | — | 5 | 15 | p1-40-w15 |
| p1-40-w0 | 综合 / Both | 两者共同 / Both requirements | 15 | 15 | 15 | p1-40-w15 |
| p1-40-w0 | PORT | 固定集合 / Fixed register | — | — | — | — |
| p1-40-w0 | PORT | 逐日顺序 / Daily selection | — | 5 | — | — |
| p1-40-w0 | PORT | 两者共同 / Both requirements | — | — | — | — |
| p1-40-w0 | WAREHOUSE | 固定集合 / Fixed register | 15 | 15 | 15 | p1-40-w15 |
| p1-40-w0 | WAREHOUSE | 逐日顺序 / Daily selection | — | 10 | 15 | p1-40-w15 |
| p1-40-w0 | WAREHOUSE | 两者共同 / Both requirements | 15 | 15 | 15 | p1-40-w15 |

| 原设施 / Start | 恢复设计 / Restoration | 新增 kW / Added kW | 全周物理可行 / Fixed register | 逐日顺序 / Daily selection | 逐日策略保留周数 / Weeks retaining R |
|---|---|---:|---|---|---:|
| p1-20-w0 | p1-20-w15 | 15 | 可行 / feasible | 六周保留 / retained | 6/6 |
| p1-20-w0 | p1-40-w0 | 20 | 不可行 / infeasible | 有车日遗漏 / omissions | 5/6 |
| p1-40-w0 | p1-40-w15 | 15 | 可行 / feasible | 六周保留 / retained | 6/6 |

新增核验设施 / Additional designs checked — p1-45-w0, p1-20-w10, p1-50-w0, p1-40-w10, p1-20-w15, p1-40-w15 (6/6).

[逐周证据、已排除的小档位与逐日服务 / Weekly proofs, smaller ratings and daily service](holdout_test.json)

## 停靠资格敏感性 · Charging eligibility sensitivity

留出期 20 个两端相距至少 1 km 的已映射停靠区间均属 5 号车，源自 17 对相邻行程。主情景允许在这些窗口充电。敏感性关闭窗口，保留跨日衔接，重新登记并只检验服务。断点之间未记录的行驶能耗不计入模型。

All 20 mapped date-clipped intervals with endpoints at least 1 km apart belong to vehicle 5 and span 17 track pairs. The main run permits charging. The sensitivity removes those windows, preserves cross-day links, registers service anew and evaluates service only. Energy consumed during unrecorded travel between the endpoints is outside the model.

重新登记 / Reregistered — 50 个车日 / vehicle-days. 移出 / Removed — 2021-12-15 (5), 2021-12-16 (5). 新增 / Added — ∅.

下表“移出／新增”比较同一配置在主情景与敏感性中的实际选择。“少完成”逐项对照重新登记的集合。

Removed and added duties compare each configuration with its own main result. Missing duties are measured against the sensitivity register. This sensitivity evaluates service only.

| 硬件 / Hardware | 港/仓限峰 / Meter kW | 逐日完成 / Served | 保留新集合 / Register | 少完成 / Missing | 移出 / Removed | 新增 / Added | 11-26 车 1 / Vehicle 1 |
|---|---|---:|---|---|---|---|---|
| p1-20-w0 | 20/0 | 48 | 缺口 / gap | 2021-11-26 (1), 2021-12-07 (5) | 2021-12-07 (5), 2021-12-15 (5), 2021-12-16 (5) | ∅ | 遗漏 / missed |
| p1-40-w0 | 40/0 | 49 | 缺口 / gap | 2021-11-26 (1) | 2021-12-15 (5), 2021-12-16 (5) | ∅ | 遗漏 / missed |
| p1-20-w20 | 20/20 | 49 | 缺口 / gap | 2021-12-07 (5) | 2021-12-07 (5), 2021-12-15 (5), 2021-12-16 (5) | ∅ | 完成 / served |
| p1-40-w20 | 40/20 | 50 | 保留 / retained | ∅ | 2021-12-15 (5), 2021-12-16 (5) | ∅ | 完成 / served |
| p1-20-w20 | 20/15 | 49 | 缺口 / gap | 2021-12-07 (5) | 2021-12-07 (5), 2021-12-15 (5), 2021-12-16 (5) | ∅ | 完成 / served |
| p1-40-w20 | 40/15 | 50 | 保留 / retained | ∅ | 2021-12-15 (5), 2021-12-16 (5) | ∅ | 完成 / served |

| 范围 / Scope | 车日 / Duty | 原因 / Diagnosis | 单车证据 / Single-truck limits |
|---|---|---|---|
| 新登记 / Register | 2021-12-15 (5) | 单车充电功率限制 / truck charging-power limit | 无可充窗口 / no charging window · 段末 SOC 无法恢复 / terminal SOC unreachable |
| 新登记 / Register | 2021-12-16 (5) | 单车充电功率限制 / truck charging-power limit | 段末 SOC 无法恢复 / terminal SOC unreachable |
| p1-20-w0 @ [20,0] | 2021-11-26 (1) | 该设施即使只服务该车也不可行 / infeasible even with exclusive access | 单趟超可用电量 / trip exceeds usable battery · 行程处 SOC 越界 / trip SOC limit |
| p1-20-w0 @ [20,0] | 2021-12-07 (5) | 该设施即使只服务该车也不可行 / infeasible even with exclusive access | 行程处 SOC 越界 / trip SOC limit |
| p1-40-w0 @ [40,0] | 2021-11-26 (1) | 该设施即使只服务该车也不可行 / infeasible even with exclusive access | 单趟超可用电量 / trip exceeds usable battery · 行程处 SOC 越界 / trip SOC limit |
| p1-20-w20 @ [20,20] | 2021-12-07 (5) | 该设施即使只服务该车也不可行 / infeasible even with exclusive access | 行程处 SOC 越界 / trip SOC limit |
| p1-20-w20 @ [20,15] | 2021-12-07 (5) | 该设施即使只服务该车也不可行 / infeasible even with exclusive access | 行程处 SOC 越界 / trip SOC limit |

11 月 26 日的 1 号车仍在新登记集合中，两套港区单站仍遗漏这一天。12 月 7 日，5 号车在 20/20 kW 设施上即使独占两站、放开刻钟限峰，在包含该日的两种允许连续段中，行程 9855 后的电量上限也都只有 24.27 kWh，低于 30 kWh 储备。仓库限至 15 kW 时仍有这个缺口。12 月 15、16 日则是基准本身也失去的车日，缩短后的可充时间与单车 50 kW 上限使连续段无法回到规定的 150 kWh 段末电量。

Vehicle 1 on 26 November remained in the new register and both port-only facilities still missed it. On 7 December, even with both 20 kW chargers reserved for vehicle 5 and the quarter-hour caps relaxed, SOC after trip 9855 could reach at most 24.27 kWh in either allowable segment, below the 30 kWh reserve. The 15 kW warehouse cap also leaves that gap. On 15 and 16 December the baseline itself lost vehicle 5's duties. The remaining windows at the 50 kW vehicle limit could not restore the required 150 kWh segment-end SOC.

## 复现 · Reproduction

正式运行源码 / Source — `bd75ba0cf9e421d53184fe4a1ad23468b14c5ea1`. 墙钟 / Wall time — 389.42 s. 求解 / Solver calls — 170.

从仓库根执行。下列两条 Python 命令分别重新求解至新目录和独立回放已有正式归档。 / From the repository root, the two Python commands reproduce the solves in a fresh directory and independently replay the existing formal archive.

```powershell
$env:PYTHONPATH = 'src'
$archive = Join-Path $env:USERPROFILE 'UM-local-records\conversations\0001_records\runs\20261121_holdout_weeks'
$fresh = Join-Path $archive ('reproduction-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m um_charging.holdout --output $fresh
.\.venv\Scripts\python.exe -m um_charging.holdout --verify (Join-Path $archive 'formal')
```

### 修复与敏感性复现 · Repair and sensitivity reproduction

源码 / Source — `d17195a455ece2f604297e8c18a7596eee0c4cd7`. 墙钟 / Wall time — 109.89 s. 求解 / Solver calls — 220. 已回放可行排程 / Replayed feasible schedules — 220.

从仓库根执行。 / Run from the repository root.

```powershell
$env:PYTHONPATH = 'src'
$runs = Join-Path $env:USERPROFILE 'UM-local-records\conversations\0001_records\runs'
$previous = Join-Path $runs '20261121_holdout_weeks\formal'
$repairArchive = Join-Path $runs '20261121_holdout_repair_bills'
$fresh = Join-Path $repairArchive ('reproduction-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m um_charging.holdout_repair --previous $previous --output $fresh
.\.venv\Scripts\python.exe -m um_charging.holdout_repair --previous $previous --verify (Join-Path $repairArchive 'formal')
```
