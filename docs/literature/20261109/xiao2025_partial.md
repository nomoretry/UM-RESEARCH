# Xiao 2025 有限证据卡：等待全文

> Source coverage: Partial paper（出版社预览及官方勘误）
> Extraction confidence: High for available text；正文缺失
> Locator mode: structure-grounded
> Primary analytical lens: methods
> Secondary analytical lens: None
> Context verification: Targeted external check
> Card completeness: Partial；未完成全文精读

## 01 基本信息

[External] Liyang Xiao, Luxian Chen, Peng Sun, Gilbert Laporte, Roberto Baldacci. The container drayage problem for electric trucks with charging resource constraints. TR-C 174 (2025), 105100. [出版社预览](https://www.sciencedirect.com/science/article/pii/S0968090X25001044)；[学校记录](https://researchportal.bath.ac.uk/en/publications/the-container-drayage-problem-for-electric-trucks-with-charging-r/)。

勘误：[TR-C 176, 105167](https://doi.org/10.1016/j.trc.2025.105167)。2026-11-09核查：Bath所列公开接受稿正常HTTP访问403，Undermind无PDF；其他作者库未取得附件。不得把本卡当全文卡。

## 02 一句话概括

[Analysis] 该文把集装箱运输任务、补能方式和有限资源排队联系起来；适合运输运营扩展阅读，尚不足以逐式复现。

## 03 研究问题

[Paper] 码头—客户仓库任务有时间窗，电动卡车可普通充电、快充或换电，充电机和可替换电池有限。协调路径、任务和补能以降低运营成本。[Paper: Problem description; Introduction]

## 04 背景与发展路径

[Paper-framed; external verification not performed] 论文强调路径与补能资源竞争的耦合；未独立核验首创性。

## 05 核心难点

| 难点 | 现有证据 | 缺失 |
|---|---|---|
| 排队影响任务时效 | 有限充电机／可替换电池 | 精确排队与时序约束 |
| 非线性部分充电 | 普通与快充均考虑 | 分段线性化、变量和断点 |

[Paper: Introduction; Problem description]

## 06 核心思路

[Paper] 使用MILP，结合增强自适应大邻域搜索和CPLEX处理补能排队。[Paper: Highlights; Conclusions]

## 07 方法总览

[Paper] 第一阶段构建暂不考虑充电排队的路线；第二阶段按触发规则调用CPLEX进一步优化补能策略。[Paper: Introduction]

[Analysis] 其方法范围大于当前固定任务顺序模型；没有全文时不移植算法参数。

## 08 模块拆解

Not assessable from available material：任务转换、车辆流、资源排序、电池动态与线性化模块的具体方程未取得。

## 09 关键公式

Not assessable from available material。集合、变量精确名称、式号、SOC初末条件、逐站kW约束、电池回充负荷均留空。不能把“充电资源约束”自动解释成配电网约束。

## 10 数据、实验与证据链

[Paper] 任务位置和时间窗以物流公司数据为基础。出版社预览披露Java JDK17、CPLEX12.6.1、7200秒限制、单线程；ALNS每实例运行10次并取最好值。任务完整规模、抽样及参数来源未全部取得。[Paper: Numerical experiments]

[Analysis] 后续应另报均值、离散程度和最差值，不能把最好值解释为平均表现。全部图表清单未取得，全文实验覆盖未完成。

[External] [官方全部勘误](https://researchportal.bath.ac.uk/en/publications/corrigendum-to-the-container-drayage-problem-for-electric-trucks-/)：

| 位置 | 更正及对复现的影响 |
|---|---|
| Table 4 | 最优值上标导致成本列错位，改粗体；需核对列对齐 |
| Table A.1 | 任务／站点移除的upper limit误写lower limit；影响参数含义 |
| Sections 5.3–5.4 | TC字体统一 |
| Figure 15(b) | 左右轴分别为充电次数、换电次数 |
| Figure 15(a) | kg单位规范 |
| Table 8、Table B.6 | Gap补百分号 |
| Table 4 | Gap下标字体更正 |
| Table B.5 | Gap与百分号间空格 |

## 11 如何解释结论

[Analysis] 现有证据足以判断主题相关，不能据此保证精确模型或表格结果可复现；勘误未列模型方程更正，不等于方程已由我们验证。

## 12 作者明确承认的局限

Not assessable from available material；不从摘要推断作者局限。

## 13 批判性分析

[Analysis] 需要全文确认：充电非线性怎样线性化；空电池是否回充；换电库存是否随时间恢复；排队是否与运输任务耦合；功率限额与充电机数是否分开。未取得全文不判断这些模块缺失。

## 14 可迁移知识

[Analysis] 运输资源与补能资源应在相同时间轴核对。算法最好值、平均值和精确求解界限不可混用。

## 15 与现有模型的连接

[External] UM当前任务归属和路线固定，没有任务重排或显式排队成本；已有接口并发和连续电量。该文适合后续开放运输灵活性阶段，见[衔接说明](BASELINE_DESIGN.md)。

## 16 后续研究判断

[Hypothesis] 允许有限等待调整可能缓解接口瓶颈，但也可能违反发车时限。原文差异尚待全文核实，不主张创新。

如何验证：取得全文后，固定同一任务和硬件，比较固定顺序与有限时移；独立检查所有时间窗、接口和电量。

可能失败：允许的时移没有真实运营依据；效益只是放宽运输服务标准。创新状态：unverified。

**完成本卡所需材料：原文作者接受稿或正式PDF；如有附录和实例数据，一并读取。当前未把它选为主基线。**
