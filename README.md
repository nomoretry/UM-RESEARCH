# UM-RESEARCH

整个项目从 [PROGRESS](docs/PROGRESS.md) 接续；按聊天记录见 [对话索引](conversations/INDEX.md) 和 [操作说明](docs/workflow/CONVERSATIONS.md)。共享科研状态继续保存在原位置。

电动重卡充电设施与调度研究。当前已恢复旧MILP原型、复跑德国数据校验，并新建和验证三车两站固定设施连续SOC模型。全部研究结果的来源、限制与下一任务见 [STATUS](docs/research/STATUS.md)。

## 本轮可核验结果

| 内容 | 实际完成 | 入口 |
|---|---|---|
| 旧原型恢复 | 20个必要文件按字节复制；本次106项测试通过 | [恢复审计](docs/research/LEGACY_RECOVERY_20261104.md)、[复现结果](results/legacy_reproduction_20261104/README.md) |
| 德国数据工程 | 原验证器和独立重算通过；保留换行字节导致的两次失败 | [数据审计](docs/research/DATA_AUDIT_20261104.md)、[精选结果](results/data_verification_20261104/README.md) |
| 新固定设施MILP | 37项测试、六情景；基准200kWh/300模拟货币，三类无解、零需求及零收益保留 | [实例与命令](docs/model/MINIMAL_INSTANCE.md)、[精选结果](results/fixed_facility_20261104/README.md) |

旧历史报告、本次正式复现和计划分别记录。最小实例为四小时合成周期，不是德国或南沙实证。接口投资与离散扩容尚未实现，真实运营窗口尚未确认。

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
- 仓库外并列 `UM-RESEARCH-runs-local/`：已初始化的独立本地Git，无remote；保存失败、stdout/stderr、完整输入及原始解，不推送。

本仓库保持原有私有状态。数据仅用于德国匿名运营样本与典型电网情景，不能写成真实港口业务或实际接入关系。
