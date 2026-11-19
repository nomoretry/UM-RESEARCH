# 精读卡（2026-11-18 第一轮文献—项目对照）

本文件逐篇记录本轮精读的文献。每张卡只写实际读到的内容；未读部分注明“未读”。页码优先用期刊页码，括号内为 PDF 页。PDF、逐页抽取文本和页面渲染图保存在离线记录库 `runs/20261118_literature_review/`（无 remote），不入 GitHub。检索与筛选过程见 [SEARCH_LOG.md](SEARCH_LOG.md)，与 UM 的逐项对照见 [EVIDENCE_MATRIX.md](EVIDENCE_MATRIX.md)。

阅读程度用四级：元数据 / 摘要 / 指定章节 / 全文。“指定章节”指按本轮六个主题定位的模型、假设、实验与结论章节，其余章节只浏览。

---

## P1 Pelletier, Jabali, Laporte (2018) 货运电动车的场站充电调度

- **书目**：S. Pelletier, O. Jabali, G. Laporte. Charge scheduling for electric freight vehicles. *Transportation Research Part B* 115 (2018) 246–269. https://doi.org/10.1016/j.trb.2018.07.010
- **版本**：正式刊版 PDF（用户已有资料，24 页）。另有 CIRRELT 预印本，未对照。
- **阅读程度**：指定章节：§1–2.4（pp. 246–253）、§4.1（p. 258）、电池尺寸实验（p. 263）、§5（p. 266）。降解建模（§3）只浏览。
- **问题与模型**：车辆路线和时刻给定，只在场站充电，决策逐时段的充电电流和充电器分配；目标为电费＋设施需量费 F·y（式 2，p. 250）。约束：线路期间禁止充电（式 3），每类快充器同时使用数 ≤ κ_s（式 5），每车每时段最多一台充电器（式 6），SOC 上下界（式 11），电网上限（式 13），每次停靠的充电事件数 ≤ C（式 14–16，p. 252）。
- **关键假设**：规划期为“数日”，因为多班次运营不能假设每晚都能充满（p. 247）；每车初始 SOC 为给定常数（p. 250）；一次线路的全部能耗记在最后一个时段（p. 250）；一台充电器被某车使用的时段内整段不可给其他车（p. 250）；快充器数量 κ_s 为输入而非决策（p. 248）。式 (3)–(18) 中未见期末 SOC 下限或回到初值的约束。
- **数据与实验**：生成实例，3/6/9 车 × 每规模 5 个，双班次，3 天、30 分钟时段，初始 SOC 0.9（p. 258）；CPLEX gap 容差 0.5%，230 次测试平均 gap 0.50%（p. 258）。需量费按每月 22 个工作日折算到 3 天（p. 259）。
- **结论与局限**：按最大功率计费可使“仅为降低电费而购买快充器”不划算，但长线路运营可能仍需快充器（p. 266）。比较 40 与 80 kWh 电池时，作者把大电池初始 SOC 从 0.9 改为 0.45 以“公平比较”（p. 263）。作者列出的后续方向是同时做车辆分配与路线（p. 266）。
- **与 UM 的关系**：支持把“跨日结转电量”作为模型要求而非可选细节；其电池尺寸比较需要调整初始 SOC，说明 UM 的 0.5·C 缩放规则本身是一项影响结论的假设。“每次停靠充电事件数上限”是换车成本的一种代理，UM 的换枪研究以分钟计，更直接。

## P2 Ye, Yu, Wei (2024) 港口集卡的充电站与电力系统联合规划（正式刊版补核）

- **书目**：Z. Ye, N. Yu, R. Wei. Joint planning of charging stations and power systems for heavy-duty drayage trucks. *Transportation Research Part D* 134 (2024) 104320. https://doi.org/10.1016/j.trd.2024.104320
- **版本**：本轮补读正式刊版（开放获取，21 页，PDF 页 = 文章页）。11 月 9 日的[阅读卡](../20261109/ye2024.md)依据 arXiv v1。
- **阅读程度**：指定章节：§3 模型（pp. 5–9）、§4 数据（pp. 10–11）、§5.2.4（p. 15）、附录轨迹处理（p. 18）。
- **本轮核对结果**：
  - 式 (1) 通过 Next(t) 把末时段接回首时段，作者称“循环能量回路”（p. 6）。时段集合为一个代表日；起点电量由优化决定。
  - 式 (1) 的写法与正文解释的对应关系**有待澄清**（p. 6，已在渲染页面上核对），见文末“公式疑点登记”Q1。本轮未确认这是笔误还是记号约定，不作为论文勘误。
  - 每车电池容量 e_i^cap 为决策变量，费用为 c^btr·(e_i^cap − e^bse)（式 9，p. 7）；车队平均所需电池容量随电动化目标上升（§5.2.4，p. 15）。
  - 充电器按 kW 计价（表 2 中的 c^chg，p. 6），模型中没有接口个数整数；作者说明动态功率方案可能比贪心满功率方案需要更多充电器（p. 7）。
  - 充电资格：停车不少于 30 分钟（p. 5）且距站点不超过 0.5 英里（p. 7、p. 11），由 GPS 推断，不是观测到的插枪记录。
