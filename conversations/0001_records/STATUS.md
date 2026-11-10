# 状态 — 0001

## 2026-11-10科研接续：投资层已验证

按用户明确绑定沿用0001，不扫描其他聊天、不init/register。原研究checkout与记录机制checkout的工作保持原位；研究在独立codex/investment-milp-20261110分支。

已完成：Ye 2024作为问题/投资框架的本项目改编；新增接口整数、互斥扩容、闭合港区—仓库任务链及独立C01–C07/费用检查。源码43e34cac0d9ad4268dc54e9aa98fcea25e977320正式运行102测试、9投资情景/140组合及原6情景回归全部通过。[结果](../../results/investment_20261110/README.md)、[设计](artifacts/INVESTMENT_DESIGN_20261110.md)。

结果：仅港区联合238.333，两地仅接口233.333，两地联合208.333；为同一四小时周期合成总费。仅扩功率仍无解，仓库已有功率75→100零收益。五个投资无解及非唯一调度保留，不推断真实经济性/最小峰值/潮流。

历史核查：旧106、新37的原JUnit与记录哈希一致，原两套六情景确认；11月9日d07d452仅文献与设计。旧106本轮未重跑，原37包含在本轮102中。记录机制集成测试本轮没有重跑。

失败与处理：系统Python缺pytest/scipy，改用历史command.json中的原虚拟环境，没有安装依赖。Git所有权差异采用当前进程精确safe.directory处理，不改全局信任。开发70项成功和缺pytest失败日志均保留；正式运行无失败。

完整记录在机器配置所指外部本地Git的本对话runs下，登记名20261110_investment_tests、20261110_investment_suite；对应_evidence保存原始证据。仅测试用的临时Git夹具完整保留到系统临时目录，位置见本地temporary_fixture_location.json；研究输入/结果未移动。

在干净源码提交及requirements-milp.txt对应环境重跑，输出必须是现有无remote独立Git内的全新目录：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -X utf8 -B -m um_charging.investment_cli --config configs/port_warehouse_investment.json --regression-config configs/minimal_three_trucks.json --output '<既有外部本地Git>/<全新运行目录>/artifacts'
python -X utf8 -B -m pytest -q -p no:cacheprovider tests/test_fixed_facility.py tests/test_cli_paths.py tests/test_investment_input.py tests/test_investment.py
```

下一步：相同物理时长、耗能和费用下做时间粒度检验，再固定硬件做窗口扰动。真实窗口/成本、年化多代表日与上级供电未验证。同步仅推送本轮研究分支并实时核对远程SHA，不合并main。

## 记录机制建设时的原状态（保留，不当作本轮验收）

更新：2026-11-10。独立主对话，用户已确认；平台 ID 未取得，编号和标题为本地登记。目录固定为 `conversations/0001_records/`。

## 已验证

- 实际研究库和远程已核实，原研究 checkout 干净；本机制在独立 `codex/conversation-records-20261110` worktree 中实现，原 checkout 没有切换分支。
- 主对话登记和绑定已在正式项目执行；动作日志已进入外部独立本地 Git，无 remote。初始化失败和前期观察已明确补录。
- 外层 117 个研究源码/配置/说明文件及新增工作区 AGENTS 已建立仅本地保护提交 `c1f5ab12f40267c68395c5fab50a1850786515d2`，分支 `codex/local-preservation-20261110`；118 个 Git blob 与工作树 SHA-256 相同。使用独立索引，外层当前 HEAD、暂存区和原文件未变。
- 另保护 3 份根目录研究提案/文献说明，保护分支最新提交 `47ff93942eef96fc3d2c57ddd4bf419fc79fc800`，共 120 个研究文件及外层 AGENTS。480 个历史结果（12,563,877 bytes）已保存到外部本地库，最终 Git blob 逐一哈希核验全部一致。
- 两处德国数据目录的 11 个公共文件哈希相同；完整关系见 [资源索引](../../docs/workflow/RESOURCE_INDEX.md)。没有合并目录，也没有重跑科研实验。
- App 工具采集边界已核对，见 [APP_CAPTURE](../../docs/workflow/APP_CAPTURE.md)。

## 未完成与限制

- 机制集成测试、代码审查修正和正式配置分支同步正在完成；不把本地文件存在视为已同步。
- 原有详细日志库原地保留；新库路径在忽略的机器配置中。完整聊天和全部工具事件没有自动导出。
- 科研实验、模型代码和文献结论未在本次重验；科研下一步仍见 [科研 STATUS](../../docs/research/STATUS.md)。

## 失败与处理

首次受限网络 fetch 失败，授权网络 fetch 成功；两次 init 因 Git check-ignore 不支持 literal pathspec 失败，修复后登记成功。独立审查发现快照字节保留与脱敏覆盖需加强，修正和回归测试进行中。详细过程只在本地 actions.jsonl 保存。

历史结果首次提交遇到 Windows 命令长度限制，改用 NUL 分隔 stdin 路径清单后成功。另发现系统 core.autocrlf 转换了 451 个首次归档 blob；原件与工作副本未变，新增本地 `* -text` 后定点重新提交，480 个 blob 最终全部匹配。保留旧提交和修正审计，不掩盖首次失败。

## 接续与验证命令

在当前机制 worktree 根目录运行：

```powershell
python -X utf8 scripts/conversation_records.py bind --conversation 0001
python -X utf8 scripts/conversation_records.py status --conversation 0001
python -m unittest discover -s tests -p test_conversation_records.py -v
git diff --check
```

下一步：完成隔离测试和审查，保存配置检查点，明确推送该分支并核对实时远程 SHA。其他聊天首次接入必须登记自己的编号，不能因本机当前绑定为 0001 就共用本对话目录。
