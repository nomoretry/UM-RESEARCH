# 子车队充电设施外部检验

在同一承运人、同一日历划分、由基准设施定义登记的条件下，两个主队列按样本内成本最低选出的设施都没能守住之后几周的服务。

## 检验设计

按车辆数值名次分组。主队列为 6–10、11–15，次要队列为 16–18。选型期为 2021-09-27 至 2021-12-19，检验期为 2021-12-20 至 2022-02-06。完整车日门槛分别为 68、28，登记车日门槛分别为 50、20。以港区和仓库各 50 kW 的基准逐周登记。

在 35 套有价硬件的额定点上比较同一登记服务的年费区间。主口径为官方网费、新建接入，按 52/12 年化选型账单，按 52/7 年化检验账单，均以 2025 年欧元计。主终点依据入选设施在检验期各周的固定服务证书判定。同一车连续服务段的首末电量均为 150 kWh。

输入使用公开行程记录及其模拟耗电。到达和发车时刻界定停靠上界，港区、仓库资格按站点标志映射；这些窗口不代表实际发生过充电。[数据来源与车日质量规则](DATA.md)

## 主结果

完整、登记和可行栏依次列出选型期与检验期；可行数按设施计。划线表示此前门槛已确定不满足或所需数值未判清。最低设施及年费按额定点列示。

| 名次区间 | 完整车日 | 登记车日 | 可行设施 | 最低设施 | 年费（€/年） | 判定 | 按构造无信息 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6-10 | 138 / 50 | 83 / 33 | 22 / 9 | p1-30-w20 | 11,859.57–11,859.65 | 未守住 | 否 |
| 11-15 | 165 / 55 | 112 / 45 | 20 / 7 | p1-40-w20 | 25,790.48–25,790.61 | 未守住 | 否 |
| 16-18 | 72 / 21 | — / — | — / — | — | — | 不可评 | — |

16-18 未达到完整车日门槛，后续选型、主服务检验和次要分析跳过。

## 失败周与独占服务段

预测一检查失败周中是否存在单车独占所选设施也无法完成的段。预测二检查这样的段是否至少有一站所需档严格高于该站训练期最大档。每行对应一个所选设施的失败段。港/仓为固定另一站在网格最大配置时的最低有价档。缺口以 kWh 计，训练最大档与检验所需档均以 kW 计。

| 名次 | 设施 | 周起始 | 日期 | 站点 | 缺口 | 训练最大档 | 所需档 | 预测一 / 二 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6-10 | p1-30-w20 | 2022-01-03 | 2022-01-03, 2022-01-04 | 港区, 仓库 | 23.678 | 20 / 20 | 50 / 0 | 命中 / 命中 |
| 6-10 | p1-30-w20 | 2022-01-31 | 2022-01-31 | 港区, 仓库 | 0.701 | 20 / 20 | 30 / 30 | 命中 / 命中 |
| 11-15 | p1-40-w20 | 2022-01-10 | 2022-01-14 | 港区, 仓库 | 25.952 | 20 / 20 | 40 / 40 | 命中 / 命中 |

诊断表中的站点是该段可用的停靠位置。依次把另一站设到网格最大配置后，11–15 的失败段在仓库需达到 40 kW；6–10 的跨日段在港区需达到 50 kW。

## 次要结果

| 名次 | 既有最低设施 | 既有年费 | 既有判定 | 全期可行数 | 港/仓最低档 | p1-40-w20 全期 | p1-40-w40 全期 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6-10 | p1-30-w20 | 11,191.72–11,191.79 | 未守住 | 9 | 50 / 30 | 不可行 | 不可行 |
| 11-15 | p1-40-w20 | 24,989.06–24,989.19 | 未守住 | 7 | 40 / 40 | 不可行 | 不可行 |

| 名次 | 时期 | 仅港 | 仅仓 | 两站 | 无站 |
| --- | --- | --- | --- | --- | --- |
| 6-10 | 选型 | 8 | 1 | 74 | 0 |
| 6-10 | 检验 | 5 | 0 | 28 | 0 |
| 11-15 | 选型 | 9 | 1 | 102 | 0 |
| 11-15 | 检验 | 2 | 2 | 41 | 0 |

