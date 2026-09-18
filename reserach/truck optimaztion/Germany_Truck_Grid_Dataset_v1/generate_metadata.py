from pathlib import Path
import json, shutil, pandas as pd

H=Path(__file__).resolve().parent
R=H if (H/'raw').exists() else H/'Germany_Truck_Grid_Dataset_v1'
s=json.loads((R/'summary.json').read_text())

descs={
'vehicle_id':('','原始匿名车辆编号；跨表关联，不能识别企业或司机'),
'fleet_test_id':('','原始匿名车队编号；四个样本车队，不代表四个省份'),
'track_id':('','原始行驶记录主键；不是GPS点编号'),
'tour_id':('','原作者行程分组，保留但本版本不直接用作完整任务链'),
'distance':('m','单条记录的行驶距离'),
'distance_km':('km','观测记录里程换算或指定周期的里程合计'),
'track_gap':('m','原README称与后一段的空间缺口；首段缺失模式提示方向需核实'),
'avg_speed':('m/s','原始记录平均速度'),
'max_speed':('m/s','原始记录最大速度'),
'r_signal_loss':('ratio','原始信号丢失路程比例；异常/缺失保留质量标记'),
'gross_vehicle_weight':('kg','额定最大总质量，不是实际载荷'),
'total_mass_with_trailer':('kg','含挂车最大组合质量，不是实测货物重量'),
'home_base':('boolean','记录终点处于车队基地；不证明该处已有充电设施'),
'cid':('','匿名终点聚类编号；没有对应经纬度'),
'start_time':('timestamp','原始起始时间，保留UTC偏移'),
'stop_time':('timestamp','原始结束时间，保留UTC偏移'),
'next_departure_utc':('UTC timestamp','下一条记录起点，停靠窗口的观测边界'),
'energy_battery_kwh':('kWh','场景值：记录里程×假设单位电耗'),
'energy_grid_kwh':('kWh','场景值：电池能量/充电效率'),
'p_immediate_kw':('kW AC','独立周期到达即充情景，时段平均电网侧功率'),
'p_uniform_kw':('kW AC','独立周期在窗口均匀补能情景，非优化解'),
'strict_valid':('boolean','研究者质量规则联合筛选结果，不等于完整无遗漏轨迹'),
'scenario_eligible':('boolean','满足周期和窗口证据要求，尚未检查电池或补能时长'),
'baseline_profile_eligible':('boolean','满足本版本独立周期电量和时间条件；不证明连续SOC可行'),
'cycle_quality_pass':('boolean','组成记录及双边空间缺口通过当前规则'),
'boundary_gap_conservative_m':('m','相邻两条track_gap较大值；任一缺失则未知'),
'window_h':('h','相邻记录之间的基地停靠候选时长'),
'vmR':('kV','SimBench节点额定电压'),
'vmMin':('p.u.','原模型电压下限，不替换为自拟限值'),
'vmMax':('p.u.','原模型电压上限，不替换为自拟限值'),
'loadingMax':('%','原模型加载率上限；变压器原值50%，不可默改100%'),
'pLoad':('MW','SimBench负荷有功基值；乘以对应_pload曲线'),
'qLoad':('Mvar','SimBench负荷无功基值；乘以对应_qload曲线'),
'pRES':('MW','SimBench分布式电源有功基值；乘以对应profile曲线'),
'profile':('','SimBench时序曲线键，必须与曲线列对应'),
'grid_node':('','人为情景映射的SimBench节点；不是真实基地接入点'),
'profile_time':('benchmark time','SimBench原始2016年时序标签，不假定与货车同时观测'),
'net_demand_before_losses_mw':('MW','模型负荷减分布式发电，不含网络损耗或潮流结果'),
'time_utc':('UTC timestamp','统一计算时间；本地时间须转Europe/Berlin'),
'evidence_class':('','数据性质标签：观测/推导/情景/基准模型'),
}
descs.update({
'next_track_id':('','同车按开始时间排序后的下一条原始记录ID；末条为空'),
'n_signal_loss':('count','原始记录内信号丢失次数'),
'd_signal_loss':('m','原始记录内信号丢失期间路程'),
'avg_hdop':('source unit','原README写m；HDOP含义/单位未独立确认，本版不据此筛选'),
'long_haul':('boolean','原作者标记：记录终点距离基地超过150km'),
'rest_area':('boolean','原作者标记：记录终点位于无服务休息区'),
'service_area_fuel':('boolean','原作者标记：记录终点位于服务区'),
'industrial_area':('boolean','原作者标记：记录终点位于工业区'),
'start_utc':('UTC timestamp','原始起始时刻转换为UTC'),
'stop_utc':('UTC timestamp','原始终止时刻转换为UTC'),
'duration_h':('h','该记录或周期的末时刻减首时刻；周期时长含中间停留'),
'avg_speed_kmh':('km/h','avg_speed乘3.6'),
'distance_over_time_kmh':('km/h','该条记录里程除以持续时间'),
'local_start_date':('date','开始时刻按Europe/Berlin本地日历归属；跨日整段归起始日'),
'next_start_utc':('UTC timestamp','同车下一条记录开始时刻；末条为空'),
'next_track_gap_m':('m','同车下一行track_gap，供双边保守筛查'),
'overlap_previous':('boolean','本条开始早于同车上一条结束'),
'flag_missing_distance':('boolean','原始distance缺失'),
'flag_speed':('boolean','原始均速或距离/时长超过130km/h，或原始均速为负'),
'flag_signal_ratio':('boolean','r_signal_loss>0.2或<0；研究者阈值'),
'flag_unknown_signal':('boolean','正里程记录的r_signal_loss缺失'),
'basic_valid':('boolean','距离存在且非负、时长正、不重叠、不触发速度标记'),
'inter_record_gap_h':('h','下一记录开始减本记录结束；不自动证明期间静止'),
'window_time_plausible':('boolean','记录间隔在0.25至48小时之间'),
'base_window_candidate':('boolean','基地标记、窗口时长、双边空间缺口、两端记录质量同时通过'),
'track_count':('count','当前车辆/车辆日/周期的原始片段数'),
'recorded_distance_km':('km','原始非缺失里程合计；带异常记录时不代表有效总里程'),
'strict_valid_tracks':('count','通过联合质量规则的片段数'),
'first_start_utc':('UTC timestamp','分组内最早起始时刻'),
'last_stop_utc':('UTC timestamp','分组内最晚终止时刻'),
'axle_class':('source code','原作者车辆轴型分类编码；参见raw/dt_cargo/README.md的BASt引用'),
'observed_days':('count','有记录的不同本地开始日期数，不是完整有效天数'),
'scenario_vehicle_type':('text','假设电动替代的状态说明；不把原始样本认作电动车'),
'vehicles':('count','分组内车辆数'),
'tracks':('count','分组内原始片段数'),
'observed_vehicle_days':('count','有记录的车辆×日期数；直方图中另要求日内均通过质量及≥1km'),
'sample_mean_km_per_observed_day':('km/day','分组内记录里程/有记录车辆日；不是总体平均日需求'),
'flagged_tracks':('count','该车辆日未通过联合质量规则的片段数'),
'recording_h':('h','该车辆日归属记录的持续时间之和，不是整日可用时长'),
'strict_recorded_distance_km':('km','车辆日内仅通过联合质量的记录里程合计'),
'coverage_note':('text','车辆日覆盖范围说明'),
'cycle_id':('','本处理版本的周期唯一编号；不等于原tour_id'),
'previous_home_track_id':('','界定周期之前基地端点的原记录ID'),
'first_track_id':('','该周期第一条纳入里程合计的原记录ID'),
'last_track_id':('','该周期返回基地的末条原记录ID'),
'departure_utc':('UTC timestamp','周期首段记录开始；不补造出场GPS'),
'arrival_utc':('UTC timestamp','周期末段记录结束；候选补能起点'),
'window_quality_pass':('boolean','周期末记录对应的base_window_candidate'),
'battery_feasible':('boolean','本独立周期假设电池能耗≤500×(0.9−0.1)kWh；无跨周期SOC递推'),
'window_energy_feasible':('boolean','假设电网能量≤150kW×候选窗口小时数'),
'exclusion_reason':('category','included_in_profile/quality_or_window_evidence/battery/window/battery_and_window'),
'distance_bin':('km interval','无标记且记录里程≥1km的车辆日分箱；区间左闭右开'),
'metric':('text','质量审计统计项'),
'value':('count','该审计项的计数'),
'interpretation_zh':('text','审计口径与限制'),
'check':('text','脚本执行的一致性检查名称'),
'pass_':('boolean','检查是否通过；失败会使脚本终止'),
'energy_kwh_per_km':('kWh/km','假设电池侧单位里程能耗'),
'charger_ac_kw':('kW','假设单车电网侧充电有功输入功率'),
'eligible_cycles':('count','周期与窗口证据均通过的周期数'),
'battery_feasible_cycles':('count','本参数情景下满足可用电池能量限制的周期数'),
'window_feasible_cycles':('count','本参数情景下满足窗口补回能量条件的周期数'),
'both_feasible_cycles':('count','同一周期同时满足电池与窗口条件的数量'),
'energy_grid_mwh':('MWh','全部证据合格周期的假设需电量，包含电池/时间条件失败的周期'),
'time_local':('HH:MM','示例UTC时刻转Europe/Berlin得到的当地钟表时间'),
'grid_profile_time':('benchmark time','叠加所用2016年网模曲线时刻，显式区别车辆日期'),
'background_net_mw':('MW','选定网模日的负荷减发电，不含损耗'),
'immediate_total_mw':('MW','背景净需求＋立即补能功率/1000；不是潮流结果'),
'uniform_total_mw':('MW','背景净需求＋均匀补能功率/1000；不是潮流结果'),
'alignment_class':('text','标记不同年份按星期/钟表时刻作情景对齐'),
'hypothetical_depot_id':('','人为车队基地情景ID，不对应公开真实场址'),
'mapping_rule':('text','网模现有MV负荷节点按名称排序后均匀取4个索引'),
'gross_load_mw':('MW','各pLoad×对应_pload曲线的求和'),
'reactive_load_mvar':('Mvar','各qLoad×对应_qload曲线的求和'),
'res_generation_mw':('MW','各pRES×对应发电曲线的求和'),
'id':('','本SimBench表的元件或型号主键'),
'node':('','连接节点，外键Node.id'),
'nodeA':('','线路/开关A端节点，外键Node.id'),
'nodeB':('','线路/开关B端节点，外键Node.id'),
'nodeHV':('','变压器高压侧节点，外键Node.id'),
'nodeLV':('','变压器低压侧节点，外键Node.id'),
'type':('source code','源表元件类别/型号；线路与变压器的type分别关联LineType.id与TransformerType.id'),
'length':('km','线路长度'),
'subnet':('','SimBench子网标识'),
'voltLvl':('source code','SimBench电压层级编码，不是以kV计的额定电压'),
'sR':('MVA','元件额定视在功率'),
'r':('ohm/km','线路型号的单位长度电阻'),
'x':('ohm/km','线路型号的单位长度电抗'),
'b':('microS/km','线路型号的单位长度并联电纳；50Hz转换定义见官方converter'),
'iMax':('A','线路型号最大电流；官方converter转换成pandapower时乘1e-3'),
'vmSetp':('p.u.','节点电压设定幅值'),
'vaSetp':('degree','节点电压设定相角'),
'substation':('','所属变电站标识；缺失不补造'),
'coordID':('','对应raw/simbench/csv/Coordinates.csv坐标键；不是货车位置'),
'vmHV':('kV','变压器高压侧额定电压'),
'vmLV':('kV','变压器低压侧额定电压'),
'va0':('degree','变压器额定相移'),
'vmImp':('%','变压器短路电压百分数'),
'pCu':('kW','变压器额定负载铜耗'),
'pFe':('kW','变压器铁耗'),
'iNoLoad':('%','变压器空载电流百分数'),
'tapable':('boolean/code','源模型是否可调分接头'),
'tapside':('HV/LV','变压器型号分接头所在侧'),
'dVm':('%/step','每档分接头的电压幅值变化百分数'),
'dVa':('degree/step','每档分接头相角变化'),
'tapNeutr':('step','中性分接头档位'),
'tapMin':('step','分接头最低档位'),
'tapMax':('step','分接头最高档位'),
'tappos':('step','当前变压器分接头档位'),
'autoTap':('source code','源模型自动调压设置，原样保留'),
'autoTapSide':('source code','源模型自动调压所控制侧，原样保留'),
'cond':('boolean/code','开关状态，源表1为闭合，0为断开'),
'calc_type':('source code','潮流元件计算类型，例如pq、vavm；原样保留'),
'qRES':('Mvar','分布式电源无功基值'),
'dspf':('ratio','外部电网有功平衡分配系数；保留源值'),
'pExtNet':('MW','外部电网有功给定值；空缺不补造'),
'qExtNet':('Mvar','外部电网无功给定值；空缺不补造'),
'pWardShunt':('MW','Ward并联等值有功参数；本模型为空'),
'qWardShunt':('Mvar','Ward并联等值无功参数；本模型为空'),
'rXWard':('ohm','扩展Ward等值电阻；本模型为空'),
'xXWard':('ohm','扩展Ward等值电抗；本模型为空'),
'vmXWard':('p.u.','扩展Ward内部电压幅值；本模型为空'),
})
dictionary=[]
for f in sorted((R/'processed').glob('*.csv')):
    df=pd.read_csv(f,nrows=2)
    for col in df.columns:
        unit,desc=descs.get(col,('','保留原模型字段（grid_*）或由build_dataset.py定义的派生字段；详见源README与处理脚本'))
        if not unit:
            for suf,un in [('_kwh','kWh'),('_mwh','MWh'),('_km','km'),('_kmh','km/h'),('_kw','kW'),('_mw','MW'),('_mvar','Mvar'),('_h','h'),('_utc','UTC timestamp')]:
                if col.endswith(suf): unit=un; break
        dictionary.append(dict(file=f.name,column=col,unit=unit,description_zh=desc))
