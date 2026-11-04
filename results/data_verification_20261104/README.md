# 德国数据验证精选结果

数据源提交：`bc892a70457721b4253066ac07d397287e6a0d0a`。

**正式复跑通过**：入口源码提交 `4d3f3a045cc02ddde35acd69249ff08f78270861`，run_id 为 `20261104_dataset_snapshot_canonical`，退出码0；运行时工作树干净，Python断言开启。环境为 Python 3.12.14、pandas 2.3.3、numpy 2.5.4，满足旧工程依赖声明。

本轮首先保留了两次真实失败：Windows 工作树副本的 `raw/dt_cargo/fleet.csv` 哈希不符；Git blob 副本的 `raw/simbench/csv/Coordinates.csv` 哈希不符。诊断证明是原数据混合换行与 Git 转换造成的字节差异。

按原 SHA-256 清单，从版本化 SimBench ZIP 恢复16个CSV的原始字节后，未修改的 `verify_dataset.py` 通过。新入口的开发验证和正式复跑均通过64条清单记录，并独立重算关键数量及原始LoadProfile完整性。完整过程见[数据审计](../../docs/research/DATA_AUDIT_20261104.md)；[validation.json](validation.json)为正式验证摘要，[development_validation.json](development_validation.json)保留开发验证，[reproduction.json](reproduction.json)分别记录四次开发运行和正式运行。

| 指标 | 本次从现存文件重算 |
|---|---:|
| 车辆 / 车队 | 53 / 4 |
| 行驶片段 / 有记录车辆日 | 101826 / 6869 |
| 派生周期 / 质量合格周期 | 7073 / 3520 |
| 进入规则曲线的周期 / 车辆 | 2546 / 49 |
| 曲线补能量 | 76749.89684203 kWh |
| 质量合格周期需电量覆盖率 | 14.0872071% |
| 原始LoadProfile行数 | 35136，未发现空单元格 |

四次开发运行使用 Python 3.12.14、numpy 2.5.3、pandas 3.0.5；其中 pandas 超出旧工程声明的 `<3.0` 范围。该环境差异及两次失败继续保留。正式运行使用另建环境，验证结果单独记录，不修改这些历史运行。

正式输入清单见 [input_inventory.json](input_inventory.json)。本地原清单 SHA-256 为 `0c552f2eb646dd0ac51e6a1ebd1cb6d9865a27b90c8371d320e84b09d7bb8ab0`；本目录统一使用 LF 换行，发布副本 SHA-256 为 `28b811a1cf1a9f3b809235728eeb76f12b1b60cfecb8ecdc20b220146123e72f`。两份 JSON 的逐文件路径、字节数和数据哈希完全相同。本地完整运行包及 driver 的文件摘要见 [canonical_evidence_index.json](canonical_evidence_index.json)，该索引 SHA-256 为 `c65ff3d55e0df433e9523707453408d551f42a6baa2a7949ba863981f6ce17eb`。索引只包含文件名、大小和哈希，不包含日志正文。

重跑入口是 [scripts/verify_dataset_snapshot.py](../../scripts/verify_dataset_snapshot.py)：指定完整 `--source-commit`、仓库外无remote独立Git中的新 `--output` 目录，以及 `--python-executable`。入口保持原清单不变、拒绝覆盖既有目录、强制保留 Python 断言，并保存全部本地证据。

在上述入口源码提交的研究仓库目录中，使用已配置的本地独立环境运行下列 PowerShell 命令。`20261104_dataset_snapshot_rerun` 是新的输出目录名，不能已存在：

```powershell
& '..\UM-RESEARCH-runs-local\.venv-dataset\Scripts\python.exe' scripts/verify_dataset_snapshot.py --source-commit bc892a70457721b4253066ac07d397287e6a0d0a --output '..\UM-RESEARCH-runs-local\20261104_dataset_snapshot_rerun' --python-executable '..\UM-RESEARCH-runs-local\.venv-dataset\Scripts\python.exe'
```

另一台机器须先初始化仓库外无remote的独立运行Git，并在所选Python环境安装本次实际验证版本 `pandas==2.3.3`、`numpy==2.5.4`。上述路径是本机重跑布局；实际正式执行的完整参数另存于 `reproduction.json` 的 `canonical_run.actual_command`。

本轮没有运行 `build_dataset.py`，没有从原始运营记录重新构造全部派生表。规则曲线覆盖的是筛选后的独立周期，没有验证跨周期SOC、接口或接入功率可行性；这些数值不证明全车队或真实港口的运营可行性。无优化求解，所以 objective、bound、gap 均为 null。

完整日志、隔离数据副本与运行脚本快照仅保存在外部 `UM-RESEARCH-runs-local/`；本目录不包含原始日志。
