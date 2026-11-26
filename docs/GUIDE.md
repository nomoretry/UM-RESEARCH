# 仓库导览 · Repository Guide

[中文](#中文) · [English](#english) · [首页 / Home](../README.md) · [维护规范 / Contributing](../CONTRIBUTING.md)

## 中文

### 1. 这个仓库回答什么问题

本仓库研究**固定运输任务下港区与仓库的双站电动重卡充电设施规划**：在电池电量上下限、站点电网接入容量、充电接口数量与可充电窗口约束下，比较完成同一运输服务所需的设施投资与运行成本，检验运营灵活性何时能替代扩容，以及规划期选出的设施能否在后续未见运营周守住同一组服务。实证主案例使用德国单一承运人 5 辆重卡（1–5 号车）的公开轨迹与上游模拟耗电数据（DT-CARGO / TUMFTM）及同期 DE-LU 原生日前电价（SMARD），外部检验另用同一承运人的 6–18 号车，并辅以 4 小时三车合成算例和独立的米兰城市配送论文缩例复算。在 1–5 号车两次按时间顺序的留出检验，以及 6–10、11–15 号车各一次预登记的外部检验中，样本内年费最低的设施都没能守住后续运营周的登记任务；1–5 号车的完整周已全部用完，本项目没有经样本外验证的推荐设施规模。

### 2. 三条阅读路线

#### 路线一：五分钟速览（把握核心决策与边界）

直接阅读首页 [README.md](../README.md#中文)，重点看以下五个部分：

1. **导语与三项核心结论**：了解研究对象与最高级别判断。
2. **第 1 节（什么时候必须增加接口）**：通过 4 小时三车合成算例，看懂接口时段瓶颈与扩容无效的条件。
3. **第 2 节（第二个港区接口值多少钱）**：通过德国车队 3 天与 6 周对照，看懂为何第二接口不增加完成车日且运行节费远低于独立整机成本。
4. **第 3 节（两站需要多大功率：选型、两次留出与外部检验）**：对照两折留出检验的选型、缺口约束、双站基准构造边界与事后修复诊断，以及外部检验的结果。
5. **第 4 节（核心假设与结论边界）**：明确观测数据与情景假设的区别、周全信息离线排程口径及推断范围。

#### 路线二：半小时精读（按时间顺序核对四份核心研究报告）

按以下顺序精读 `studies/fleet-service/` 下的四份主报告，即可掌握两站定容、两次留出检验与外部检验的定量依据：

1. **先看规划期选型** — [两站功率联合选型（site_sizing.md）](../studies/fleet-service/site_sizing.md)：看 6 周规划期（2021-09-27 至 2021-11-07，基准登记 54/73 个车日）在 12 个网费与接入口径下的粗／细网格选型（官方网费新建 20/0 kW、既有 40/0 kW）、下界排除证明与设备打平价位。
2. **再看第一折留出** — [六周留出检验（holdout_test.md）](../studies/fleet-service/holdout_test.md)：看三套事先固定设施在随后 6 周（2021-11-08 至 2021-12-19，基准登记 52/63 个车日）的表现——港区单站 20/0、40/0 kW 均漏掉 11 月 26 日的 1 号车（首趟行程储备越界），以及仓库增容事后诊断与 5 号车记录断点敏感性。
3. **再看第二折留出** — [第二次留出检验（second_holdout.md）](../studies/fleet-service/second_holdout.md)：看合并 12 周（106/136 个车日）重选出的 40/20 kW（`F40`）与 20/20 kW（`F20`），在开封前预登记的随后 7 周（2021-12-20 至 2022-02-06，基准登记 49/57 个车日）上如何全部失败（`F40` 漏掉 2022-01-19 的 1 号车，段末电量距 150 kWh 差 46.237 kWh），以及次要运营策略对照、开封后四档有价阶梯诊断与封存时间线。
4. **最后看外部检验** — [子车队外部检验（external_test.md）](../studies/fleet-service/external_test.md)：看事先封存的 6–18 号车怎样按冻结的规则开封一次：6–10、11–15 号车选出的设施都没完成检验期的全部登记任务，16–18 号车不可评；并看失败段的差额、预测、规则对照、嵌套窗口和时间戳登记。

如需查阅单个建模假设的专项敏感性，可按需延伸阅读：[数据来源与质量筛选（DATA.md）](../studies/fleet-service/DATA.md)、[未完成车日归因（service_gap.md）](../studies/fleet-service/service_gap.md)、[跨日电量边界（energy_boundary.md）](../studies/fleet-service/energy_boundary.md)、[共享柜与需量电费（cabinet_demand.md）](../studies/fleet-service/cabinet_demand.md)、[车队换车时间（changeover.md）](../studies/fleet-service/changeover.md)、[段末电量约定（boundary_sensitivity.md）](../studies/fleet-service/boundary_sensitivity.md)。

#### 路线三：完整复核（模型、数据、代码、测试与复算）

1. **核对数学模型**：阅读 [固定任务充电与容量投资 MILP（FORMULATION.md）](model/FORMULATION.md) 核查变量、约束 C01–C08 与物理换车公式，配合 [公式代码对应（IMPLEMENTATION_MAP.md）](model/IMPLEMENTATION_MAP.md) 定位基础模型实现。
2. **核对输入数据与成本口径**：阅读 [车队数据与电价说明（DATA.md）](../studies/fleet-service/DATA.md)，并检查 `studies/day-ahead/` 下的电价 CSV、网费（`network_charges.json`）与设备／接入建设费（`connection_cost.json`、`connector_cost.json`）及 `configs/` 下的合成算例 JSON。
3. **审阅源码与独立检查器**：检查 `src/um_charging/` 中的 MILP 建模、独立回放审计、网费结算、下界筛选与留出运行模块，以及 `tests/` 中的对应单元测试与回归测试。
4. **运行复算与测试**（在仓库根目录的 Windows PowerShell 中，使用安装有 `requirements-milp.txt` 的 Python 3.12 环境）：

```powershell
$env:PYTHONPATH = 'src'

# 1. 首页快速复算（3 天车队对照与 1 月价回放）
python -m um_charging.connector_value

# 2. 运行全量自动化测试套件（含模型、回放检查与报告数字一致性检验）
python -B -m pytest tests -q -p no:cacheprovider

# 3. 单独运行两份留出报告、外部检验与 JSON 的一致性检验（无需离线档案）
python -B -m pytest -q -p no:cacheprovider tests/test_published_holdout.py tests/test_published_second_holdout.py tests/test_published_external_test.py
```

多数专题报告末尾另列有更细粒度的单题复算命令与（面向离线档案持有者的）全量证书重放命令；外部检验的证书重放同样需要离线档案。

### 3. 目录地图

下表区分**当前结论与有效代码**和**历史记录与早期归档**，避免将早期里程碑快照误读为当前结论：

| 目录 | 存放内容 | 当前定位 |
|---|---|---|
| `studies/` | 核心实证研究报告与机器可读 JSON 证据：`fleet-service/`（两站功率选型、两次留出检验、外部检验、数据说明及五项专项敏感性）、`day-ahead/`（第二接口门槛、原生 DE-LU 电价、网费与设备价目输入）、`fresia-2025/`（独立米兰配送论文缩例复算）、`truck-energy/`（合成单程能耗转移敏感性） | **当前结论**（实证主结论以此目录和 `README.md` 为准） |
| `src/` | `src/um_charging/` 全部研究源码：固定任务 MILP、接口与扩容投资、物理换车、跨日结转、需量结算、选型下界、留出检验与外部检验（分阶段封存）运行及独立回放审计 | **当前代码** |
| `tests/` | 全量自动化测试套件：单模型手算实例、回放一致性、下界检验、M10、M11 规则与两份留出报告、外部检验报告的数字一致性锁定测试 | **当前测试** |
| `docs/model/` | 数学模型与合成输入规范：`FORMULATION.md` 为核心 MILP 与物理换车公式说明；`IMPLEMENTATION_MAP.md`、`MINIMAL_INSTANCE.md`、`INVESTMENT_INPUT.md`、`TIMEGRID_INPUT.md` 记录早期合成算例的模型接口与输入格式 | **模型参考**（`FORMULATION.md` 持续有效；其余四份为早期合成模型阶段规范） |
| `docs/research/` | 项目演进记录：`STATUS.md`（按时间倒序的里程碑记录）、`DECISIONS.md`（研究决策台账）、`CAPABILITIES.md`（截至 2026-11-11 的能力快照）、`DATA_AUDIT_20261104.md` 与 `LEGACY_RECOVERY_20261104.md`（2026-11-04 专项审计）；另含 `docs/PROGRESS.md`（早期进展摘要） | **历史记录**（用于追溯研究演变与决策理由；当前结论以 `README.md` 与 `studies/fleet-service/` 为准） |
| `docs/literature/` | 文献精读与书目：`references.bib`（全库共享 BibTeX；出版社 PDF 存离线档案）、`20261109/`（初轮 3 篇文献精读与基线建议）、`20261118/`（定向综述、精读卡、证据矩阵、检索记录与阶段诊断） | **文献档案**（`references.bib` 持续使用；两期笔记按日期反映当时阶段判断） |
| `results/` | 早期合成算例与基础验证的精选输出包：其中 `known_delay_investment_20261111/` 与 `shared_investment_20261112/` 对应首页第 1 节合成算例；`changeover_20261112/`、`eligibility_stress_20261111/`、`dt_cargo_stop_20261111/` 及 2026-11-04 / 2026-11-10 各目录保留早期合成检验与数据验证证据 | **合成算例证据与历史记录**（车队实证结论不在本目录，见 `studies/`） |
| `data/` | `data/germany-truck-grid-v1/`：早期德国车队（DT-CARGO v1.1）与 SimBench 城市中压配电网数据工程快照及校验脚本 | **历史数据工程线**（独立于 `studies/fleet-service/` 所用的 DT-CARGO v2 / BETOS 车队切片） |
| `legacy/` | `legacy/truck_charging_v1/`：按字节恢复的早期有限方案原型（每任务独立初始电量、枚举路径与定功率充电），含原始测试与合成输入 | **历史原型归档**（非当前连续电量固定任务模型，仅作溯源保留） |

此外，根目录下的 `configs/` 存放合成算例 JSON 输入，`scripts/` 存放独立数据校验与绘图辅助脚本，[CONTRIBUTING.md](../CONTRIBUTING.md) 说明公开仓库与离线档案的分工和维护规范。

### 4. 证据等级怎么读

阅读仓库中的数字与结论时，请始终按以下三个维度区分证据等级：

1. **事先登记并封存后检验 vs. 事后探索与诊断**
   - **事先登记、开封前封存的检验**：[第二折留出检验（second_holdout.md）](../studies/fleet-service/second_holdout.md) 的主终点与次要终点。检验前已完成规则预登记、执行代码冻结与外部时间戳存证（第 1 份 13 文件清单在开封前已取得比特币区块证明；第 2 份含补充 2 的 16 文件清单开封时仅有待定日历证明，区块证明晚于开封），开封时先封存主终点证书。`F40`、`F20`、`U`、`D40`（`S1`）、`I`（`S2`）及 `S3` 均在设施与规则固定后接受检验。[第一折留出检验（holdout_test.md）](../studies/fleet-service/holdout_test.md) 中三套固定设施（20/0、40/0 kW 与 `B`）同样在规划后固定检验（检验后该 6 周已并入 12 周选型样本，不再独立）。
   - **事前约束最强的检验**：[子车队外部检验（external_test.md）](../studies/fleet-service/external_test.md)。判据、门槛、执行代码和各种结局的写法在提取 6–18 号车任何记录之前冻结，清单的比特币区块证明早于开封授权；两个主队列的主终点先单独封存，再做次要分析。
   - **按构造成立而非样本外验证**：两折的登记集合 `R`（52/63 与 49/57）均由双站基准 `B`（两站各 50 kW 充电机、100/75 kW 接入）按自身可行服务确定。因此 `B` 在主情景完成 `R` 是按构造成立的，不代表 `B` 经样本外验证稳健（行程耗电增加 10% 时，`B` 自己也漏掉 1 个车日）。外部检验的两个队列同样由双站基准（各 50 kW、100/75 kW 接入）定义登记集合，基准守住也是按构造成立。
   - **事后或开封后诊断（不构成样本外验证）**：第一折看到 11 月 26 日缺口后确定的仓库 +15 kW 物理恢复及 20/20、40/20 kW 有价修复账单，以及第二折主终点失败后按预登记顺序运行的四档有价修复阶梯（`p1-40-w30` 不可行、`p1-40-w40` 可行，35 kW 不在预登记阶梯内；最低额外固定年费新建 €756.91、既有 €489.77），均属于看到缺口后的诊断，不构成样本外验证，也不将任何配置作为推荐规模。记录断点关闭与行程耗电 +10%/+20% 属于机理与裕度敏感性分析；规划期选型（`site_sizing.md`）与合成算例（`results/`）属于样本内或确定性情景分析。

2. **不可行证据的核验强度**
   - 在 [second_holdout.md](../studies/fleet-service/second_holdout.md) 中，失败结果按证据强度明确分级：**独立复核或独立回放确证失败**（`F40`、`F20`、`U`、`S2`、`S3`）与**仅求解器证明不可行**（`S1` 按天滚动；事后另有精确有理数复核，见 [boundary_sensitivity.md](../studies/fleet-service/boundary_sensitivity.md)）。所有可行排程均经独立回放检查电量、接口、站点功率与费用。

3. **观测记录 vs. 推断上界 vs. 情景假设**
   - 原始轨迹只记录行程起止时间与位置分类；相邻行程的时间间隔仅为**停车时长上界**，不能当作实测在站或插枪时长。
   - 站点映射（基地→港区、非基地工业区→仓库）、仓库 45 分钟放行延迟、允许插枪窗口、上游 BETOS 模拟行程耗电，以及设施固定后的按周全信息离线排程（非在线策略），均为显式声明的模型与情景假设。

---

## English

### 1. What this repository studies

This repository investigates **two-site (port and warehouse) charging infrastructure sizing for heavy-duty electric trucks under fixed transport duties**. Holding transport tasks, battery limits, site grid connection capacities, connector counts, and charging windows fixed, it compares total investment and operating cost for completing the exact same service to test when operational flexibility can substitute for capacity expansion, and whether facilities selected in a planning window retain service during subsequent unseen weeks. The main empirical case pairs recorded German truck trajectories and upstream simulated trip energies for five trucks of one carrier (trucks 1–5, DT-CARGO / TUMFTM) with contemporaneous native DE-LU day-ahead prices (SMARD). An external test uses trucks 6–18 of the same carrier. The repository also holds a four-hour three-truck synthetic benchmark and a separate reduced Milan urban-delivery paper replication. In two chronological holdouts for trucks 1–5 and one preregistered external test each for trucks 6–10 and 11–15, the lowest-cost in-sample build did not complete all registered duties in later weeks; all full weeks of trucks 1–5 are used, and the study makes no out-of-sample-validated sizing recommendation.

### 2. Three reading paths

#### Path 1: Five-minute overview (headline decisions and scope limits)

Read [README.md](../README.md#english), focusing on five parts:

1. **Opening summary and three headline findings:** the study scope and top-level takeaways.
2. **Section 1 (When a connector is necessary):** the four-hour three-truck synthetic benchmark showing when connector-slot shortages cannot be resolved by grid expansion alone.
3. **Section 2 (When a second port connector lowers the bill):** three-day and six-week German fleet comparisons showing zero service gain and operating savings far below standalone charger cost.
4. **Section 3 (Port and warehouse power sizing: two holdouts and an external test):** side-by-side summary of planning selection, both chronological holdouts, baseline construction bounds, post-hoc repair diagnostics, and the external test.
5. **Section 4 (Key assumptions and scope limits):** records versus scenario assumptions, weekly full-information offline scheduling, and inference boundaries.

#### Path 2: Half-hour deep read (four core studies in chronological order)

Read these four reports in `studies/fleet-service/` in sequence for the quantitative evidence on two-site sizing, the chronological holdouts and the external test:

1. **Planning-period sizing** — [site_sizing.md](../studies/fleet-service/site_sizing.md#english): six planning weeks (27 September to 7 November 2021; 54/73 registered vehicle-days), coarse and refined grid sizing across 12 tariff-and-access cases (20/0 kW new and 40/0 kW existing under the official tariff), lower-bound exclusions, and equipment price crossovers.
2. **First holdout** — [holdout_test.md](../studies/fleet-service/holdout_test.md): six subsequent weeks (8 November to 19 December 2021; 52/63 registered vehicle-days) testing three prespecified facilities—port-only 20/0 and 40/0 kW each missed vehicle 1 on 26 November (in-trip reserve breach)—plus post-hoc warehouse repair diagnostics and vehicle 5 recording-gap sensitivity.
3. **Second holdout** — [second_holdout.md](../studies/fleet-service/second_holdout.md): twelve-week reselection on the priced coarse grid (106/136 vehicle-days; 40/20 kW `F40` and 20/20 kW `F20`) followed by a preregistered seven-week holdout (20 December 2021 to 6 February 2022; 49/57 baseline register) in which all selected designs failed (`F40` missed vehicle 1 on 19 January, ending 46.237 kWh below the 150 kWh terminal requirement), together with secondary policy checks, the post-opening four-step priced repair ladder, and sealing/timestamp records.
4. **External test** — [external_test.md](../studies/fleet-service/external_test.md): how trucks 6–18, set aside beforehand, were opened once under frozen rules. The builds selected for trucks 6–10 and 11–15 did not complete all registered duties in the test weeks, and trucks 16–18 are not evaluable; the report also lists the shortfall of each failed segment, the two predictions, the rule comparisons, the nested windows and the timestamp record.

For targeted sensitivity checks on individual assumptions, read as needed: [DATA.md](../studies/fleet-service/DATA.md), [service_gap.md](../studies/fleet-service/service_gap.md), [energy_boundary.md](../studies/fleet-service/energy_boundary.md), [cabinet_demand.md](../studies/fleet-service/cabinet_demand.md), [changeover.md](../studies/fleet-service/changeover.md), and [boundary_sensitivity.md](../studies/fleet-service/boundary_sensitivity.md) (Chinese).

#### Path 3: Full verification (model, data, code, tests, and commands)

1. **Inspect the mathematical formulation:** read [FORMULATION.md](model/FORMULATION.md#english) for the MILP variables, constraints C01–C08, and physical connector changeover model, together with [IMPLEMENTATION_MAP.md](model/IMPLEMENTATION_MAP.md) for equation-to-code entry points of the core synthetic model.
2. **Audit inputs and cost bases:** check [DATA.md](../studies/fleet-service/DATA.md) for trip filtering, spatial recording gaps, and SMARD price snapshots; inspect `studies/day-ahead/` (`network_charges.json`, `connection_cost.json`, `connector_cost.json`, and hourly price CSVs) and `configs/` for synthetic inputs.
3. **Review code and independent verifiers:** inspect `src/um_charging/` (MILP builders, independent schedule replay auditors, tariff settlement, lower-bound screening, and holdout runners) and `tests/` (unit, regression, audit, and published-report consistency tests).
4. **Run reproduction and verification commands** (from the repository root in Windows PowerShell using a Python 3.12 environment with `requirements-milp.txt` installed):

```powershell
$env:PYTHONPATH = 'src'

# 1. Quick homepage benchmark (three-day fleet case and January price replay)
python -m um_charging.connector_value

# 2. Full automated test suite (models, replay checks, and published-report consistency)
python -B -m pytest tests -q -p no:cacheprovider

# 3. Published holdout and external-test report checks alone (no offline archive required)
python -B -m pytest -q -p no:cacheprovider tests/test_published_holdout.py tests/test_published_second_holdout.py tests/test_published_external_test.py
```

Most study reports provide study-specific rerun commands and full offline certificate-replay commands (for environments with access to the separate offline archive); replaying the external-test certificates needs the same archive.

### 3. Directory map

The table below distinguishes **current findings and active code** from **historical logs and earlier archives** so milestone snapshots are not mistaken for current conclusions:

| Directory | Contents | Status |
|---|---|---|
| `studies/` | Core empirical study reports and machine-readable JSON evidence: `fleet-service/` (two-site power sizing, both holdout tests, the external test, data provenance, and five assumption sensitivities), `day-ahead/` (second-port hurdle, native DE-LU prices, network tariff and equipment cost inputs), `fresia-2025/` (separate reduced Milan paper replication), `truck-energy/` (synthetic leg-energy sensitivity) | **Current findings** (authoritative empirical results alongside `README.md`) |
| `src/` | `src/um_charging/`: optimization models, independent replay auditors, tariff settlement, sizing bounds, holdout runners, and the staged external-test runner | **Current code** |
| `tests/` | Automated test suite covering hand-checked instances, replay verification, lower bounds, M10 and M11 rules, and published-report consistency checks | **Current tests** |
| `docs/model/` | Mathematical model and synthetic input specifications: `FORMULATION.md` (core MILP constraints C01–C08 and physical changeover); `IMPLEMENTATION_MAP.md`, `MINIMAL_INSTANCE.md`, `INVESTMENT_INPUT.md`, and `TIMEGRID_INPUT.md` (earlier synthetic-model specifications through 2026-11-10) | **Model reference** (`FORMULATION.md` current; the other four document earlier synthetic stages) |
| `docs/research/` | Project evolution records: `STATUS.md` (reverse-chronological milestone log), `DECISIONS.md` (decision register), `CAPABILITIES.md` (capability snapshot as of 2026-11-11), `DATA_AUDIT_20261104.md` and `LEGACY_RECOVERY_20261104.md` (2026-11-04 audits), plus `docs/PROGRESS.md` (early summary) | **Historical records** (for audit trail and rationale; current findings live in `README.md` and `studies/fleet-service/`) |
| `docs/literature/` | Literature notes and bibliography: `references.bib` (shared BibTeX; publisher PDFs stay in the offline archive), `20261109/` (initial three-paper notes), and `20261118/` (targeted review, reading cards, evidence matrix, search log, and diagnostic memo) | **Literature archive** (`references.bib` active; dated folders reflect stage-specific assessments) |
| `results/` | Curated outputs for synthetic benchmarks and early verifications: `known_delay_investment_20261111/` and `shared_investment_20261112/` support README Section 1; `changeover_20261112/`, `eligibility_stress_20261111/`, `dt_cargo_stop_20261111/`, and the 2026-11-04 / 2026-11-10 packages record early synthetic and dataset checks | **Synthetic evidence & historical records** (empirical fleet findings live in `studies/`, not here) |
| `data/` | `data/germany-truck-grid-v1/`: early German truck (DT-CARGO v1.1) and SimBench MV-urban dataset engineering snapshot and verification scripts | **Historical data engineering track** (distinct from the DT-CARGO v2 / BETOS fleet excerpt in `studies/fleet-service/`) |
| `legacy/` | `legacy/truck_charging_v1/`: byte-exact recovered finite-plan prototype (independent per-job initial SOC, enumerated paths, fixed charging rate) with original tests and synthetic inputs | **Historical prototype archive** (not the current continuous-SOC fixed-duty model) |

Top-level supporting items also include `configs/` (synthetic benchmark JSON inputs), `scripts/` (standalone audit and plotting helpers), and [CONTRIBUTING.md](../CONTRIBUTING.md) (maintenance and archive conventions).

### 4. How to read the evidence tiers

Interpret every quantitative result in this repository along three evidence distinctions:

1. **Preregistered, pre-sealed tests vs. post-hoc diagnostics**
   - **Preregistered and sealed before opening:** The primary and secondary endpoints of the [second holdout (second_holdout.md)](../studies/fleet-service/second_holdout.md). Rules were preregistered, execution code was frozen, and external OpenTimestamps manifests were created before raw holdout inputs were opened (the first 13-file manifest had Bitcoin block attestations before opening; the second 16-file manifest covering addendum 2 had pending calendar attestations at opening, with any block attestation postdating opening). Primary endpoint certificates were committed before secondary billing. `F40`, `F20`, `U`, `D40` (`S1`), `I` (`S2`), and `S3` were all evaluated with facilities and rules fixed beforehand. Similarly, the three prespecified facilities (20/0, 40/0 kW, and `B`) in the [first holdout (holdout_test.md)](../studies/fleet-service/holdout_test.md) were fixed prior to testing (afterward, those six weeks were merged into the 12-week selection sample and are no longer independent).
   - **The test with the strongest advance constraints:** [external_test.md](../studies/fleet-service/external_test.md). The endpoint, thresholds, execution code and wording of each outcome were frozen before any record of trucks 6–18 was extracted, and the Bitcoin block proof of the manifest predates the opening authorization; the primary endpoints of both main cohorts were sealed separately before any secondary analysis.
   - **True by construction, not out-of-sample validation:** In both holdouts, the baseline register `R` (52/63 and 49/57 vehicle-days) was defined by the two-site baseline `B` (one 50 kW charger per site on 100/75 kW connections) from its own feasible daily service. Retaining `R` in the main scenario therefore holds by construction for `B` and does not validate `B` as robust (at +10% driving energy, `B` itself missed one vehicle-day). The two external cohorts use the same two-site baseline (50 kW per site on 100/75 kW connections) to define their registers, so the baseline retains them by construction as well.
   - **Post-hoc / post-opening diagnostics (not out-of-sample validation):** The first-holdout warehouse repairs (+15 kW physical restoration; 20/20 and 40/20 kW priced repair bills) were identified after seeing the 26 November gap. Likewise, although the four-step priced repair ladder in the second holdout (`p1-40-w30` infeasible, `p1-40-w40` feasible, 35 kW not in the preregistered ladder; lowest added annual fixed cost €756.91 new / €489.77 existing) followed a preregistered diagnostic order, it ran after observing the primary failure; it does not validate `p1-40-w40` out of sample or establish it as a recommended build. Recording-gap exclusions and +10%/+20% driving-energy shifts are mechanism and margin sensitivities; planning-period sizing (`site_sizing.md`) and synthetic benchmarks (`results/`) are in-sample or deterministic analyses.

2. **Verification strength of infeasibility findings**
   - In [second_holdout.md](../studies/fleet-service/second_holdout.md), failures explicitly distinguish **independently corroborated or independently replayed failures** (`F40`, `F20`, `U`, `S2`, `S3`) from **solver-only infeasibility proofs** (`S1`, daily rolling; an exact rational-arithmetic check was added later, see [boundary_sensitivity.md](../studies/fleet-service/boundary_sensitivity.md)). Every reported feasible schedule passes independent replay verification for SOC, connector limits, site power, and billing.

3. **Observed records vs. inferred bounds vs. scenario assumptions**
   - Raw trajectories supply trip start/stop timestamps and endpoint classifications only; elapsed time between adjacent trips is solely an **upper bound on parking duration**, not observed station occupancy or plug-in time.
   - Site mapping (home base to port, non-home industrial area to warehouse), the 45-minute warehouse release delay, plug eligibility windows, upstream BETOS simulated trip energies, and weekly full-information offline scheduling after facilities are fixed (not an online policy) are all explicit modeling and scenario assumptions.
