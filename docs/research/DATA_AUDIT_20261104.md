# 德国数据工程审计 — 2026-11-04

数据源码基线：`bc892a70457721b4253066ac07d397287e6a0d0a`。本轮验证已有文件及其一致性，没有运行 `build_dataset.py`，没有重新下载来源，没有改原始清单或数据。

## 已找到的两个目录

- 完整数据目录：`reserach/truck optimaztion/Germany_Truck_Grid_Dataset_v1/`，58 个 tracked 文件。
- 较短目录：`reserach/Germany_Truck_Grid_Dataset_v1/`，11 个 tracked 文件。
- 11 个共同文件的 Git blob 字节完全一致。较短目录没有 tracked `raw/` 或 `processed/`；两个版本均保留，不把短目录当作完整数据交付。

## 本轮实际运行

| run_id | 输入和操作 | 实际结果 |
|---|---|---|
| `20261104_dataset_verification_initial` | 完整工作树的隔离副本；原样运行 `verify_dataset.py` | exit=1，`raw/dt_cargo/fleet.csv` 的 SHA-256 不符 |
| `20261104_dataset_verification_gitblob` | 从基线提交提取原始 Git blob；同一未修改验证器 | exit=1，`raw/simbench/csv/Coordinates.csv` 的 SHA-256 不符 |
| `20261104_dataset_verification_restored_bytes` | Git blob 副本中，从版本化 SimBench ZIP 恢复 16 个 CSV 的原始字节；原清单保持不变 | exit=0，原验证器通过 |
| `20261104_dataset_snapshot_smoke` | 新入口 `scripts/verify_dataset_snapshot.py` 的开发验证；同样恢复方法，增加独立计数和原始 LoadProfile 完整性检查 | exit=0，64 条清单记录全部匹配 |

以上四次使用 Python 3.12.14、numpy 2.5.3、pandas 3.0.5，均未启用 `-O`。pandas 3.0.5 超出了旧工程 `pandas>=2.0,<3.0` 的声明范围；因此这些成功是有环境差异的本次验证，不能写成原声明环境已经复现。正式复跑记录见[精选结果](../../results/data_verification_20261104/README.md)。

## 失败原因及可重现处理

本机克隆配置为 `core.autocrlf=true`。原始清单共有 7 条来源记录和 57 条文件记录（部分文件在两张清单中重复）。工作树只有 18/64 条哈希匹配；提交内 Git blob 有 48/64 条匹配。差异是换行字节，不是数值验证失败。

16 个 `raw/simbench/csv/*.csv` 的原始字节采用 CRLF，早先加入 Git 时已被归一化为 LF。它们当前 Windows 工作树的字节符合原清单，但 Git blob 的字节不符合。其余受转换影响的文本文件相反：Git blob 符合清单，Windows CRLF 工作树不符合。因此统一切为 LF、统一切为 CRLF或只关闭自动换行都不足以恢复所有原始哈希。

版本化 `raw/simbench/1-MV-urban--0-sw.zip` 本身符合既有来源 SHA-256；其中 `1-MV-urban--0-sw/` 下的 16 个 CSV 成员逐一符合既有文件清单。新入口在仓库外的新目录提取指定提交，再从该 ZIP 恢复这 16 个成员，检查全部既有 SHA-256 和字节数，最后运行未修改的 `verify_dataset.py`。每次保存输入清单、恢复记录、环境、命令、退出码和源脚本快照；失败和已有目录均不覆盖。

这是按原始清单恢复文件字节，不是重建派生数据或修改清单以使验证通过。主仓库旧数据与旧清单保持原状。

## 独立重算得到的范围

开发验证从文件重新计数：53 辆、4 个车队、101826 条片段、6869 个有记录车辆日、7073 个派生周期。3520 个周期通过既有质量/窗口规则，2546 个周期进入规则曲线，涉及49辆车；其需电量为 76749.89684203 kWh，占质量合格周期需电量的约14.0872%。原始 LoadProfile 有35136行且未发现空单元格。

原 `verify_dataset.py` 重算主键、外键、里程、曲线能量和网模连接一致性，但对 `validation_checks.csv` 只读其已有 `pass_` 列，不能把该文件中的全部历史检查都称为重新计算。本轮新入口另行检查了原始 LoadProfile 的行数和非空性。

## 数据工程到模型的实际边界

- `build_dataset.py` 对相邻基地记录端点构造独立周期；`track_gap` 方向未获澄清，因此同时约束相邻两行。该保守规则不等于真实插枪窗口已验证。
- `energy_kwh_per_km=1.2`、`charger_ac_kw=150.0`、`efficiency=0.95`、`battery_nominal_kwh=500.0` 和 SOC 10%–90% 是情景参数。能量从里程推导，不是实测电动车 SOC 或充电量。
- 即时/均匀曲线是各独立周期的补能规则，无连续跨周期 SOC、接口数、排队或站点功率优化。14.0872%的覆盖率不能推成全车队电动化可行。
- 四车队与 SimBench 节点的对应是按排序索引生成的情景映射；德国车辆记录与2016网模曲线没有真实同地同时关联。
- 本轮未重建全数据、未验证缺口的物理含义、未运行潮流，也未以这些数据构造真实港口运营结论。固定任务小 MILP 的合成输入应与此数据线明确分开。

完整运行包仅在仓库外 `UM-RESEARCH-runs-local/`，其独立 Git 无 remote。主仓库仅存本文、可复跑入口及精选结果。