- **与 UM 的关系**：给出了“循环且起点可优化”的日边界，介于 UM 当前固定 0.5·C 日界与真正多日结转之间；电池容量作为决策变量的做法可直接对照 UM 的电池档敏感性。

## P3 Xiao, Chen, Sun, Laporte, Baldacci (2025) 充电资源受限的电动集卡集装箱拖运问题（全文，补 11 月 9 日缺口）

- **书目**：L. Xiao, L. Chen, P. Sun, G. Laporte, R. Baldacci. The container drayage problem for electric trucks with charging resource constraints. *Transportation Research Part C* 174 (2025) 105100. https://doi.org/10.1016/j.trc.2025.105100
- **版本**：正式刊版全文（用户资料，32 页，PDF 页 = 文章页）。取代 11 月 9 日只读到预览的[有限证据卡](../20261109/xiao2025_partial.md)。
- **阅读程度**：指定章节：§1–3.1（pp. 1–6）、§5.1（p. 16）、§7（p. 23）。算法章节（§4）只浏览。
- **问题与模型**：港口—客户 O–D 拖运任务的路线、充电与换电联合优化；目标含能耗、延误、充电与换电费用。充电站的充电桩数量有限，车多时须排队；充电过程为分段线性的非线性函数；换电固定 5 分钟，换电站排队忽略（p. 6）。
- **关键假设**：场站全天开放，车辆满电出发（p. 5，假设 1–2）；任务带软时间窗，延误按罚金计（pp. 5–6）。充电桩数量（实例中 NCP = 4）为输入，不是设施决策（p. 16）。单日问题。
- **数据**：福建—广东一家物流企业的 60 个真实任务，再随机生成 8 组、每组 10 个实例（p. 16）。
- **结论与局限**：作者提出的后续工作是有效不等式与分支切割以求精确最优（p. 23）。
- **与 UM 的关系**：“接口个数限制同时充电”与 UM 的 C04 同义，但 Xiao 以排队等待和延误罚金计价未及时服务，UM 以硬约束要求任务全部完成（或报告最大可完成车日）。Xiao 采用满电出发的单日设定，与 UM 的固定半电起止不同；两种设定的可行域强弱须在同一算例中对照，不能仅凭初值判断。

## P4 Bertucci, Salazar, Hofman (2025) 联合优化与多智能体仿真的电动卡车设施协同设计

- **书目**：J. P. Bertucci, M. Salazar, T. Hofman. Battery Electric Truck Infrastructure Co-Design via Joint Optimization and Agent-Based Simulation. *IEEE Transactions on Transportation Electrification* 11(5) (2025) 11296–11306. https://doi.org/10.1109/TTE.2025.3575704
- **版本**：正式刊版（用户资料）；同一研究的会议版为 Bertucci, Hofman, Salazar, ACC 2024（https://doi.org/10.23919/ACC60939.2024.10644339），本轮只读元数据，按“同一研究的另一报告”登记，不重复计数。
- **阅读程度**：指定章节：§II 模型（pp. 11297–11300）、§III 案例（p. 11302）、§V 结论（p. 11305）。
- **问题与模型**：给定物流行程，决策各配送中心各类型充电器数量 X 与每车每段的充电选择；同一辆车相邻时段不能换到另一台充电器（式 12–13，p. 11299）；“能量周期”约束要求分析期起止电量均为 φ·E_max（式 14–15，p. 11299）；目标含充电器资本、电费与按峰值计的接入费用。
- **关键假设**：电池容量按车型固定（225/315/315 kWh），作者称电池尺寸“可直接加入”但本文未作为决策（p. 11302）；当前商用车无法完成的任务在优化前删除（p. 11302）。
- **数据与验证**：荷兰北部一家配送中心，100 辆车、356 个地点、一周（2023-11-06 至 11-13），φ = 0.8；用训练/测试集与随机仿真检验设计（pp. 11297、11302）。
- **结论**：联合设计较规则设计，平均降低总成本 5.2%–6.4%，总装机功率平均降低 20.1%（p. 11305）。
- **与 UM 的关系**：标题称协同设计，但电池未优化；“删除不可完成任务”正是 UM 用逐车日归因避免的做法。一周起止电量相同的边界是 UM 跨日结转的现成参照。

