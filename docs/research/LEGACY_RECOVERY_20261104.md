# 旧原型恢复证据：2026-11-04

本文件记录本轮**读取源码、历史结果与计算文件哈希**所得事实。本文中的 106 项测试、六情景目标和三车单站数值均为历史输出；编写本审计时未重新运行测试或求解器。本轮正式复现应另记源码提交、run_id 和结果包，不能把这里的历史数值改称本次结果。

## 定位及保存边界

本机原始工作目录为 `C:\Users\27788\OneDrive\文档\ChatGPT\UM`。实际定位到：

1. `truck_charging_v1/`：有源码、测试、合成输入及历史结果，恢复副本位置为本研究仓库的 [legacy/truck_charging_v1](../../legacy/truck_charging_v1/)。这是实际找到的原型，不再仅是聊天线索。
2. `outputs/2026-10-15_research_scope_small_case/`：另一个三车单基地连续电量算例，源码和历史验证均存在。本轮仅定位和审阅，未移植、未重跑。

原始目录没有被修改。恢复范围仅包括必要源码、测试、合成输入和说明；`.venv/`、缓存、原始测试 XML、完整历史方案与运行结果不复制到主仓库。本文件保存精选事实和哈希；完整运行记录按 [STORAGE](../workflow/STORAGE.md) 放在主仓库之外的独立本地 Git。

## truck_charging_v1：已实现及证据边界

输入 `data/synthetic/demo.json` 明确是人为测试数据：4 个抽象节点、5 条有向边、2 个可建设位置、2 项独立运输任务。不是广东、德国或港口实测数据。

| 实现 | 恢复副本内精确位置 | 已核实行为 |
|---|---|---|
| 数据接口 | `truckplan/data.py`：`validate_dataset`、`load_dataset` | 严格字段、类型、引用、来源及重复 JSON 键校验 |
| 路径和充电安排 | `truckplan/plans.py`：`generate_plans` | 前 K 条按距离排序的简单有向路径；枚举完整时隙的等待和定功率充电；超过方案数上限显式报错 |
| 设施与方案选择 | `truckplan/model.py`：`solve` | 建站二元、整数充电位、方案选择二元；每任务恰选一方案；站点联动、接口并发和站点功率分别约束 |
| 成本 | `truckplan/model.py`：`cost_vector`；`truckplan/plans.py` | 年化设施投资加典型日运营费乘年度天数；运营电费按行驶耗能/效率计算，不是逐站时变电价结算 |
| 独立物理与成本复算 | `truckplan/verify.py`：`verify_solution` | 从原始边、车辆和事件重算方向、里程、时间、电量、接口、功率及年目标，不直接相信方案汇总字段 |
| 穷举核验 | `tests/test_enumeration.py`：`test_milp_matches_exhaustive_enumeration` | 对 5 个小情景穷举每任务方案组合，与 MILP 最优目标或不可行状态核对 |

**连续 SOC 边界：**单个任务内电量按实数递推，但 `model.py` 的全部求解变量均设为整数；没有连续电量或功率决策变量。`plans.py` 为每个 `job` 从各自 `initial_kwh` 开始，不能将同车多个任务直接视为连续日程。充电功率为站点给定常数，充电时长是整数时隙。最优性和不可行性仅针对生成的有限路径/方案集。

因此它不能直接充当 [FORMULATION](../model/FORMULATION.md) 中固定任务链、完整周期连续电量、连续功率、已有设施及离散扩容模型。恢复旧工程与实现当前规范是两项独立工作。旧工程的严格校验、无解保留和独立复算方法可继续使用。

## 106 项历史测试：已找到原件，未在本审计中重跑

原件：原始工作目录下 `truck_charging_v1/results/test_report.xml`。

- `tests=106`、`errors=0`、`failures=0`、`skipped=0`。
- `timestamp=2026-09-10T11:24:31.846295+08:00`，`time=3.055`。
- 按 XML `classname` 分组：`tests.test_data_plans` 14、`tests.test_enumeration` 5、`tests.test_integration` 6、`tests.test_model` 25、`tests.test_verify` 56。
- 历史测试数是程序验证数量，不是研究样本规模，也不构成真实车队验证。
- 历史 XML 没有记录测试源码哈希或 Git 提交。下列测试文件哈希是本次恢复时计算，不能倒推为历史运行时哈希。

