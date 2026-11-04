# 德国数据验证精选结果

数据源提交：`bc892a70457721b4253066ac07d397287e6a0d0a`。

本轮首先保留了两次真实失败：Windows 工作树副本的 `raw/dt_cargo/fleet.csv` 哈希不符；Git blob 副本的 `raw/simbench/csv/Coordinates.csv` 哈希不符。诊断证明是原数据混合换行与 Git 转换造成的字节差异。

按原 SHA-256 清单，从版本化 SimBench ZIP 恢复16个CSV的原始字节后，未修改的 `verify_dataset.py` 通过。新入口的开发验证也通过64条清单记录，并独立重算关键数量及原始LoadProfile完整性。完整过程见[数据审计](../../docs/research/DATA_AUDIT_20261104.md)；[validation.json](validation.json)是精选数值，[reproduction.json](reproduction.json)记录四次开发运行的状态及本地证据摘要哈希。

| 指标 | 本次从现存文件重算 |
|---|---:|
| 车辆 / 车队 | 53 / 4 |
| 行驶片段 / 有记录车辆日 | 101826 / 6869 |
| 派生周期 / 质量合格周期 | 7073 / 3520 |
| 进入规则曲线的周期 / 车辆 | 2546 / 49 |
| 曲线补能量 | 76749.89684203 kWh |
| 质量合格周期需电量覆盖率 | 14.0872071% |
| 原始LoadProfile行数 | 35136，未发现空单元格 |

四次开发运行使用 Python 3.12.14、numpy 2.5.3、pandas 3.0.5；其中 pandas 超出旧工程声明的 `<3.0` 范围。这些运行不可替代声明依赖范围内的正式复跑。后续正式运行须在源代码提交之后执行，并将其源提交、环境与结果另行记录。

重跑入口是 [scripts/verify_dataset_snapshot.py](../../scripts/verify_dataset_snapshot.py)：指定完整 `--source-commit`、仓库外无remote独立Git中的新 `--output` 目录，以及 `--python-executable`。入口保持原清单不变、拒绝覆盖既有目录、强制保留 Python 断言，并保存全部本地证据。

本轮没有运行 `build_dataset.py`，没有从原始运营记录重新构造全部派生表。规则曲线覆盖的是筛选后的独立周期，没有验证跨周期SOC、接口或接入功率可行性；这些数值不证明全车队或真实港口的运营可行性。无优化求解，所以 objective、bound、gap 均为 null。

完整日志、隔离数据副本与运行脚本快照仅保存在外部 `UM-RESEARCH-runs-local/`；本目录不包含原始日志。