## P5 Davatgari, Cokyasar, Subramanyam 等 (2024) 固定线路网络的充电设施选址与容量分配

- **书目**：A. Davatgari, T. Cokyasar, A. Subramanyam, et al. Electric vehicle supply equipment location and capacity allocation for fixed-route networks. *European Journal of Operational Research* 317 (2024) 953–966. https://doi.org/10.1016/j.ejor.2024.04.022
- **版本**：正式刊版（用户资料，14 页）。另有预印本，未对照。
- **阅读程度**：指定章节：§3 假设与模型（pp. 955–958）、§5 实例（p. 960）、§6 结论（pp. 962–963）。
- **问题与模型**：线路与客户顺序固定，决策在哪些候选设施、装多少台哪类充电器（整数 z_fk）以及途中充电时刻，显式计入排队等待（pp. 955–958）。
- **关键假设**：需求确定；电动化不改变线路与访问顺序；车辆同质；充电量与充电时间、能耗与行驶时间均为线性（p. 955）。初始与期望期末电量为给定参数 B^ι、B^ω（式 17–18，p. 958）。
- **数据**：POLARIS 模拟的芝加哥包裹配送线路，200 个实例（p. 960），不是实测车队。
- **结论**：业界常见做法是只在场站给每车配一台充电器，放弃了通过调度节省的可能（p. 963）；充电器设备费是成本的最大部分（摘要）。
- **与 UM 的关系**：与 UM“固定运输服务”的研究定位最一致；其接口整数与排队等待对应 UM 的 C04 与换枪研究。初末电量同样为给定边界。

## P6 Wu, Zhang, Chen (2023) 港口电动集卡运营与充电站规划的动态规划联合优化

- **书目**：X. Wu, Y. Zhang, Y. Chen. A Dynamic Programming Model for Joint Optimization of Electric Drayage Truck Operations and Charging Stations Planning at Ports. *IEEE Transactions on Intelligent Transportation Systems* 24(11) (2023) 11710–11719. https://doi.org/10.1109/TITS.2023.3285668
- **版本**：正式刊版（用户资料，10 页，PDF 页 = 11709 + 页序）。
- **阅读程度**：指定章节：§II（pp. 11711–11713）、§III 结果（pp. 11714–11715）。
- **问题与模型**：上层决定电动集卡数量、类型和充电站数量，下层按小时动态规划逐车安排运输与充电（p. 11712）。
- **关键假设**：所有车辆满电起步，S_{0,i} = U_i（p. 11713）；行程按三档距离，参数取自洛杉矶/长滩港在用集卡数据的统计（p. 11714）。
- **结论**：250 kWh 车型需 140 辆车、51 个充电站，$50.8/TEU；500 kWh 车型 125 辆、22 个充电站，$52.9/TEU，因车更重、能耗更高；两类混合可得最低成本（pp. 11714–11715）。
- **与 UM 的关系**：直接给出“电池更大 → 充电设施更少”的替代关系，与 UM 服务缺口研究中“设施菜单不能替代电池”的结论方向相容但问题不同（Wu 改变车队规模，UM 固定服务）。Wu 采用满电起步，与 UM 的固定半电起止是不同的初值设定。

## P7 Balke, Zähringer, Paper, Lienkamp (2024) 德国重卡公共充电网络的优化与爬坡策略（数据来源核查）

- **书目**：G. Balke, M. Zähringer, A. Paper, M. Lienkamp. Navigating the Change: Optimization and Ramp-Up Strategy of a Charging Network for Battery Electric Heavy Trucks. *IEEE ITSC 2024*, pp. 1594–1599. https://doi.org/10.1109/ITSC58415.2024.10920217
- **版本**：IEEE 正式版（用户资料，6 页）。
- **阅读程度**：指定章节：摘要、引言、数据（pp. 1594–1596）。
- **核查目的与结果**：Balke 是 UM 车队数据 DT-CARGO 数据论文的作者之一。本文使用 OpenStreetMap 路网与货运交通流数据（其参考文献 [21]，Data in Brief 2022），研究公共走廊快充站选址，**未使用 DT-CARGO 车队轨迹**（p. 1596）。因此不构成对 UM 车队证据的重复计数；但与 UM 数据出自同一研究团队，评价外部验证时应注明。

