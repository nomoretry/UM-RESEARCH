# 子车队充电设施外部检验

在同一承运人、同一日历划分、由基准设施定义登记的条件下，两个主队列按样本内成本最低选出的设施都没能守住之后几周的服务。

## 检验设计

按车辆数值名次分组。主队列为 6–10、11–15，次要队列为 16–18。选型期为 2021-09-27 至 2021-12-19，检验期为 2021-12-20 至 2022-02-06。完整车日门槛分别为 68、28，登记车日门槛分别为 50、20。以港区和仓库各 50 kW 的基准逐周登记。

在 35 套有价硬件的额定点上比较同一登记服务的年费区间。主口径为官方网费、新建接入，按 52/12 年化选型账单，按 52/7 年化检验账单，均以 2025 年欧元计。主终点依据入选设施在检验期各周的固定服务证书判定。同一车连续服务段的首末电量均为 150 kWh。

输入使用公开行程记录及其模拟耗电。到达和发车时刻界定停靠上界，港区、仓库资格按站点标志映射；这些窗口不代表实际发生过充电。[数据来源与车日质量规则](DATA.md)

双站基准用 50/50 kW 登记服务，因此它守住检验期是按构造成立，对各定容方法没有区分力。比较同一选型期、同一服务和新建口径时，基准按 100/75 kW 接入，有价网格的 p1-50-w50 按 50/50 kW 接入。二者的接入年费分别为 €2,337.49 和 €1,335.71，解释了同名硬件的账单差额。

## 主结果

完整、登记和可行栏依次列出选型期与检验期；可行数按设施计。划线表示此前门槛已确定不满足或所需数值未判清。最低设施及年费按额定点列示。

| 名次区间 | 完整车日 | 登记车日 | 可行设施 | 最低设施 | 年费（€/年） | 判定 | 按构造无信息 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6-10 | 138 / 50 | 83 / 33 | 22 / 9 | p1-30-w20 | 11,859.57–11,859.65 | 未守住 | 否 |
| 11-15 | 165 / 55 | 112 / 45 | 20 / 7 | p1-40-w20 | 25,790.48–25,790.61 | 未守住 | 否 |
| 16-18 | 72 / 21 | — / — | — / — | — | — | 不可评 | — |

16-18 未达到完整车日门槛，后续选型、主服务检验和次要分析跳过。

两个主队列的最低集合均无按构造成员，有信息的外部子车队分母为 2。次要队列不计入分母。最终未定请求为 0。

## 失败周与独占服务段

预测一检查失败周中是否存在单车独占所选设施也无法完成的段。预测二检查这样的段是否至少有一站所需档严格高于该站训练期最大档。每行对应一个所选设施的失败段。港/仓为固定另一站在网格最大配置时的最低有价档。缺口以 kWh 计，训练最大档与检验所需档均以 kW 计。

| 名次 | 设施 | 周起始 | 日期 | 站点 | 缺口 | 训练最大档 | 所需档 | 预测一 / 二 | 约束类型 | 独占可达电量上界（kWh） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6-10 | p1-30-w20 | 2022-01-03 | 2022-01-03, 2022-01-04 | 港区, 仓库 | 23.678 | 20 / 20 | 50 / 0 | 命中 / 命中 | 段末电量 | 126.322 |
| 6-10 | p1-30-w20 | 2022-01-31 | 2022-01-31 | 港区, 仓库 | 0.701 | 20 / 20 | 30 / 30 | 命中 / 命中 | 行程储备 | 29.299 |
| 11-15 | p1-40-w20 | 2022-01-10 | 2022-01-14 | 港区, 仓库 | 25.952 | 20 / 20 | 40 / 40 | 命中 / 命中 | 段末电量 | 124.048 |

诊断表中的站点是该段可用的停靠位置。依次把另一站设到网格最大配置后，11–15 的失败段在仓库需达到 40 kW；6–10 的跨日段在港区需达到 50 kW。

