# 检索与筛选记录（2026-11-18）

**定位**：定向综述与项目诊断，不是系统综述。检索服务于 UM 主线：固定运输服务下的电池限制、可充电窗口、接口数量、站点接入容量、设施投资与运行费用。单人筛选，没有第二评审，也没有做 PRISMA 意义上的完整检索。因此，“本轮没有检索到”只表示在下述来源和检索式范围内未见，不等于该问题无人研究。

## 来源

| 来源 | 日期（UTC） | 用法 | 原始结果位置 |
|---|---|---|---|
| OpenAlex API（经 citation-management 技能 `search_openalex.py`；技能库见 Kassis 等 2026） | 2026-11-18 09:35 | 8 组检索式，年份 2021–2026，按相关性各取前 25 条 | 离线 `sources/q*.json`、`queries.tsv` |
| 通用网页检索 | 2026-11-18 | 6 组，补充跨日 SOC、接枪/准备时间、电池与设施、未完成服务价值、两条书目核实 | 本文件下表 |
| 用户已有 PDF | 2026-11-18 | 研究仓库 `reserach/`、`文献学习/` 与父目录未提交资料中的 40 个 PDF，抽取首页识别 | 离线 `extracts/index.json`；这 18 个仓库内 PDF 已于 2026-11-19 移出仓库，新旧文件名对照见离线库 `literature/papers/INDEX.md` |
| 已有项目笔记 | 2026-11-09 | Ye 2024、Wang/Moura 2025、Xiao 2025（当时仅预览） | `docs/literature/20261109/` |
| 开放全文下载 | 2026-11-18 | arXiv:2510.13100、UC Davis 报告 UCD-ITS-RR-23-63；IJPR 2024 出版社返回 HTTP 403 | 离线 `pdfs/` |

## OpenAlex 检索式

| 编号 | 主题 | 检索式 |
|---|---|---|
| q1 | 跨日 SOC、夜间补电 | electric truck depot charging scheduling state of charge overnight multi-day |
| q2 | 电池与设施共同设计 | battery size charging infrastructure joint optimization electric trucks |
| q3 | 停靠与放行 | electric truck charging dwell time loading unloading charging opportunity logistics hub |
| q4 | 接口与接入容量 | charging station capacity number of chargers grid connection electric freight fleet depot |
| q5 | 港口集卡 | electric drayage trucks port charging infrastructure planning |
| q6 | 电价与需量费 | demand charges time-of-use tariff electric truck fleet charging cost depot |
| q7 | 车队数据与验证 | electric truck fleet GPS data charging infrastructure simulation validation real-world |
| q8 | 固定线路 | fixed route electric vehicle charging station location capacity allocation |

## 网页检索式

1. electric truck fleet charging scheduling multi-day rolling horizon state of charge carry-over depot overnight optimization
2. electric vehicle charging plug-in time connection setup time charger handover scheduling depot trucks buses optimization
3. battery capacity and charging infrastructure co-design electric trucks optimization battery sizing charger power depot fleet 2023 2024 2025
4. electric truck depot charging infrastructure sizing unmet demand penalty service level marginal value additional charger demand charge
5. Mercedes-Benz eActros 600 battery capacity 621 kWh usable（仅用于服务缺口研究中的背景参照）
6. Frank Oebel Gnann "Optimizing Charging Infrastructure for Truck Depots" EVS38（书目核实）

## 计数

| 阶段 | 数量 | 说明 |
|---|---:|---|
| OpenAlex 返回 | 200 | 8 × 25 |
| OpenAlex 去重 | 159 | 按 DOI 或题名 |
| 本地 PDF 文件 | 40 | 去重后约 26 部作品，其中 2 份非研究文献（招聘文件、数据集文档方法） |
| 标题/摘要筛选后列入候选 | 24 条记录 / 23 项研究 | 下表“纳入”；#4 与 #12 为同一研究 |
| 精读（指定章节或全文） | 9 | 见 [CARDS.md](CARDS.md) P1–P9 |
| 全文未取得 | 3 | IJPR 2024（403）、SSRN 2026（无摘要）、EVS38 2025（仅机构库题录） |

记录（record）与研究（study）分开：Bertucci 2024（ACC）与 Bertucci 2025（TTE）是同一研究的两份报告，按一项研究计。Ye 2024 的 arXiv v1 与刊版同理。

## 纳入标准

