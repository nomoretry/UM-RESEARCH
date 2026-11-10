# 容量投资输入规范

这是本项目对 Ye 2024 问题与投资框架的模型改编，不是论文原式或案例数字的复现。实现入口为 `src/um_charging/model.py` 的 `validate_input` 和 `solve`；独立检查与正式运行证据另由对应研究任务维护。

## 版本与费用边界

`fixed-facility-v1` 的字段、单位、固定设施语义和解数组保持不变。新增严格版本 `capacity-investment-v1`；禁止猜测字段别名或大小写转换。

新版本沿用原顶层所有字段，增加 `cost_basis`，其唯一接受值为 `synthetic_cycle_equivalent`。`representative_weight` 必须为 1。接口和扩容费用均为分配到当前完整任务周期的合成等效费用，与该周期购电费相加；它们不是设备一次性购置价，也不是年费。真实寿命、折现率、利用周期数尚未校准，不据此推断真实节约率；本版本不接受把四小时电费直接乘 365 与任意投资费相加。

目标为 `sum(interface_cost * n) + sum(option.cost * u) + sum(price_per_kwh * power_kw * slot_hours)`。所有金额使用 `synthetic_currency`；既有设施为沉没成本。

## 站点字段

每个站点保留 `id`、`active`、`interfaces`、`available_power_kw`、`price_per_kwh`，并增加：

| 字段 | 类型与含义 |
|---|---|
| `max_new_interfaces` | 非负整数，新增接口数量上限 |
| `interface_cost` | 非负有限数，每个新增接口的周期等效合成费用 |
| `upgrade_options` | 数组，可为空；各项字段仅为下表三项 |

| 扩容选项字段 | 类型与含义 |
|---|---|
| `id` | 非空字符串，同一站点内唯一 |
| `additional_power_kw` | 严格正有限数，增加到该站每个时间槽的可用网侧功率 |
| `cost` | 非负有限数，该档位的周期等效合成费用 |

同一站点最多选一个扩容档位；不选表示不扩容，不把档位叠加。`active` 仍是输入，未增加开站决策。停用站点的新增接口和所有扩容选择均固定为零。已有接口数保持原输入语义，实际充电同时受站点启用约束。

## 固定任务、位置与插枪资格

每辆车保留原字段，并增加长度恰为 `slot_count` 的 `timeline`。各时间槽严格包含：

| 字段 | 接受值 |
|---|---|
| `from`、`to` | 已定义的精确站点 `id`，分别是槽开始和结束位置 |
| `activity` | `drive` 或 `dwell` |
| `plug_allowed` | 严格布尔值，固定且非优化决策 |

`drive` 要求起终点不同、`drive_energy_kwh` 严格正、禁止插枪、`charging_site` 为 `null`。`dwell` 要求起终点相同且行驶耗能为零；允许插枪时 `charging_site` 必须等于当前位置，不允许时必须为 `null`。这只限定本次合成输入格式，不宣称现实停车辅助负荷总为零。

相邻槽位置必须衔接，最后位置必须等于首槽起点，构成闭合任务链。车辆电量跨全部槽连续传递；初始电量固定，末端至少恢复初值。该输入验证证明时间轴与位置描述内部一致，不验证实际路线长度、交通时长或现场插枪条件。

仅港区与两地补能的对照应保持车辆输入相同，使用站点 `active` 禁止仓库服务；不能改变路线、耗能或初始电量制造优势。接口占用为整槽二元变量，不含槽内车辆轮换、插拔时间、排队成本或共享功率柜。

## 变量与约束

新增 `n_j` 为整数，`0 <= n_j <= max_new_interfaces * active`；`u_jm` 为档位二元变量，`sum_m u_jm <= active`，对应 C01。

- C04：逐站逐槽接口占用之和不超过 `interfaces + n_j`。
- C05：逐站逐槽功率之和不超过 `available_power_kw[t] * active + sum_m additional_power_kw[m] * u_jm`。
- C02、C03、C06、C07 沿用固定设施模型的插枪资格、车辆功率、连续电量与初末边界。

供电约束是站点可用功率上限，不是潮流、电压或并网校验；未增加换电、路径重排、V2G、储能或市场机制。

## 输出

求解状态、目标、界限、gap 和原始解保留原结构。新版本在 `solution` 的 `occupancy`、`power_kw`、`energy_kwh` 之外增加：

- `new_interfaces`：按输入站点顺序排列的一维数组；保留求解器原值供独立整数性检查，不预先取整。
- `upgrade_selected`：按站点顺序、每站再按输入扩容选项顺序排列的数组；空选项对应空数组。

固定设施旧版本不添加这些字段；无原始可行解时 `solution` 仍为 `null`。