按表的次序，三段所需的港区/仓库档分别为 50/0、30/30、40/40 kW。6–10 的 01-03 至 01-04 是跨两个车日的一段，证书只排除了整段可行性，无法识别其中哪一天缺失。01-31 的 29.299 kWh 出现在 13:55 的行程结束后，该时刻检验行程储备。预测二的定义在原队列彩排后修订了 2 次，均早于外部开封。

## 次要结果

| 名次 | 既有最低设施 | 既有年费 | 既有判定 | 全期可行数 | 港/仓最低档 | p1-40-w20 全期 | p1-40-w40 全期 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6-10 | p1-30-w20 | 11,191.72–11,191.79 | 未守住 | 9 | 50 / 30 | 不可行 | 不可行 |
| 11-15 | p1-40-w20 | 24,989.06–24,989.19 | 未守住 | 7 | 40 / 40 | 不可行 | 不可行 |

下表按车日统计每个连续段可用的站点。

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

严格隔离对照移除借助跨期凭据形成的选型期窗口，重做登记和选型，再在同一已封存检验集合判服务。两个外部主队列用前 6 周选、随后 6 周检验都守住。11–15 的 16 周选型窗口已含 01-10 失败周，只余 3 周检验。这些重叠窗口不足以说明延长选型期能避免服务失败。

## 适用范围

这些队列共享时间窗和承运人。登记由基准定义，停靠与充电资格按假设映射，固定设施的排程使用周内全信息。失败诊断只归属于对应服务段；嵌套窗口之间相互重叠。原队列 1–5 只作事后参照。其 F40 在 49 个登记车日中的失败实例与本轮外部结果分列。

三个可评队列共用同一日历，登记由基准定义。所有失败都发生在 2022 年一月，样本外效应与季节无法分开。三个外部失败段的物理约束有别，不能据此认定同一机制、给出所需数据量或外推到其他承运人。

### 怎么读这个结果

三个可评子车队为 1–5（预登记的第二次留出，本文只作事后参照）、6–10 和 11–15。16–18 不可评。外部三个失败段两站均有可充窗口，1–5 的 01-19 仅有仓库窗口。共同点是至少一站所需档高于选型期任何一段，其中一个外部段只差 0.70 kWh。

### 开封后的描述性比较

下表按额定点、官方网费和新建接入排列封存的选型期年费，其中原队列取重彩排账本。每个队列中，比两期均可行的最低设施更便宜的设计后来全部失败。差额相对当时选出的最低设施，百分比以其选型期账单为分母，用相反端点给出区间。

| 名次 | 两期均可行的最低设施 | 选型期费用名次 | 选型年费（€/年） | 多付（€/年） | 多付（%） | 更便宜且后续失败的设施数 |
| --- | --- | --- | --- | --- | --- | --- |
| 1-5 | p1-40-w40 | 7 | 18,848.74–18,848.98 | 1,206.95–1,207.40 | 6.841–6.844 | 6 |
| 6-10 | p1-50-w30 | 9 | 15,517.69–15,517.80 | 3,658.05–3,658.22 | 30.844–30.846 | 8 |
| 11-15 | p1-50-w40 | 9 | 29,038.06–29,038.20 | 3,247.45–3,247.71 | 12.592–12.593 | 8 |

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

### 正式封存时序

| 节点 | 时刻（含时区） |
| --- | --- |
| 清单 | 2026-11-25T09:43:08.992675+00:00 |
| 比特币区块 | 2026-11-25T09:54:39+00:00 |
| 开封授权 | 2026-11-25T18:34:39+08:00 |
| 首个求解请求 | 2026-11-25T10:35:30.440502+00:00 |

