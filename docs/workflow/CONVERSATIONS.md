# 按对话组织的记录与版本管理

需要 Python 3.10+ 和 Git；不安装第三方依赖。以下命令在已包含本机制的研究 worktree 根目录执行。Windows 也可将 `python -X utf8 scripts/conversation_records.py` 换为 `& .\scripts\records.ps1`。脚本只执行明确请求的操作，不在后台监听。

## 首次接入与继续

本机日志路径仅保存于已忽略的 `.um-records.local.json`。初始化拒绝非空未知目录、未知用途的 Git 库、含 remote 的记录库，以及位于其他 Git 仓库内部的新记录库；不会覆盖或移动旧日志。

```powershell
python -X utf8 scripts/conversation_records.py init --records-root '<外部日志库绝对路径>'
python -X utf8 scripts/conversation_records.py bind --conversation 0001
python -X utf8 scripts/conversation_records.py status --conversation 0001
```

`0001` 仅属于本次记录机制聊天。新聊天不能直接沿用配置中的上次编号。先确认其真实登记关系；有明确编号时 bind；没有编号时从 INDEX 查找未使用的四位编号并登记。平台 ID 未取得时不传 `--platform-id`，registry 保留 null。标题为本地登记标题时明确写出，不声称平台原标题。

读取当前对话 STATUS/DECISIONS，分支还要读取主对话 STATUS，以及 `docs/PROGRESS.md` 和必要的科研状态。换机器或 worktree 要分别运行 init，路径不能从别人的配置猜测。

## 新建主对话与分支

以下是操作示例；`0002`、`0003` 不代表本次已经登记的聊天，执行前先确认编号未占用。登记会读取创建时间和实际 HEAD，写入背景、来源主对话与目录，但不会切换或创建 Git 分支，也不会自动提交主仓库。

```powershell
python -X utf8 scripts/conversation_records.py register --id 0002 --slug charging-study --title '充电研究（本地登记标题）' --kind main --background '填写已明确的任务、证据入口及边界'
python -X utf8 scripts/conversation_records.py register --id 0003 --slug capacity-check --title '容量验证（本地登记标题）' --kind branch --parent 0002 --background '明确继承主对话哪些已验证结论、起始配置和待检验问题'
python -X utf8 scripts/conversation_records.py bind --conversation 0003
```

结构为 `conversations/0002_charging-study/branches/0003_capacity-check/`。主对话和分支各有 README、STATUS、DECISIONS、artifacts；INDEX 登记全局唯一编号、标题、父对话、目录和状态。`registry.json` 是索引源。

同一登记只允许一层主对话下的分支；来源不明就询问，不按文件主题猜测。要改展示标题或状态，精确编辑 registry 中对应字段后运行 `index`，同时更新该对话 README/STATUS，再审核提交。编号、slug、目录和原始创建信息保持不变。编辑前读取当前 schema；不批量重写其他对话。

## 工作时记录与检查点

```powershell
python -X utf8 scripts/conversation_records.py log --conversation 0001 --task '核查记录' --action 'inspect' --result '描述实际观察到的结果' --file docs/PROGRESS.md --verification '写明核验方法及边界'
python -X utf8 scripts/conversation_records.py log --conversation 0001 --task '执行检查' --action 'validate' --result 'failed' --failure '实际失败原因与退出码' --artifact '<本地产物位置>'
git diff --check
git diff -- docs/PROGRESS.md conversations/0001_records/STATUS.md
python -X utf8 scripts/conversation_records.py checkpoint --conversation 0001 --message 'Describe the verified work unit' --path docs/PROGRESS.md --path conversations/0001_records/STATUS.md
```

log 会追加时间、对话编号、任务、动作、文件、结果、失败原因、验证信息、产物位置和当前代码提交，并精确提交本地 JSONL。日志的常见凭据模式会脱敏；它不能保证识别任意敏感值，调用前仍须审核。

checkpoint 只接受显式列出的单个 UTF-8 文本文件（每个不超过 10 MiB），拒绝 main/master、游离 HEAD、无关暂存项、目录/通配符/路径穿越、环境缓存、详细日志、本机配置及发现的敏感内容；不自动处理删除。二进制正式产物另行检查来源、授权及内容后，用精确文件路径执行 Git 提交，并调用 log 记录。不要为绕过审核使用全目录 add。

一个小任务完成就检查差异并建立检查点。中断前更新 STATUS 的已验证、未验证、失败、下一步和准确复现命令；失败和零收益结果不得删去。分支重要结论以链接和证据追加到主对话 DECISIONS/STATUS，解释结论变化，保留旧记录。

若 Git 提交或日志写入中途失败，保留当前文件和暂存状态，读取错误及 status 后处理；不要 reset/clean。锁文件遗留时先检查其 PID、时间和对应进程是否仍在运行，确认没有写入者后才显式处理。辅助脚本之间使用独占锁，外部手工修改仍需协调。