历史 `results/base/manifest.json` 记录了 `run.py` 及四个 `truckplan` 模块的源码 SHA-256；本次读取并计算当前原件哈希，5 项全部与历史清单一致。此证据建立源码字节对应，不单独证明历史求解及数值正确，也不能替代正式重跑。

## 六个已存历史情景

来源：原始目录 `truck_charging_v1/results/comparison.json`。目标单位为 CNY/year；所有数值均依赖合成成本、能耗和年度天数。

| 情景精确标识 | 历史求解状态 | 历史年度目标 | 完整约束验证 | 历史设施结果 |
|---|---|---:|---|---|
| `base` | `optimal` | 462000 | `true` | SA 2 位，SB 不建 |
| `no_charge_needed` | `optimal` | 315000 | `true` | 两站均不建 |
| `site_power_limited` | `optimal` | 491000 | `true` | SA 1 位，SB 不建 |
| `tight_deadline_one_bay` | `infeasible` | null | 无可验证解 | 不输出伪方案 |
| `reverse_access_blocked` | `optimal` | 608000 | `true` | SA 不建，SB 2 位 |
| `relaxed_service` | `optimal` | 461000 | `false` | SA 1 位但发生并发超占用 |

最后一项的独立验证错误原文：`site 'SA', slot 1: occupied bays 2 exceed installed bays 1`。这是一项诊断性失败，应保留；461000 不是满足完整约束的可执行方案成本。零建站和不可行结果同样保留。

## 三车单基地原型：仅定位、未移植

原始路径：`outputs/2026-10-15_research_scope_small_case/model/solve_small_case.py`，配套 `model/README.md`、`model/manifest.json`、`model/milp_results.csv`、`independent_validation.py`、`independent_validation.json` 均存在。

该实现有连续功率与整日能量账：3 辆车、1 个基地、48 个 15 分钟时段、300 kWh 电池、初始及期末最低 150 kWh、安全下限 60 kWh、效率 0.94、每接口及车辆上限 150 kW。全部是合成压力算例设定。任务整趟耗能在离场槽扣除一次，并要求离场前预留整趟能量和安全余量；这是预留记账，不能解释成实测行驶中 SOC 曲线。

`build` 实现连接二元 `x`、开始二元 `z`、连续功率 `p`、连续电量 `e`、整数接口数 `M`、峰值 `peak`。每停车窗至多一次连续连接；零功率连接仍占接口。`solve` 先最小化接口数，确认最优后固定接口数并最小化峰值。

| 已存节奏 | G / kW | 历史状态 | 接口数 | 最低峰值 / kW |
|---|---|---|---:|---:|
| WIDE | 150 | 不可行 | null | null |
| WIDE | 200、300、400 | 各情景最优 | 2 | 191.489362 |
| NARROW | 150、200、300 | 各情景不可行 | null | null |
| NARROW | 400 | 最优 | 3 | 382.978723 |

历史 `independent_validation.json` 日期为 2026-10-15，记录 287/287 检查通过，且明确其范围是读取已存 CSV、解析必要界和构造可行见证，**没有重新运行求解器**。本审计同样未运行该文件。

本次计算 `solve_small_case.py` 的哈希，与历史 `manifest.json` 的 `generator_sha256` 完全一致。该原型尚不具备当前要求的 2–3 站、已有设施成本和离散扩容；目标是接口数/峰值，不是年化投资加购电费用。它也不能当作德国运营数据上的连续 SOC 实证。直接执行原脚本会写回脚本所在目录，所以未来复现必须先隔离。

## 恢复文件及 SHA-256

以下路径相对于恢复副本 `legacy/truck_charging_v1/`；哈希在 2026-11-04 从原始文件字节计算。复制应保持字节不变。