| 队列 | 阶段 | 封存时刻 |
| --- | --- | --- |
| 6-10 | 1 | 2026-11-25T18:35:14+08:00 |
| 11-15 | 1 | 2026-11-25T18:35:21+08:00 |
| 6-10 | 2 | 2026-11-25T18:36:45+08:00 |
| 11-15 | 2 | 2026-11-25T18:46:05+08:00 |
| 6-10 | 3 | 2026-11-25T18:46:20+08:00 |
| 11-15 | 3 | 2026-11-25T18:46:35+08:00 |
| 6-10 | 4 | 2026-11-25T18:50:00+08:00 |
| 11-15 | 4 | 2026-11-25T18:53:06+08:00 |
| 16-18 | 1 | 2026-11-25T18:53:14+08:00 |
| 16-18 | 2 | 2026-11-25T18:56:50+08:00 |
| 16-18 | 3 | 2026-11-25T18:56:58+08:00 |
| 16-18 | 4 | 2026-11-25T18:57:04+08:00 |

两份澄清界定了共享源内存过滤以及记录写入失误的处理；重新冻结改了 3 处（归属、执行提交和墙钟限时条款）。次要队列阶段 2 因空证据目录封存失败，先记录已见文件并核对散列，再以空占位完成封存，全程未重跑该阶段。11–15 的 p1-50-w20 在 2021-12-06 当周达到 300 秒时限，区间宽 €0.065/周，按冻结规则结算。

### 逐周完整车日

| 周起始 | 1-5 | 6-10 | 11-15 | 16-18 |
| --- | --- | --- | --- | --- |
| 2021-09-27 | 12 | 14 | 12 | 7 |
| 2021-10-04 | 13 | 15 | 15 | 5 |
| 2021-10-11 | 12 | 11 | 9 | 5 |
| 2021-10-18 | 14 | 12 | 15 | 8 |
| 2021-10-25 | 16 | 18 | 13 | 7 |
| 2021-11-01 | 6 | 6 | 11 | 6 |
| 2021-11-08 | 9 | 11 | 14 | 7 |
| 2021-11-15 | 16 | 6 | 16 | 5 |
| 2021-11-22 | 13 | 8 | 14 | 5 |
| 2021-11-29 | 8 | 11 | 16 | 7 |
| 2021-12-06 | 8 | 11 | 20 | 6 |
| 2021-12-13 | 9 | 15 | 10 | 4 |
| 2021-12-20 | 8 | 7 | 6 | 2 |
| 2021-12-27 | 0 | 0 | 0 | 0 |
| 2022-01-03 | 6 | 6 | 5 | 1 |
| 2022-01-10 | 14 | 8 | 11 | 7 |
| 2022-01-17 | 10 | 5 | 14 | 3 |
| 2022-01-24 | 9 | 12 | 7 | 6 |
| 2022-01-31 | 10 | 12 | 12 | 2 |

开封前已知原队列结果及已发布的 42,701 趟行程、承运人 1 的 6,888 趟和原队列 1,904 趟。2026-11-21 的汇总还披露外部 585 个完整车日，其中 189 个落在前 6 周，承运人共 18 辆车；外部、原队列每车每周约 2.42、2.43 个完整车日。规则是在原队列第二次留出开封后制定的。共享源按队列过滤，阶段一在选型前给出了检验期逐周完整车日和分期行程数。期后相邻发车只界定截至午夜的停靠窗口。全数据的能耗缺失、正距离和带符号净耗电等既有披露见预登记信息披露节。

## 复核办法

用登记清单核对定稿文件、执行提交和区块证明，再按队列回放四阶段清单、固定服务和购电证书。在执行提交 F′ 的只读入口调用对应队列的 verify(archive, cohort)，其中 archive 为正式阶段归档。随附的 [external_test.json](external_test.json) 提供表格所用的原始精度区间、各期可行设施、严格隔离变化与未定请求。

[全部额定设计](external_designs.json)和[失败段事件序列](external_segments.json)提供逐周判定、账单及可达电量轨迹。

完整证书回放需要离线归档和冻结提交上的 `um_charging.m11_external_run.verify`。仅核对仓库内公开报告与 JSON 可运行以下命令。

```sh
python -B -m pytest -q -p no:cacheprovider tests/test_published_external_test.py
```

# External test of sub-fleet charging facilities

