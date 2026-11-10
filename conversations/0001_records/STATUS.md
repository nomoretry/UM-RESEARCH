# 状态 — 0001

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
