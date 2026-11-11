# 电动重卡在港区和仓库的充电设施规划

三辆重卡从港区驶往仓库，装卸后返回港区。车辆停在仓库时，有多少时间真正可以接上充电枪？这段时间会改变港区需要安装的接口数量，也会改变两站各自需要的接入功率。给定相同的运输任务和期末电量要求，模型联合决定两地新增多少接口、是否付费扩容，以及每辆车在什么时间充多少电。

## 一个接口不够用的算例

在一个四小时合成算例中，港区有 2 个接口、100 kW 容量，仓库有 1 个接口、75 kW 容量。每辆车最多以 50 kW 充电。车辆在仓库停留 60 分钟，其中 45 分钟允许插枪。模型允许每 15 分钟轮换车辆，假设换枪不耗时。

三辆车合计需要从电网购入 133.33 kWh。只看两站的功率和可用时间，最多可供 137.5 kWh。把这部分电量分配到每辆车时，仓库的 3 个可用接口时段用完后，回到港区仍至少需要 9 个接口时段，而港区只能提供 8 个。相同的停车和运输任务下，若仓库允许插枪的时间延长到 60 分钟，同一套设施就能完成任务。

[运输任务与设备参数](configs/port_warehouse_investment.json) · [实验配置](configs/power_window_study.json) · [数学模型](docs/model/FORMULATION.md) · [结果图、计算依据与 Windows 复现命令](results/boundary_20261110/README.md)

## 研究进展

[当前状态与适用范围](docs/research/STATUS.md) · [项目进度](docs/PROGRESS.md) · [对话索引](conversations/INDEX.md) · [记录流程](docs/workflow/CONVERSATIONS.md)

2026-11-11 · 固定设施压力测试。两辆车准时到仓库，但要等 45 分钟才能插枪，第三辆车仍可用完整窗口。在相同的港区 100 kW、仓库 75 kW 供电条件下，港区有两个接口时无法完成任务，增加到三个接口后可以完成。若延迟 60 分钟，两套设施均无解。[十个情景的结果](results/eligibility_stress_20261111/metrics.json) · [验证与复现命令](results/eligibility_stress_20261111/reproduction.json)

2026-11-10 · 已完成15分钟港区已有功率×仓库补能窗口适用边界，222测试、100情景/3150枚举、100任务审计和310跨情景性质检查通过。50个同策略比较有23降费、17零收益、8恢复可行性、2均无解；费用均为同周期合成参数。见[可展示结果、任务窗口图、设施矩阵、瓶颈解释与Windows命令](results/boundary_20261110/README.md)、[能力清单](docs/research/CAPABILITIES.md)。

2026-11-10上一里程碑：同一物理任务链60/30/15分钟检验已完成，149测试、54情景/840组合枚举、18次历史核对与原6情景回归通过。槽边界零耗时换枪时两地联合投资75→50；整窗固定连接时粗细网格均75。原实际到离站和插枪时长未变，结论须限定连接政策。见[时间粒度历史结果](results/timegrid_20261110/README.md)。当时计划的功率×窗口实验现已完成，见最新结果。

2026-11-10上轮：在连续电量模型上实现接口整数与离散接入扩容；完整合成港区—仓库闭合链、102测试、9投资情景/140组合枚举及原6情景回归通过。见[历史投资结果](results/investment_20261110/README.md)。采用Ye 2024的问题与投资框架，明确为项目改编；费用仅为同周期合成等效费用。

## 2026-11-04历史可核验结果

| 内容 | 实际完成 | 入口 |
|---|---|---|
| 旧原型恢复 | 20个必要文件按字节复制；本次106项测试通过 | [恢复审计](docs/research/LEGACY_RECOVERY_20261104.md)、[复现结果](results/legacy_reproduction_20261104/README.md) |
| 德国数据工程 | 原验证器和独立重算通过；保留换行字节导致的两次失败 | [数据审计](docs/research/DATA_AUDIT_20261104.md)、[精选结果](results/data_verification_20261104/README.md) |
| 新固定设施MILP | 37项测试、六情景；基准200kWh/300模拟货币，三类无解、零需求及零收益保留 | [实例与命令](docs/model/MINIMAL_INSTANCE.md)、[精选结果](results/fixed_facility_20261104/README.md) |

历史报告、本轮检查与本轮新运行分别记录。实例为四小时合成周期，不是德国或南沙实证。接口投资与离散扩容已于11月10日验证；真实运营窗口、真实成本及年化多代表日仍未确认。

## 接续入口

- [AGENTS.md](AGENTS.md)、[首次恢复提示词](prompts/BOOTSTRAP.md)、[继续提示词](prompts/RESUME.md)
- [研究状态](docs/research/STATUS.md)、[决策记录](docs/research/DECISIONS.md)
- [数学规范](docs/model/FORMULATION.md)、[公式与验证对应](docs/model/IMPLEMENTATION_MAP.md)
- [本地日志与结果保存规则](docs/workflow/STORAGE.md)

## 现有结构

- `src/um_charging/`、`tests/`、`configs/`：新固定设施模型、独立复算和合成配置；实际环境锁定见 `requirements-milp.txt`。
- `legacy/truck_charging_v1/`：实物恢复的旧有限方案MILP。README中的旧“本次”文字属于历史说明，以当前STATUS为准。
- `reserach/truck optimaztion/Germany_Truck_Grid_Dataset_v1/`：完整德国数据工程，58个基线tracked文件。
- `reserach/Germany_Truck_Grid_Dataset_v1/`：较小同名目录，11个tracked文件；11个公共文件的Git字节完全一致，两目录均保留。
- `scripts/verify_dataset_snapshot.py`：从指定commit建立仓库外隔离副本，用已核验ZIP恢复原始字节，再运行原验证器；不改原清单，不重建数据。
- `results/`：可共享的精选指标、验证及复现清单。`build_dataset.py`与`generate_metadata.py`本轮未执行。
- 仓库外并列 `UM-RESEARCH-runs-local/`：历史独立本地Git，无remote，原地保留。新运行沿用机器配置所指既有外部记录Git及对话0001；完整日志/原始解不推送，见[存储约定](docs/workflow/STORAGE.md)。

本仓库保持原有私有状态。数据仅用于德国匿名运营样本与典型电网情景，不能写成真实港口业务或实际接入关系。
