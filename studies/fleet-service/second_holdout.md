# 固定充电设施的第二次留出检验 · Second holdout of fixed charging facilities

[运输样本 / Sample](DATA.md#seven-calendar-weeks-for-the-second-holdout) · [结果数据 / Results](second_holdout.json) · [第一次留出 / First holdout](holdout_test.md) · [规划期 / Planning period](site_sizing.md)

**核心结论：在开封前预登记的第二次留出检验中，用前 12 周选出的两套有价粗网格最低年费设施——港区 40 kW 加仓库 20 kW（`F40`，`p1-40-w20`）与港/仓各 20 kW（`F20`，`p1-20-w20`）——均未能守住随后 7 周的同一组运输服务。** 主终点（官方网费选出的 `F40`）为经独立复核的确证失败。两段留出各用于一次预定的样本外检验（第一折检验后并入 12 周选型样本，不再作为独立样本）；至此 1–5 号车的可用完整周已全部用完，本项目没有经样本外验证的推荐规模。

- **12 周重新选型（2021-09-27 至 2021-12-19）**：沿用规划期与第一折各自的基准登记，合计 106/136 个完整车日；有价粗网格的 12 个费率与接入口径中，5 个选出 `F40`（含 Netze BW 官方新建与既有），7 个选出 `F20`。
- **第二折结果与缺口机理（2021-12-20 至 2022-02-06，7 周）**：`F40` 少完成 1 个登记车日——2022-01-19 的 1 号车单日段记录的充电全部在仓库、当天没有港区停靠，当日行程可跑完，但段末电量上界 103.763 kWh 距模型规定的 150 kWh 仍差 46.237 kWh；`F20` 少完成 2 个登记车日（另少 2022-01-31 的车 4）。12 周各周最低方案的设施并集（稳健基准 `U`）以及按天滚动（`D40`）、到站即充（`I`）选出的设施同样未能完成登记服务。
- **双站基准与同服务账单**：第二折的 49/57 个登记车日由双站基准 `B`（两站各 50 kW 充电机、100/75 kW 接入，`p1-50-w50`）按自身可行服务选出，主情景下 `B` 守住该集合是按构造成立的；行程耗电增加 10% 时，`B` 也少完成 1 个车日。`B` 是主矩阵中唯一可出同服务年账单的设施，官方网费年费为新建 €22,232.75–22,232.83、既有 €19,895.26–19,895.34（2025 年欧元，按 52/7 年化）。
- **开封后诊断与比较口径**：开封后从 `F40` 出发按预登记四档有价阶梯诊断，港区升至 50 kW 或仓库升至 30 kW 仍不可行，仓库升至 40 kW（`p1-40-w40`）恢复全部服务，仓库 35 kW 未检验；阶梯内最低额外固定年费为新建 €756.91、既有 €489.77（2025 年欧元），这属于看到结果后的诊断而非样本外验证。设施固定后采用按周全信息离线排程（非在线策略）；规划期、第一折与第二折 DE-LU 日前均价分别为 €138.23、€206.16 和 €173.46/MWh，年费仅在同一时期内比较。

**Headline finding: In the preregistered second holdout, both least-cost facilities selected on the 12-week priced coarse grid—40/20 kW (`F40`, `p1-40-w20`) and 20/20 kW (`F20`, `p1-20-w20`) at port/warehouse—failed to retain the same transport service over the following seven weeks.** The primary endpoint (official-tariff selection `F40`) is an independently corroborated failure. Each holdout was used once for its planned out-of-sample test (the first holdout was merged into the 12-week selection sample after its test and is no longer independent). All available full weeks for cohort vehicles 1–5 have now been used, and the study has no out-of-sample-validated facility size.

- **Twelve-week selection (27 September to 19 December 2021):** Combining the planning and first-holdout baseline registers gives 106/136 complete vehicle-days. Across 12 tariff-and-access cases on the priced coarse grid, five selected `F40` (including both official Netze BW cases) and seven selected `F20`.
- **Second-holdout outcome and mechanism (20 December 2021 to 6 February 2022, seven weeks):** `F40` missed one registered vehicle-day—a single-day segment for vehicle 1 on 19 January 2022 where all recorded charging occurred at the warehouse with no port stop that day; the trips completed, yet the terminal battery upper bound of 103.763 kWh fell 46.237 kWh short of the modeled 150 kWh requirement. `F20` missed two vehicle-days (also missing vehicle 4 on 31 January 2022). The union of weekly least-cost facilities (`U`), as well as the designs selected under daily rolling (`D40`) and charge-on-arrival (`I`) dispatch, also failed to complete the register.
- **Baseline scope and same-service bills:** The two-site baseline `B` (one 50 kW charger per site on 100/75 kW connections, `p1-50-w50`) defined the 49/57 register from its own feasible service and therefore retained it by construction in the main scenario; with 10% higher driving energy, `B` also missed one vehicle-day. `B` is the sole facility in the main matrix with a same-service annual bill, at €22,232.75–22,232.83 for new connections and €19,895.26–19,895.34 for existing access under the official tariff (2025 euros, 52/7 annualization).
- **Post-opening diagnosis and comparison basis:** In the preregistered four-step priced ladder conducted after opening from `F40`, raising the port to 50 kW or the warehouse to 30 kW remained infeasible, 40 kW at the warehouse (`p1-40-w40`) restored full service, and 35 kW was untested; the lowest additional annual fixed cost in the ladder was €756.91 (new) and €489.77 (existing) in 2025 euros. This ladder is a post-opening diagnostic rather than out-of-sample validation. Fixed-facility scheduling uses weekly full-information offline optimization—not an online policy—and annual bills are compared only within the same period (mean DE-LU day-ahead prices: €138.23/MWh in planning, €206.16/MWh in the first holdout, €173.46/MWh in the second holdout).

## 1. 十二周重新选型与运营方式对照 · Twelve-week selection and operating policies

### 1.1 选型设定与粗网格结果 · Selection setup and coarse-grid results

十二周选型样本合并了 M8 规划期（6 周）与第一次留出（6 周），共 106/136 个登记车日。全信息排程在固定设施与两站刻钟限峰后按周离线优化，已知该周全部运输任务和 Europe/Berlin 当地交割的 DE-LU 原生日前小时价。跨日结转边界（边界 B）要求每个连续服务段首尾各为 150 kWh，行程中始终保留 30 kWh 储备。选型只在完成同一登记集合的设施间比较；有价细网格尚有 534 个点未判定，留作后续样本内稳健性检验。下表报告有价粗网格的 12 个口径最低方案，金额为 2025 年欧元/年，按 52/12 年化。表内费率代码含义：`N0` 为无网费，`frank` 为 Frank 等（2025）表 4，`official` 为 Netze BW 2024 官方中压网费，`capacity_0` / `capacity_22_79` / `capacity_208_38` 为固定需量单价（0、22.79、208.38 €/kW·年，2024 币值）。[能量边界 / Energy boundary](energy_boundary.md) · [样本与电价 / Samples and prices](DATA.md)

The twelve-week selection sample combines M8 planning (six weeks) and the first holdout (six weeks), totaling 106/136 registered vehicle-days. Full-information scheduling fixes the facility and each site’s quarter-hour demand cap and optimizes offline by week with all tasks and native hourly DE-LU day-ahead prices (Europe/Berlin) known for that week. Boundary B requires 150 kWh at both ends of each continuous service segment and a 30 kWh reserve throughout. Selection compares only facilities serving the identical register; 534 unresolved priced fine-grid points remain for in-sample robustness work. The table reports coarse-grid minima in 2025 euros per year using 52/12 annualization. Tariff codes: `N0` = no network charge; `frank` = Frank et al. (2025) Table 4; `official` = Netze BW 2024 official medium-voltage tariff; `capacity_0` / `capacity_22_79` / `capacity_208_38` = fixed demand rates of 0, 22.79, and 208.38 €/kW·year (2024 basis).

| 费率 / Tariff | 选型新建 / Selected for new access | 新建选型年费 / Selection bill, new | 选型既有 / Selected for existing access | 既有选型年费 / Selection bill, existing |
|---|---|---:|---|---:|
| N0 | F40 | 10,975.76–10,975.93 | F40 | 10,174.33–10,174.50 |
| frank | F20 | 17,542.68–17,542.85 | F40 | 16,984.54–16,984.71 |
| official | F40 | 17,641.62–17,641.79 | F40 | 16,840.19–16,840.36 |
| capacity_0 | F20 | 12,818.52–12,818.69 | F20 | 12,284.24–12,284.41 |
| capacity_22_79 | F20 | 13,749.98–13,750.16 | F20 | 13,215.70–13,215.88 |
| capacity_208_38 | F20 | 21,335.37–21,335.55 | F20 | 20,801.09–20,801.27 |

### 1.2 三种运营方式与稳健并集 · Operating policies and robust union

为检验调度信息结构与简单稳健规则对选型的影响，十二周上同时对比了全信息排程（官方最低方案记为 `F40`）、按天滚动（官方最低方案记为 `D40`）、到站即充（官方最低方案记为 `I`）以及各周最低方案的设施并集（稳健基准 `U`）。按天滚动每天只使用当天任务、日前电价与已知可充窗口，日末回到 150 kWh。到站即充按可充窗口排队补电，不避峰也不择价，连续段从 150 kWh 起步、段末至少 150 kWh，因此需要更高港区装机（`p2-100-w20`）并留下较多段末余电；电表全额计费，超出 150 kWh 的电池余电除以 0.9 折为网侧电量，按同车同段实购网侧电量加权单价（含批发电费与按 kWh 计的网费，不含税）单列披露，峰值、接入与设备固定费用不参与余电分摊。

To test how scheduling information and a simple robust rule affect sizing, the twelve-week sample compares full-information dispatch (official winner `F40`), daily rolling dispatch (`D40`), charge-on-arrival (`I`), and the union of weekly least-cost facilities (`U`). Daily rolling uses only each day’s tasks, day-ahead prices, and charge windows, targeting 150 kWh at day-end. Charge-on-arrival charges whenever a plug is free—starting each segment at 150 kWh and ending at least at 150 kWh—which requires more port capacity (`p2-100-w20`) and leaves terminal surplus. Full metered draw is billed; surplus battery energy is divided by 0.9 to convert to grid kWh and valued at that truck-segment’s grid-energy-weighted purchase plus volumetric network rate (excluding taxes, demand, capacity, connection, and equipment charges).

| 策略 / Policy | 设施 / Facility | 港/仓限峰 kW / Port and warehouse caps | 官方新建年费 / Selection-period official new bill | 官方既有年费 / Selection-period official existing bill |
|---|---|---|---:|---:|
| 全信息 / Full information | p1-40-w20 | 40/20 | 17,641.62–17,641.79 | 16,840.19–16,840.36 |
| 按天滚动 / Daily rolling | p1-40-w20 | 40/20 | 18,171.44–18,171.84 | 17,370.02–17,370.42 |
| 到站即充 / Charge-on-arrival | p2-100-w20 | 100/20 | 41,725.58 | 40,122.74 |
| 各周最低方案的设施并集 / Union of weekly least-cost facilities | p1-40-w20 | 40/20 | 17,641.62–17,641.79 | 16,840.19–16,840.36 |

官方即充总账中已包含 11,430.88 欧元/年的段末余电分项（新建与既有接入口径相同）。在固定需量价 208.38 €/kW·年下，按天滚动的最低点为港区 30 kW、仓库 20 kW。共同稳健并集 `U` 与官方全信息运行点 `F40` 完全重合，两个官方接入口径的事前溢价区间均为 −0.17 至 0.17 欧元/年（区间包含零）。[十二周账单和并集 / Twelve-week bills and union](second_holdout.json)

The official charge-on-arrival bill already includes 11,430.88 euros per year attributable to terminal surplus under both access bases. Under the 208.38 €/kW·year fixed demand charge, the least-cost daily rolling point uses 30 kW at the port and 20 kW at the warehouse. The robust union `U` coincides with the official full-information point `F40`, giving an ex ante premium interval of −0.17 to 0.17 euros per year (containing zero) for both official access cases. [Twelve-week bills and union](second_holdout.json)

### 1.3 十二周断点敏感性与仓库 15 kW 保本价 · Breakpoint sensitivity and 15 kW warehouse break-even prices

在十二周样本中关闭 23 个已映射的记录断点区间后，基准重新登记 104/136 个车日，移出 2021-12-15 和 2021-12-16 的车 5。固定两套原选定运行点检验服务：`F40` 完成全部 104 个车日；F20 在 2021-12-06 起始周不可行，独立单车放松定位出 12 月 7 日车 5 的缺口。该检验未重新对粗网格做费用排序。

Closing the 23 mapped recording-gap intervals across the twelve-week sample reduced the baseline register to 104/136 vehicle-days, removing vehicle 5 on 15 and 16 December 2021. With the two selected operating points held fixed, `F40` retained all 104 vehicle-days, whereas `F20` was infeasible in the week starting 6 December 2021 (independent single-truck relaxation identified vehicle 5 on 7 December). The coarse grid was not reranked on the revised register.

仓库 15 kW 硬件缺乏公开标价，下表给出其在 2026 年未税欧元下的净设备保本门槛。计算方法：按官方网费、固定相同港区功率，用仓库 20 kW 方案的完整年费减去仓库 15 kW 方案除未报价设备外的全部年费，再按设备年化系数折回设备净购置价。四个组合均完成全部 106/106 个登记车日。

Because 15 kW warehouse hardware lacks a retail quote, the table below reports its break-even net purchase price in 2026 euros under the official tariff. Holding the port rating fixed, the known annual costs of the 15 kW build are subtracted from the full annual bill of the 20 kW build and converted back to a net equipment price via the equipment annualization factor. All four cases serve 106/106 registered vehicle-days.

| 设施与限峰 / Facility and caps | 新建净价门槛 / Break-even net price, new | 既有净价门槛 / Break-even net price, existing |
|---|---:|---:|
| p1-20-w15 [20,15] | 5,476.20–5,479.38 | 5,087.62–5,090.80 |
| p1-40-w15 [40,15] | 5,409.85–5,412.70 | 5,021.27–5,024.12 |

## 2. 第二次留出的登记集合与主终点 · Second-holdout register and primary endpoint

在 2021-12-20 至 2022-02-06 的七个完整柏林自然周中，双站基准 `B`（两站各 50 kW 充电机、100/75 kW 接入）在 57 个完整车日中登记 49 个，逐周计数为 7/0/5/11/8/8/10（不含完整任务的第二周仍计入按 52/7 年化的分母）。登记集合 `R` 由 `B` 自身在 50/50 kW 额定点逐日选出，因此主情景中 `B` 守住 `R` 是按构造成立的，并不等同于 `B` 经样本外验证稳健；行程耗电增加 10% 时，`B` 自己也少完成 1 个登记车日。

Across the seven complete Berlin weeks from 20 December 2021 to 6 February 2022, the two-site baseline `B` (one 50 kW charger per site on 100/75 kW connections) registered 49 of 57 complete vehicle-days, with weekly counts of 7/0/5/11/8/8/10 (the empty week stays in the 52/7 annualization denominator). Because `B` defined the register `R` itself from its feasible daily service at 50/50 kW, its main-scenario completion holds by construction and does not validate `B` as robust; with 10% higher driving energy, `B` also missed one registered vehicle-day.

**主终点为确证失败并经独立复核。** `F40` 在 2022-01-17 起始周的整数不可行证书同时适用于官方新建与既有接入两个口径。2022-01-19 的 1 号车在独立单车放松下的段末电量上界为 103.763 kWh，距模型规定的 150 kWh 仍差 46.237 kWh。该车当天行程可以全部跑完，记录的充电全部在仓库，当天没有港区停靠，缺口源于段末必须回到 150 kWh 的建模约定。`F20` 在同一周同样漏掉该日，此外还少完成 2022-01-31 的车 4。

**The primary endpoint is a confirmed failure with independent corroboration.** The weekly integer infeasibility certificate for `F40` in the week of 17 January 2022 applies to both official new and existing access cases. For vehicle 1 on 19 January 2022, independent single-truck relaxation gives a terminal SOC upper bound of 103.763 kWh—46.237 kWh below the modeled 150 kWh requirement. The vehicle completed all trips that day and all recorded charging occurred at the warehouse, with no port stop that day; the shortfall stems from the modeled 150 kWh terminal boundary. `F20` missed the same day and also missed vehicle 4 on 31 January 2022.

| 留出 / Holdout | 车日缺口 / Missed duty | 约束 / Binding service condition | 证据 / Evidence |
|---|---|---|---|
| 第一次 / First | 2021-11-26 (1) | 行程储备 / In-trip reserve | 单日段从 150 kWh 出发，首趟前保留 30 kWh 储备还差 84.578 kWh。 / The one-day segment starts at 150 kWh and falls 84.578 kWh short of protecting the 30 kWh reserve on the first trip. |
| 第二次 / Second | 2022-01-19 (1) | 连续段末电量 / Terminal energy | 当天行程跑完，段末上界 103.763 kWh，距 150 kWh 差 46.237 kWh。 / The truck completes the trips, with a terminal upper bound of 103.763 kWh and a 46.237 kWh shortfall to 150 kWh. |

**两折缺口的共同点与不同点**：第一次留出中，基准登记 52/63 个完整车日，两套港区单站设施各完成 51 个；保持原港区功率并在仓库增加 15 kW 恢复服务（最小有价档 20 kW）。两折缺口的共性仅限于同一辆车（1 号车）、单日段、缺口在仓库一侧且所试港区增容均无效——第一折首趟出发前无港区窗口，第二折将港区从 40 升至 50 kW（仓库维持 20 kW）仍不可行。但决定性约束类型不同：第一折是首趟行驶触发 30 kWh 行程储备越界，第二折是行程完成后段末电量回不到 150 kWh。[第一次留出的缺口证据 / First-holdout gap evidence](holdout_test.md) · [第二次留出摘要 / Second-holdout evidence](second_holdout.json)

**Commonalities and differences across folds:** In the first holdout, the baseline registered 52/63 complete vehicle-days and each port-only facility served 51; adding 15 kW at the warehouse restored service (smallest priced step: 20 kW). Both folds share only four features—vehicle 1, a single-day segment, a warehouse-side bottleneck, and ineffectiveness of all tested port upgrades (no port window before the first trip in Fold 1; raising the port from 40 to 50 kW at a 20 kW warehouse failed in Fold 2). The binding constraints differ: Fold 1 breached the 30 kWh in-trip reserve, whereas Fold 2 completed the trips and bound at the 150 kWh terminal SOC requirement.

## 3. 次要终点、同服务年费与余电披露 · Secondary endpoints, same-service bills and surplus disclosure

除主终点外，按天滚动（`S1`，`D40`）、到站即充选出的设施（`S2`，`I`：`p2-100-w20`）、`F40` 按到站即充运行（`S3`）以及各周并集稳健基准（`U`）在第二次留出中也全部在 2022-01-17 起始周失败（`S3` 另在 2022-01-31 起始周失败）。其中 `S1` 仅有求解器不可行证明，`S2`、`S3` 经独立回放确证，`U` 经独立单车放松复核确证。

All secondary operating policies and the robust union also failed in the week starting 17 January 2022 (`S3` also failed in the week of 31 January): daily rolling (`S1`, `D40`), charge-on-arrival’s selected build (`S2`, `I`: `p2-100-w20`), `F40` under charge-on-arrival (`S3`), and the robust union (`U`). `S1` rests on a solver infeasibility proof alone, while `S2`–`S3` are confirmed by independent replay and `U` by independent corroboration.

| 终点 / Endpoint | 运行政策 / Operating point | 失败周起点 / Failed week starts | 证据等级 / Evidence class |
|---|---|---|---|
| S1 | F40 按天滚动 / F40 daily rolling | 2022-01-17 | 只有求解器证明 / Solver-only failure |
| S2 | I 到站即充 / I charge-on-arrival (p2-100-w20) | 2022-01-17 | 独立回放确证失败 / Failure confirmed by independent replay |
| S3 | F40 到站即充 / F40 charge-on-arrival | 2022-01-17, 2022-01-31 | 独立回放确证失败 / Failure confirmed by independent replay |
| U | F40 稳健并集 / F40 robust union | 2022-01-17 | 独立复核确证失败 / Failure independently corroborated |

因此，在留出期主矩阵中，`B` 是唯一完成全部 49 个登记车日并可出同服务年账单的设施，12 个计费口径的费用名次界均为 `[1,1]`。无网费（`N0`）沿用事先冻结的 50/50 kW 额定点；其余五种网费原冻结限峰无法完成 `R`，按预登记规则回退至 50/50 kW 额定后备。因 `F40`、`I` 与 `D40` 均未完成同一组服务，I−F40 和 D40−F40 的官方年费差均不可识别（新建与既有接入、保留或扣除余电费用均如此），故本研究不报告留出期内“灵活性能替代多少扩容”的金额差。下表以 2025 年欧元/年列示 `B` 的七周留出年费（52/7 年化；费率代码含义同第 1.1 节；仅在同一留出期内可比）。

Accordingly, `B` is the only facility in the main holdout matrix with a same-service annual bill, holding rank bounds `[1,1]` across all 12 cases. `N0` kept its frozen 50/50 kW point; all other tariffs fell back to rated 50/50 kW as prespecified when their frozen caps failed `R`. Because `F40`, `I`, and `D40` lack same-service bills, the official annual differences `I−F40` and `D40−F40` are unidentified under both access bases with or without surplus allocation, so no holdout dollar value for flexibility substituting for capacity is reported. Costs below are in 2025 euros per year (52/7 annualization; tariff codes as in Section 1.1; comparable only within this holdout).

| 费率 / Tariff | B 新建留出年费 / Holdout bill, new | B 既有留出年费 / Holdout bill, existing | B 运行点 / Operating point |
|---|---:|---:|---|
| N0 | 16,190.73–16,190.81 | 13,853.24–13,853.32 | 冻结 / Frozen |
| frank | 22,334.49–22,334.57 | 19,997.00–19,997.08 | 额定后备 / Rated fallback |
| official | 22,232.75–22,232.83 | 19,895.26–19,895.34 | 额定后备 / Rated fallback |
| capacity_0 | 20,005.82–20,005.90 | 17,668.33–17,668.41 | 额定后备 / Rated fallback |
| capacity_22_79 | 22,334.49–22,334.57 | 19,997.00–19,997.08 | 额定后备 / Rated fallback |
| capacity_208_38 | 41,297.96–41,298.04 | 38,960.47–38,960.55 | 额定后备 / Rated fallback |

**七周即充余电披露**：以下仅作分项披露，不改变总账与名次。官方网费下，`I` 结束服务段时累计电池侧余电 4,500.00 kWh，对应七周按量费用 €1,557.24；`F40` 与 `F20` 即充各有 1 个服务段因失败未观测，已观测电池侧余电分别为 4,350.00 kWh 与 3,569.49 kWh，对应七周按量费用 €1,555.09 与 €1,013.30（均为 2025 年欧元；逐车日记录与汇总见离线档案）。

**Seven-week charge-on-arrival surplus disclosure:** Reported separately without altering total bills or ranks. Under the official tariff, `I` ended segments with 4,500.00 kWh of battery-side surplus (seven-week volumetric cost €1,557.24); `F40` and `F20` each had one unobserved segment, with observed surpluses of 4,350.00 and 3,569.49 kWh costing €1,555.09 and €1,013.30 (2025 euros; vehicle-day details remain in the offline archive).

## 4. 开封后修复诊断与服务敏感性 · Post-opening repair diagnostics and service sensitivity

### 4.1 最小物理修复与四档有价阶梯 · Minimum physical repair and four-step priced ladder

`F20` 与 `F40` 确证失败后，按预登记规则依次执行两项开封后诊断：

1. **最小物理增容检索**：按预登记顺序检验 6 套单站小步长增容方案，均未能恢复全部 49 个登记车日；另有 6 套较小方案因可行域完全包含于已证不可行的更大方案中而被直接排除。由此仅确立两个起点的单站增容下界均为至少 15 kW，该检索路径未测出可行上界。
2. **四档有价阶梯诊断**：从 `F40` 出发，按预登记顺序依次检验 `p1-50-w20`、`p1-40-w30`、`p1-40-w40`、`p1-40-w50`。前两档（港区升至 50 kW、仓库升至 30 kW）均失败，后两档（仓库升至 40 kW 或 50 kW）恢复全部 `R`；仓库 35 kW 未检验。

Following the confirmed failures of `F20` and `F40`, two preregistered post-opening diagnostics ran:

1. **Minimum physical repair search:** Six single-site upgrades tested in preregistered order all failed to restore `R`, and six smaller designs were ruled out by feasible-set inclusion. This establishes a lower bound of at least 15 kW for single-site additions from either starting design, with no feasible upper bound verified along this path.
2. **Four-step priced ladder from `F40`:** Testing `p1-50-w20`, `p1-40-w30`, `p1-40-w40`, and `p1-40-w50` in order showed that the first two failed while the last two restored all of `R`; the 35 kW warehouse step was untested.

| 恢复设施 / Restoring facility | 新建额外固定年费 / Added fixed cost, new | 既有额外固定年费 / Added fixed cost, existing | 恢复后新建年费 / Restored bill, new | 恢复后既有年费 / Restored bill, existing |
|---|---:|---:|---:|---:|
| p1-40-w40 | 756.91 | 489.77 | 15,845.56–15,845.76 | 14,776.99–14,777.19 |
| p1-40-w50 | 3,361.11 | 2,960.40 | 18,670.30–18,670.37 | 17,468.17–17,468.24 |

在预登记四档有价阶梯内，`p1-40-w40` 恢复服务所需的额外固定年费最低（新建 €756.91、既有 €489.77，2025 年欧元/年）。由于 `F40` 缺少同服务账单，相对 `F40` 的完整总年费差不可识别。该阶梯是在观察到留出失败之后按预登记规则做的事后诊断，不构成样本外验证，也不能将 `p1-40-w40` 写成推荐规模或将 €756.91 写成经验证的稳健溢价。

Within the four preregistered priced steps, `p1-40-w40` has the lowest additional annual fixed cost to restore service (€756.91 new, €489.77 existing, in 2025 euros/year). The total annual cost difference against `F40` is unidentified because `F40` has no same-service bill. Because this ladder ran after observing the holdout failure, it is a post-opening diagnostic—not out-of-sample validation—and neither endorses `p1-40-w40` as a recommended size nor establishes €756.91 as a validated robustness premium.

### 4.2 停车资格断点与行程耗电裕度 · Parking eligibility and driving-energy margins

关闭 30 个停车资格区间后，基准重新登记 46 个车日，移出 2022-01-26、2022-01-29 和 2022-02-01 的车 5；六个全信息运行点中，只有额定 `B` 完成新登记。行程耗电裕度检验保持原 49 个车日 `R`，在 +10% 与 +20% 两档下，`B`、`F40` 与 `F20` 全部出现经独立复核的服务缺口。下表列出基准 `B` 的缺口（逐周证据见离线档案）。

Closing 30 charging eligibility intervals lowered the baseline register to 46 vehicle-days, removing vehicle 5 on 26 and 29 January and 1 February 2022; among the six full-information points, only rated `B` served the revised register. The driving-energy sensitivity keeps the original 49-day register `R`: `B`, `F40`, and `F20` all incurred independently corroborated gaps at both +10% and +20%. Baseline misses appear below (week-level evidence in the offline archive).

| 行程耗电变化 / Driving-energy increase | 基准缺口 / Baseline misses |
|---|---|
| +10% | 2022-01-31 (4) |
| +20% | 2022-01-06 (1), 2022-01-19 (1), 2022-01-31 (4) |

## 5. 适用范围与不作宣称的事项 · Scope limits and non-claims

本报告仅呈现德国单一承运人 5 辆重卡在两段按时间顺序留出期上的实证反例、机理诊断与可复用检验流程。两段留出各用于一次预定检验（第一折检验后并入 12 周选型样本），1–5 号车数据已全部用完。本研究**不给出**经样本外验证的推荐设施规模，**不宣称**样本内选型存在普遍或系统性偏小、两折属同一约束机制或基准本身稳健，也**不做**统计显著性或跨车队推广声明。

This report documents a preregistered empirical counterexample, its mechanism diagnosis, and a reusable verification protocol on five trucks from one German carrier. Each holdout was used once for its planned test (with Fold 1 merged into the 12-week selection sample afterward), exhausting all full weeks for vehicles 1–5. The study makes **no** out-of-sample-validated sizing recommendation and does **not** claim systematic undersizing, an identical binding mechanism across folds, baseline robustness, statistical significance, or broader generalizability.

## 6. 封存时间线、外部时间戳与复现核验 · Sealing chronology, timestamps and verification

实验执行代码冻结在提交 `055a3ce`；开封前最新研究提交 `091858e` 仅在合成回归测试中增加进程隔离，未改动模型、求解或计费逻辑。下表时间为北京时间（UTC+08）；完整提交号、逐周表、证书与离线档案路径见 [second_holdout.json](second_holdout.json) 的证据索引。

Execution code was frozen at commit `055a3ce`; the pre-opening research commit `091858e` added only process isolation for synthetic regression tests without changing model, solver, or billing logic. Times below are Beijing time (UTC+08); full commit hashes, weekly tables, certificates, and archive paths are indexed in [second_holdout.json](second_holdout.json).

| 事件 / Event | 提交 / Commit | 时间 / Time |
|---|---|---|
| 原预登记 / Original preregistration | 22b843ac | 2026-11-22 02:58:58 |
| 粗网格封存 / Coarse-grid seal | e89e7ba4 | 2026-11-22 13:39:25 |
| 选型冻结 / Selection freeze | 4f7d19ea | 2026-11-22 14:59:22 |
| 运营政策预登记 / Operating-policy preregistration | ce0c4adc | 2026-11-22 18:24:38 |
| 待检矩阵与补充 1 / Holdout matrix and addendum 1 | 719a9387 | 2026-11-22 21:35:59 |
| 补充 2 / Addendum 2 | da79ea42 | 2026-11-22 23:44:30 |
| 开封前核验 / Pre-opening checks | c6822a07 | 2026-11-23 02:11:47 |
| 首次读取 / First raw-input read | — | 2026-11-23 02:13:13.562180 |
| 原件哈希封存 / Raw-input hashes sealed | 34e847e9 | 2026-11-23 02:13:20 |
| 主终点先行封存 / Primary endpoint sealed | f016db24 | 2026-11-23 02:14:16 |
| 正式结果封存 / Final seal | 5f1c94de | 2026-11-23 02:26:27 |

**外部时间戳存证**：第一份 OpenTimestamps 清单覆盖 13 个文件，SHA-256 为 `050def390b0fde75fe8537d7c20b0f62ac9ba4cd9492ac5c2781e70eafca1164`，开封前已取得比特币区块证明（区块高度 977068、977072、977073）。第二份清单覆盖 16 个文件（含预登记补充第 2 号），SHA-256 为 `698efc2bf101326ebd055f949a26c358d72d1c4fa6fecc18f6dc55484095d4fd`；开封时及复盘时均仅有日历服务器的待定证明，任何后续比特币区块证明均晚于开封，因此补充第 2 号的开封前时间顺序由离线 Git 提交记录与待定日历证明共同支持。

**External timestamps:** The first OpenTimestamps manifest covers 13 files (SHA-256 `050def390b0fde75fe8537d7c20b0f62ac9ba4cd9492ac5c2781e70eafca1164`) and had Bitcoin attestations at block heights 977068, 977072 and 977073 before opening. The second manifest covers 16 files, including preregistration addendum 2 (SHA-256 `698efc2bf101326ebd055f949a26c358d72d1c4fa6fecc18f6dc55484095d4fd`); it had only pending calendar attestations at opening and at review. Any block attestation for the second manifest postdates opening. The offline Git commit and pending calendar attestations document the pre-opening record of addendum 2.

**求解与回放审计**：第二次留出共执行 595 个原生请求，对全部 550 个可行结果完成独立回放，另有 45 个不可行证书，无未定周组。执行时先运行冻结的服务可行性检验并单独提交主终点证书，再复用已生成的同一组证书完成计费与次要分析，全程沿用冻结的模型与计费代码。以种子 20261122 在全新进程中随机抽查 20 项，20/20 匹配。

**Solve and replay audit:** The second holdout executed 595 native requests, independently replaying all 550 feasible results alongside 45 infeasibility certificates, with zero unresolved weekly groups. The frozen service-only check ran and committed the primary endpoint certificates first; procurement billing and secondary analyses then reused the same certificate ledger under the frozen model and billing code. With seed 20261122, 20 of 20 fresh-process spot checks matched.

**核验命令**：以下命令在研究仓库根目录的 PowerShell 中执行。第一条 `pytest` 仅读取本报告和 `second_holdout.json`，无须离线档案即可验证表格与关键结论一致性。后续逐证书离线回放需将环境变量 `UM_M10_RUNS` 指向保管方提供的离线档案 `runs` 目录：M8 至 R015 核验各自存量证书；R016 冻结核验入口在原执行提交 `091858e` 上比对两份已登记输入文件的 SHA-256 并重放证书。在文档提交之后复验时，离线适配脚本会先逐字节确认执行代码与 `091858e` 一致，再以原提交号调用同一核验入口完成补充第 2 号的来源核对，全过程只读原档、不重新运行优化（命令、脚本与日志均存离线封存中）。

**Verification commands:** Run the PowerShell commands below from the research repository root. The first `pytest` command checks this report against `second_holdout.json` without needing the offline archive. Full certificate replay requires `UM_M10_RUNS` to point to the custodian’s offline `runs` directory: M8–R015 verify their archived certificates, while the frozen R016 verifier checks both registered input SHA-256 hashes and replays all certificates at execution commit `091858e`. On later documentation commits, an offline adapter verifies that the execution source is byte-identical to `091858e` and passes that commit ID to the same verifier for addendum 2 provenance binding, reading the archive without re-optimizing (commands, adapter, and logs are in the offline seal).

~~~powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = 'src'
$python = '.\.venv\Scripts\python.exe'
& $python -B -m pytest -q -p no:cacheprovider tests/test_published_second_holdout.py

$runs = $env:UM_M10_RUNS
$m8 = Join-Path $runs '20261121_site_sizing_known_peak/audit'
$m9 = Join-Path $runs '20261121_holdout_weeks/formal'
$m9Repair = Join-Path $runs '20261121_holdout_repair_bills/formal'
$r11 = Join-Path $runs '20261122_m10_selection_coarse/formal'
$r12 = Join-Path $runs '20261122_m10_selection_coarse2/formal'
$r13 = Join-Path $runs '20261122_m10_refine/formal'
$r14Prereg = Join-Path $runs '20261122_m10_policies'
$r14 = Join-Path $runs '20261122_m10_policies_continuation'
$r15 = Join-Path $runs '20261122_m10_holdout_prep'
$r16 = Join-Path $runs '20261123_m10_second_holdout/formal'
$matrix = Join-Path $r14 'holdout_matrix.json'
$breakpoints = Join-Path $r15 'breakpoint_sensitivity'
$addendum = Join-Path $r15 'PREREG_SECOND_HOLDOUT_ADDENDUM_2.md'

& $python -B -m um_charging.m10_selection --verify $m8 --legacy m8
& $python -B -m um_charging.m10_selection --verify $m9 --legacy m9
& $python -B -m um_charging.m10_selection --verify $m9Repair --legacy m9-repair --previous $m9
& $python -B -m um_charging.m10_selection --verify $r11
& $python -B -m um_charging.m10_selection --verify $r12
& $python -B -m um_charging.m10_refine --coarse $r12 --verify $r13
& $python -B (Join-Path $r14 'verify_selection_only.py') --coarse $r12 --refinement $r13 --prereg-folder $r14Prereg --verify (Join-Path $r14 'formal')
& $python -B -m um_charging.m10_breakpoint --verify $breakpoints
& $python -B -m um_charging.m10_final_run --matrix $matrix --breakpoint-archive $breakpoints --rehearsal --verify (Join-Path $r15 'rehearsal')
# UM-R016 原执行头 / Execution head 091858e
& $python -B -m um_charging.m10_final_run --matrix $matrix --open-registered-holdout $addendum --verify $r16
~~~

[数字、逐项档案索引与封存校验 / Results, archive index and verification evidence](second_holdout.json)