| 名次 | 接入 | 选型方法 | 设施 | 年费 | 相对主选型溢价 | 检验 |
| --- | --- | --- | --- | --- | --- | --- |
| 6-10 | 新建 | 规则① | p1-30-w20 | 11,859.57–11,859.65 | -0.07–0.07 | 未守住 |
| 6-10 | 新建 | 规则② | p1-30-w20 | 11,859.57–11,859.65 | -0.07–0.07 | 未守住 |
| 6-10 | 新建 | 规则③ | p1-30-w40 | 13,048.25–13,048.35 | 1,188.60–1,188.77 | 未守住 |
| 6-10 | 新建 | 规则④ | p1-30-w30 | 12,524.25–12,524.32 | 664.61–664.74 | 未守住 |
| 6-10 | 新建 | 逐周并集 | p1-40-w20 | 12,146.30–12,146.41 | 286.65–286.84 | 未守住 |
| 6-10 | 新建 | 双站基准 | p1-50-w50 | 19,877.71–19,877.80 | 8,018.06–8,018.23 | 守住 |
| 6-10 | 既有 | 规则① | p1-30-w20 | 11,191.72–11,191.79 | -0.07–0.07 | 未守住 |
| 6-10 | 既有 | 规则② | p1-30-w20 | 11,191.72–11,191.79 | -0.07–0.07 | 未守住 |
| 6-10 | 既有 | 规则③ | p1-30-w40 | 12,113.25–12,113.35 | 921.46–921.63 | 未守住 |
| 6-10 | 既有 | 规则④ | p1-30-w30 | 11,722.83–11,722.89 | 531.04–531.17 | 未守住 |
| 6-10 | 既有 | 逐周并集 | p1-40-w20 | 11,344.87–11,344.99 | 153.08–153.27 | 未守住 |
| 6-10 | 既有 | 双站基准 | p1-50-w50 | 17,540.22–17,540.32 | 6,348.43–6,348.60 | 守住 |
| 11-15 | 新建 | 规则① | p1-30-w20 | 26,113.03–26,113.21 | 322.42–322.73 | 未守住 |
| 11-15 | 新建 | 规则② | p1-30-w20 | 26,113.03–26,113.21 | 322.42–322.73 | 未守住 |
| 11-15 | 新建 | 规则③ | p1-30-w40 | 27,330.41–27,330.68 | 1,539.80–1,540.19 | 未守住 |
| 11-15 | 新建 | 规则④ | p1-40-w40 | 26,864.63–26,864.81 | 1,074.02–1,074.32 | 未守住 |
| 11-15 | 新建 | 逐周并集 | p1-40-w20 | 25,790.48–25,790.61 | -0.13–0.13 | 未守住 |
| 11-15 | 新建 | 双站基准 | p1-50-w50 | 32,847.79–32,848.05 | 7,057.19–7,057.57 | 守住 |
| 11-15 | 既有 | 规则① | p1-30-w20 | 25,445.18–25,445.36 | 455.99–456.30 | 未守住 |
| 11-15 | 既有 | 规则② | p1-30-w20 | 25,445.18–25,445.36 | 455.99–456.30 | 未守住 |
| 11-15 | 既有 | 规则③ | p1-30-w40 | 26,395.41–26,395.68 | 1,406.23–1,406.62 | 未守住 |
| 11-15 | 既有 | 规则④ | p1-40-w40 | 25,796.07–25,796.24 | 806.88–807.18 | 未守住 |
| 11-15 | 既有 | 逐周并集 | p1-40-w20 | 24,989.06–24,989.19 | -0.13–0.13 | 未守住 |
| 11-15 | 既有 | 双站基准 | p1-50-w50 | 30,510.31–30,510.56 | 5,521.12–5,521.50 | 守住 |

嵌套窗口按前 k 周选型，随后一直检验至所列末周。分子为超过训练期最大所需档的段，分母为后续全部登记段；另列未识别段数。