1. 研究对象为电动货车（重卡、集卡、中型配送车）或固定时刻表的电动车队（公交只在主题 3 缺少货车文献时纳入）；
2. 决策至少涉及以下之一：充电调度与电量轨迹、接口或充电器数量、站点功率或接入容量、电池容量、充电资格或停靠时间；
3. 给出可检查的模型、实验或数据；
4. 年份以 2021–2026 为主，保留被多篇引用的基础文献（如 Pelletier 2018）。

## 排除理由（主要类别）

| 类别 | 例子 | 理由 |
|---|---|---|
| 乘用车或网约车 | 城市 PEV 选址（2016、2018）、网约车快充需求 | 车辆与服务结构不同，不涉及固定货运任务 |
| 公共走廊网络规划 | 欧洲/德国公共快充网络、高速公路网络 | 与 UM 的场站/站点设施问题相关性低；仅保留 Speth 2025 与 Balke 2024 作为数据和容量约束参照 |
| 无线/电气化道路 | 港口无线充电、ERS 成本 | 技术路线不在 UM 范围 |
| 综述与行业稿 | 通用充电综述、厂商博客 | 不提供可核查模型；只作背景，未纳入证据表 |
| 换电专项 | 多篇换电网络 | UM 当前不做换电；保留已精读的 Wang/Moura 2025 |
| 无关文献 | 共享出行潜在需求、商场停车场、Physica A 充电桩配置、数据集文档方法 | 与主题无关 |

## 纳入候选（24 条）

| # | 文献 | 主题 | 阅读程度 | 处理 |
|---:|---|---|---|---|
| 1 | Pelletier, Jabali, Laporte 2018, TR-B | 1、4、5 | 指定章节 | 精读 P1 |
| 2 | Ye, Yu, Wei 2024, TR-D | 1、2、4 | 指定章节（刊版补核） | 精读 P2 |
| 3 | Xiao et al. 2025, TR-C | 3、4、5 | 指定章节（全文） | 精读 P3 |
| 4 | Bertucci, Salazar, Hofman 2025, IEEE TTE | 1、2、4、6 | 指定章节 | 精读 P4 |
| 5 | Davatgari et al. 2024, EJOR | 1、4 | 指定章节 | 精读 P5 |
| 6 | Wu, Zhang, Chen 2023, IEEE TITS | 2、4 | 指定章节 | 精读 P6 |
| 7 | Balke et al. 2024, IEEE ITSC | 6 | 指定章节 | 精读 P7（数据来源核查） |
| 8 | Ding et al. 2025, arXiv | 1、3、5 | 指定章节 | 精读 P8 |
| 9 | Wang, Miller, Fulton 2023 报告（2025 期刊版未读） | 5 | 报告结论 | 精读 P9 |
| 10 | Froger et al. 2022, Transportation Science | 4 | 摘要（本地全文未精读） | 下一轮 |
| 11 | Wang, Martinez, … Moura 2025, IEEE TSG | 2、4 | 2026-11-09 全文 | 引用已有卡 |
| 12 | Bertucci, Hofman, Salazar 2024, ACC | 2、4 | 元数据 | 与 #4 同一研究 |
| 13 | Speth, Plötz, Wietschel 2025, TR-A | 4、6 | 摘要 | 背景 |
| 14 | Shoman 等 2023, TR-D | 1、2 | 摘要 | 背景（夜间充电器数量） |
| 15 | Wang 等 2025, IJPR 63(10)（2024 年在线发表） | 3 | 摘要（全文 403，2026-11-18） | 全文缺口 |
| 16 | Song 等 2024, WEVJ | 1、5 | 摘要 | 背景（需量费、365 天） |
| 17 | Biedenbach, Strunz 2024, WEVJ | 5 | 摘要 | 背景（场站多用途） |
| 18 | Link, Frank, Speth et al. 2026, SSRN | 1、6 | 元数据 | 全文缺口，下一轮优先 |
| 19 | Bragin, Ye, Yu 2024, TR-C | 3、5 | 摘要（本地全文未精读） | 下一轮 |
| 20 | Zhao et al. 2023, IEEE TITS | 4 | 摘要（本地全文未精读） | 背景 |
| 21 | Alp, Tan, Udenio 2022, Omega | 2、4 | 摘要 | 背景（拥堵与车队更替） |
| 22 | Walz, Rudion 2024, Energies | 3、6 | 摘要 | 背景（物流中心到离分布） |
| 23 | Balke, Adenaw 2023, Data in Brief（DT-CARGO） | 6 | 摘要 | UM 数据来源 |
| 24 | Fresia et al. 2025, SEGAN | 2、4 | 项目已复算 | 引用 `studies/fresia-2025/` |

另：Frank, Oebel, Gnann 2025（EVS38）为 UM 接口成本来源，不在纳入表中；2026-11-18 补读了成本相关章节（精读卡 S1）。

