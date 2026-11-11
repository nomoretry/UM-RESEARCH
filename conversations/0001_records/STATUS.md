# 状态 — 0001

## 已知延迟的联合设施规划

起始分支与远程 055d08c 一致。源码 f9b8ab4 复用零延迟联合/54 组及正延迟 A/B 的 8 组，新增 4 个联合/208 个运营求解。五档最低投资 20、20、20、40、75。45 分钟时港二仓二可行，比最低成本的港三仓一贵 10。全部原始调度检查与 245 项测试通过。完整记录编号 `20261111_known_delay_investment`，下一项为检验有换枪耗时的设施替代边界。[复现命令和范围](../../docs/research/STATUS.md) · [结果](../../results/known_delay_investment_20261111/metrics.json)

## 2026-11-11 · 停车间隔与插枪资格

`py -3 scripts/trace_dt_cargo_stop.py` 在干净源码 `c2e5041` 下复核车队 1、车辆 1、片段 168→169，记录间隔 1,230.765 秒。可匹配的独立到站、放行、接枪和送电时刻均为空。4 项测试通过。完整运行在已绑定的外部记录库 `20261111_dt_cargo_single_stop`。下一步由同一停靠的作业或充电会话记录核实可插枪时间。[精选输出](../../results/dt_cargo_stop_20261111/event.json)

## 2026-11-11 · 读者复算入口

本地干净研究树已快进至远程 7037963。固定设施插枪延迟已在该提交记录。本轮在 Windows 用 `py -3 scripts/check_eligibility_slots.py` 复算 45 分钟档的 9 个接口时段，A 无解、B 可行。十个 MILP 状态与已存结果一致，10 项相关测试通过。默认 pytest 临时路径首次拒绝访问，改用新的本地证据子目录后通过。完整运行见既有本地记录 `20261111_readme_delay_replay`；首页链接算例输入、模型和求解结果。

## 2026-11-10功率×窗口边界实验已验证

仍为明确绑定0001、codex/investment-milp-20261110和原外部无remote记录库。起始3a618b6、本地/远程一致、工作树干净。长期研究与Claude协作规则已进入AGENTS/工作流，规则里程碑c9b3005已实时同步核对；没有新增记录系统、读取其他项目或迁移磁盘。

正式源码a520cac2ea26dd237d4c6cccd32c0518cb8247f7：222测试、100情景/3150枚举、100任务审计、310性质比较、4历史重叠及原6回归通过。88联合最优、12无解；1048可行解497,502检查，最大残差2.5264e-13、联合最大gap3.5776e-16。[对照/图/解释/Windows命令](../../results/boundary_20261110/README.md)

50同政策范围对照有23降费、17零收益、8恢复可行性、2均无解。运营费均400/3，费用变化来自周期合成投资。仓库+25kW在H75/W45有价值；原零收益结论需限定窗口。H100窗口30→45→60投资50→40→20，但接口组成(2,2)→(3,1)→(2,1)非单调。3格并列设施完整保留，不声称调度唯一。

本地登记`20261110_boundary_tests`与`20261110_boundary_suite`，10,199个详细证据文件逐Git blob核验。开发73测试与正式222分开。正式实验无失败；Claude只读调用因未登录失败、0模型token，任务书已留存，未发生实际Claude审查。独立检查器原提交1b1aca1已集成；不能将Codex内部协作写成Claude协作。

下一项仅设计：固定H100的港2/仓1和港3/仓1两套硬件，容量均100/75，延迟V1/V2仓库资格起点而保持运输事件不变；均继续采用槽边界零耗时换枪政策，只重求运营，不重选设施。尚未实施压力测试或情景规划。

复现从本研究树根目录、requirements-milp.txt对应环境运行；输出为已有外部无remote Git内新目录：

```powershell
$env:PYTHONPATH = Join-Path $PWD.Path 'src'
python -X utf8 -B -m um_charging.boundary_cli --config configs/power_window_study.json --output '<已有外部Git>/<新运行目录>/artifacts'
python -X utf8 -B -m pytest -q -p no:cacheprovider tests/test_fixed_facility.py tests/test_cli_paths.py tests/test_investment_input.py tests/test_investment.py tests/test_timegrid_model.py tests/test_timegrid.py tests/test_boundary.py tests/test_boundary_validation.py
```

预期222通过、completion.json passed=true且100/3150/310；源码hash、环境、原始状态/界限/gap见精选复现清单。结果里程碑仅推送当前研究分支并实时核SHA，不合并main、不改变可见性。

## 上一里程碑：2026-11-10时间粒度检验（历史保留）

沿用明确绑定0001、当前codex/investment-milp-20261110及既有外部无remote记录Git；没有init/register、移动研究文件或迁移磁盘。起始HEAD与实时远程均318bf74，工作树干净。

本轮正式源码1c4df03c6a6943ce221e09e05a2bce538de304a7：149测试、54情景、840设施枚举、18次60分钟历史状态/目标比较、原6情景回归全部通过；54次物理事件审计确认实际到离时刻和窗口不变。285个可行解共86,375检查通过，最大残差2.8422e-14；联合最大gap1.5503e-16，保留浮点级非零。

核心结果：允许槽边界零耗时换枪时，两地联合投资60分钟75、30／15分钟50；两地仅接口100→50；仅港区联合105不变。整窗固定连接时粗细投资与可行硬件集合均不变。原投资结论应限定占用政策；不推断真实节约率或一般时间收敛。[结果表/图](../../results/timegrid_20261110/README.md)、[设计](artifacts/TIMEGRID_DESIGN_20261110.md)、[模型契约](../../docs/model/TIMEGRID_INPUT.md)。

记录：`20261110_timegrid_tests`、`20261110_timegrid_suite`；完整证据2940文件存于既有外部Git并逐一核验blob。开发129/20测试与正式149分开。正式测试/求解无失败；后处理曾提前读取未完成的归档清单，并在受限进程读取临时绘图包时遇到访问问题，已等待归档并用相应访问权限重试，失败与恢复记本地。求解环境未改，绘图用独立临时依赖。

在干净源码和requirements-milp.txt对应环境，输出使用既有外部无remote Git内新目录：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -X utf8 -B -m um_charging.timegrid_cli --config configs/timegrid_study.json --output '<既有外部本地Git>/<新运行目录>/artifacts'
python -X utf8 -B -m pytest -q -p no:cacheprovider tests/test_fixed_facility.py tests/test_cli_paths.py tests/test_investment_input.py tests/test_investment.py tests/test_timegrid_model.py tests/test_timegrid.py --junitxml '<本地测试证据>/junit.xml' --basetemp '<系统临时目录>/<新夹具目录>'
```

下一任务：港区已有可用功率50/75/100/125/150 kW × 仓库插枪窗口0/15/30/45/60分钟（从60分钟起，停靠到离时刻不动），固定15分钟网格；比较仅港区/两地联合投资，并用整窗连接与枚举检查。该二维实验本轮仅设计、未执行。同步目标仍为研究分支，实时远程SHA核验留本地，不合并main。

## 上轮：2026-11-10科研接续投资层验证（历史保留）

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