For both primary cohorts of the same carrier, using the same calendar split and baseline-defined registration, the facility with the lowest in-sample cost did not complete all registered duties in the following weeks.

## Study design

Numeric vehicle ranks define primary cohorts 6–10 and 11–15 and descriptive cohort 16–18. Selection ran from 2021-09-27 to 2021-12-19 and evaluation from 2021-12-20 to 2022-02-06. The minimum complete duty-day counts were 68 and 28, and minimum registered counts were 50 and 20. The registration baseline supplied 50 kW at each site.

Annual bill intervals were compared at the rated settings of 35 priced builds for the same registered duties. The primary comparison used official network charges and new connections. Selection and evaluation bills were annualised by 52/12 and 52/7 respectively, in 2025 euros. The primary endpoint used weekly fixed-service certificates for the selected builds. Battery energy at both ends of each continuous duty segment was 150 kWh.

Inputs comprise published trip records and simulated trip energy. Arrival and departure times bound possible parking, and site flags determine port or warehouse eligibility. These windows describe possible charging opportunities. [Data provenance and duty-day quality rules](DATA.md)

The 50/50 kW dual-site baseline defines registered service. Its success follows by construction and offers no evidence for a sizing method. For the same selection period and duties under new connections, the baseline contracts 100/75 kW and the priced p1-50-w50 grid build contracts 50/50 kW. Their annual connection charges of €2,337.49 and €1,335.71 account for the difference between bills for the identically labelled hardware.

## Primary results

Complete days, registered days and feasible builds are shown in selection/evaluation order. A dash denotes an unavailable value following an earlier gate or unresolved evidence. Minimum-cost builds and bills refer to rated operation.

| Rank interval | Complete days | Registered days | Feasible builds | Minimum-cost build | Annual bill (€/yr) | Outcome | Uninformative by construction |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6-10 | 138 / 50 | 83 / 33 | 22 / 9 | p1-30-w20 | 11,859.57–11,859.65 | Failed | No |
| 11-15 | 165 / 55 | 112 / 45 | 20 / 7 | p1-40-w20 | 25,790.48–25,790.61 | Failed | No |
| 16-18 | 72 / 21 | — / — | — / — | — | — | Not evaluable | — |

16-18 did not meet the complete-duty gate. Facility selection, service testing and secondary analyses were skipped.

Neither primary cohort had a selected member that held by construction. The informative external denominator is 2 sub-fleets. The secondary cohort is excluded. The final count of undetermined requests is 0.

## Failed weeks and single-truck service

The first prediction tests whether a truck fails even with exclusive access to the selected facility. For a failed segment, the second tests whether at least one required station rating exceeds that station’s training maximum. Each row is a failed segment for a selected facility. Port/warehouse ratings are the minimum priced levels with the other site at its grid maximum. Deficits are in kWh and training maxima and required ratings in kW.

| Ranks | Build | Week of | Dates | Sites | Deficit | Training max | Required | First / second prediction | Constraint | Exclusive-access upper bound (kWh) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6-10 | p1-30-w20 | 2022-01-03 | 2022-01-03, 2022-01-04 | Port, Warehouse | 23.678 | 20 / 20 | 50 / 0 | Hit / Hit | Terminal energy | 126.322 |
| 6-10 | p1-30-w20 | 2022-01-31 | 2022-01-31 | Port, Warehouse | 0.701 | 20 / 20 | 30 / 30 | Hit / Hit | Post-trip reserve | 29.299 |
| 11-15 | p1-40-w20 | 2022-01-10 | 2022-01-14 | Port, Warehouse | 25.952 | 20 / 20 | 40 / 40 | Hit / Hit | Terminal energy | 124.048 |

Sites in the diagnostic table are eligible stops on the segment. With the opposite site at the maximum grid configuration, the failed segment for ranks 11–15 required 40 kW at the warehouse. The multi-day segment for ranks 6–10 required 50 kW at the port.

