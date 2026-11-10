# 记录与版本管理机制（本地登记标题）

- Stable local ID: `0001`
- Kind: `main`
- Parent main conversation: None; explicitly registered as a main conversation
- Created (UTC): 2026-11-10T02:38:39.831330+00:00
- Starting Git commit: `d07d452961f5fb3e208350a82f320f8ad803a39f`
- Platform chat ID: Unavailable; this binding uses a stable local number, not a fabricated platform ID

## Inherited/task background

用户于2026-11-10明确要求为UM科研项目建立按对话组织、分支嵌套的记录和Git机制，并确认本聊天为独立主对话。保护原工作，索引共享资源，详细日志仅本地，独立分支验证后推送，不合并main。科研状态以已有源文件证据为准。

## Continuation

Read [STATUS.md](STATUS.md) and [DECISIONS.md](DECISIONS.md).
Store conversation-specific shareable outputs in `artifacts/`; link shared code and data without duplicating them.
The conversation directory does not select a Git branch. Keep its path unchanged when renaming the chat.
