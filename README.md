# 电动重卡在港区和仓库的充电设施规划

三辆重卡从港区驶往仓库，装卸后返回港区。仓库有一个充电接口，如果其中两辆车装卸后只能赶上最后 15 分钟，港区需要几个接口才能完成当天这组任务？本项目给定路线、车辆任务和期末电量，用混合整数线性规划（MILP）联合决定两站新增接口、付费扩容档位和逐车充电功率。下面取两套已选设施，各自固定硬件，只重新安排充电。

**同一组四小时合成任务。** 三车各行驶一小时到仓库，停车一小时，再行驶一小时回港，最后在港区停车一小时。每段行程耗电 20 kWh。车辆从 100 kWh 满电出发，期末须回到 100 kWh。充电效率为 90%，每车最多取电 50 kW，全队需购电 133.33 kWh。两站容量分别为港区 100 kW、仓库 75 kW，每隔 15 分钟可零耗时换枪。

**为什么需要 9 个接口时段，港区只有 8 个？** 两辆车在仓库等候 45 分钟才能插枪，只能争用最后一个接口时段。第三辆可以全程插枪，但到站时电池只空出 20 kWh，最多购电 22.22 kWh。即使仓库按最有利的方式分配，一辆车补足这 22.22 kWh，一辆用最后一槽补 12.5 kWh，另一辆未能补电。回港后三车至少还需 2、3、4 个接口时段。方案 A 的两个港区接口一小时只能提供 8 个时段，无法完成任务。

把港区接口增至三个（方案 B），三车可同时充电，合计约 98.61 kW 即可完成任务，港区无需扩容。若仍采用方案 A，把两车的插枪等候缩短到 30 分钟也可完成任务。此处调度预先知道等候时长。A、B 的新增接口投资分别为 20、40 个四小时周期的合成费用单位，每个可行调度的购电费均为 133.33 个单位。

**在 Windows 仓库根目录复算。** 安装 Python 3 后，在 PowerShell 中运行下面一行。程序只用标准库，穷举仓库各时段可连接的车辆，直接在终端输出结果。

```powershell
py -3 scripts/check_eligibility_slots.py
```

找到 `delay_min` 等于 `45` 的一组。应读到 `min_required_port_plug_slots = 9`、`A_feasible = false`、`B_feasible = true`。在 `delay_min = 30` 的一组，A、B 都为 `true`。

| 跟着算例运行 | 入口 |
|---|---|
| 核对车辆任务和插枪资格 | [任务与设备](configs/port_warehouse_investment.json) · [固定设施、受延迟车辆和五档时长](configs/eligibility_stress.json) · [生成逐车 15 分钟输入](src/um_charging/eligibility_stress.py) |
| 检查设施与调度怎样求得 | [变量、目标和约束](docs/model/FORMULATION.md) · [公式与代码](docs/model/IMPLEMENTATION_MAP.md) |
| 运行完整 MILP 并检查解 | [Windows 命令和环境](results/eligibility_stress_20261111/reproduction.json) · [十组实际求解状态与费用](results/eligibility_stress_20261111/metrics.json) |
| 比较仅港区与两地联合投资 | [港区功率 × 仓库补能窗口的设施、费用和可行性](results/boundary_20261110/README.md) |

**停车多久，能有多久充电？** 德国 DT-CARGO 车队 1 的车辆 1 有一对相邻记录。片段 168 在当地时间 00:05:28.378 结束，片段 169 在 00:25:59.143 开始，相隔 20 分 30.765 秒。这给出了两次记录之间可用于充电的时间上界。作业放行、实际接枪和开始供电时刻均未知，港区合成算例的插枪资格仍由配置给定。

```powershell
py -3 scripts/trace_dt_cargo_stop.py
```

终端输出应显示 `recording_gap_seconds = 1230.765` 和 `verified_charging_minutes = null`。从车辆及片段键可核对前后两个时刻、处理表中的停靠间隔和四项独立时间戳的证据。[原始来源与固定版本](reserach/truck%20optimaztion/Germany_Truck_Grid_Dataset_v1/source_manifest.json) · [停靠筛选代码](reserach/truck%20optimaztion/Germany_Truck_Grid_Dataset_v1/build_dataset.py#L30) · [该事件的复算结果](results/dt_cargo_stop_20261111/event.json)

[研究状态与下一步](docs/research/STATUS.md) · [历史进展与接续入口](docs/PROGRESS.md) · [开发与记录约定](AGENTS.md)