| 文件 | SHA-256 |
|---|---|
| `run.py` | `fe178ab9773c6b21cbe81618de1961a556b28efe273399975d46dfacbb29dca7` |
| `truckplan/__init__.py` | `e20227da2ea5c52809d77d403003eaf7f5c4e613b962665d0553b69f6340446f` |
| `truckplan/data.py` | `35468883219ae71bec54ca9a88aa6f9d348d514ab0fb82bc38fda078eb666ab2` |
| `truckplan/plans.py` | `3fe91d436b4759ad9aef975a039ce6e11b9b7acb80cc59f56319d75d0af99fb7` |
| `truckplan/model.py` | `c753c4be2dea5b6378639a2d9221a8368ddec438792be222755d51e0906e81f1` |
| `truckplan/verify.py` | `8ef0e3e01125cfa4e0545d4ece70ca1e8a00ebded28558cd5702fb208bd538aa` |
| `tests/test_data_plans.py` | `f6fa357b98af8bf1f2bf1652d1a4851dad824cadaef7fb3493d7da6e79284356` |
| `tests/test_enumeration.py` | `72725319df12b0b094235eade6d9b4bfac1755e62ea6733ff9712d80dfadbd57` |
| `tests/test_integration.py` | `f074839b7de0317afcf70bb3c8b988e252427aae5b8db1ad7a086127afeeb398` |
| `tests/test_model.py` | `05a23955e3e7c74a047952d830bdff072872a7f1f301049f452d5e86a1423131` |
| `tests/test_verify.py` | `1da731ac184ca9fff7160ce80bbb2507bf95c88ffc0f7cb96ffa948b9d8c0263` |
| `data/synthetic/demo.json` | `31aee16cb20a899a490f2101929932862019b6dc63a3cfd9b3372d392e8305a9` |
| `README.md` | `f28be8a7a4d91cbc7363cb4338748d6f564622cb9dfeaa49eea6a5f994c9f38a` |
| `MODEL.zh.md` | `c0ab54b9e77afac608dc8b1c5e18db6304dee934a0467b463ac6173301afc06b` |
| `CONTRACT.md` | `a74f60222b701f60554b8f010e412e05e711a88d8d27537bb8d8e062c0a0a667` |
| `DATASET.zh.md` | `e3fa54e5e5b8d126c7837335f92b4b975dd8dcd551787e72e168d00308499cb6` |
| `requirements.txt` | `03fab59c975e353e86abcee8a89962907cc2f9e0d34f705a369ecda646a9483f` |

恢复的历史 README 原样包含旧 `results/`、参考参数表及本机 `.venv/` 的阅读/运行提示；这些不属于此次最小恢复副本。以本文件和本轮正式结果包为恢复入口，不把旧 README 的“本次验证”误读为 2026-11-04 复现。

### 未复制到主仓库的历史证据哈希

前五项路径相对于原始 `truck_charging_v1/`，后五项相对于原始 `outputs/2026-10-15_research_scope_small_case/`。仅有哈希不能从远端重建这些历史原件；新复现应由已版本化源码及合成输入生成独立证据。

| 原件 | SHA-256 |
|---|---|
| `results/test_report.xml` | `4e2b5298ae25fe21d71f255a2fd04a43d0a7087c0b4807b56562f9f78985af99` |
| `results/comparison.json` | `4af09dd5df56b9a1fcb0e2093fbf219d9c7effed07d4320b3aa79e3645c6a556` |
| `results/base/manifest.json` | `f45e7d28e78d88782027cfefead13ae53d52079ca20311968b54af707aedf960` |
| `results/base/verification.json` | `2f3269efe20b82cbf5c337b42a458d0816bc8852f6878cda2d08e5d093e14044` |
| `results/relaxed_service/verification.json` | `3f915ab620b02e5ef32086fdcd3d5ae7b09f843a1172a832201443a7d80d9cf2` |
| `model/solve_small_case.py` | `c599f8f6c4941eb3a9f9ae46ca16c7cf3e69a9d3620cba068aa74ebe40b2c480` |
| `model/manifest.json` | `c8d4bc5441ebdac71ed191884cfaddd5f8095e4af851b32fbf21bf9a9fd24265` |
| `model/milp_results.csv` | `69899e5e674f067258f417ee2452197dc0d96838dcfd3b3b08f116de8f2a3c9f` |
| `independent_validation.py` | `d47c2e03662cbc072b8b3da90e905bca18fac4966db55aac16bf55f8fccf7dd2` |
| `independent_validation.json` | `c885b5ef8cf675caf14e1c5df3a6f30301b5ef27c194ad7491115f32751de472` |

## 本轮可执行验收

先将恢复源码和合成输入提交到研究分支，再用该精确提交重跑原型。`run.py` 已有 `--output` 参数，应明确指定外部运行目录。测试使用 `python -B -m pytest -q -p no:cacheprovider` 并把 JUnit XML 写入外部运行目录，以免覆盖旧报告或在恢复副本产生运行缓存。

同时，按当前 FORMULATION 新建或扩展固定任务、固定设施、2–3 站的连续电量模型；明确新实现来源，独立复算电量、接口、功率和成本。不要以恢复旧原型或读取历史 JSON 代替这一步。本文件不预先宣布任何本轮测试通过。