pd.DataFrame(dictionary).to_csv(R/'data_dictionary.csv',index=False,encoding='utf-8-sig')

readme=f'''# 德国重卡运营—典型配电网研究数据集 v1

构建日期：2026-09-17。用途：向导师展示可获取的数据、处理过程与可开展的研究；尚不是已验证的真实站点规划结果。

## 1. 为什么选择德国

德国适合作为当前的数据起点：DT-CARGO提供可下载的匿名逐车行驶片段及基地标签，SimBench提供公开配电网拓扑、设备参数和全年15分钟曲线。两个来源可分别提供“何时需要补能”和“电网怎样承受负荷”的输入。这里没有声称德国在全球数据最完整，也没有将两套独立样本伪装成真实地点的一一对应。

建议暂定题目：**基于公开重卡运营数据的充电设施容量配置与配电网协同优化——以德国典型配电网为例**。v1先研究给定运营任务下的补能需求与接入能力；真实道路路径优化需要另一套有道路空间信息的数据。

## 2. 具体来源、下载方式与样本范围

### A. DT-CARGO：真实运营记录的公开匿名版本

- 原作者仓库：https://github.com/TUMFTM/dt-cargo
- 关联论文：Balke & Adenaw, Heavy commercial vehicles’ mobility: Dataset of trucks’ anonymized recorded driving and operation (DT-CARGO), Data in Brief, 2023. https://doi.org/10.1016/j.dib.2023.109246
- 固定仓库提交：805c534c73ed4d247babd053f60468b486f92519。
- 车辆原表：https://raw.githubusercontent.com/TUMFTM/dt-cargo/805c534c73ed4d247babd053f60468b486f92519/input/public/fleet.csv
- 行驶原表：https://raw.githubusercontent.com/TUMFTM/dt-cargo/805c534c73ed4d247babd053f60468b486f92519/input/public/tracks.csv
- 本版本直接下载作者提供的CSV，未向企业索取私有记录，未从地图反推轨迹。

实际文件含 **{s['raw_vehicles']}辆、4个匿名车队、{s['raw_tracks']:,}条行驶片段**。这些是记录汇总，不是101,826个GPS点，也不是101,826份货运订单。额定车辆总质量为18–32吨，不能用作实际载货量。

原始文件最早时间2021-08-26，最晚2022-04-11；记录里程合计1,269,133.283 km，含已标记异常片段，不能全部当作已清洗有效里程。各车观测时间不同，有6,869个有记录的车辆日，不构成完整连续运营普查。日期与数量由公开版本的实际覆盖决定，本研究没有为扩大充电需求挑选时间或车辆。保留全部原始数据后再进行可追溯筛选。

关联论文描述54辆，而当前固定公开文件只有53辆；不补造第54辆。仓库README的speed.zip完整下载链接仍写TODO，本包没有声称已取得全部10Hz速度数据。坐标、企业名、货物订单、真实电池/SOC/充电过程未公开在这两张表中。

### B. SimBench：德国典型配电网基准模型

- 官方选择与下载页：https://simbench.de/en/download/datasets/
- 本版本网络代码：**1-MV-urban--0-sw**（城市中压、基准情景0、显式开关）。
- 实际CSV压缩包：https://daks.uni-kassel.de/bitstreams/6ad5e5f8-6b47-4275-906d-db780344b9ee/download
- 代码与说明：https://github.com/e2nIEE/simbench

包含440个节点、147条线路、305个开关、2台110/10 kV变压器、139个负荷元素和134个分布式电源元素。440个节点包含开关相关辅助节点，不能称为440个充电候选站。模型主要中压为10 kV，原变压器loadingMax=50%，节点电压限值与设备参数均保留。

全年曲线有35,136个15分钟时段，原时间标签为2016年。它们是基准模型曲线，不是与2021–2022年货车同时间、同地点测得的配网数据。选择城市中压模型是为了开始研究集中车队补能的接入问题，属于研究者的算例选择，后续必须对其他馈线与网络类型复核。

全部下载URL、UTC时间、字节数与SHA-256见source_manifest.json。两套数据库均带有ODbL/DbCL许可说明；原许可证保存在raw中。衍生数据库继续注明来源并按ODbL共享；本包不替代原始许可文本。

## 3. 文件怎么用

| 文件/目录 | 内容 | 性质 |
|---|---|---|
| raw/dt_cargo/ | 作者车辆表、行驶表及说明，原字节保留 | 匿名实测汇总 |
| raw/simbench/ | 官方网模ZIP、完整CSV、许可 | 基准电网模型 |
| processed/vehicles.csv | 53辆车的参数、记录量及覆盖期 | 观测汇总 |
| processed/tracks_with_quality.csv | 全部101,826行及逐行质量标记 | 观测＋质量判断 |
| processed/vehicle_days.csv | 6,869个有记录车辆日 | 观测汇总，不保证全天完整 |
| processed/stop_windows.csv | 相邻记录间隙、基地标签及候选窗口 | 推断的停靠窗口 |
| processed/duty_cycle_scenarios.csv | 7,073个≥1km基地端点间周期及筛选原因 | 观测里程＋电动化假设 |
| processed/charging_profiles_15min.csv | 四车队、15分钟、立即/均匀补能曲线 | 独立周期示例，不是全车队预测 |
| processed/grid_*.csv | 可连接的网模表；背景曲线另存 | 基准模型及确定性换算 |
| processed/scenario_depot_grid_mapping.csv | 四个匿名车队对应四个网模负荷节点 | 人为映射，无真实地理关联 |
| processed/demo_grid_load_overlay.csv | 一个演示日的充电需求与背景需求叠加 | 跨年份同星期及时刻的情景对齐 |
| processed/sensitivity_summary.csv | 3档电耗×2档功率，共6个情景 | 参数敏感性筛查 |
| data_dictionary.csv | 各处理表的字段与主要单位 | 字段字典 |
| scenario_parameters.json | 所有本版本假设与筛选阈值 | 研究者设定 |
| build_dataset.py / download_sources.py | 重建数据、重新下载来源 | 可复现脚本 |
| summary.json / processed/quality_audit.csv | 数量核验与统计口径 | 数据审计 |

主键：vehicle_id联接车辆与片段；track_id追溯原记录；cycle_id标识本版本派生周期；grid_node联接网模Node.id。匿名cid没有公开坐标，不与电网坐标强行匹配。

## 4. 清洗、任务周期与停靠窗口

1. 保留所有原始记录。统一为UTC计算；展示日历用Europe/Berlin，包含夏令时。
2. 缺失里程49条；零里程1,270条；速度规则标记45条。均速或距离/时长超过130 km/h、负速度、同车时序重叠等被标记。信号损失比例大于20%、小于0或正里程时缺失也被标记。130 km/h和20%是本研究阈值，后续应做敏感性检验。
3. 联合规则后100,427条记录通过。通过不等于完整轨迹，观测遗漏仍可能存在。
4. 对同一车辆，按时间取相邻两个home_base=True的记录终点，将其间记录作为基地端点间周期；只输出合计≥1km的周期。该算法可能被基地内挪车切碎，v1没有擅自把这些片段合成长途运输订单。
5. 停靠候选窗口是上一记录终点至下一记录起点的时差。仅在15分钟至48小时之间、基地标记成立、相邻记录质量通过且空间缺口≤500m时进入保守子集。超过48小时不直接视为连续可充电时间。
6. 原README称track_gap是到后一段的缺口，但各车首段缺失模式提示方向可能需作者澄清。因此同时检查相邻两行的track_gap≤500m；任一缺失则不通过。这是保守处理，会损失样本，不能写成已核实字段含义。
7. 逐周期保留质量失败、电池条件失败、时间条件失败等原因，未满足条件的数据没有删除。

最终有 **3,520个周期**同时通过周期和窗口质量条件，覆盖记录里程{s['quality_eligible_distance_km']:,.1f} km。它们是有条件的分析子集，不代表全国货运或每辆车的完整运行。

## 5. 从运营记录到电力需求：哪些量是真实，哪些是设定

| 量 | 本版本取值 | 依据 |
|---|---:|---|
| 行驶里程、到达/下一次记录时间 | 原始记录推导 | 观测 |
| 单位电耗 | 1.2 kWh/km | 假设；另用0.9/1.5检验 |
| 充电功率 | 150 kW AC/车 | 假设；另用350检验 |
| 电池容量 | 500 kWh | 假设，未指认具体品牌车型 |
| SOC工作区间 | 10%–90%，可用400 kWh | 假设 |
| 充电效率 | 0.95 | 假设；电网输入到电池的效率 |
| 充电功率因数、桩数、站点容量 | 尚未设定 | 潮流/优化阶段需补齐 |

公式：E_battery(kWh)=distance(km)×e(kWh/km)；E_grid=E_battery/η；t_min(h)=E_grid/P_AC(kW)。**kWh是能量，kW是瞬时有功功率；MW=1,000kW。** 不要把两者混称为“电力大小”。

仅在独立周期E_battery≤400kWh、且150kW能在候选窗口内补回能量时，生成对照曲线：到达即以150kW输入充电，或在整个窗口均匀充电。计算按真实秒数与15分钟网格的交集分摊，避免把短事件硬凑成整小时。

**重要覆盖限制：**3,520个合格证据周期的假设需电量共{s['quality_eligible_grid_energy_mwh']:.2f}MWh，其中2,546个周期进入曲线，覆盖49辆车，但曲线只覆盖{s['baseline_grid_energy_mwh']:.2f}MWh，即需求的{s['baseline_profile_energy_coverage']:.1%}。其余974个周期仍在表中；长里程与短窗口周期更容易失败。不能用已通过子集得出整个车队“电动化容易”或“电网能够承受”的结论。

这不是全时段SOC仿真：各周期独立地假设能够补回该周期能耗，没有证明前一周期SOC可传递，也没有排队、端口数量、车辆受电曲线或接入容量约束。“均匀补能”只是规则对照，并不是已求解的最优调度。

## 6. 配电网数据如何进入下一步模型

保留Node、Line、LineType、Switch、Transformer、TransformerType、ExternalNet、Load、RES及全年曲线。负荷有功按pLoad×对应profile_pload，无功按qLoad×profile_qload；发电按pRES×对应RESProfile。电网背景需求为负荷减发电，未计线路/变压器损耗。

当前映射把四车队分别放到按名称排序后均匀取位的四个现有MV负荷节点上，仅供可重复的算例对比。不是通过企业位置、GPS或电网台账验证的接入点。后续应遍历多个接入节点、馈线和网型；不能用本映射给现实企业推荐站址。

演示日期{s['demo_date']}按“当日合格曲线到达事件涉及车辆数最多，其次事件数最多，最后最早日期”选择，**不是典型日**。示例曲线该日峰值分别为{s['demo_immediate_peak_kw']:.1f}和{s['demo_uniform_peak_kw']:.1f}kW；只针对已通过条件的独立周期。按星期和时刻对齐到SimBench {s['grid_profile_demo_date']}，显式保留两个日期，未将2016年曲线改称2021年实测。

下一步可在潮流模型里检查：节点电压幅值(p.u.)、线路电流/负载率、变压器负载率、网损和接入容量。当前只有输入与负荷叠加，**没有执行潮流，没有生成充电导致的电压变化或过载结论**。raw中的NodePFResult.csv是原作者随网模提供的基准结果，不能冒充本研究的新结果。

电网变化不能反向替代或识别货运路径；合理转换是保留可观测的任务需求，把决策由“道路路径”转为“桩功率/数量、补能时间、接入位置或储能配置”。

## 7. 已完成的校验与仍需的验证

已通过9项一致性检查：片段主键唯一、车辆外键完整、原始数量保留、日汇总里程守恒、两种曲线能量守恒、映射节点存在、线路端点存在、全年负荷曲线完整。结果见processed/validation_checks.csv。

尚未完成：与作者确认53/54辆及track_gap方向；验证基地内短片段合并；证明连续多周期SOC与未观测间隙的可行性；车型能耗与充电曲线校准；充电桩/电网/土地成本；真实基地接入位置；潮流与优化求解；研究样本代表性。这些是研究阶段边界，不能藏进附注后声称已经完成规划。

## 8. 重现

已有原始数据时，在本目录执行：

```bash
python build_dataset.py
```

环境需求：Python 3.10+，pandas 2.x，numpy。脚本输出processed与summary.json。CSV采用UTF-8 BOM便于中文Excel打开，单位写在字段名/字典。若需重新抓取固定版本来源，运行download_sources.py；重新下载时核对source_manifest的SHA-256。此过程不需要物流公司授权或登录。

完整数据以本ZIP内CSV为准。全部7,073个派生周期均保留，未用少量示例替代完整表。若调整参数并重建，应同时运行generate_metadata.py刷新字段目录；说明中的固定版本统计是v1的构建快照，改变规则后需同步更新研究描述。

## 9. 给老师的简短说明

“我选择德国作为公开数据算例，已取得4个车队53辆货车的运营汇总记录，并配套德国SimBench典型配电网。真实输入是车辆的时间、里程与基地标签；电池、电耗与基地接入节点是明确标注的情景设定。当前完成了原始数据保留、质量标记、周期与停靠窗口提取以及15分钟补能需求对照。下一步拟在连续任务可行性得到验证后，研究充电设施容量和电网约束下的调度，不再声称可以还原真实道路路径。”

导师讨论重点：是否接受“真实运营样本＋典型电网”的方法验证定位；先解决基地挪车/数据遗漏带来的任务链问题，还是先做给定补能请求的配网容量模型；论文的新增方法是什么，而非仅下载并拼接两个数据源。
'''
(R/'README_zh.md').write_text(readme,encoding='utf-8')
if H != R:
    shutil.copy2(H/'build_dataset.py',R/'build_dataset.py')
    shutil.copy2(H/'download_sources.py',R/'download_sources.py')
(R/'requirements.txt').write_text('pandas>=2.0,<3.0\nnumpy>=1.24\n',encoding='utf-8')
print('README and dictionary prepared')
