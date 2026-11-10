# UM 项目进展入口

更新：2026-11-10。科研进展与记录机制分开核验；GitHub 分支内容不代表外层本地工作区的完整进展。

## 当前科研状态

[科研 STATUS](research/STATUS.md) 与 [科研 DECISIONS](research/DECISIONS.md) 保留原有证据边界。2026-11-04 的旧原型、德国数据校验与合成固定设施 MILP 结果是已有正式记录；2026-11-09 更新文献及基线建议，未重跑求解。本次仅建设记录和版本管理机制，不新增科研实验结论。

下一研究工作仍见科研 STATUS；接口投资与离散扩容尚未实现。真实港口数据及可信插枪窗口未确认。

## 对话与工作接续

- [对话总索引](../conversations/INDEX.md)：仅登记明确接入的聊天，不批量补造历史对话。
- [0001：记录与版本管理机制](../conversations/0001_records/STATUS.md)：本次独立主对话，用户已明确确认；编号及标题为本地登记，不是平台 ID 或平台标题。
- [操作说明与命令](workflow/CONVERSATIONS.md)、[App 采集边界](workflow/APP_CAPTURE.md)、[存储边界](workflow/STORAGE.md)。
- [共享资源与历史材料索引](workflow/RESOURCE_INDEX.md)：包括两处德国数据目录关系、外层源码和重要被忽略结果。

当前配置在 `codex/conversation-records-20261110` 独立分支和 worktree 中进行；原研究 checkout 保持 `codex/literature-baseline-20261109`。不会自动合并到 `main`。

## 建设前的本地与远程差异

实际研究 Git 根是外层 UM 下的 `UM-RESEARCH/`。起始工作树干净，HEAD `d07d452961f5fb3e208350a82f320f8ad803a39f`；远程同名文献分支具有相同提交。原 fetch 配置只抓取旧接续分支，本次显式 fetch 并核对其他实际存在的远程引用，确认原有本地分支提交均已出现在远程分支。

远程 `main` 是 `4ecd82e7b06f9fcdecce71020b0ad7bd19a5e713`，比起始研究 HEAD 少 6 个提交。没有把“未合并到 main”误写为“没有上传”。

外层 UM 自身是另一个无 remote 的 Git 仓库，起始只有空的 `f4243180c9a295850cbb2d1f73c610faf2d72838` 提交；大量本地研究与非研究文件尚未跟踪。它们不会随本次配置分支全部上传。

完成验证、检查点与同步证据见 [当前对话 STATUS](../conversations/0001_records/STATUS.md)。完整操作日志仅保存于忽略的机器配置所指向的外部本地 Git 库。