## P8 Ding, Ao, Duenas-Martinez 等 (2025) 工业场站轻型卡车电动化的决策相关鲁棒充电设施规划

- **书目**：Y. Ding, R. Ao, P. Duenas-Martinez, et al. Decision-dependent Robust Charging Infrastructure Planning for Light-duty Truck Electrification at Industrial Sites. arXiv:2510.13100 (2025). https://doi.org/10.48550/arXiv.2510.13100 。题名差异：arXiv 题录不含 “and Scheduling”，v2 正文首页含。
- **版本**：arXiv 预印本，2025 年首发；实际阅读 v2（2026-02-06 修订，2026-11-18 下载 PDF，57 页）；未同行评审。下文页码与式号指该 PDF，HTML 版式号不同。
- **阅读程度**：指定章节：§2.6（pp. 7–11）、§3.1（p. 15）、§4.1–4.5（pp. 18–23）。
- **问题与模型**：选择充电器类型与位置并调度充电；车辆等待超过阈值即放弃充电（abandonment，二元变量，pp. 7–10），特定区域允许夜间充电（p. 10）；每个 30 分钟停车时段的有效可用比例 pp 取 [5/30, 1]（式 15，p. 10；文字解释见 p. 11）。该式约束的是时段内有效可用时长，不等于“每次实际充电至少 5 分钟”。
- **初末电量**：优化期起止 SOC 相同（式 13，p. 10）。代表日法在代表日前后加入相邻日以保持行程和电池周期连续；全年法按月滚动并在相邻月间重叠若干天（p. 15、pp. 21–22）。
- **数据**：一处矿区 189 辆轻型卡车一年的 GPS（p. 18），由此识别停车与充电区。
- **结论**：去掉夜间充电区等情景改变各区快慢充电器数量（p. 23，图 10）。
- **与 UM 的关系**：提供了两种可直接借用的做法：用重叠日保持跨日电量连续；把“放弃充电”作为显式变量而不是不可行。车型为轻型卡车，外推到重卡需谨慎。

## P9 Wang, Miller, Fulton (2023 报告 / 2025 期刊) 电动卡车场站充电的设施成本

- **书目（实际阅读的报告版）**：G. Wang, M. R. Miller, L. M. Fulton. The Infrastructure Cost for Depot Charging of Battery Electric Trucks. UC Davis Institute of Transportation Studies, Research Report UCD-ITS-RR-23-63, 2023-10-26. https://escholarship.org/uc/item/1p49662g
- **同一研究的期刊版（未读）**：*The Electricity Journal* (2025) 107490. https://doi.org/10.1016/j.tej.2025.107490 。二者可能有差异，下文结论只引报告。
- **阅读程度**：报告目录与 §9 结论（报告 p. 14）。
- **结论**：场站充电设施的单车成本随车队规模迅速下降，约 50 辆中型配送车或约 10 辆重型短途车后趋缓（假设充电器利用率 50%）；资本成本对充电器利用率敏感，提高利用率可减少所需充电器数；年化设施成本远小于年电费（报告 p. 14）。
- **与 UM 的关系**：支持把“接口利用率”而非仅峰值功率作为接口投资的经济指标；UM 当前的第二接口门槛只比较电费差额与整机年费，可补充利用率视角。

---

## 本轮只做摘要或元数据筛选的记录

见 [SEARCH_LOG.md](SEARCH_LOG.md) 的纳入/排除表。其中 Froger 等（2022，Transportation Science，充电站容量受限的 E-VRP）、Bragin 等（2024，TR-C，路线与充电联合调度）、Zhao 等（2023，TITS，车队与充电服务商的非合作设计）有本地全文但本轮未精读；Wang 等（2025，IJPR 63(10)，2024 年在线发表；含充电准备时间的公交充电调度）出版社返回 403，仅读摘要；Link, Frank, Speth 等（2026，SSRN，基于真实运营数据的场站充电需求）仅有元数据，OpenAlex 无摘要。

---

## S1 Frank, Oebel, Gnann (2025) 卡车场站充电设施优化（成本来源核对，不计入 9 份精读）

