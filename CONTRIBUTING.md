# 维护规范 · Maintaining the UM charging study

[中文](#中文) · [English](#english)

## 中文

1. **实验锚定与边界区分**：港区—仓库实验须始终锚定于固定运输服务、卡车电池上下限、站点电网接入容量、接口数量与充电窗口。核心比较为完成同一运输服务所需的设施投资与运行成本。观测时间戳、由此推断的停车上界以及情景假设的可充电资格须严格分开记录。
2. **可运行小算例与记录规范**：使用可运行的小算例解释规划决策为何改变。每个结果须注明单位、成本周期并关联至对应输入；主结论变化时同步更新首页 `README.md` 的中英文内容；方法与数据须在正文使用处规范引用；重要研究决策（包括负面结果与失败检验）均记入既有研究记录。只把实际做过的复核写成复核，并写明它核对了什么；没有进行的检查照实写“未进行”。
3. **论文复算与市场结算**：米兰配送论文复算保留在 `studies/fresia-2025/` 下，使用替代数据或固定 UM 路线得到的结果须显式标注。固定设施的购电调度采用原生历史日前电价时段结算，并完整记录市场区域、日期、时区、价格单位以及排程时已知的信息范围。
4. **双语首页与可追溯路径**：双语首页聚焦设施规划决策，仅在证据改变该决策时更新主结论，将具体排程明细与运行历史留在对应研究案例中。每项核心结果须可从带来源的输入与情景假设，一路追溯到一条可复现命令、预期数值与结果文件；该路径须从仓库根目录实际运行验证，并在目标分支上核对全部链接有效。
5. **公开仓库与离线档案分工**：GitHub 公开仓库存放研究代码、来源清晰且具备共享许可的数据、可测试示例、方法文档与精选结果；详细运行日志、个人文档与工作笔记保存在独立的离线 Git 档案库中。推送前核查暂存路径。研究分支按主题命名（如 `research/fleet-charging-costs`），仅在区分同一主题的不同轮次时附加日期。目录与文件按内容采用简短小写英文命名（如 `data/germany-truck-grid-v1`）。出版社论文 PDF 仅存离线档案，正文统一通过 `docs/literature/references.bib` 引用。经确认后将已验证的里程碑发布至 `main` 并核对远端提交。

## English

1. **Experimental anchor and record boundaries:** Keep the port–warehouse experiments anchored to a fixed transport service, truck battery limits, site connection capacity, connector counts, and charging windows. The principal comparison is the investment and operating cost of completing the same service. Keep observed timestamps, inferred parking bounds, and assumed charging eligibility distinct.
2. **Runnable explanations and study records:** Use a small runnable case to explain a change in a planning decision. Give units, state the cost horizon, and tie each result to its inputs. Update both languages in the main `README.md` when the headline case changes. Cite methods and data where they are used. Record material research decisions, including negative findings, in the existing study records. Report a review only if it was actually carried out, state what it covered, and record a check that did not run as not performed.
3. **Paper replication and market settlement:** The Fresia replication lives under `studies/fresia-2025/`. Label results obtained using substitute data or fixed UM routes. Settle fixed-facility dispatch with the native historical day-ahead intervals, and record the market area, dates, timezone, price units, and what the operator knows when scheduling.
4. **Homepage focus and traceability:** Keep the bilingual homepage focused on the facility decision. Change a headline when evidence changes that decision; keep schedules and run history in the case. Trace each result from credited inputs and scenario assumptions to one command, its expected number, and the results file. Run that path from the repository root and check links on the branch where readers will open them.
5. **Repository scope, naming, and releases:** GitHub holds research code, data with provenance and appropriate sharing rights, testable examples, methods, and selected results. Preserve detailed run logs, personal documents, and working notes in the separate offline Git archive. Check staged paths before pushing. Name research branches by topic, such as `research/fleet-charging-costs`; add a date only to separate rounds of the same topic. Name folders and files by content in short lowercase English, such as `data/germany-truck-grid-v1`. Keep publisher PDFs in the offline archive and cite them through `docs/literature/references.bib`. Publish validated milestones to `main` when authorized and verify the remote commit.
