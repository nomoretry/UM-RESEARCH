# UM-RESEARCH

电动重卡充电设施容量与调度研究。当前重点是恢复可核实进度，并将研究问题、数学模型、代码和实验结果连接起来。

**当前状态：旧 truck_charging_v1 已在用户工作目录定位并恢复，历史测试证据已核实；德国数据完成隔离开发校验；三车两站固定设施连续 SOC 模型为本轮新建。正式运行状态与限制统一见 [STATUS](docs/research/STATUS.md)。**

## 从这里开始

- [当前进度与证据](docs/research/STATUS.md)
- [研究决策与待确认项](docs/research/DECISIONS.md)
- [固定任务 MILP 建模草案](docs/model/FORMULATION.md)
- [公式—代码—验证对应表](docs/model/IMPLEMENTATION_MAP.md)
- [本地运行记录与 GitHub 结果的保存规则](docs/workflow/STORAGE.md)
- [首次恢复提示词](prompts/BOOTSTRAP.md)
- [后续继续提示词](prompts/RESUME.md)

AGENTS.md 提供会话入口规则；STATUS.md 是项目当前状态，不依赖聊天记忆。提示词中的命令须在真实工作环境执行后才可以记为成功。

## 已有工程

完整数据工程位于 `reserach/truck optimaztion/Germany_Truck_Grid_Dataset_v1/`。
同名目录也出现在 `reserach/Germany_Truck_Grid_Dataset_v1/`，其 tracked 文件较少。先比较、确认路径依赖再整理，不删除其中任一版本。

已有入口：
- `build_dataset.py`：重建派生数据，会写文件。应在隔离副本中复现。
- `verify_dataset.py`：读取已有数据与清单进行一致性检查，不要使用 Python -O。
- `generate_metadata.py`：生成元数据。
- `README_zh.md`、`summary.json`：历史数据快照及其限制。

以上脚本存在并经部分内容审阅，不表示本次运行通过。

## 逐步形成的结构

| 位置 | 用途 | 状态 |
|---|---|---|
| docs/research/ | 进度、证据、研究决策 | 已添加恢复记录 |
| docs/model/ | 公式、假设、代码对应关系 | 草案，待映射和求解 |
| prompts/ | 首次恢复与继续执行提示词 | 已添加 |
| 原有 reserach/、文献学习/ | 历史材料与数据工程 | 原样保留 |
| src/、tests/、configs/ | 新的可安装模型、验证与配置 | 按实际开发需要添加；不要先制造空架构 |
| results/ | 精选结果、分项指标、图表及复现清单 | 待真实实验后添加 |
| 仓库外 UM-RESEARCH-runs-local/ | 完整运行记录，独立本地 Git，无远程 | 须在实际运行机器初始化 |

本仓库保持现有私有状态。完整运行记录不上传，精选结果仍需足以解释来源和复现限制。