| 名次 | 选型周数 | 末周 | 设施 | 后续服务 | 新需求 / 总段 | 未识别段 |
| --- | --- | --- | --- | --- | --- | --- |
| 6-10 | 4 | 19 | p1-30-w20 | 未守住 | 2 / 47 | 0 |
| 6-10 | 6 | 12 | p1-30-w20 | 守住 | 0 / 19 | 0 |
| 6-10 | 6 | 19 | p1-30-w20 | 未守住 | 2 / 40 | 0 |
| 6-10 | 8 | 19 | p1-30-w20 | 未守住 | 2 / 35 | 0 |
| 6-10 | 10 | 19 | p1-30-w20 | 未守住 | 2 / 28 | 0 |
| 6-10 | 12 | 19 | p1-30-w20 | 未守住 | 2 / 21 | 0 |
| 6-10 | 14 | 19 | p1-30-w20 | 未守住 | 2 / 18 | 0 |
| 6-10 | 16 | 19 | p1-50-w20 | 未守住 | 1 / 13 | 0 |
| 11-15 | 4 | 19 | p1-30-w20 | 未守住 | 2 / 52 | 0 |
| 11-15 | 6 | 12 | p1-40-w20 | 守住 | 0 / 26 | 0 |
| 11-15 | 6 | 19 | p1-40-w20 | 未守住 | 2 / 46 | 0 |
| 11-15 | 8 | 19 | p1-30-w20 | 未守住 | 2 / 39 | 0 |
| 11-15 | 10 | 19 | p1-40-w20 | 未守住 | 2 / 29 | 0 |
| 11-15 | 12 | 19 | p1-40-w20 | 未守住 | 2 / 20 | 0 |
| 11-15 | 14 | 19 | p1-40-w20 | 未守住 | 2 / 19 | 0 |
| 11-15 | 16 | 19 | p1-50-w40 | 守住 | 0 / 12 | 0 |

| 名次 | 严格隔离登记车日 | 增加 / 移除 | 严格隔离最低设施 | 隔离判定 |
| --- | --- | --- | --- | --- |
| 6-10 | 80 | 0 / 3 | p1-30-w20 | 未守住 |
| 11-15 | 111 | 0 / 1 | p1-50-w20 | 未守住 |

下表列出完成检验期登记服务设施的检验期年费区间（€/年）。

| 名次 | 设施 | 新建 | 既有 |
| --- | --- | --- | --- |
| 6-10 | p1-50-w30 | 14,628.93–14,628.94 | 13,560.37–13,560.38 |
| 6-10 | p1-50-w40 | 15,159.71–15,159.72 | 13,957.57–13,957.58 |
| 6-10 | p1-50-w50 | 17,990.93–17,991.03 | 16,655.23–16,655.32 |
| 6-10 | p2-100-w30 | 20,137.73–20,137.77 | 18,401.31–18,401.35 |
| 6-10 | p2-100-w40 | 20,668.51–20,668.55 | 18,798.52–18,798.56 |
| 6-10 | p2-100-w50 | 23,499.80–23,499.85 | 21,496.24–21,496.29 |
| 6-10 | p2-50-w30 | 18,353.22–18,353.23 | 17,284.65–17,284.66 |
| 6-10 | p2-50-w40 | 18,884.00–18,884.01 | 17,681.86–17,681.87 |
| 6-10 | p2-50-w50 | 21,715.29–21,715.30 | 20,379.58–20,379.60 |
| 11-15 | p1-40-w50 | 24,658.22–24,658.47 | 23,456.08–23,456.34 |
| 11-15 | p1-50-w40 | 24,329.03–24,329.14 | 23,126.90–23,127.00 |
| 11-15 | p1-50-w50 | 27,137.80–27,137.92 | 25,802.09–25,802.22 |
| 11-15 | p2-100-w40 | 29,462.71–29,462.73 | 27,592.72–27,592.74 |
| 11-15 | p2-100-w50 | 32,282.96–32,282.98 | 30,279.40–30,279.42 |
| 11-15 | p2-50-w40 | 28,050.38–28,050.39 | 26,848.25–26,848.26 |
| 11-15 | p2-50-w50 | 30,859.85–30,859.86 | 29,524.15–29,524.16 |

分站可行下限与所选设施相比，6–10 在港区、仓库分别相差 20、10 kW，11–15 分别相差 0、20 kW。两站下限可来自不同整套设施。规则④在耗电乘 1.2 后分别保留 81、107 个车日。严格隔离使 11–15 的最低设施变为 p1-50-w20，两队列的服务判定都保持未守住。6–10 在已扫描窗口中没有持续守住的起点；11–15 从已扫描的 16 周窗口起，余下检验周均守住。