## 实验记录

`record-run` 登记已执行的实验，不执行命令。输入 JSON 必须使用以下完整字段；路径是相对于源码 Git 根的精确文件路径，使用 `/`。manifest 本身放在外部本地位置。下面仅是格式示例，不能直接当作已运行证据。

```json
{
  "schema_version": 1,
  "run_id": "unique_run_id",
  "task": "实际问题与运行范围",
  "source_commit": "实际执行时的完整提交编号",
  "source_dirty": false,
  "config_files": [],
  "data_files": [],
  "untracked_files": [],
  "seed": null,
  "seed_reason": "填写不使用随机数的原因，或设置实际seed",
  "metrics": {},
  "validation": "实际验证命令、结果及未验证部分",
  "artifacts": [],
  "command": [],
  "environment": {},
  "exit_code": 0,
  "failure_reason": null
}
```

```powershell
python -X utf8 scripts/conversation_records.py record-run --conversation 0001 --manifest '<本地实验清单绝对路径>'
```

脚本要求提交与当前 HEAD 相同、dirty 标记与当前工作树一致、所有非忽略未跟踪文件被明确枚举。它保存配置/数据 SHA-256、配置与未跟踪文本快照、dirty patch（如有）以及调用者提供的种子、指标、环境、命令和产物位置。重复 run_id 拒绝覆盖；binary dirty patch 拒绝登记。详细 stdout/stderr/求解器产物需执行者保存在对应本地 runs 目录并精确提交，不由登记命令自动抓取。

`failure_reason` 是可选字段；失败运行应明确填写实际原因，缺失时脚本记录为调用者未提供，不补造原因。

事后观察到的文件不证明就是实验运行时使用的文件；运行前应提交准确源码并记录输入哈希，运行后及时登记，不在期间修改配置。若 patch 被脱敏，要明确它不能逐字节还原原始差异。历史运行保留原清单和原库，不伪装成新 helper 捕获的实验。

## 并行工作、共享文件与同步

共享代码和数据保持原位，以相对路径引用；对话特有的正式文档/图表放入 artifacts。历史资源见 [RESOURCE_INDEX](RESOURCE_INDEX.md)。对话登记不复制共享代码或数据。

并行改共享代码前，核实实际仓库/起点/工作目录，使用各自独立 worktree 和新 Git 分支；不要在别人正在使用的 checkout 内切换。独立用户聊天按明确来源登记和绑定；同一已绑定聊天委派的技术子任务（含Claude）无需重复init/register，由主执行者在原对话记录其基准、范围、提交及验收。登记表并行新增仍可能产生 Git 合并冲突，须保留双方编号并核实唯一性，不能覆盖另一条登记。

同步前审查 `git status`、提交路径与将推送的提交，详细 actions/runs 只能在外部无 remote 库中。只推送实际工作分支，不使用 `--all`、`--mirror` 或强推，不自动合并到 main。完成推送后用 `git ls-remote origin <完整分支引用>` 对照本地 `git rev-parse HEAD`。status 只报告缓存 tracking refs；没有 upstream 或没有实时网络核验，均不代表已同步。失败时保留本地提交并记录原因。

### 长期研究与协作规则（2026-11-10用户明确要求）

研究模块由UM自身问题和证据决定。申请材料仅用于核实/展示；无UM证据的能力列待核实，不借用其他项目成果，不读取或修改半导体物流项目。确定性规划与边界实验后，再做固定设施压力测试；需要情景规划时先写清信息揭晓与事前/事后决策。敏感性分析不称为不确定性规划。

Codex负责主线、集成和发布；Claude可负责限定模块、检查器或建模/代码审查。任务书必须包含完整基准提交、输入输出、负责文件、禁止改动范围及验收标准。使用独立worktree，保留提交来源；集成后的验证属于主执行者职责。没有实际调用成功就记录不可用，交付可直接转交的任务书并继续工作，不能把准备提示词写成完成协作。

每个有意义的实现或实验里程碑及时本地提交；验证后即可推送精选成果并实时核SHA。完整日志从一开始就在外部无remote Git，不进入可推送历史。保留失败、无收益、并列最优和未解决状态。展示材料须包含问题/输入/决策、任务与窗口图、实测对照、瓶颈解释、公式代码对应、Windows复现命令和结果位置。

## 自检

```powershell
python -m unittest discover -s tests -p test_conversation_records.py -v
python -X utf8 scripts/conversation_records.py status --conversation 0001
```

测试使用独立临时 Git 目录，不把测试主对话、分支、日志或模拟实验写入正式研究登记。本地记录库不会自动上传；其文件还需要用户控制的离线备份。实际自动采集范围见 [APP_CAPTURE](APP_CAPTURE.md)。
