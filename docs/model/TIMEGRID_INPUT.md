# 时间粒度输入与接口占用：capacity-investment-v2

这是本项目新增的输入契约，用于固定物理任务链的时间粒度检验；不是 Ye 2024 公式或案例的严格复现。原 `fixed-facility-v1` 与 `capacity-investment-v1` 仍接受原精确字段和语义，原三车两站回归保留。

## 精确字段

`capacity-investment-v2` 保留 [INVESTMENT_INPUT.md](INVESTMENT_INPUT.md) 中 `capacity-investment-v1` 的全部字段，只更改 `schema_version` 的值，并新增两个必需顶层字段：

| 字段 | 精确取值与含义 |
| --- | --- |
| `transit_locations` | 字符串列表，允许空列表；每项非空且唯一，与 `sites[*].id` 不交叠；每项必须实际出现在至少一条 `timeline` 中。 |
| `connector_policy` | 只接受 `slot_boundary_switching` 或 `fixed_dwell_connection`。 |

标识符不做大小写、拼写或别名匹配。`timeline` 每槽仍恰含 `from`、`to`、`activity`、`plug_allowed`。`from` 与 `to` 可以是实际站点标识符，或 `transit_locations` 明确声明的在途边界标识符。

- `drive`：两个端点不同，该槽 `drive_energy_kwh` 严格为正，`plug_allowed=false` 且 `charging_site=null`。
- `dwell`：两个端点为同一个**实际站点**，耗能为零；`plug_allowed=true` 时 `charging_site` 必须是该站点，否则必须为 `null`。
- 前一槽终点与后一槽起点精确相同；完整周期首末位置相同且必须为实际站点。
- 在途边界只是同一行程内部的时间切分位置，不是新增站点。不得在其停车、插枪、声明接口或设置站点功率。

例：粗网格一小时行程 `P -> W` 可以在 30 分钟网格表达成 `P -> OUT -> W`，但 `OUT` 必须声明为在途位置，两槽耗能之和必须等于原行程耗能。模型输入校验只能检验每个输入的合法性；物理时间、总耗能和插枪资格的跨网格不变性必须由任务链生成与对照检查单独验证。

## 接口占用政策与 C08

`slot_boundary_switching`：保留 C01–C07。每个时间槽可独立决定 `a[v,j,t]`，同一停车窗口内可以在槽边界释放接口、换枪或让其他车辆接入；槽内不能换枪。接口交换不收取时间和能耗，且未设挪车区域或调车资源约束。细网格因此增加**同一物理停车窗口内的调度机会**，不代表停车窗口增长。该政策未增加 C08 约束，输出的 `constraint_counts.C08=0`；检查器 `max_violation_by_constraint.C08=0` 代表未应用锁定，不是已验证了整段占用。

`fixed_dwell_connection`：保留 C01–C07，并增加 C08。对每辆车，若相邻槽的 `charging_site` 相同且不为 `null`，对所有站点约束：

$$a_{v,j,t}=a_{v,j,t-1}.$$

这些相邻等式使整个连续可插枪窗口的连接选择不变：该次停车开始时决定是否占接口，选择后一直占用至该窗口结束；可以保持连接但令充电功率为零，也可以逐槽调整功率。不能延迟占接口、中途释放后转给其他车。`charging_site=null` 或站点变化结束原窗口；后续窗口重新决定连接。这里锁定的是占用数量，接口同质，未另设接口身份变量。

此政策是明确的运营约束对照：**整段占用**，比只规定“充电过程中不拔枪”更强。它没有引入正的插拔/挪车时长，而是禁止在同一完整窗口内转交接口。两个政策都不改变任务、实际到离站时间或原有可插枪时段。

## 不变的投资和费用语义

新增接口整数、每站至多一个离散扩容档位、站点启用参数、设备功率和效率均沿用 v1。投资变量及解数组格式不变。初末电量仍为 C07：初值固定、末值至少恢复初值，不能用改变初值制造协同优势。

只接受 `cost_basis=synthetic_cycle_equivalent` 与 `representative_weight=1`。目标仍为当前完整周期的合成等效新增接口费、扩容费与电费之和；没有真实寿命、折现或年度代表天数校准，不支持真实节约率推断。

对小规模硬件组合枚举时，必须保留 `capacity-investment-v2`、在途位置和 `connector_policy`。把该组合落实到站点 `interfaces` 与 `available_power_kw`，再令 `max_new_interfaces=0`、`upgrade_options=[]`、`interface_cost=0`，独立求该硬件下运营最优；枚举外部计算该组合的投资费。不能退回 v1 而丢失 C08，也不能读取联合 MILP 的运营解代替独立求解。

## 公式与代码、独立验证

| 契约 / 约束 | 实现 | 独立核验 |
| --- | --- | --- |
| v2 精确字段、在途合法性、闭合路线 | `src/um_charging/model.py::validate_input` 与 `_validate_timeline` | 输入拒绝测试覆盖未知、重复、未用在途标识、在途停车、断链与首末在途。 |
| C01–C07 | `src/um_charging/model.py::solve`，沿用原实现 | `src/um_charging/validation.py::check_solution` 复算电量、占用、功率、投资和运营费。 |
| C08 固定完整窗口连接 | `solve` 对相邻同站非空插枪资格增加占用等式 | `check_solution` 直接从原始输入与原始占用逐槽比较；不读取模型矩阵、残差或分组函数。 |

`tests/test_timegrid_model.py` 使用独立手算两车算例：两车各需 20 kWh，同一港区停车窗口长一小时，设备 40 kW、已有一接口、站点容量 80 kW。30 分钟槽且允许换枪时无须新增接口；整段占用时新增一接口。其合成单周期电费均为 40，新增接口费为 10，故目标分别为 40 与 50。把合法换枪解交给整段占用检查器时，只有 C08 失败；另检验固定连接允许功率变化及零功率。

这只是约束语义测试。正式 60/30/15 分钟实验还必须记录源提交、输入哈希、求解状态、界限/gap、独立检查与配置枚举结果，不能把本测试直接当作正式实验结论。

复现测试（在研究仓库根目录，使用已安装 NumPy/SciPy/pytest 的解释器）：

```powershell
python -m pytest tests/test_timegrid_model.py tests/test_fixed_facility.py tests/test_investment_input.py tests/test_investment.py tests/test_cli_paths.py -q
```