规则①按独占服务段选型，规则②要求全队列共同可行，规则③在规则②的港区配置下提高仓库档位，规则④按加大耗电后的可服务集合筛选。逐周并集取各周最低设施的分量最大值。溢价按区间端点计算，区间跨零时无法据此确定方向。

## 适用范围

这些队列共享时间窗和承运人。登记由基准定义，停靠与充电资格按假设映射，固定设施的排程使用周内全信息。失败诊断只归属于对应服务段；嵌套窗口之间相互重叠。原队列 1–5 只作事后参照。其 F40 在 49 个登记车日中的失败实例与本轮外部结果分列。

## 登记与时间戳

| 项目 | 标识 |
| --- | --- |
| PREREG_M11_EXTERNAL.md | c5907af318cf231f7499fb0ae829b80b5728f0bfa907e7d284f685c62c3ded20 |
| EXECUTION_PLAN.md | 98b4d1e699f60e6e0112fe0e007675544e7f4da38ab3171bbf88db9651bc05aa |
| APPENDIX_EXECUTION_RULES.md | 2d716b9ab7b80d1adf7aaeb0ee88cc38958e6f2bf258c6b5e5b410fd5ecdc359 |
| 清单 SHA-256 | 0bcccae8bfb39756a3098f72d78133a4dbdb11634bb7e3c683343665b42f5b2a |
| P′ | 51ccfe5a2528299e8a21b1e5d03348ef31fbf1f8 |
| F′ | 2fb11e4403fca2c5305ef8f1b260e5ad098fe3c1 |
| 区块高度 | 977496 |
| 区块时间（UTC） | 2026-11-25T09:54:39+00:00 |

## 复核办法

用登记清单核对定稿文件、执行提交和区块证明，再按队列回放四阶段清单、固定服务和购电证书。在执行提交 F′ 的只读入口调用对应队列的 verify(archive, cohort)，其中 archive 为正式阶段归档。随附的 [external_test.json](external_test.json) 提供表格所用的原始精度区间、各期可行设施、严格隔离变化与未定请求。

# External test of sub-fleet charging facilities

For both primary cohorts of the same carrier, using the same calendar split and baseline-defined registration, the facility with the lowest in-sample cost failed to serve every registered duty in the following weeks.

## Study design

Numeric vehicle ranks define primary cohorts 6–10 and 11–15 and descriptive cohort 16–18. Selection ran from 2021-09-27 to 2021-12-19 and evaluation from 2021-12-20 to 2022-02-06. The minimum complete duty-day counts were 68 and 28, and minimum registered counts were 50 and 20. The registration baseline supplied 50 kW at each site.

Annual bill intervals were compared at the rated settings of 35 priced builds for the same registered duties. The primary comparison used official network charges and new connections. Selection and evaluation bills were annualised by 52/12 and 52/7 respectively, in 2025 euros. The primary endpoint used weekly fixed-service certificates for the selected builds. Battery energy at both ends of each continuous duty segment was 150 kWh.

Inputs comprise published trip records and simulated trip energy. Arrival and departure times bound possible parking, and site flags determine port or warehouse eligibility. These windows describe possible charging opportunities. [Data provenance and duty-day quality rules](DATA.md)

## Primary results

Complete days, registered days and feasible builds are shown in selection/evaluation order. A dash denotes an unavailable value following an earlier gate or unresolved evidence. Minimum-cost builds and bills refer to rated operation.

| Rank interval | Complete days | Registered days | Feasible builds | Minimum-cost build | Annual bill (€/yr) | Outcome | Uninformative by construction |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6-10 | 138 / 50 | 83 / 33 | 22 / 9 | p1-30-w20 | 11,859.57–11,859.65 | Failed | No |
| 11-15 | 165 / 55 | 112 / 45 | 20 / 7 | p1-40-w20 | 25,790.48–25,790.61 | Failed | No |
| 16-18 | 72 / 21 | — / — | — / — | — | — | Not evaluable | — |

16-18 did not meet the complete-duty gate. Facility selection, service testing and secondary analyses were skipped.