- **书目**：F. Frank, J. Oebel, T. Gnann. Optimizing Charging Infrastructure for Truck Depots. EVS38, Göteborg, 2025. Fraunhofer 机构库：https://publica.fraunhofer.de/handle/publica/489174
- **版本与阅读程度**：机构库 PDF（12 页，2026-11-18 取得）。只读了与 UM 成本参数相关的章节：§2.2、§2.2.2（p. 5）、表 2 与表 4（p. 6）。
- **核对结果**：表 2 列出 “50 kW DC charging point” 投资 €20,882，参考文献 [24] 为 Alpitronic HYC50 的零售页面（p. 6）。§2.2.2 设定每辆卡车配一个专用充电点；寿命 10 年；规划、安装与调试为投资的 30%；年维护 1%；全部 EAC 计算的利率为 5%（p. 5）。表 4 为 Netze BW 2024 年按年满负荷小时分档的网费，含容量价（€/kW）（p. 6）。
- **与 UM 的关系**：UM 的 `studies/day-ahead/connector_cost.json` 参数与原文一致。成本基准是“一个独立的 50 kW 充电点”，与 UM 两接口情景“各 50 kW、只受站点 100 kW 限制”的物理设定对应。表 4 可作为后续需量费检验的有来源价目。

---

## 公式疑点登记

只记录可能影响 UM 模型修改的疑点。每条写明原文位置、符号定义、观察到的内容、可能的解释、对 UM 的影响和解决办法；未确认的解释不作为勘误。

| 编号 | 文献与位置 | 符号定义（原文） | 观察到的内容 | 可能的解释（均未确认） | 对 UM 的影响 | 解决办法 | 状态 |
|---|---|---|---|---|---|---|---|
| Q1 | Ye, Yu, Wei 2024, TR-D 134:104320, p. 6, 式 (1)；表 2（p. 6） | κ：表 2 记为 “Battery charging cycle efficiency”；p_it：充电功率（kW）；r_it^stp：时段内停车时间比例 | 式 (1) 为 e_it′ = e_it + (1−√κ)·p_it·r_it^stp·Δt − x_i·Δe_it^con；正文称 “(1−√κ)·p_it” 为 charging-related energy loss，并引用 Foggo and Yu (2017)。arXiv v1 写法相同 | （a）排版或记号问题，意在 √κ·p_it 为入电能量；（b）κ 在所引文献中表示损失相关量；（c）正文措辞与作者实现不一致而实现本身无误 | 不影响 UM 现有模型：UM 用自有效率 η = 0.9。只在严格复现 Ye 的数值时相关 | 核对 Foggo and Yu (2017) 的 κ 定义；询问作者或取得实现代码；用论文报告的负荷与电量作数值反推 | 未解决 |
| Q2 | Ding 等 2025, arXiv:2510.13100 v2 PDF p. 10, 式 (15)；解释见 p. 11 | pp_{i,d,t}：车辆 i 在第 d 天第 t 个 30 分钟时段的有效停车比例 | 式 (15) 为 5/30 ≤ pp ≤ 1；p. 11 文字称其限制每个时间窗的充电时长“大于 5 分钟且小于 30 分钟” | 该式约束的是时段内可用时长比例，不是每次实际充电的最短时长；HTML 版式号不同（作者编号随版本变化） | 本轮初稿曾误读为“最短充电时长”，已改正；不影响 UM 现有模型 | 若借用该约束，按 PDF v2 原式实现并注明版本 | 已澄清表述 |

## S2 车队换车时间补查（2026-11-19）

