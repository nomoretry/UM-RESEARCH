# 港区与仓库的重卡充电设施规划

[中文](#中文) · [English](#english)

## 中文

三辆电动重卡从港区出发，到仓库装卸后返港。两辆车在仓库等候 45 分钟才可插枪，返港后一小时竟需要至少 9 个接口时段。港区两个接口每 15 分钟允许轮换，一小时只能给出 8 个。仓库保持一个接口时，在原有 100 kW 接入下增加第三个港区接口即可完成同一运输任务。数据、投资费和换枪时间均按合成案例设定。[模型输入](configs/port_warehouse_investment.json) · [设施与逐档结果](results/known_delay_investment_20261111/metrics.json)

**在 main 上复算。** 从本仓库根目录用 Python 3 运行，无需安装第三方包。45 分钟行应显示 `min_required_port_plug_slots = 9`、`A_feasible = false`、`B_feasible = true`。

```powershell
python scripts/check_eligibility_slots.py
```

**德国车队和真实日前电价。** 在 2021 年 9 月的三个留出日，一、两个港区接口均完成 8 个车日；在同一批任务和同期报价下，第二个接口令最低批发电费少 €10.62。六周扩展和年化门槛的输入、代码在已验证的研究版本。按链接打开该版本的 README 并在该版本根目录运行其中命令。[双语研究首页与快速复算](https://github.com/nomoretry/UM-RESEARCH/tree/undefined) · [完整投资实验](https://github.com/nomoretry/UM-RESEARCH/blob/undefined/studies/day-ahead/second_port.md) · [main 上的独立米兰论文复算](studies/fresia-2025/)

## English

[中文](#中文)

Three trucks leave the port, unload at the warehouse and return. When two wait 45 minutes for their warehouse plug, the final port hour requires at least nine connector-slots. Two connectors supply eight quarter-hour slots. Keeping one warehouse connector, a third port connector completes the same synthetic duty at the existing 100 kW grid limit. [Inputs](configs/port_warehouse_investment.json) · [Facility results](results/known_delay_investment_20261111/metrics.json)

**Run on main.** From this repository root, run the following PowerShell command with Python 3. It requires only the standard library. At 45 minutes expect `min_required_port_plug_slots = 9`, `A_feasible = false` and `B_feasible = true`.

```powershell
python scripts/check_eligibility_slots.py
```

**German fleet and day-ahead prices.** Both port builds served eight truck-days on the three September 2021 holdout dates. With the same tasks and delivery prices, the second connector reduced the optimized wholesale bill by €10.62. The linked research revision contains its own inputs and solver commands, the six subsequent operating weeks and the investment threshold. Run the market example from that revision. [Verified bilingual research README](https://github.com/nomoretry/UM-RESEARCH/tree/undefined) · [Full investment case](https://github.com/nomoretry/UM-RESEARCH/blob/undefined/studies/day-ahead/second_port.md) · [Milan replication on main](studies/fresia-2025/)
