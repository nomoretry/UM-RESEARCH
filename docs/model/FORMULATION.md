# 固定任务充电与容量投资 MILP

[中文](#固定任务充电与容量投资-milp) · [English](#english)

**状态：2026-11-10 已增加新增接口整数与离散功率扩容，采用 Ye 2024 问题及投资框架的本项目改编，不是严格复现论文公式或案例数字。站点启用仍为输入，年化/多代表日投资尚未实现。正式执行证据以 STATUS 和精选结果为准。旧原型不是本文连续任务链实现。**

同日后续已完成相同物理链的60/30/15分钟检验，新增v2在途边界与C08整窗连接诊断。原v1输入及回归不改；[时间输入与占用政策](TIMEGRID_INPUT.md)、[本轮结果](../../results/timegrid_20261110/README.md)明确换枪、挪车和时间积分假设。

现已进一步完成15分钟[功率×窗口边界实验](../../results/boundary_20261110/README.md)。C01–C08及原模型代码未改，本轮新增受控情景生成、B01–B04任务/输入审计和跨情景性质检查，属于确定性敏感性分析。

原 [最小实例](MINIMAL_INSTANCE.md) 保留为固定设施回归。新增 港区—仓库闭合实例（离线记录库 `runs/20261110_investment_suite/`） 同样为四小时合成周期，采用周期等效合成投资加本周期电费，权重严格为1；不将四小时外推全年。精确输入和费用语义见 [INVESTMENT_INPUT](INVESTMENT_INPUT.md)。

## 业务边界

任务归属、服务顺序、主要路线和车辆位置时间轴给定。先验证运输本身可行，再构造允许充电的时间段。装卸等待不自动意味着可插枪；非充电时段不允许补能。基地与夜间补能纳入完整周期。

后续数据应用规范覆盖完整代表日或多日连续区间；本轮仅验证上述四小时合成封闭周期。固定时间表下等待成本若不受决策影响，应作为共同常数省略；有限绕行需要额外位置/时间/能耗约束，不通过扩大可用窗口偷偷加入。

## 集合、参数和单位

- $v\in V$：车辆；$j\in J$：站点；$t=0,\ldots,T-1$：时段；$m\in M_j$：扩容档位。
- $\Delta t$：小时；$d_{vt}\ge0$：该时段电池侧行驶耗能，kWh。
- $A_{vjt}\in\{0,1\}$：车辆该完整时段可在站点充电。固定路线首版同一车辆时段最多对应一个地点；不把任意地点选择当成免费移动。
- $P_{vj}$：车辆与接口共同允许的电网侧功率上限，kW；$\eta_v$：综合效率。
- $H_{jt}$：扣除其他用电后可分配给研究车队的功率，kW；不是变压器铭牌容量。
- $\Delta H_{jm}$：扩容后的新增可用kW；$N_j^0$：已有接口数；$\bar N_j$：新增上限。
- $E_v^{\min},E_v^{\max},E_v^0$：电池能量边界与初值，kWh。
- 当前实现的接口/扩容成本为合成周期等效费用，电价为合成货币/kWh；年化成本仅为下文后续规范。已有投资为沉没成本，不重复收取新建成本。

部分时段到达/离开：首版只保留完全可用的时间槽，记录该保守处理；以后若细化，必须同时处理槽内行驶/充电先后，不能只检查端点SOC。

## 变量

- $x_j\in\{0,1\}$：站点启用；已有运营站点固定 $x_j=1$。
- $n_j\in\mathbb Z_{\ge0}$：新增接口数。
- $u_{jm}\in\{0,1\}$：选择一个扩容档位。
- $a_{vjt}\in\{0,1\}$：车辆占用接口。
- $p_{vjt}\ge0$：电网侧充电功率，kW。
- $e_{vt}$：时段边界的电池能量，kWh。

固定设施版本将 $x,n,u$ 固定；投资版本保持 $x$ 给定，释放 $n,u$。可选档位为空时没有扩容变量。原始解保留浮点值，由独立检查器复核整数性，不先四舍五入。

## 约束

**C01 站点与扩容联动**

$$0\le n_j\le\bar N_j x_j,\qquad \sum_m u_{jm}\le x_j.$$

**C02 充电机会、位置与单车互斥**

$$a_{vjt}\le A_{vjt},\qquad a_{vjt}\le x_j,\qquad \sum_j a_{vjt}\le1.$$

输入校验确保 $d_{vt}>0$ 的行驶槽不开放充电；驾驶/服务可行性不能只由上述公式推定。

**C03 单车与设备功率**

$$0\le p_{vjt}\le P_{vj}a_{vjt}.$$

若多枪共享功率柜，需另设相应柜级约束；初版限定独立接口或明确聚合上限。

**C04 接口并发**

$$\sum_v a_{vjt}\le N_j^0+n_j.$$

**C05 可用接入功率**

$$\sum_v p_{vjt}\le H_{jt}x_j+\sum_m\Delta H_{jm}u_{jm}.$$

$H$ 是参数，故 $H x$ 为线性项。若 $H$ 已扣除背景负荷，不再次扣除。以上不能证明潮流、电压或实际并网合格。

**C06 连续电量守恒**

$$e_{v,t+1}=e_{vt}+\eta_v\Delta t\sum_j p_{vjt}-d_{vt}.$$

**C07 电量与周期边界**

$$E_v^{\min}\le e_{vt}\le E_v^{\max},\quad e_{v0}=E_v^0,\quad e_{vT}\ge E_v^0.$$

保证完整周期补回能量；若采用周期稳态可改为等号并记录决定。各方案使用同一边界，不把初始满电当免费能源。数据缺口不能默认为零耗能。

**C08 可选整窗固定连接（v2）**

当且仅当`connector_policy=fixed_dwell_connection`，若同一辆车相邻槽的`charging_site`相同且非空，对所有站点增加：

$$a_{v,j,t}=a_{v,j,t-1}.$$

于是同一次连续可插枪停靠期间占用保持不变；功率可变或为0，但不能中途转交接口。`slot_boundary_switching`不添加该等式，允许槽边界零耗时、零能耗换枪及挪车；不计操作费和挪车空间约束。两政策不增加停车时间。没有采用接口身份变量，接口同质。

时间细化保持物理事件起止：原一小时驾驶按1/2/4个片段均分耗能，内部位置必须列入`transit_locations`且不能停靠或充电；设备kW和电价在原小时内重复，kWh与电费乘新的$\Delta t$，投资费用不缩放。`audit_physical_equivalence`独立聚合回真实事件并比对到离、资格、能耗和参数。均匀驾驶耗能是本合成例假设，不是实际速度轨迹。

## 已实现的功率×窗口实验定义

固定$\Delta t=0.25$小时，港区已有功率$H_{P,t}=h$，$h\in\{50,75,100,125,150\}$kW；C05中的付费扩容增量不变，容量为$h+\sum_m\Delta H_{Pm}u_{Pm}$，不能把h直接叫作扩容后容量。

对原仓库停靠内的三车，窗口$w\in\{0,15,30,45,60\}$分钟：

$$A_{v,W,t}(w)=\mathbf1\{60\le15t,\quad15(t+1)\le60+w\}.$$

实际仓库到离仍为60/120分钟，$w=0$只关闭资格，不删除任务或停靠。仅港区范围固定$x_W=0$，两地范围固定$x_W=1$；已有仓库是沉没设施、无开站费。所有比较保留相同任务/能耗/初末电量、参数和周期费用，两个连接政策分开比较。

输入审计B01比较屏蔽资格后的物理事件链与逐槽能耗，B02核对声明的资格子窗，B03只允许已有功率/启用变化，B04核对费用与单位。它们是输入/实验不变量检查，不是新增求解器约束；原C01–C08检查器仍独立复算原始解。

310项跨情景比较验证范围等价/优势及本实例的单调性。整窗窗口单调依赖共同到站及共同延长，不能推广到异质重叠窗口。敏感性、固定设施压力测试与真正事前共享投资的情景规划须分别命名。

## 目标

以下是年化代表日的后续规范，尚未实现：

$$\min \sum_{j\in J_{\rm new}}F_j x_j+\sum_j C_j n_j+
\sum_{j,m}K_{jm}u_{jm}
+w\sum_{v,j,t}\pi_{jt}p_{vjt}\Delta t.$$

$F,C,K$ 为年化投资，$w$ 为该日的年度代表天数。单日示例不能不加说明外推全年。多代表日共享投资变量、分别调度并使用明确权重。未取得可靠成本时，报告透明的参数情景。

本轮已实现的单周期版本为 $\min\sum_j C_j^{cycle}n_j+\sum_{j,m}K_{jm}^{cycle}u_{jm}+\sum_{v,j,t}\pi_{jt}p_{vjt}\Delta t$。站点启用固定，既有设施成本省略。新增费用明确是分摊到当前周期的合成等效费用，不是一次性设备购置额或年费；只接受权重1。寿命、折现、实际周期次数未校准，不能推断真实经济性。

## 最小验证

- 独立复算每辆车的电量、每站接口占用与总功率、全部费用；不直接读取模型残差当独立验证。
- 构造“接口不足但功率充足”“功率不足但接口充足”和时间窗不足的已知实例。
- 可手算的小实例；需要时穷举少量投资组合核验最优值。
- 固定同一任务集比较基地方案、预定义规则投资后调度、联合投资调度。
- 报告不可行、超时但有可行解、未找到可行解和已证最优的区别；记录界限与gap。
- 时间离散化、连续周期和初末电量必须检查；沿用独立周期规则曲线不能代替上述模型。

## Physical connector changeover

车辆放行决定可在何站、何槽插枪。接口换车间隔 δ 另行限制同一物理接口上不同车辆的先后占用。每站的接口单独编号，每辆车每个 15 分钟槽最多使用一把，每把每槽最多分给一辆车。首车无准备时间，同车连续占用没有重复损失。上一车占用到其最后一槽的右边界，完整空槽可抵扣间隔。下一车可在槽边界获得该枪，实际启充要等到应有间隔已满。两个接口可以同时换车。仓库没有同一接口上前车释放与后车接枪的实测配对，δ 为敏感性输入。[已核数据字段](../../results/dt_cargo_stop_20261111/event.json)

模型用二元变量 $x_{vkt}$ 给车辆 $v$ 分配具名接口 $k$。设槽宽 $L=15$ 分钟，槽 $t$ 内距左边界 $b$ 分钟处，如 $(t-t'-1)L+b<δ$ 且该接口在较早的槽 $t'$ 分配给另一辆车，则 $v$ 在此时的功率必须为零。功率只需在槽边界和 $δ$ 除以 15 的余数处核算。每车在本槽内可用期间使用同一功率设定，站点上限对每个子区间分别施加，电量累计为 $η∑PΔm/60$。这些切点只计算损失，新增的槽内改派次数和可独立调节的充电设定数都是 0。δ=0 时对功率积分恢复原槽模型，四组新旧可行性逐一相同。[MILP](../../src/um_charging/changeover.py) · [逐车逐枪独立复核](../../src/um_charging/changeover_check.py)

### Limits for the two-port/two-warehouse build

令 $h=60E/(50×0.9)$ 为补回一段行驶所耗电量需要的 50 kW 充电分钟。V1、V2 在仓库各最多获得 15 个额定功率分钟，最后一槽又要共享 75 kW，合计最多 22.5 个额定功率分钟。V3 即使在仓库补满第一程耗电，仍至少需要 $h$ 个港区分钟。两种能耗下三车分别至少需要 3、3、2 个港区接口槽，刚好用完两个接口的八槽。两把枪都必须换车，否则同一辆车需占四槽，另外两车的下限无法同时满足。

若 V3 接过别车用过的枪，它最多可用 $30-δ$ 分钟。至少有一辆晚放行车也要接过别车的枪，否则两辆晚车只能同时连续占用最初三槽，V3 只剩最后一槽。晚车合计最多取得 $90-δ$ 个港区分钟，加上仓库的 22.5，须覆盖两车两程合计的 $4h$。若 V3 完全避开接枪损失，两把港区枪的换车时间都落在晚车上，更紧的条件为 $2δ≤112.5-4h$。因此在本研究两个能耗点，上界为 $min(30-h,112.5-4h)$。以下排程恰好达到该上界，两车编号互换也成立。

| 港区接口 | 11:00–11:15 | 11:15–11:30 | 11:30–11:45 | 11:45–12:00 |
|---|---|---|---|---|
| 1 | V1 | V1 | V1 | V2 等 δ 后启充 |
| 2 | V2 | V2 | V3 等 δ 后启充 | V3 |

三车在港可用时均以 50 kW 充电，分别得到 $45$、$45-δ$、$30-δ$ 个额定功率分钟。仓库的 V3 在头两槽补齐其余所需电量并释放接口。V1、V2 在最后一槽分用两把枪。20.00 kWh 时 V3 在仓库恰好补满，港区的两个槽限制其可承受的延迟。20.636628905957647 kWh 时，晚车在仓库末槽恰好用满 75 kW，港区六槽内再损失时间就无法达标。[手算排程测试](../../tests/test_changeover_bounds.py)

港三仓一在 20.00 kWh 下需要从仓库至少获得 40 个额定功率分钟，V3 最多提供其中 26⅔，晚车至少需 13⅓。V3 至少占用仓库开头两槽，最早在 09:30 释放接口。晚车 09:45 放行，可利用之前 15 分钟空档，临界间隔为 16⅔ 分钟。高能耗时即便零换车时间，港区最后一小时仍至少需 102.14794 kWh，超过可用的 100 kWh。

**高能耗恢复。** 仓库从 75 扩至 100 kW，两个晚车在最后一槽可各取 15 个额定功率分钟。超过 $30-h$ 后，V3 不能在港口接过别车的枪，晚车要承担两次换车，故 $4h≤90-2δ+30$。在 $δ=60-2h$ 的边界，端点求解及独立检查给出可行排程。对 5 与 10 分钟，从已装港二仓二出发，最低增量均为在港区加一个接口（+20）。此时三辆车可以在港口各用一把枪，仓库仍需协调换车。所有费用为同一周期的合成投资单位。[各档最优配置及枚举范围](../../results/changeover_20261112/metrics.json)

---

## English

**Status (as of 2026-11-10):** Integer connector additions and discrete grid-capacity expansion have been added, adapting the problem structure and investment framework of Ye et al. (2024) rather than strictly reproducing that paper’s equations or numerical case. Site activation remains an input parameter, and annualized multi-representative-day investment is not yet implemented in this core specification. Formal execution evidence is governed by [STATUS.md](../research/STATUS.md) and the curated results packages. The archived legacy prototype is not an implementation of this continuous-duty formulation.

Subsequent 60/30/15-minute time-step checks on the same physical duty chain introduced v2 transit boundaries and the C08 fixed-dwell connection diagnostic while leaving v1 inputs and regressions unchanged; [TIMEGRID_INPUT.md](TIMEGRID_INPUT.md) and the [time-grid results](../../results/timegrid_20261110/README.md) state the assumptions on plug switching, vehicle repositioning, and time integration.

A 15-minute [port-power × warehouse-window boundary study](../../results/boundary_20261110/README.md) was also completed without altering constraints C01–C08 or the core solver code, adding controlled scenario generation, input audits B01–B04, and cross-scenario property checks as a deterministic sensitivity analysis.

The original [minimal instance](MINIMAL_INSTANCE.md) is retained as the fixed-facility regression case. The closed port–warehouse instance (archived in the offline log repository under `runs/20261110_investment_suite/`) likewise models a four-hour synthetic cycle using cycle-equivalent synthetic investment costs plus single-cycle electricity costs with strict weight 1; four-hour results are not extrapolated to an annual horizon. Exact input fields and cost semantics are documented in [INVESTMENT_INPUT.md](INVESTMENT_INPUT.md).

### Operational scope

Task assignment, service order, primary routes, and vehicle location timelines are given exogenously. Transport feasibility is verified first, and charging-eligible slots are constructed afterward. Dwell time for loading or unloading does not automatically confer plug eligibility, and charging is forbidden outside eligible windows. Home-base and overnight charging belong inside the full operating cycle.

Future empirical extensions cover full representative days or continuous multi-day spans; this core benchmark validates the four-hour closed synthetic cycle described above. Under a fixed schedule, waiting costs unaffected by charging decisions are omitted as a common constant; bounded detours require explicit location, time, and energy constraints and must not be smuggled in by inflating charging windows.

### Sets, parameters, and units

- $v\in V$: vehicles; $j\in J$: sites; $t=0,\ldots,T-1$: time slots; $m\in M_j$: discrete capacity-expansion tiers at site $j$.
- $\Delta t$: slot duration in hours; $d_{vt}\ge0$: battery-side driving energy consumed by vehicle $v$ in slot $t$, in kWh.
- $A_{vjt}\in\{0,1\}$: binary indicator equal to 1 if vehicle $v$ is eligible to charge at site $j$ across the entire slot $t$. In the fixed-route baseline, each vehicle-slot maps to at most one site; arbitrary site selection is not treated as costless travel.
- $P_{vj}$: joint grid-side charging power upper bound allowed by vehicle $v$ and the connector at site $j$, in kW; $\eta_v$: grid-to-battery charging efficiency.
- $H_{jt}$: grid power available to the study fleet at site $j$ in slot $t$ after deducting background load, in kW (not transformer nameplate capacity).
- $\Delta H_{jm}$: incremental available power from selecting expansion tier $m$ at site $j$, in kW; $N_j^0$: existing connector count at site $j$; $\bar N_j$: upper bound on added connectors at site $j$.
- $E_v^{\min},E_v^{\max},E_v^0$: lower bound, upper bound, and initial battery energy for vehicle $v$, in kWh.
- Connector and capacity-expansion costs in the current single-cycle implementation are synthetic cycle-equivalent costs, and electricity prices are in synthetic currency per kWh; annualized costs appear only in the future specification below. Existing infrastructure is treated as sunk and is not charged as new construction.

Partial-slot arrivals and departures: the initial formulation retains only fully available slots and documents this conservative treatment; any finer representation must model the ordering of driving and charging within a slot rather than checking slot-endpoint SOC alone.

### Decision variables

- $x_j\in\{0,1\}$: site activation indicator; existing operating sites are fixed at $x_j=1$.
- $n_j\in\mathbb Z_{\ge0}$: number of newly added connectors at site $j$.
- $u_{jm}\in\{0,1\}$: binary indicator for choosing discrete expansion tier $m$ at site $j$.
- $a_{vjt}\in\{0,1\}$: binary indicator equal to 1 if vehicle $v$ occupies a connector at site $j$ in slot $t$.
- $p_{vjt}\ge0$: grid-side charging power drawn by vehicle $v$ at site $j$ in slot $t$, in kW.
- $e_{vt}$: battery energy of vehicle $v$ at the start boundary of slot $t$, in kWh.

The fixed-facility version fixes $x,n,u$; the investment version keeps $x$ fixed as an input and optimizes $n,u$. No expansion variable is created when a site’s tier set is empty. Raw floating-point solver outputs are preserved and checked for integrality by an independent verifier without prior rounding.

### Constraints

**C01 Site activation and expansion linkage**

$$0\le n_j\le\bar N_j x_j,\qquad \sum_m u_{jm}\le x_j.$$

**C02 Charging eligibility, site presence, and single-site exclusivity**

$$a_{vjt}\le A_{vjt},\qquad a_{vjt}\le x_j,\qquad \sum_j a_{vjt}\le1.$$

Input validation ensures that driving slots with $d_{vt}>0$ are never charging-eligible; transport feasibility itself is not inferred solely from these inequalities.

**C03 Vehicle and connector power limit**

$$0\le p_{vjt}\le P_{vj}a_{vjt}.$$

Where multiple plugs share a power cabinet, a separate cabinet-level limit is required; the baseline formulation covers independent connectors or explicitly aggregated power limits.

**C04 Simultaneous connector occupancy**

$$\sum_v a_{vjt}\le N_j^0+n_j.$$

**C05 Available site grid power**

$$\sum_v p_{vjt}\le H_{jt}x_j+\sum_m\Delta H_{jm}u_{jm}.$$

Because $H_{jt}$ is an exogenous parameter, $H_{jt}x_j$ is linear. Background load already deducted from $H_{jt}$ is not subtracted again. Satisfying C05 does not prove AC power-flow, voltage, or interconnection compliance.

**C06 Continuous battery energy balance**

$$e_{v,t+1}=e_{vt}+\eta_v\Delta t\sum_j p_{vjt}-d_{vt}.$$

**C07 Energy bounds and cycle boundary**

$$E_v^{\min}\le e_{vt}\le E_v^{\max},\quad e_{v0}=E_v^0,\quad e_{vT}\ge E_v^0.$$

This enforces energy replenishment over the full cycle (an equality constraint may be used for periodic steady state when documented). All compared configurations share the same boundary so initial charge is never treated as free energy, and missing trip records are never defaulted to zero consumption.

**C08 Optional fixed-dwell connection policy (v2)**

If and only if `connector_policy=fixed_dwell_connection`, whenever two consecutive slots for vehicle $v$ share the same non-empty `charging_site`, add for all sites $j$:

$$a_{v,j,t}=a_{v,j,t-1}.$$

Connector occupancy therefore remains unchanged throughout a continuous eligible dwell; charging power may vary or drop to zero, but the connector cannot be handed over mid-dwell to another truck. Under `slot_boundary_switching`, this equality is omitted, permitting zero-time, zero-energy, zero-cost plug switching and repositioning at slot boundaries without modeling staging-space limits. Neither policy adds dwell time. Connectors at a site are homogeneous and unnamed in this base model.

Time-step refinement preserves physical event boundaries: each original one-hour driving leg is split evenly across 1, 2, or 4 sub-slots, intermediate locations must be listed in `transit_locations` with no dwell or charging allowed, power limits and electricity prices repeat across sub-slots within the parent hour, kWh and electricity costs scale by the new $\Delta t$, and investment costs do not scale. `audit_physical_equivalence` independently re-aggregates sub-slots back to physical events to verify arrival/departure times, eligibility, leg energy, and parameters. Uniform energy distribution across driving sub-slots is an explicit synthetic assumption, not an empirical speed profile.

### Implemented power × window boundary specification

Fix $\Delta t=0.25$ hours and vary existing available port power $H_{P,t}=h$ over $h\in\{50,75,100,125,150\}$ kW; paid expansion tiers in C05 are unchanged, giving post-expansion capacity $h+\sum_m\Delta H_{Pm}u_{Pm}$ (distinct from existing power $h$).

For the three vehicles during their warehouse dwell, vary the warehouse charging window $w\in\{0,15,30,45,60\}$ minutes:

$$A_{v,W,t}(w)=\mathbf1\{60\le15t,\quad15(t+1)\le60+w\}.$$

Physical warehouse arrival and departure remain fixed at 60 and 120 minutes; $w=0$ disables charging eligibility without removing trips or dwell. The port-only scope fixes $x_W=0$ and the two-site scope fixes $x_W=1$, treating existing warehouse hardware as sunk with no site-opening fee. All comparisons hold duties, leg energies, boundary SOC, equipment parameters, and cycle costs identical, comparing the two connection policies separately.

Input audit B01 verifies the physical event chain and per-slot energy after masking eligibility, B02 checks the declared eligible sub-windows, B03 permits only declared changes in existing power or site activation, and B04 checks cost parameters and units. These are input and experiment invariant checks rather than solver constraints; the C01–C08 checker independently verifies every primal solution.

Across 310 cross-scenario property comparisons, scope equivalence/dominance and instance-level monotonicity are verified. Under `fixed_dwell_connection`, window monotonicity relies on all three trucks arriving and extending their windows simultaneously and does not generalize to staggered overlapping windows. Sensitivity sweeps, fixed-facility stress tests, and true stochastic planning with shared ex ante investment and adaptive dispatch must remain distinct.

### Objective

The following annualized representative-day objective is a future specification and is not implemented in this core synthetic module:

$$\min \sum_{j\in J_{\rm new}}F_j x_j+\sum_j C_j n_j+
\sum_{j,m}K_{jm}u_{jm}
+w\sum_{v,j,t}\pi_{jt}p_{vjt}\Delta t.$$

Here $F,C,K$ denote annualized investment costs and $w$ is the annual representative-day weight. A single-day instance must not be extrapolated to a full year without explicit justification; multi-representative-day formulations share investment variables while dispatching each day separately with documented weights. When reliable quotes are unavailable, transparent parametric scenarios should be reported.

The implemented single-cycle objective is $\min\sum_j C_j^{cycle}n_j+\sum_{j,m}K_{jm}^{cycle}u_{jm}+\sum_{v,j,t}\pi_{jt}p_{vjt}\Delta t$, with site activation fixed and existing facility costs omitted. Added-equipment charges are explicitly synthetic cycle-equivalent costs amortized to the modeled cycle—not one-time CAPEX or annual bills—and accept only weight 1. Lifetimes, discounting, and annual cycle counts are uncalibrated here and do not support real-world economic claims.

### Minimum verification requirements

- Independently recompute every vehicle’s SOC trajectory, per-site connector occupancy, total site power, and all cost terms from primal variables; never treat solver residuals as independent verification.
- Construct known diagnostic cases isolating “insufficient connectors with ample power,” “insufficient power with ample connectors,” and “insufficient charging window.”
- Verify optimality on hand-solvable instances and, where feasible, by exhaustive enumeration of facility combinations.
- Compare base-site only, rule-based sizing with fixed-facility dispatch, and joint investment-and-dispatch on the exact same duty set.
- Distinguish clearly among infeasible, time-limited with incumbent, no incumbent found, and proven optimal statuses; record dual bounds and optimality gaps.
- Check time discretization, cycle continuity, and boundary SOC explicitly; independent per-cycle rule-based charging profiles cannot substitute for this formulation.

### Physical connector changeover (English)

Vehicle release timing governs which site and slots are eligible for plugging in. Connector changeover time $\delta$ separately constrains consecutive use of the **same physical plug** by different trucks. Plugs at each site are individually indexed; each vehicle occupies at most one plug per 15-minute slot, and each plug serves at most one vehicle per slot. The first user incurs no setup loss, and consecutive slots by the same vehicle incur no repeated loss. A departing vehicle occupies its plug until the right boundary of its final assigned slot, and full empty slots count toward $\delta$. The next truck may claim the plug at the slot boundary, but power delivery cannot begin until the full turnaround $\delta$ has elapsed. Multiple plugs may turn over concurrently. Because no paired empirical timestamps exist for unplugging and re-plugging at the same physical connector, $\delta$ is treated as a sensitivity parameter. [Verified source fields](../../results/dt_cargo_stop_20261111/event.json)

The model introduces binary variables $x_{vkt}$ assigning vehicle $v$ to named plug $k$ in slot $t$. Let slot length $L=15$ minutes. At offset $b$ minutes from the left boundary of slot $t$, if $(t-t'-1)L+b<\delta$ and plug $k$ was assigned to a different truck in an earlier slot $t'$, then vehicle $v$’s power on plug $k$ must be zero at that offset. Power only needs to be tracked at slot boundaries and at the remainder of $\delta \bmod 15$. Each truck uses a single power setpoint across its active portion of slot $t$, site power caps apply on every sub-interval, and delivered battery energy accumulates as $\eta\sum P\Delta m/60$. These sub-interval cuts account only for turnaround loss—they add zero intra-slot reassignment opportunities and zero extra independent power setpoints. Integrating power at $\delta=0$ recovers the original slot formulation, with identical feasibility across all four baseline configurations. [MILP](../../src/um_charging/changeover.py) · [Independent per-truck, per-plug checker](../../src/um_charging/changeover_check.py)

#### Analytical limits for the two-port / two-warehouse build

Let $h=60E/(50\times0.9)$ be the minutes of 50 kW charging needed to replenish one driving leg of energy $E$. At the warehouse, V1 and V2 can each receive at most 15 rated-power minutes, and because they share 75 kW in the final slot, their combined warehouse replenishment is at most 22.5 rated-power minutes. Even if V3 fully replenishes its first leg at the warehouse, it still requires at least $h$ minutes at the port. At both tested leg energies, the three trucks require at least 3, 3, and 2 port connector-slots respectively—exhausting all eight slots of two port plugs. Both port plugs must switch vehicles; otherwise one truck would occupy four slots and the lower bounds of the other two could not both be met.

If V3 takes over a plug previously used by another truck, V3 gets at most $30-\delta$ minutes. At least one late-released truck must also take over a previously used plug; otherwise the two late trucks occupy the first three slots simultaneously, leaving only one slot for V3. Together, the two late trucks obtain at most $90-\delta$ port minutes plus 22.5 warehouse minutes to cover $4h$ across their four legs. If V3 avoids any changeover loss, both port turnovers fall on the late trucks, tightening the requirement to $2\delta\le112.5-4h$. Across the two tested energies, the exact upper bound is therefore $\min(30-h,112.5-4h)$. The schedule below attains this bound (and remains valid if V1 and V2 are swapped):

| Port plug | 11:00–11:15 | 11:15–11:30 | 11:30–11:45 | 11:45–12:00 |
|---|---|---|---|---|
| 1 | V1 | V1 | V1 | V2 waits $\delta$, then charges |
| 2 | V2 | V2 | V3 waits $\delta$, then charges | V3 |

All three trucks charge at 50 kW whenever active at the port, receiving $45$, $45-\delta$, and $30-\delta$ rated-power minutes respectively. At the warehouse, V3 finishes replenishing in the first two slots and releases the plug, while V1 and V2 share the two plugs in the last slot. At 20.00 kWh per leg, V3 fills exactly at the warehouse and its two port slots set the binding delay limit. At 20.636628905957647 kWh per leg, the two late trucks saturate the 75 kW warehouse cap in the final slot, so any further time loss across their six port slots makes the duty infeasible. [Hand-checked schedule tests](../../tests/test_changeover_bounds.py)

For the three-port / one-warehouse build at 20.00 kWh, the fleet needs at least 40 rated-power minutes from the warehouse: V3 can contribute at most $26\frac{2}{3}$ minutes, leaving at least $13\frac{1}{3}$ minutes for the late trucks. V3 occupies at least the first two warehouse slots and releases the plug no earlier than 09:30; the late trucks become eligible at 09:45, utilizing the 15-minute gap for a critical changeover limit of $16\frac{2}{3}$ minutes. At the higher leg energy, even $\delta=0$ requires at least 102.14794 kWh during the final port hour, exceeding the 100 kW port connection.

**High-energy recovery:** Upgrading the warehouse connection from 75 to 100 kW allows each late truck to draw 15 rated-power minutes in the final warehouse slot. Beyond $\delta>30-h$, V3 can no longer absorb a port handover, so both port turnovers shift onto the late trucks, yielding $4h\le90-2\delta+30$. At the boundary $\delta=60-2h$, endpoint solves and independent verification confirm a feasible schedule. For $\delta=5$ and 10 minutes starting from the installed two-port / two-warehouse build, the minimum incremental addition is a third port connector (+20 synthetic cost units), allowing each truck to keep a dedicated port plug while coordinating warehouse handover. All costs are synthetic cycle-equivalent units. [Optimal builds and enumeration scope](../../results/changeover_20261112/metrics.json)