In table order, the required port/warehouse ratings were 50/0, 30/30 and 40/40 kW. For ranks 6–10, 01-03 through 01-04 was a single segment spanning two duty-days. The certificate rules out completing the entire segment and leaves the missed day unidentified. On 01-31 the 29.299 kWh bound was reached after the trip ending at 13:55, when the trip reserve applied. The second prediction was revised 2 times after rehearsal on the reference cohort, before external opening.

## Secondary results

| Ranks | Existing minimum | Existing annual bill | Existing outcome | Full-period feasible | Port/warehouse minimum | p1-40-w20 full period | p1-40-w40 full period |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6-10 | p1-30-w20 | 11,191.72–11,191.79 | Failed | 9 | 50 / 30 | Infeasible | Infeasible |
| 11-15 | p1-40-w20 | 24,989.06–24,989.19 | Failed | 7 | 40 / 40 | Infeasible | Infeasible |

The following table counts duty-days by the charging sites available on their continuous segment.

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

Strict isolation removes selection-period windows supported by cross-boundary records, repeats registration and selection, then tests the resulting build on the same sealed evaluation duties. Both primary external cohorts held when selected on the first 6 weeks and tested on the next 6. For ranks 11–15, the 16-week selection already includes the failed week of 01-10 and leaves only 3 evaluation weeks. These overlapping windows do not establish that longer histories prevent failure.

## Scope

These cohorts share a carrier and calendar windows. Registration is baseline-defined, parking and charging eligibility are modelled, and fixed-facility schedules use full weekly information. Diagnostics apply to the observed segments and the nested windows overlap. Original ranks 1–5 are a post hoc reference only. Their F40 failure among 49 registered days is reported separately from the external outcomes.

The three evaluable sub-fleets share the same calendar and baseline-defined registration. All failures occurred in January of 2022, so out-of-sample effects cannot be separated from seasonality. The three external segments had different binding constraints. These observations establish neither a single mechanism nor a data-length recommendation and do not generalise to other carriers.

### Reading the result

The three evaluable sub-fleets are ranks 1–5 (the preregistered second holdout, used here as a post hoc reference), 6–10 and 11–15. Ranks 16–18 were not evaluable. All three external failed segments had charging windows at both sites. For ranks 1–5 on 01-19 only the warehouse was available. In every case at least one station required a higher rating than on any selection-period segment. One external segment missed by just 0.70 kWh.

### Post-opening descriptive comparison

The table ranks sealed selection-period bills at rated operation with official network charges and new connections. The reference bills come from the repeat rehearsal. In each cohort, every build cheaper than the least costly one that served both periods later failed. Premiums are relative to the build originally selected. Percentage bounds use its selection bill as the denominator, pairing opposite interval endpoints.

| Ranks | Cheapest build serving both periods | Selection cost rank | Selection bill (€/yr) | Premium (€/yr) | Premium (%) | Cheaper builds failing evaluation |
| --- | --- | --- | --- | --- | --- | --- |
| 1-5 | p1-40-w40 | 7 | 18,848.74–18,848.98 | 1,206.95–1,207.40 | 6.841–6.844 | 6 |
| 6-10 | p1-50-w30 | 9 | 15,517.69–15,517.80 | 3,658.05–3,658.22 | 30.844–30.846 | 8 |
| 11-15 | p1-50-w40 | 9 | 29,038.06–29,038.20 | 3,247.45–3,247.71 | 12.592–12.593 | 8 |

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

### Formal chronology

| Event | Timestamp with offset |
| --- | --- |
| Manifest | 2026-11-25T09:43:08.992675+00:00 |
| Bitcoin block | 2026-11-25T09:54:39+00:00 |
| Opening authorisation | 2026-11-25T18:34:39+08:00 |
| First solve request | 2026-11-25T10:35:30.440502+00:00 |