## Failed weeks and single-truck service

The first prediction tests whether a truck fails even with exclusive access to the selected facility. For a failed segment, the second tests whether at least one required station rating exceeds that station’s training maximum. Each row is a failed segment for a selected facility. Port/warehouse ratings are the minimum priced levels with the other site at its grid maximum. Deficits are in kWh and training maxima and required ratings in kW.

| Ranks | Build | Week of | Dates | Sites | Deficit | Training max | Required | First / second prediction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6-10 | p1-30-w20 | 2022-01-03 | 2022-01-03, 2022-01-04 | Port, Warehouse | 23.678 | 20 / 20 | 50 / 0 | Hit / Hit |
| 6-10 | p1-30-w20 | 2022-01-31 | 2022-01-31 | Port, Warehouse | 0.701 | 20 / 20 | 30 / 30 | Hit / Hit |
| 11-15 | p1-40-w20 | 2022-01-10 | 2022-01-14 | Port, Warehouse | 25.952 | 20 / 20 | 40 / 40 | Hit / Hit |

Sites in the diagnostic table are eligible stops on the segment. With the opposite site at the maximum grid configuration, the failed segment for ranks 11–15 required 40 kW at the warehouse. The multi-day segment for ranks 6–10 required 50 kW at the port.

## Secondary results

| Ranks | Existing minimum | Existing annual bill | Existing outcome | Full-period feasible | Port/warehouse minimum | p1-40-w20 full period | p1-40-w40 full period |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6-10 | p1-30-w20 | 11,191.72–11,191.79 | Failed | 9 | 50 / 30 | Infeasible | Infeasible |
| 11-15 | p1-40-w20 | 24,989.06–24,989.19 | Failed | 7 | 40 / 40 | Infeasible | Infeasible |

| Ranks | Period | Port only | Warehouse only | Both | Neither |
| --- | --- | --- | --- | --- | --- |
| 6-10 | Selection | 8 | 1 | 74 | 0 |
| 6-10 | Evaluation | 5 | 0 | 28 | 0 |
| 11-15 | Selection | 9 | 1 | 102 | 0 |
| 11-15 | Evaluation | 2 | 2 | 41 | 0 |

| Ranks | Connection | Method | Build | Annual bill | Premium over selection minimum | Evaluation |
| --- | --- | --- | --- | --- | --- | --- |
| 6-10 | New | Solo-segment rule | p1-30-w20 | 11,859.57–11,859.65 | -0.07–0.07 | Failed |
| 6-10 | New | Joint-service rule | p1-30-w20 | 11,859.57–11,859.65 | -0.07–0.07 | Failed |
| 6-10 | New | Warehouse restoration rule | p1-30-w40 | 13,048.25–13,048.35 | 1,188.60–1,188.77 | Failed |
| 6-10 | New | Energy-margin rule | p1-30-w30 | 12,524.25–12,524.32 | 664.61–664.74 | Failed |
| 6-10 | New | Weekly union | p1-40-w20 | 12,146.30–12,146.41 | 286.65–286.84 | Failed |
| 6-10 | New | Dual-site baseline | p1-50-w50 | 19,877.71–19,877.80 | 8,018.06–8,018.23 | Held |
| 6-10 | Existing | Solo-segment rule | p1-30-w20 | 11,191.72–11,191.79 | -0.07–0.07 | Failed |
| 6-10 | Existing | Joint-service rule | p1-30-w20 | 11,191.72–11,191.79 | -0.07–0.07 | Failed |
| 6-10 | Existing | Warehouse restoration rule | p1-30-w40 | 12,113.25–12,113.35 | 921.46–921.63 | Failed |
| 6-10 | Existing | Energy-margin rule | p1-30-w30 | 11,722.83–11,722.89 | 531.04–531.17 | Failed |
| 6-10 | Existing | Weekly union | p1-40-w20 | 11,344.87–11,344.99 | 153.08–153.27 | Failed |
| 6-10 | Existing | Dual-site baseline | p1-50-w50 | 17,540.22–17,540.32 | 6,348.43–6,348.60 | Held |
| 11-15 | New | Solo-segment rule | p1-30-w20 | 26,113.03–26,113.21 | 322.42–322.73 | Failed |
| 11-15 | New | Joint-service rule | p1-30-w20 | 26,113.03–26,113.21 | 322.42–322.73 | Failed |
| 11-15 | New | Warehouse restoration rule | p1-30-w40 | 27,330.41–27,330.68 | 1,539.80–1,540.19 | Failed |
| 11-15 | New | Energy-margin rule | p1-40-w40 | 26,864.63–26,864.81 | 1,074.02–1,074.32 | Failed |
| 11-15 | New | Weekly union | p1-40-w20 | 25,790.48–25,790.61 | -0.13–0.13 | Failed |
| 11-15 | New | Dual-site baseline | p1-50-w50 | 32,847.79–32,848.05 | 7,057.19–7,057.57 | Held |
| 11-15 | Existing | Solo-segment rule | p1-30-w20 | 25,445.18–25,445.36 | 455.99–456.30 | Failed |
| 11-15 | Existing | Joint-service rule | p1-30-w20 | 25,445.18–25,445.36 | 455.99–456.30 | Failed |
| 11-15 | Existing | Warehouse restoration rule | p1-30-w40 | 26,395.41–26,395.68 | 1,406.23–1,406.62 | Failed |
| 11-15 | Existing | Energy-margin rule | p1-40-w40 | 25,796.07–25,796.24 | 806.88–807.18 | Failed |
| 11-15 | Existing | Weekly union | p1-40-w20 | 24,989.06–24,989.19 | -0.13–0.13 | Failed |
| 11-15 | Existing | Dual-site baseline | p1-50-w50 | 30,510.31–30,510.56 | 5,521.12–5,521.50 | Held |

