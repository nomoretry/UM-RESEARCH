# 共享资源与历史材料索引

核查日期：2026-11-10。以本地文件、Git 清单和 SHA-256 为依据；不推断文件属于哪一次历史聊天。未登记的历史聊天在首次接入时确认关系。

## 仓库中的共享资源

| 路径 | 用途与状态 |
|---|---|
| [src/um_charging](../../src/um_charging/) | 固定设施连续能量模型和验证代码；本次未修改模型或重跑求解 |
| [configs](../../configs/)、[tests](../../tests/) | 共享配置与测试；新增记录机制测试独立于科研测试 |
| [legacy/truck_charging_v1](../../legacy/truck_charging_v1/) | 已恢复的旧原型；20 个来源文件与外层原件、RECOVERY.json 的哈希相同 |
| [results](../../results/) | 已有精选结果；历史运行日期和限制以原清单为准 |
| [docs/research/STATUS.md](../research/STATUS.md) | 科研状态；本次未产生新的 MILP、真实数据或经济性结果 |
| [docs/literature/20261109](../literature/20261109/) | 11月9日文献与基线建议，不能把推荐阶段写成已实现 |

## 两处 Germany_Truck_Grid_Dataset_v1

| 准确路径（保留原拼写） | tracked 文件数 | 当前工作树总字节数 |
|---|---:|---:|
| [reserach/Germany_Truck_Grid_Dataset_v1](../../reserach/Germany_Truck_Grid_Dataset_v1/) | 11 | 99,761 |
| [reserach/truck optimaztion/Germany_Truck_Grid_Dataset_v1](../../reserach/truck%20optimaztion/Germany_Truck_Grid_Dataset_v1/) | 58 | 105,025,497 |

小目录的 11 个相对路径全部存在于大目录，逐文件 SHA-256 相同；小目录无独有文件。大目录另外 47 个文件：24 个 processed、4 个 DT-CARGO 原始文件、19 个 SimBench 原始文件。未发现这两处的未跟踪或被忽略文件。

这只证明本次工作树字节关系，不证明创建原因、聊天归属、数据正确性或可接入性。本次不合并、删除或改名；需要完整工程时按已有研究说明使用大目录。没有执行原数据验证器。

## 外层工作区的历史材料（本地关联，不上传原件）

以下相对链接依赖当前并列目录结构；GitHub/其他机器没有这些外部文件时不能声称已读取。

| 位置 | 本次分类与处理 |
|---|---|
| [port-drayage-charging](../../../port-drayage-charging/) | 非独立 Git 仓库；32 个源码/配置/说明文件进入外层本地保护清单。带输出的 notebook 排除 |
| [truck_charging_v1](../../../truck_charging_v1/) | 非独立 Git 仓库；21 个源码/配置/说明文件进入外层本地保护清单 |
| [outputs/2026-10-15_group_meeting](../../../outputs/2026-10-15_group_meeting/) | 29 个研究脚本与说明进入本地保护清单 |
| [outputs/2026-10-15_research_scope_small_case](../../../outputs/2026-10-15_research_scope_small_case/) | 9 个文件进入本地保护清单 |
| [outputs/2026-10-16_port_delay_small_case](../../../outputs/2026-10-16_port_delay_small_case/) | 7 个文件进入本地保护清单 |
| [outputs/2026-10-19_proposal_live_demo](../../../outputs/2026-10-19_proposal_live_demo/) | 13 个文件进入本地保护清单；详细 runs 单独保存在本地 |
| [outputs/researchwrite/port-delay-20261016](../../../outputs/researchwrite/port-delay-20261016/) | 6 个研究说明文件进入本地保护清单 |
| [UM-RESEARCH-runs-local](../../../UM-RESEARCH-runs-local/) | 既有独立本地 Git，无 remote；原地保留。核查起始 HEAD 为 ec82a6607abd1e3b9be7c05634788f8d4e4ada27 |

上述源码/说明清单共 117 文件、982,638 bytes。有限凭据模式扫描未发现相关密钥；不把模式扫描当作绝对保证。未批量 add 外层未跟踪目录。

随后另核查并保存外层 `literature_review_5papers.md`、`UM_重卡充电Proposa.md`、`UM_重卡充电Proposal与1V1汇报_2026-10-15.md` 三份研究说明。仅本地保护分支共保存 120 个研究文件及新增外层 AGENTS；最终保护提交为 `47ff93942eef96fc3d2c57ddd4bf419fc79fc800`，没有切换外层 HEAD 或改变暂存区。

重要历史详细结果：`port-drayage-charging/results` 274 文件/7,345,651 bytes（被忽略）；`port-drayage-charging/reports` 96/3,338,966；`truck_charging_v1/results` 40/89,615；`outputs/2026-10-19_proposal_live_demo/runs` 70/1,789,645。这些不是可丢弃缓存，保护详情见当前对话的本地日志。

以上 480 个历史结果文件已复制到外部本地记录库的当前对话 preservation 目录，原件保留；最终逐一验证 Git blob 与原件哈希相同。期间发现系统 CRLF 转换影响首次提交，已用本地 `* -text` 属性定点修正并保留前后审计；没有改写旧历史。

个人简历、申请材料、课程作业、技能库、缓存和环境不纳入本次研究同步。`tmp` 部分环境目录读取被拒绝，不能声称全工作区逐文件无遗漏审计；这些目录未进入保存或上传范围。