| Cohort | Stage | Sealed at |
| --- | --- | --- |
| 6-10 | 1 | 2026-11-25T18:35:14+08:00 |
| 11-15 | 1 | 2026-11-25T18:35:21+08:00 |
| 6-10 | 2 | 2026-11-25T18:36:45+08:00 |
| 11-15 | 2 | 2026-11-25T18:46:05+08:00 |
| 6-10 | 3 | 2026-11-25T18:46:20+08:00 |
| 11-15 | 3 | 2026-11-25T18:46:35+08:00 |
| 6-10 | 4 | 2026-11-25T18:50:00+08:00 |
| 11-15 | 4 | 2026-11-25T18:53:06+08:00 |
| 16-18 | 1 | 2026-11-25T18:53:14+08:00 |
| 16-18 | 2 | 2026-11-25T18:56:50+08:00 |
| 16-18 | 3 | 2026-11-25T18:56:58+08:00 |
| 16-18 | 4 | 2026-11-25T18:57:04+08:00 |

Two clarifications addressed in-memory filtering of the shared source and correction of a written record. The registration changed in 3 places before refreezing (attribution, execution commit and wall-clock clause). Secondary stage 2 initially failed to seal an empty evidence directory. The files already seen were recorded, their hashes checked and the directory sealed with an empty placeholder, without rerunning the stage. For ranks 11–15, p1-50-w20 in the week of 2021-12-06 reached the 300-second limit, with an interval width of €0.065/week accepted under the frozen rule.

### Weekly complete duty-days

| Week starting | 1-5 | 6-10 | 11-15 | 16-18 |
| --- | --- | --- | --- | --- |
| 2021-09-27 | 12 | 14 | 12 | 7 |
| 2021-10-04 | 13 | 15 | 15 | 5 |
| 2021-10-11 | 12 | 11 | 9 | 5 |
| 2021-10-18 | 14 | 12 | 15 | 8 |
| 2021-10-25 | 16 | 18 | 13 | 7 |
| 2021-11-01 | 6 | 6 | 11 | 6 |
| 2021-11-08 | 9 | 11 | 14 | 7 |
| 2021-11-15 | 16 | 6 | 16 | 5 |
| 2021-11-22 | 13 | 8 | 14 | 5 |
| 2021-11-29 | 8 | 11 | 16 | 7 |
| 2021-12-06 | 8 | 11 | 20 | 6 |
| 2021-12-13 | 9 | 15 | 10 | 4 |
| 2021-12-20 | 8 | 7 | 6 | 2 |
| 2021-12-27 | 0 | 0 | 0 | 0 |
| 2022-01-03 | 6 | 6 | 5 | 1 |
| 2022-01-10 | 14 | 8 | 11 | 7 |
| 2022-01-17 | 10 | 5 | 14 | 3 |
| 2022-01-24 | 9 | 12 | 7 | 6 |
| 2022-01-31 | 10 | 12 | 12 | 2 |

Pre-opening information included the reference results and published counts of 42,701 trips, including carrier 1’s 6,888 and the reference cohort’s 1,904. Aggregates dated 2026-11-21 disclosed 585 complete external duty-days, including 189 in the first 6 weeks, and 18 trucks for the carrier. External and reference densities were approximately 2.42 and 2.43 duty-days per truck-week. The rules were written after opening the reference cohort’s second holdout. The shared source was filtered by cohort. Before selection, stage one disclosed weekly complete evaluation duty-days and trip counts by period. Adjacent post-period departure records bounded parking at midnight. The registration disclosure also records previously published coverage of missing energy, positive distances and signed net energy.

## Verification

Check the registration files, execution commit and block proof against the manifest. Replay each cohort’s four stage manifests, fixed-service certificates and purchase certificates. At execution commit F′, call verify(archive, cohort) for each cohort with the formal stage archive. The accompanying [external_test.json](external_test.json) contains full-precision intervals, feasible builds, strict-isolation changes and unresolved requests.

[Rated designs](external_designs.json) and [failed-segment events](external_segments.json) provide weekly outcomes, bills and reachable energy traces.

Full certificate replay requires the offline archive and `um_charging.m11_external_run.verify` at the frozen commit. The following command checks the published report against the repository JSON.

```sh
python -B -m pytest -q -p no:cacheprovider tests/test_published_external_test.py
```