| 来源 | 阅读程度与页码 | 对 UM 的含义 |
|---|---|---|
| Wang、Zheng、Hamdan 与 Jouini，IJPR 63(10)，3538–3563，2024-11-09 在线 | 定向核对期刊排版正文 §3.1（第 3543–3544 页）与 §7.2、表 7（第 3557–3558 页）。出版 PDF 与 Bangor 接收稿本次请求均返回 403，页码据期刊正文的网页副本。 | 准备时间含前一辆公交驶回停车位和下一辆开到充电位。固定准备时间对照用 12 分钟，依据该案例优化排程的平均值。包含较长挪车时，10–15 分钟与其量级相近。它没有给出这批重卡的人工拔插实测。[期刊文章](https://doi.org/10.1080/00207543.2024.2424973) · [机构库记录](https://research.bangor.ac.uk/en/publications/charging-scheduling-optimisation-of-battery-electric-buses-with-c/) |
| Link、Frank、Speth、Gnann 与 Plötz，SSRN 预印本，2026 | 已读作者摘要和 32 页书目记录。全文缺口，SSRN 文件返回 403，Fraunhofer 条目为 `metadata.only` 且附件数为 0。正文页码无法核实。 | 摘要明确区分真实车队运营数据、场站负荷与模拟充电。摘要无逐枪更换分钟数，无法用它在 2 与 5 分钟之间择档。[SSRN 摘要](https://ssrn.com/abstract=7543981) · [机构库访问状态](https://publica-rest.fraunhofer.de/server/api/core/items/feebdcf6-ff78-4bdd-8c53-7fd183d674e4/accessStatus) |
| ABB，《Plug-in mines》，ABB Review 2/2023，第 140–145 页 | 定向核对厂商原文第 145 页图 05。 | 自动化矿卡接驳示例中，接合及安全检查约 18 秒，断开约 7 秒。进出工位和挪车没有完整计时，数字仅反映设备动作。2 分钟是本研究中较短的正换车假设，仍需道路重卡场站时间记录来检验。[厂商原文](https://library.e.abb.com/public/320194e2ac7647d78ac9f2d16da5d519/140-145%20m2357_EN.pdf?x-sign=auPHzlKZZY34TWrQU51cPc7IUeNV23I%2FiKNK2Qp8NUCU5p6MnMUC1m6esslnxzXz) |

主情景保持 0、2、5 分钟。10、15 分钟按已登记规则作为压力情景，外部材料只用于解释量级。

## S3 两站充电功率的费用来源（2026-11-20）

| 输入 | 来源等级与核对结果 | 用法 |
|---|---|---|
| 接入建设费 | 运营商官方价目。Netze BW 2026-01-01 生效，中压电网 `Mittelspannungsnetz` 行每 kW €172.74 未税、€205.56 含税。 | 新建按全部 kW，既有按超过已付容量的 kW，5% 折现和 20 年寿命。需求和电量网费取同运营商 2024 年中压价目。[运营商价目](https://assets.cdn.netze-bw.de/xytfb1vrn7of/3WkwLb2wCAE2YcQuG0YU4m/cff72cf6af73c9b225d0268390f45ebf/preisuebersicht-baukostenzuschuss-bkz-strom.pdf) |
| 50 kW | 会议论文设备基准。Frank、Oebel 和 Gnann（2025）表 2 为 €20,882，引用 24 指向 Alpitronic HYC50。表内其余卡车直流设备为 80 和 150 kW。 | 设备价加 30% 安装与每年 1% 维护，10 年寿命、5% 折现。税基在现有材料中未核实。[Frank 表 2](https://publica-rest.fraunhofer.de/server/api/core/bitstreams/794e2305-1b7f-4c8d-bf53-c1728befda2d/content#page=6) |
| 20 kW | 网店商品标价。WallboxCenter 的商品页与厂商数据表均列型号 EMUC0204G1BC、EAN 4024559264382 和 20 kW DC。核对当日公开价格为 €5,290 含 19% VAT，运费另计。 | 除以 1.19 得未税设备价。壁挂、CCS2、厂商资料列输入 21 kVA。该档与 HYC50 的使用强度、输入和计量要求须分别核实。[商品页](https://wallboxcenter.de/shop/wallbox/dc-wallboxen/dc-wallbox-20kw-em2go-ultra-compact-inkl-5m-ccs-ladekabel-rfid-lanwlansim/) · [厂商数据表](https://wallboxcenter.de/wp-content/uploads/2026/02/DC-Wallbox-20kw-Ultra-Compact_Datenblatt.pdf) |
| 30 和 40 kW | 网店商品标价。J&S Energy B.V. 德语商品页的 CCS2 立式基础设备各为 €6,295、€7,295 未税。 | 两档与 50 kW 同用财务及安装维护比例。实际安装与售后报价留空。[30 kW](https://jsenergystorage.de/PRODUKTE/30-kW-Gleichstrom-Ladestation-CCS2/) · [40 kW](https://jsenergystorage.de/PRODUKTE/40-kW-Gleichstrom-Ladestation-CCS2/) |
| CPI | 官方统计。德国综合 CPI 以 2020=100，2026 年 10 月为 126.5，沿用 2025 年全年 121.9。 | 把 2026 年建设费和商品价换算为 2025 年购买力。2021 年批发价及 2024 年网费分别沿用已有对应索引。[Destatis](https://www.destatis.de/DE/Presse/Pressemitteilungen/2026/11/PD26_392_611.html) |