## 主题覆盖评估

| 主题 | 覆盖 | 说明 |
|---|---|---|
| 1 跨日 SOC 与夜间补电 | 中 | Pelletier、Bertucci、Ding 直接处理；未检索到专门比较“日独立”与“跨日结转”对设施规模影响的货车研究 |
| 2 电池与设施共同设计 | 中 | Ye（电池为决策）、Wu（电池情景）；Bertucci 名为协同设计但电池未优化 |
| 3 停靠、放行、接枪与换车时间 | 弱 | 货车文献只见充电事件数上限、禁止相邻换枪、停车时段有效可用比例、排队；含准备时间的公交研究全文未取得 |
| 4 接口占用、共享功率与接入容量 | 中—强 | Froger、Xiao、Davatgari、Pelletier 区分接口数与功率；Ye 只有 kW 容量 |
| 5 边际收益、电价与未完成服务价值 | 弱—中 | 需量费有多篇；未完成服务多以延误罚金或放弃变量表示，未见与 UM 相同口径的“服务价值” |
| 6 数据来源与外部验证 | 中 | 多数研究用模拟或单一运营商数据；独立样本外检验少见（Bertucci 有训练/测试划分） |

## 记录、报告、研究与书目的对应

按“记录—报告—研究”分开计数。纳入表中的 24 条是检索记录。合并同一研究的不同报告后为 23 项作品，其中 22 项为研究论文或报告，1 项为数据集论文（#23 DT-CARGO）。

| 层次 | 数量 | 组成 |
|---|---:|---|
| 纳入表记录 | 24 | 上表 #1–#24 |
| 作品（研究或数据集） | 23 | #4 与 #12 为 Bertucci 等同一研究的期刊版与会议版，合并计一项 |
| 精读材料 | 9 | 精读卡 P1–P9 对应 #1–#9。P2 读的是 Ye 刊版并对照 arXiv v1；P9 读的是 2023 年 UC Davis 报告，2025 年期刊版未读 |
| BibTeX 条目 | 28 | 纳入表 24 条各 1 条；补充 2 个报告版本（`Ye2024jointArxiv`、`Wang2023infrastructureReport`）；表外 2 条：`Frank2025optimizing`（UM 接口成本来源）、`Kassis2026scientific`（工具与研究流程引用） |

同一作品的多个报告在 BibTeX 中互相注明：Bertucci（`Bertucci2025battery` ↔ `Bertucci2024joint`）、Ye（`Ye2024joint` ↔ `Ye2024jointArxiv`）、Wang/Miller/Fulton（`Wang2025infrastructure` ↔ `Wang2023infrastructureReport`）。校验脚本报告的 2 条“可能重复”就是后两组，属于有意保留的版本记录。

**工具引用不计入研究数量。** Kassis 等（2026，arXiv:2609.00065）是本轮检索与引用核对所用技能库（literature-review、citation-management 等）的来源，只在方法说明中作为工具引用，不在纳入表中，不计入 24 条记录或 23 项作品。Frank 等（2025，EVS38）是 UM 既有成本参数的来源，本轮只核实了题录，同样不在纳入表中。

**校验与阅读程度分开。** `validate_citations.py --check-dois`（2026-11-18）显示 28 条全部有效、DOI 均可解析，只有 1 个缺页码提示（EVS38）。这说明书目信息可以解析到对应作品，不说明文中的论点已经与原文核对。论点是否核实，以精读卡标注的阅读程度和页码为准：只读到元数据或摘要的记录，不用于支持模型或实验层面的判断。

全文缺口（保留标签）：#15 Wang 等 2025（IJPR，HTTP 403）、#18 Link 等 2026（SSRN，OpenAlex 无摘要）；Frank 等 2025（EVS38）已于 2026-11-18 从机构库取得全文，核对了 §2.2.2 与表 2、表 4（pp. 5–6），见精读卡 S1，其余章节未读；#10 Froger 2022、#19 Bragin 2024、#20 Zhao 2023 本地有全文，但本轮只读到摘要级。

### 2026-11-19 · 正换车时间补查

按题名和 DOI 核对两份论文，并补查厂商公开流程。Wang 的换车定义与 12 分钟对照已在期刊排版的相应章节核实。Link 的作者摘要可读，Fraunhofer 无公开附件，全文仍为缺口。ABB 原文单列自动接合、断开和进出工位，只有前两项给出秒数。证据强度、页码与反馈见 [换车时间补查](CARDS.md#s2-车队换车时间补查2026-11-19)。
