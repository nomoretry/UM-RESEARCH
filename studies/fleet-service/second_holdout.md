# 固定充电设施的第二次留出检验 · Second holdout of fixed charging facilities

[运输样本 / Sample](DATA.md#seven-calendar-weeks-for-the-second-holdout) · [结果数据 / Results](second_holdout.json) · [第一次留出 / First holdout](holdout_test.md) · [规划期 / Planning period](site_sizing.md)

2021-09-27 至 2021-12-19 的十二周用于重新选型。沿用规划期与第一次留出各自的基准登记，合计 106/136 个完整车日。有价粗网格的十二个费率与接入口径中，五个选出港区 40 kW、仓库 20 kW 的 F40，七个选出港区与仓库各 20 kW 的 F20。两套设施在随后七周的留出检验中均出现服务缺口。F40 少完成一个登记车日，F20 少完成两个。两段留出各用于一次预定检验，本项目尚无经样本外验证的推荐规模。

The facilities were reselected over the twelve weeks from 27 September to 19 December 2021. The baseline registers from planning and the first holdout together contain 106 of 136 complete vehicle-days. On the priced coarse grid, F40, with 40 kW at the port and 20 kW at the warehouse, was least expensive in five tariff-and-access cases. F20, with 20 kW at each site, was least expensive in seven. In the following seven-week holdout F40 missed one registered vehicle-day and F20 missed two. Each holdout was used once for its planned test. The study has no out-of-sample-validated facility size.

## 十二周选型与运营方式 · Twelve-week selection and operation

十二周覆盖 M8 规划期和第一次留出。全信息调度固定设施与两站刻钟限峰，按周优化，已知该周运输任务和 Europe/Berlin 当地交割的 DE-LU 原生日前小时价。边界 B 要求每个连续服务段首尾各为 150 kWh，段内保留 30 kWh 储备。选型只比较同一登记集合。有价细网格仍有 534 个点未判定，留作样本内稳健性检验。表中为粗网格结论，费用均为 2025 欧元/年，按 52/12 年化。[能量边界 / Energy boundary](energy_boundary.md) · [样本与电价 / Samples and prices](DATA.md)

The twelve weeks combine M8 planning and the first holdout. Full-information scheduling fixes the facility and the quarter-hour demand cap at each site and optimizes by week, with all tasks and the native hourly DE-LU day-ahead prices in Europe/Berlin known for that week. Boundary B requires 150 kWh at both ends of each continuous service segment and a 30 kWh reserve throughout. Selection compares facilities serving the same register. The 534 unresolved priced fine-grid points remain for in-sample robustness work. The table covers the coarse grid. Costs are in 2025 euros per year using 52/12 annualization.

| 费率 / Tariff | 选型新建 / Selected for new access | 新建选型年费 / Selection bill, new | 选型既有 / Selected for existing access | 既有选型年费 / Selection bill, existing |
|---|---|---:|---|---:|
| N0 | F40 | 10,975.76–10,975.93 | F40 | 10,174.33–10,174.50 |
| frank | F20 | 17,542.68–17,542.85 | F40 | 16,984.54–16,984.71 |
| official | F40 | 17,641.62–17,641.79 | F40 | 16,840.19–16,840.36 |
| capacity_0 | F20 | 12,818.52–12,818.69 | F20 | 12,284.24–12,284.41 |
| capacity_22_79 | F20 | 13,749.98–13,750.16 | F20 | 13,215.70–13,215.88 |
| capacity_208_38 | F20 | 21,335.37–21,335.55 | F20 | 20,801.09–20,801.27 |

按天滚动仅用当天任务、日前价格和已知可充窗口，日末回到 150 kWh。到站即充按可充时窗排队充电，每个连续服务段从 150 kWh 开始，段末至少 150 kWh。电表用量全额结算。超出段末要求的余电用同车同段的实购网侧电量加权计价，电池余量除以 0.9 转为网侧 kWh，费用包括购电和按 kWh 计的网费。冻结账单排除税费。按峰值、功率、接入和设备收取的费用不参与分摊。

Daily rolling dispatch uses the day's tasks, day-ahead prices and known charge windows, with a 150 kWh end-of-day target. Charge-on-arrival follows the available windows and queue, with 150 kWh at the start of each segment and at least 150 kWh at its end. The full metered draw is billed. Surplus battery energy is divided by 0.9 and valued at the grid-energy-weighted price paid by the same truck in that segment. The allocation covers energy purchases and volumetric network charges. The frozen bills exclude taxes, and demand, capacity, connection and equipment charges are outside the allocation.

| 策略 / Policy | 设施 / Facility | 港/仓限峰 kW / Port and warehouse caps | 官方新建年费 / Selection-period official new bill | 官方既有年费 / Selection-period official existing bill |
|---|---|---|---:|---:|
| 全信息 / Full information | p1-40-w20 | 40/20 | 17,641.62–17,641.79 | 16,840.19–16,840.36 |
| 按天滚动 / Daily rolling | p1-40-w20 | 40/20 | 18,171.44–18,171.84 | 17,370.02–17,370.42 |
| 到站即充 / Charge-on-arrival | p2-100-w20 | 100/20 | 41,725.58 | 40,122.74 |
| 各周最低方案的设施并集 / Union of weekly least-cost facilities | p1-40-w20 | 40/20 | 17,641.62–17,641.79 | 16,840.19–16,840.36 |

官方即充总账中，段末余电分项为 11,430.88 欧元/年，两个接入口径相同，已经包含在总账中。固定需量价 208.38 欧元/kW·年的按天滚动最低点为港区 30 kW、仓库 20 kW。共同稳健并集与官方全信息运行点相同，官方两个口径的事前溢价界均为 −0.17 至 0.17 欧元/年，区间包含零。[十二周账单和并集 / Twelve-week bills and union](second_holdout.json)

The official charge-on-arrival bill includes 11,430.88 euros per year attributable to terminal surplus under both access assumptions. With the fixed demand charge of 208.38 euros per kW per year, the least-cost daily rolling point uses 30 kW at the port and 20 kW at the warehouse. The common robust union coincides with the official full-information point. The ex ante premium interval is −0.17 to 0.17 euros per year for each official access case and includes zero. [Twelve-week bills and union](second_holdout.json)

### 断点敏感性与仓库设备保本价 · Breakpoint sensitivity and warehouse break-even prices

十二周中关闭 23 个已映射的记录断点区间后，基准重新登记 104/136 个车日，移出 2021-12-15 和 2021-12-16 的车 5。F40 完成全部 104 个。F20 在 2021-12-06 起始周不可行，独立单车放松识别出 12 月 7 日车 5 的缺口。此检验固定两套既有运行点，粗网格费用排序未重新判定。

Closing the 23 mapped recording-gap intervals in the twelve-week sample reduced the baseline register to 104 of 136 vehicle-days. Vehicle 5 on 15 and 16 December 2021 left the register. F40 retained all 104 vehicle-days. F20 was infeasible in the week beginning 6 December 2021, and an independent single-truck relaxation identified vehicle 5 on 7 December. This check fixed the two previously selected operating points and did not rerank the coarse grid on the revised register.

仓库 15 kW 的净设备保本价以 2026 年欧元计。按官方网费，在同港区额定功率下，以仓库 20 kW 的完整年费减去仓库 15 kW 案除未报价设备外的全部年费，再将差额按设备年化系数折回购置净价。表内四个点均服务 106/106 个登记车日，数值是保本门槛。

Warehouse 15 kW break-even purchase prices are stated in 2026 euros. Under the official tariff, the calculation holds the port rating fixed, subtracts the known annual cost of the 15 kW design from the complete annual bill of the 20 kW design, and converts the annual difference to a net purchase price using the equipment annualization factor. All four cases serve 106 of 106 registered vehicle-days.

| 设施与限峰 / Facility and caps | 新建净价门槛 / Break-even net price, new | 既有净价门槛 / Break-even net price, existing |
|---|---:|---:|
| p1-20-w15 [20,15] | 5,476.20–5,479.38 | 5,087.62–5,090.80 |
| p1-40-w15 [40,15] | 5,409.85–5,412.70 | 5,021.27–5,024.12 |

## 第二次留出的登记与主终点 · Second-holdout register and primary endpoint

2021-12-20 至 2022-02-06 的七个完整柏林周中，双站基准 B 在 57 个完整车日中登记 49 个，周计数依次为 7/0/5/11/8/8/10。空周仍计入按 52/7 年化的分母。登记集合由 B 自身在 50/50 kW 额定点逐日选出，主情景中 B 能守住这组服务是由登记方法决定的。基准在耗电增加 10% 的敏感性检验中也少完成一个登记车日。

B, the two-site baseline, registered 49 of 57 complete vehicle-days in the seven complete Berlin weeks from 20 December 2021 to 6 February 2022. Weekly counts were 7/0/5/11/8/8/10. The empty week stays in the 52/7 annualization denominator. B selected the register itself by registering each day at its rated 50/50 kW point, so the main-scenario result for B follows from the construction of the register. B lost one registered vehicle-day in the sensitivity check with 10% higher driving energy.

**主终点为确证失败并经独立复核。** 官方新建、既有均使用 F40 的周级整数不可行证书。2022-01-19 的车 1 在独立单车放松后的段末电量上界为 103.763 kWh，距 150 kWh 差 46.237 kWh。该车当日行程可以跑完，缺口来自段末 150 kWh 的建模约定。即充回放完成了当日行程，记录的充电量全部在仓库。F20 还少完成 2022-01-31 的车 4。

**The primary endpoint is a confirmed failure with independent corroboration.** The F40 weekly integer infeasibility certificate applies to both official access cases. For vehicle 1 on 19 January 2022, the independent single-truck relaxation gives an upper bound of 103.763 kWh at segment end, 46.237 kWh below the 150 kWh requirement. The truck can drive the day's trips. The gap arises from the modeled terminal requirement. The charge-on-arrival simulation completed the trips, with all of the vehicle's recorded charging at the warehouse that day. F20 also missed vehicle 4 on 31 January 2022.

| 留出 / Holdout | 车日缺口 / Missed duty | 约束 / Binding service condition | 证据 / Evidence |
|---|---|---|---|
| 第一次 / First | 2021-11-26 (1) | 行程储备 / In-trip reserve | 单日段从 150 kWh 出发，首趟前保留 30 kWh 储备还差 84.578 kWh。 / The one-day segment starts at 150 kWh and falls 84.578 kWh short of protecting the 30 kWh reserve on the first trip. |
| 第二次 / Second | 2022-01-19 (1) | 连续段末电量 / Terminal energy | 当天行程跑完，段末上界 103.763 kWh，距 150 kWh 差 46.237 kWh。 / The truck completes the trips, with a terminal upper bound of 103.763 kWh and a 46.237 kWh shortfall to 150 kWh. |

第一次留出中，双站基准登记 52/63 个完整车日，两套港区单站设施各完成 51 个。保留原港区额定功率时，在仓库增加 15 kW 恢复全部服务，20 kW 是最小有报价档。两折都涉及车 1 的单日段与仓库侧补电。第一折在首趟之前无可用港区充电窗，单独提高港区功率也无法守住行程储备。第二折把港区从 40 kW 提高到 50 kW、仓库保持 20 kW，仍未恢复服务。第二折的约束出现在当天行程完成后。[第一次留出的缺口证据 / First-holdout gap evidence](holdout_test.md) · [第二次留出摘要 / Second-holdout evidence](second_holdout.json)

In the first holdout the two-site baseline registered 52 of 63 complete vehicle-days. Each port-only facility served 51. Keeping either port rating, adding 15 kW at the warehouse restored the register. The 20 kW warehouse charger was the smallest priced step. Both folds involve a one-day segment for vehicle 1 and a charging constraint on the warehouse side. In the first fold there was no available port window before the first trip, so a higher port rating could not protect the driving reserve. In the second fold, increasing the port from 40 to 50 kW while keeping the warehouse at 20 kW did not restore service. The second-fold constraint binds after the day's trips.

## 次要终点与同服务年费 · Secondary endpoints and same-service annual bills

| 终点 / Endpoint | 运行政策 / Operating point | 失败周起点 / Failed week starts | 证据等级 / Evidence class |
|---|---|---|---|
| S1 | F40 按天滚动 / F40 daily rolling | 2022-01-17 | 只有求解器证明 / Solver-only failure |
| S2 | I 到站即充 / I charge-on-arrival (p2-100-w20) | 2022-01-17 | 独立回放确证失败 / Failure confirmed by independent replay |
| S3 | F40 到站即充 / F40 charge-on-arrival | 2022-01-17, 2022-01-31 | 独立回放确证失败 / Failure confirmed by independent replay |
| U | F40 稳健并集 / F40 robust union | 2022-01-17 | 独立复核确证失败 / Failure independently corroborated |

留出期主矩阵中，B 是唯一有同服务账单的设施，各口径费用名次界为 [1,1]。N0 沿用事先冻结的额定点。其他费率的 B 冻结限峰无法完成 R，按登记改用额定后备。年费只在这七周的同一留出期内比较。I−F40 和 D40−F40 的官方年费差均不可识别，新建和既有接入在保留和扣除余电费用时结果均如此。各费率按 2025 欧元/年列示。

In the main holdout comparison, B is the sole facility with a same-service bill and has a rank interval of [1,1] in each case. N0 uses its frozen rated setting. B's other frozen caps fail to complete R and use the rated fallback as prespecified. The annual bills compare facilities within this same seven-week holdout. The official annual differences I−F40 and D40−F40 are unidentified for both access assumptions, with or without the surplus allocation. Costs are in 2025 euros per year.

| 费率 / Tariff | B 新建留出年费 / Holdout bill, new | B 既有留出年费 / Holdout bill, existing | B 运行点 / Operating point |
|---|---:|---:|---|
| N0 | 16,190.73–16,190.81 | 13,853.24–13,853.32 | 冻结 / Frozen |
| frank | 22,334.49–22,334.57 | 19,997.00–19,997.08 | 额定后备 / Rated fallback |
| official | 22,232.75–22,232.83 | 19,895.26–19,895.34 | 额定后备 / Rated fallback |
| capacity_0 | 20,005.82–20,005.90 | 17,668.33–17,668.41 | 额定后备 / Rated fallback |
| capacity_22_79 | 22,334.49–22,334.57 | 19,997.00–19,997.08 | 额定后备 / Rated fallback |
| capacity_208_38 | 41,297.96–41,298.04 | 38,960.47–38,960.55 | 额定后备 / Rated fallback |

七周即充试跑的余电仅作披露。官方口径下，I 的段末余量为 4,500.00 kWh，对应 1,557.24 欧元。F40 即充与 F20 即充各有一个段未观测，已观测的余量分别为 4,350.00 和 3,569.49 kWh，按量费用分别为 1,555.09 和 1,013.30 欧元。电量为电池侧，金额为七周费用，以 2025 年欧元计。逐车日和汇总留在离线档案，余电行不改变总账和名次。

Surplus from the seven-week charge-on-arrival runs is disclosed separately. Under the official tariff, I ended service segments with 4,500.00 kWh of surplus costing 1,557.24 euros. F40 and F20 each have one unobserved segment. Their observed surpluses are 4,350.00 and 3,569.49 kWh, with volumetric costs of 1,555.09 and 1,013.30 euros. These are battery-side quantities and seven-week costs in 2025 euros. The vehicle-day records and totals remain in the offline archive. The allocation leaves total bills and ranks unchanged.

## 修复与服务敏感性 · Repairs and service sensitivity

F20 与 F40 的整数不可行证书触发了最小物理修复。按预登记顺序共计入六套，均未恢复全部 R，另有六项由可行域包含关系排除。两个起点的单站增容下界均为至少 15 kW。该路径未证实可行上界。F40 的独立复核失败同时触发四档有价阶梯。依次检查 `p1-50-w20`、`p1-40-w30`、`p1-40-w40`、`p1-40-w50`，前两档失败，后两档恢复全部 R。仓库 35 kW 未检验。

The integer infeasibility certificates for F20 and F40 triggered the minimum physical repair search. Six designs counted in the preregistered sequence, and all failed to restore R. Feasible-set inclusion ruled out six additional options. The lower bound for a single-site increase is 15 kW for each starting design. This search established no feasible upper bound. The independently corroborated F40 failure also triggered the four-step priced ladder. `p1-50-w20` and `p1-40-w30` failed. `p1-40-w40` and `p1-40-w50` restored all of R. The 35 kW warehouse step was untested.

| 恢复设施 / Restoring facility | 新建额外固定年费 / Added fixed cost, new | 既有额外固定年费 / Added fixed cost, existing | 恢复后新建年费 / Restored bill, new | 恢复后既有年费 / Restored bill, existing |
|---|---:|---:|---:|---:|
| p1-40-w40 | 756.91 | 489.77 | 15,845.56–15,845.76 | 14,776.99–14,777.19 |
| p1-40-w50 | 3,361.11 | 2,960.40 | 18,670.30–18,670.37 | 17,468.17–17,468.24 |

`p1-40-w40` 在预登记四档有价阶梯内恢复服务的额外固定年费最低。表中金额为 2025 欧元/年。相对 F40 的完整年费差因原设施缺少同服务账单而不可识别。阶梯是查看留出结果之后按预登记规则进行的诊断，两次留出都已用过一次，尚无可验证该规模的独立样本。

`p1-40-w40` has the lowest additional annual fixed cost for restoring service within the four preregistered priced options. Amounts are 2025 euros per year. The difference in total annual cost from F40 is unidentified because F40 has no same-service bill. The ladder is a diagnostic conducted after observing the holdout result under a preregistered rule. Both holdouts have been used once, and no independent sample remains in this study to validate the repair.

关闭 30 个停车资格区间后，基准重新登记 46 个车日。移出 2022-01-26、2022-01-29 和 2022-02-01 的车 5。六个全信息点中只有额定 B 完成新登记。耗电裕度检验保持原 R，B、F40 与 F20 在两档均出现经独立复核的缺口。基准缺口如下，逐周证据留在离线档案。

Closing 30 charging eligibility intervals reduced the baseline register to 46 vehicle-days, removing vehicle 5 on 26 and 29 January and 1 February 2022. Rated B alone served the new register among the six full-information points. The driving-energy sensitivities retain the original R. B, F40 and F20 have independently corroborated gaps at both margins. The baseline misses are listed below, with the week-level evidence in the offline archive.

| 行程耗电变化 / Driving-energy increase | 基准缺口 / Baseline misses |
|---|---|
| +10% | 2022-01-31 (4) |
| +20% | 2022-01-06 (1), 2022-01-19 (1), 2022-01-31 (4) |

## 封存、复现与核验 · Sealing, reproduction and verification

研究执行源码冻结于 `055a3ce`，开封前的研究头 `091858e` 仅增加合成回归的进程隔离。时间均为北京时间（UTC+08）。逐周表、证书、完整提交号和档案位置见结果数据的证据索引。

The study froze the execution source at `055a3ce`. The pre-opening research head `091858e` differs only in process isolation for synthetic regression tests. Times below are Beijing time (UTC+08). The evidence index in the results data gives the offline file locations and full commit IDs for weekly tables and certificates.

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

第一份 OpenTimestamps 清单覆盖 13 个文件，SHA-256 为 `050def390b0fde75fe8537d7c20b0f62ac9ba4cd9492ac5c2781e70eafca1164`。开封前已有比特币区块证明，高度为 977068、977072、977073。第二份清单覆盖 16 个文件，含预登记补充第 2 号，SHA-256 为 `698efc2bf101326ebd055f949a26c358d72d1c4fa6fecc18f6dc55484095d4fd`。开封时只有日历服务器的待定证明。复盘时仍为待定，第二份的任何区块证明都晚于开封。补充第 2 号的开封前记录由离线 Git 提交和待定证明支持。

The first OpenTimestamps manifest covers 13 files and has SHA-256 `050def390b0fde75fe8537d7c20b0f62ac9ba4cd9492ac5c2781e70eafca1164`. Its Bitcoin attestations at heights 977068, 977072 and 977073 predate opening. The second manifest covers 16 files, including preregistration addendum 2, and has SHA-256 `698efc2bf101326ebd055f949a26c358d72d1c4fa6fecc18f6dc55484095d4fd`. It had pending calendar attestations at opening. The calendar attestations were still pending at review. Any block attestation for the second manifest postdates opening. The offline Git commit and pending calendar attestations document the pre-opening record of addendum 2.

第二次留出共有 595 个原生请求，独立回放全部 550 个可行结果。另有 45 个不可行证书，无未定周组。主终点的证书和结果先单独提交，采购与次要分析随后开始。记录层调用冻结的纯服务入口，再由原入口复用同一台账，模型和费用计算沿用冻结代码。种子 20261122 的独立新进程抽查 20/20 匹配。

The second holdout has 595 native requests. Independent replay covered all 550 feasible results, with 45 further infeasibility certificates and no unresolved weekly groups. The primary certificates and endpoint were committed before procurement and secondary analyses began. The archival launcher first invoked the frozen service-only entry. The original dispatcher then reused the same ledger and the frozen model and billing code. With seed 20261122, all 20 fresh-process spot checks matched.

研究库根目录的以下 PowerShell 命令用于核验。本页的一致性测试只读报告和结果 JSON。逐证书回放需要保管方提供离线库，在环境变量 `UM_M10_RUNS` 中指定其 `runs` 目录。下列 M8 至 R015 各入口使用相应的存量证书。R016 的冻结入口在原执行头读取两份已登记输入以核对 SHA-256 和回放证书。文档提交后的复验由离线核验程序先逐字节核对执行源，再向同一入口提供原执行头标识，以匹配补充第 2 号的来源绑定。复验仅读取原档，未运行新优化。命令、核验程序和日志随离线封存保存。

Use the PowerShell commands below from the research repository root. The consistency test reads only this report and its result JSON. Certificate replay requires the custodian's offline archive, with `UM_M10_RUNS` pointing to its `runs` directory. The M8 through R015 entries use their existing certificates. At the original execution head, the frozen R016 verifier loads the two registered inputs to check their SHA-256 hashes and replay the certificates. For verification on the documentation commit, an offline adapter checks that the execution source is byte-identical and supplies the original execution-head ID to the same verifier for the addendum 2 provenance binding. Verification reads the original archive without running new optimization. The offline seal contains the commands, adapter and logs.

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