Nested windows select on the first k weeks and evaluate through the end week shown. The numerator counts segments exceeding the training maximum. The denominator counts all later registered segments. Unknown segments are reported separately.

| Ranks | Selection weeks | End week | Build | Later service | New / total segments | Unknown |
| --- | --- | --- | --- | --- | --- | --- |
| 6-10 | 4 | 19 | p1-30-w20 | Failed | 2 / 47 | 0 |
| 6-10 | 6 | 12 | p1-30-w20 | Held | 0 / 19 | 0 |
| 6-10 | 6 | 19 | p1-30-w20 | Failed | 2 / 40 | 0 |
| 6-10 | 8 | 19 | p1-30-w20 | Failed | 2 / 35 | 0 |
| 6-10 | 10 | 19 | p1-30-w20 | Failed | 2 / 28 | 0 |
| 6-10 | 12 | 19 | p1-30-w20 | Failed | 2 / 21 | 0 |
| 6-10 | 14 | 19 | p1-30-w20 | Failed | 2 / 18 | 0 |
| 6-10 | 16 | 19 | p1-50-w20 | Failed | 1 / 13 | 0 |
| 11-15 | 4 | 19 | p1-30-w20 | Failed | 2 / 52 | 0 |
| 11-15 | 6 | 12 | p1-40-w20 | Held | 0 / 26 | 0 |
| 11-15 | 6 | 19 | p1-40-w20 | Failed | 2 / 46 | 0 |
| 11-15 | 8 | 19 | p1-30-w20 | Failed | 2 / 39 | 0 |
| 11-15 | 10 | 19 | p1-40-w20 | Failed | 2 / 29 | 0 |
| 11-15 | 12 | 19 | p1-40-w20 | Failed | 2 / 20 | 0 |
| 11-15 | 14 | 19 | p1-40-w20 | Failed | 2 / 19 | 0 |
| 11-15 | 16 | 19 | p1-50-w40 | Held | 0 / 12 | 0 |

| Ranks | Strict-isolation registered days | Added / removed | Strict minimum | Strict outcome |
| --- | --- | --- | --- | --- |
| 6-10 | 80 | 0 / 3 | p1-30-w20 | Failed |
| 11-15 | 111 | 0 / 1 | p1-50-w20 | Failed |

Evaluation-period annual bill intervals for builds serving all registered evaluation duties (€/yr) follow.

| Ranks | Build | New | Existing |
| --- | --- | --- | --- |
| 6-10 | p1-50-w30 | 14,628.93–14,628.94 | 13,560.37–13,560.38 |
| 6-10 | p1-50-w40 | 15,159.71–15,159.72 | 13,957.57–13,957.58 |
| 6-10 | p1-50-w50 | 17,990.93–17,991.03 | 16,655.23–16,655.32 |
| 6-10 | p2-100-w30 | 20,137.73–20,137.77 | 18,401.31–18,401.35 |
| 6-10 | p2-100-w40 | 20,668.51–20,668.55 | 18,798.52–18,798.56 |
| 6-10 | p2-100-w50 | 23,499.80–23,499.85 | 21,496.24–21,496.29 |
| 6-10 | p2-50-w30 | 18,353.22–18,353.23 | 17,284.65–17,284.66 |
| 6-10 | p2-50-w40 | 18,884.00–18,884.01 | 17,681.86–17,681.87 |
| 6-10 | p2-50-w50 | 21,715.29–21,715.30 | 20,379.58–20,379.60 |
| 11-15 | p1-40-w50 | 24,658.22–24,658.47 | 23,456.08–23,456.34 |
| 11-15 | p1-50-w40 | 24,329.03–24,329.14 | 23,126.90–23,127.00 |
| 11-15 | p1-50-w50 | 27,137.80–27,137.92 | 25,802.09–25,802.22 |
| 11-15 | p2-100-w40 | 29,462.71–29,462.73 | 27,592.72–27,592.74 |
| 11-15 | p2-100-w50 | 32,282.96–32,282.98 | 30,279.40–30,279.42 |
| 11-15 | p2-50-w40 | 28,050.38–28,050.39 | 26,848.25–26,848.26 |
| 11-15 | p2-50-w50 | 30,859.85–30,859.86 | 29,524.15–29,524.16 |

Relative to the selected hardware, ranks 6–10 had gaps of 20 and 10 kW at the port and warehouse. Ranks 11–15 had gaps of 0 and 20 kW. Site minima can come from different builds. Scaling energy by 1.2 under the margin rule retained 81 and 107 days respectively. Strict isolation changed the ranks 11–15 selection to p1-50-w20. Both service outcomes remained failures. Ranks 6–10 had no scanned window after which all later windows held. Ranks 11–15 served all later evaluation weeks from the scanned 16-week window.

The solo rule sizes against individual segments. The joint rule requires fleet-wide feasibility. The warehouse restoration rule increases warehouse capacity with the joint rule’s port configuration. The margin rule screens against serviceable duties under higher energy use. The weekly union takes component-wise maxima across weekly minima. A premium interval spanning zero leaves its direction undetermined.

## Scope

These cohorts share a carrier and calendar windows. Registration is baseline-defined, parking and charging eligibility are modelled, and fixed-facility schedules use full weekly information. Diagnostics apply to the observed segments and the nested windows overlap. Original ranks 1–5 are a post hoc reference only. Their F40 failure among 49 registered days is reported separately from the external outcomes.

## Registration and timestamp

| Item | Identifier |
| --- | --- |
| PREREG_M11_EXTERNAL.md | c5907af318cf231f7499fb0ae829b80b5728f0bfa907e7d284f685c62c3ded20 |
| EXECUTION_PLAN.md | 98b4d1e699f60e6e0112fe0e007675544e7f4da38ab3171bbf88db9651bc05aa |
| APPENDIX_EXECUTION_RULES.md | 2d716b9ab7b80d1adf7aaeb0ee88cc38958e6f2bf258c6b5e5b410fd5ecdc359 |
| Manifest SHA-256 | 0bcccae8bfb39756a3098f72d78133a4dbdb11634bb7e3c683343665b42f5b2a |
| P′ | 51ccfe5a2528299e8a21b1e5d03348ef31fbf1f8 |
| F′ | 2fb11e4403fca2c5305ef8f1b260e5ad098fe3c1 |
| Block height | 977496 |
| Block time (UTC) | 2026-11-25T09:54:39+00:00 |

## Verification

Check the registration files, execution commit and block proof against the manifest. Replay each cohort’s four stage manifests, fixed-service certificates and purchase certificates. At execution commit F′, call verify(archive, cohort) for each cohort with the formal stage archive. The accompanying [external_test.json](external_test.json) contains full-precision intervals, feasible builds, strict-isolation changes and unresolved requests.
