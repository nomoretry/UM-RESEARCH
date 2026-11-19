"""Rebuild derived DT-CARGO / SimBench tables. No private data, no random sampling.
Run with Python >=3.10 and pandas >=2.0, numpy. Paths relative to this script.
This is an illustrative electrification scenario, NOT measured EV charging.
"""
from pathlib import Path
import json, hashlib, shutil, math, sys
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / 'raw').exists() else HERE / 'Germany_Truck_Grid_Dataset_v1'
OUT = ROOT / 'processed'
OUT.mkdir(exist_ok=True)
TZ = 'Europe/Berlin'
P = dict(energy_kwh_per_km=1.2, charger_ac_kw=150.0, efficiency=0.95,
         battery_nominal_kwh=500.0, soc_high=0.9, soc_low=0.1,
         max_boundary_gap_m=500.0, max_signal_loss_ratio=0.2,
         min_window_h=0.25, max_window_h=48.0, min_cycle_km=1.0,
         max_avg_speed_kmh=130.0, slot_minutes=15)
(ROOT/'scenario_parameters.json').write_text(json.dumps(P, indent=2), encoding='utf-8')

def save(df, name):
    df.to_csv(OUT/name, index=False, encoding='utf-8-sig', float_format='%.8f')

def records(df):
    return json.loads(df.to_json(orient='records', date_format='iso'))

raw = pd.read_csv(ROOT/'raw/dt_cargo/tracks.csv')
fleet = pd.read_csv(ROOT/'raw/dt_cargo/fleet.csv')
t = raw.copy().sort_values(['vehicle_id','start_time','track_id'])
t['start_utc'] = pd.to_datetime(t.start_time, utc=True, format='mixed')
t['stop_utc'] = pd.to_datetime(t.stop_time, utc=True, format='mixed')
t = t.sort_values(['vehicle_id','start_utc','track_id']).reset_index(drop=True)
t['duration_h'] = (t.stop_utc-t.start_utc).dt.total_seconds()/3600
t['distance_km'] = t.distance/1000
t['avg_speed_kmh'] = t.avg_speed*3.6
t['distance_over_time_kmh'] = t.distance_km/t.duration_h
t['local_start_date'] = t.start_utc.dt.tz_convert(TZ).dt.strftime('%Y-%m-%d')
g = t.groupby('vehicle_id', sort=False)
t['previous_stop_utc'] = g.stop_utc.shift(1)
t['next_start_utc'] = g.start_utc.shift(-1)
t['next_track_id'] = g.track_id.shift(-1).astype('Int64')
t['next_track_gap_m'] = g.track_gap.shift(-1)
t['overlap_previous'] = t.start_utc < t.previous_stop_utc
t['flag_missing_distance'] = t.distance.isna()
t['flag_speed'] = ((t.avg_speed_kmh>P['max_avg_speed_kmh']) |
                   (t.distance_over_time_kmh>P['max_avg_speed_kmh']) |
                   (t.avg_speed_kmh<0))
t['flag_signal_ratio'] = (t.r_signal_loss> P['max_signal_loss_ratio']) | (t.r_signal_loss<0)
t['flag_unknown_signal'] = t.r_signal_loss.isna() & (t.distance.fillna(0)>0)
t['basic_valid'] = t.distance.notna() & (t.distance>=0) & (t.duration_h>0) & ~t.overlap_previous & ~t.flag_speed
t['strict_valid'] = t.basic_valid & ~t.flag_signal_ratio & ~t.flag_unknown_signal
t['inter_record_gap_h'] = (t.next_start_utc-t.stop_utc).dt.total_seconds()/3600
# README says track_gap refers to the following track, but the first track of
# each vehicle has NA. Require both adjacent values to be small, without silently
# resolving that direction ambiguity. This is intentionally conservative.
t['boundary_gap_conservative_m'] = t[['track_gap','next_track_gap_m']].max(axis=1, skipna=False)
t['window_time_plausible'] = t.inter_record_gap_h.between(P['min_window_h'],P['max_window_h'])
t['base_window_candidate'] = t.home_base & t.window_time_plausible & t.boundary_gap_conservative_m.le(P['max_boundary_gap_m']) & t.strict_valid & g.strict_valid.shift(-1).fillna(False).astype(bool)
t = t.merge(fleet[['vehicle_id','fleet_test_id']],on='vehicle_id',how='left',validate='many_to_one')
save(t.drop(columns=['previous_stop_utc']), 'tracks_with_quality.csv')
stops=t[['track_id','next_track_id','vehicle_id','fleet_test_id','stop_utc','next_start_utc','home_base','cid','inter_record_gap_h','boundary_gap_conservative_m','window_time_plausible','base_window_candidate']].copy()
stops['evidence_class']='INFERRED_INTER_RECORD_WINDOW'
save(stops,'stop_windows.csv')

# Calendar-day summaries allocate an entire recorded segment to its start date.
# These are recorded-distance summaries, not proof of full daily coverage.
daily=t.groupby(['vehicle_id','fleet_test_id','local_start_date']).agg(
    track_count=('track_id','size'), recorded_distance_km=('distance_km','sum'),
    strict_valid_tracks=('strict_valid','sum'), flagged_tracks=('strict_valid',lambda s:(~s).sum()),
    recording_h=('duration_h','sum'), first_start_utc=('start_utc','min'),last_stop_utc=('stop_utc','max')).reset_index()
strictdist=t.loc[t.strict_valid].groupby(['vehicle_id','local_start_date']).distance_km.sum()
daily['strict_recorded_distance_km']=[strictdist.get((r.vehicle_id,r.local_start_date),0) for r in daily.itertuples()]
daily['coverage_note']='observed segments only; entire segment assigned to start day'
save(daily,'vehicle_days.csv')

# Consecutive home-base record endpoints delimit independent duty-cycle
# candidates. No attempt is made to decode the repository's ambiguous tour_id.
cycles=[]
for vid, v in t.groupby('vehicle_id',sort=True):
    v=v.reset_index(drop=True)
    anchors=np.flatnonzero(v.home_base.to_numpy())
    for a,b in zip(anchors[:-1],anchors[1:]):
        chunk=v.iloc[a+1:b+1]
        end=v.iloc[b]
        d=chunk.distance_km.sum(min_count=1)
        if pd.isna(d) or d<P['min_cycle_km']: continue
        # Internal recording continuity: exact direction of track_gap unresolved.
        boundary=v.iloc[a:b+1].boundary_gap_conservative_m
        complete=bool(chunk.strict_valid.all() and boundary.le(P['max_boundary_gap_m']).all())
        h=float(end.inter_record_gap_h) if pd.notna(end.inter_record_gap_h) else np.nan
        ebat=d*P['energy_kwh_per_km']; egrid=ebat/P['efficiency']
        usable=P['battery_nominal_kwh']*(P['soc_high']-P['soc_low'])
        eligible=complete and bool(end.base_window_candidate)
        feasible=eligible and ebat<=usable and egrid<=P['charger_ac_kw']*h
        cycles.append(dict(cycle_id=f'C{int(vid):02d}_{int(end.track_id):06d}',vehicle_id=int(vid),fleet_test_id=int(end.fleet_test_id),
            previous_home_track_id=int(v.iloc[a].track_id),first_track_id=int(chunk.iloc[0].track_id),last_track_id=int(end.track_id),
            track_count=len(chunk),departure_utc=chunk.iloc[0].start_utc,arrival_utc=end.stop_utc,
            next_departure_utc=end.next_start_utc,distance_km=float(d),duration_h=(end.stop_utc-chunk.iloc[0].start_utc).total_seconds()/3600,
            window_h=h,cycle_quality_pass=complete,window_quality_pass=bool(end.base_window_candidate),
            scenario_eligible=eligible,energy_battery_kwh=ebat,energy_grid_kwh=egrid,
            battery_feasible=ebat<=usable,window_energy_feasible=(egrid<=P['charger_ac_kw']*h) if pd.notna(h) else False,
            baseline_profile_eligible=feasible,evidence_class='DERIVED_CYCLE_PLUS_ASSUMED_ELECTRIFICATION'))
c=pd.DataFrame(cycles)
c['exclusion_reason']=np.select([~c.scenario_eligible,~c.battery_feasible&~c.window_energy_feasible,~c.battery_feasible,~c.window_energy_feasible],['quality_or_window_evidence','battery_and_window','battery','window'],default='included_in_profile')
save(c,'duty_cycle_scenarios.csv')

vehicle=t.groupby('vehicle_id').agg(track_count=('track_id','size'),recorded_distance_km=('distance_km','sum'),strict_valid_tracks=('strict_valid','sum'),first_start_utc=('start_utc','min'),last_stop_utc=('stop_utc','max')).reset_index().merge(fleet,on='vehicle_id',validate='one_to_one')
vehicle['observed_days']=vehicle.vehicle_id.map(daily.groupby('vehicle_id').size())
vehicle['scenario_vehicle_type']='hypothetical BEV replacement; source fuel type not assigned here'
save(vehicle,'vehicles.csv')
fs=vehicle.groupby('fleet_test_id').agg(vehicles=('vehicle_id','size'),tracks=('track_count','sum'),distance_km=('recorded_distance_km','sum'),observed_vehicle_days=('observed_days','sum')).reset_index()
fs['sample_mean_km_per_observed_day']=fs.distance_km/fs.observed_vehicle_days
save(fs,'fleet_summary.csv')

# Six explicitly hypothetical energy / AC-power combinations. No parameter is
# represented as measured vehicle specification.
sens=[]
for e in [0.9,1.2,1.5]:
    for power in [150.,350.]:
        cc=c.loc[c.scenario_eligible]
        demand=cc.distance_km*e
        fitbattery=demand<=P['battery_nominal_kwh']*(P['soc_high']-P['soc_low'])
        fitwindow=demand/P['efficiency']<=power*cc.window_h
        sens.append(dict(energy_kwh_per_km=e,charger_ac_kw=power,eligible_cycles=len(cc),battery_feasible_cycles=int(fitbattery.sum()),window_feasible_cycles=int(fitwindow.sum()),both_feasible_cycles=int((fitbattery&fitwindow).sum()),energy_grid_mwh=float((demand/P['efficiency']).sum()/1000),evidence_class='ASSUMED_SCENARIO'))
sens=pd.DataFrame(sens); save(sens,'sensitivity_summary.csv')

# Full-sample 15-min charging profiles. Power is AC grid-side kW. Each cycle is
# an independent replacement-energy request. No charger count / grid / queue
# constraints or inter-cycle state-of-charge recursion are imposed.
sel=c.loc[c.baseline_profile_eligible].copy()
start=t.start_utc.min().floor('15min'); end=t.stop_utc.max().ceil('15min')+pd.Timedelta(days=2)
index=pd.date_range(start,end,freq='15min',inclusive='left')
arrays={f:np.zeros((len(index),2)) for f in sorted(fleet.fleet_test_id.unique())}
origin=start.timestamp(); slot=900.
def add_event(arr,a,b,power,col):
    a=a.timestamp(); b=b.timestamp()
    left=max(0,int(math.floor((a-origin)/slot)))
    right=min(len(arr),int(math.ceil((b-origin)/slot)))
    for j in range(left,right):
        seconds=max(0.,min(b,origin+(j+1)*slot)-max(a,origin+j*slot))
        arr[j,col]+=power*seconds/slot
for r in sel.itertuples():
    immediate_end=r.arrival_utc+pd.Timedelta(hours=r.energy_grid_kwh/P['charger_ac_kw'])
    add_event(arrays[r.fleet_test_id],r.arrival_utc,immediate_end,P['charger_ac_kw'],0)
    add_event(arrays[r.fleet_test_id],r.arrival_utc,r.next_departure_utc,r.energy_grid_kwh/r.window_h,1)
profiles=[]
for fid,arr in arrays.items():
    profiles.append(pd.DataFrame(dict(time_utc=index,fleet_test_id=fid,p_immediate_kw=arr[:,0],p_uniform_kw=arr[:,1])))
profiles=pd.concat(profiles,ignore_index=True)
profiles['evidence_class']='SIMULATED_INDEPENDENT_ENERGY_REPLENISHMENT'
save(profiles,'charging_profiles_15min.csv')
total=profiles.groupby('time_utc')[['p_immediate_kw','p_uniform_kw']].sum()
sel['arrival_local_date']=sel.arrival_utc.dt.tz_convert(TZ).dt.strftime('%Y-%m-%d')
dc=sel.groupby('arrival_local_date').agg(vehicles=('vehicle_id','nunique'),events=('cycle_id','size'))
dc=dc.reset_index().sort_values(['vehicles','events','arrival_local_date'],ascending=[False,False,True]).set_index('arrival_local_date')
demo_date=dc.index[0]
demo_start=pd.Timestamp(demo_date,tz=TZ).tz_convert('UTC')
demo=total[(total.index>=demo_start)&(total.index<demo_start+pd.Timedelta(days=1))].reset_index()
demo['time_local']=demo.time_utc.dt.tz_convert(TZ).dt.strftime('%H:%M')
save(demo,'demo_charging_day.csv')

G=ROOT/'raw/simbench/csv'
grids={name:pd.read_csv(G/f'{name}.csv',sep=';') for name in ['Node','Line','LineType','Transformer','TransformerType','Load','RES','Switch','ExternalNet','LoadProfile','RESProfile']}
for name in ['Node','Line','LineType','Transformer','TransformerType','Load','RES','Switch','ExternalNet']:
    save(grids[name],f'grid_{name.lower()}.csv')
lp=grids['LoadProfile']; rp=grids['RESProfile']; loads=grids['Load']; res=grids['RES']
base=np.zeros(len(lp)); reactive=np.zeros(len(lp)); generation=np.zeros(len(lp))
for row in loads.itertuples():
    base+=row.pLoad*lp[row.profile+'_pload'].to_numpy()
    reactive+=row.qLoad*lp[row.profile+'_qload'].to_numpy()
for row in res.itertuples():
    generation+=row.pRES*rp[row.profile].to_numpy()
bg=pd.DataFrame(dict(profile_time=pd.to_datetime(lp.time,dayfirst=True).dt.strftime('%Y-%m-%d %H:%M'),gross_load_mw=base,reactive_load_mvar=reactive,res_generation_mw=generation,net_demand_before_losses_mw=base-generation))
bg['evidence_class']='SIMBENCH_BENCHMARK_PROFILE_NOT_FLEET_SITE_MEASUREMENT'
save(bg,'grid_background_15min.csv')
# Hypothetical node candidates, distributed by deterministic quantiles over
# sorted existing MV load buses. This is not a geographic match or final siting.
nodes=sorted(loads.node.unique())
positions=np.linspace(0,len(nodes)-1,4).astype(int)
mapping=pd.DataFrame([dict(fleet_test_id=int(fid),hypothetical_depot_id=f'DEPOT_F{int(fid)}',grid_node=nodes[pos],mapping_rule='evenly spaced indices in lexicographically sorted unique MV load nodes',evidence_class='ASSUMED_NO_GEOGRAPHIC_LINK') for fid,pos in zip(sorted(fleet.fleet_test_id.unique()),positions)])
save(mapping,'scenario_depot_grid_mapping.csv')
# Illustration aligns by weekday and quarter-hour to first matching January
# weekday in 2016. No claim of concurrent grid / truck observation.
weekday=pd.Timestamp(demo_date).weekday()
grid_day=pd.Timestamp('2016-01-01')
while grid_day.weekday()!=weekday: grid_day+=pd.Timedelta(days=1)
bgtime=pd.to_datetime(bg.profile_time)
gb=bg[bgtime.dt.date==grid_day.date()].reset_index(drop=True)
combined=demo.copy()
assert len(combined)==96 and len(gb)==96
combined['grid_profile_time']=gb.profile_time
combined['background_net_mw']=gb.net_demand_before_losses_mw
combined['immediate_total_mw']=combined.background_net_mw+combined.p_immediate_kw/1000
combined['uniform_total_mw']=combined.background_net_mw+combined.p_uniform_kw/1000
combined['alignment_class']='SCENARIO_WEEKDAY_AND_CLOCK_ALIGNMENT_DIFFERENT_YEARS'
save(combined,'demo_grid_load_overlay.csv')

qc=[('raw_track_rows',len(t),'原始记录全部保留'),('raw_vehicles',len(fleet),'公开文件实际为53辆；关联论文描述54辆'),('raw_distance_missing',int(t.flag_missing_distance.sum()),'不将缺失里程填成0用于单段能耗'),('zero_distance_tracks',int(t.distance.eq(0).sum()),'保留，可能包含短暂或静止记录'),('speed_flag_tracks',int(t.flag_speed.sum()),'均速或里程/时长>130 km/h；研究者阈值'),('overlap_previous_tracks',int(t.overlap_previous.sum()),'同车当前记录早于前段结束'),('signal_quality_flag_tracks',int((t.flag_signal_ratio|t.flag_unknown_signal).sum()),'信号损失比例>20%、负值或正里程时缺失'),('strict_valid_tracks',int(t.strict_valid.sum()),'联合质量标记后的记录数'),('candidate_base_windows',int(t.base_window_candidate.sum()),'15分钟至48小时、基地端点、双边空间缺口≤500m'),('derived_cycles_ge_1km',len(c),'相邻基地端点之间的记录里程≥1km'),('quality_eligible_cycles',int(c.scenario_eligible.sum()),'周期连续性与停靠窗口均通过'),('baseline_profile_cycles',len(sel),'再通过400kWh可用电量及150kW窗口检查'),('baseline_profile_vehicles',int(sel.vehicle_id.nunique()),'只表示参与示例的车辆数'),('grid_nodes',len(grids['Node']),'含开关辅助节点；不等于440个独立负荷点'),('grid_loads',len(loads),'SimBench负荷元素'),('grid_lines',len(grids['Line']),'SimBench线路元素'),('grid_transformers',len(grids['Transformer']),'110/10kV，额定值见原表'),('grid_profile_rows',len(lp),'2016年366天×96个15分钟时段')]
qc=pd.DataFrame(qc,columns=['metric','value','interpretation_zh']); save(qc,'quality_audit.csv')

# Meaningful internal consistency checks, not tests mirroring low-impact edits.
checks=[]
def check(name,value):
    checks.append(dict(check=name,pass_=bool(value)))
    if not value: raise AssertionError(name)
check('track_unique_key',t.track_id.is_unique)
check('all_vehicle_foreign_keys',t.vehicle_id.isin(fleet.vehicle_id).all())
check('retained_raw_count',len(t)==len(raw))
check('daily_distance_reconciles',np.isclose(daily.recorded_distance_km.sum(),t.distance_km.sum()))
check('profile_immediate_energy_conservation',np.isclose(total.p_immediate_kw.sum()*0.25,sel.energy_grid_kwh.sum(),rtol=1e-9))
check('profile_uniform_energy_conservation',np.isclose(total.p_uniform_kw.sum()*0.25,sel.energy_grid_kwh.sum(),rtol=1e-9))
check('mapping_nodes_exist',mapping.grid_node.isin(grids['Node'].id).all())
check('line_endpoints_exist',grids['Line'].nodeA.isin(grids['Node'].id).all() and grids['Line'].nodeB.isin(grids['Node'].id).all())
check('load_profile_complete',len(lp)==366*96 and not lp.isna().any().any())
save(pd.DataFrame(checks),'validation_checks.csv')

valid_days=daily[daily.flagged_tracks.eq(0)&daily.recorded_distance_km.ge(1)]
bins=[0,100,200,300,400,600,float('inf')]
hist=pd.cut(valid_days.recorded_distance_km,bins,right=False).value_counts(sort=False)
histrows=[dict(distance_bin=x,observed_vehicle_days=int(y)) for x,y in zip(['1–<100','100–<200','200–<300','300–<400','400–<600','≥600'],hist)]
save(pd.DataFrame(histrows),'distance_histogram.csv')
summary=dict(country='Germany',created_utc=pd.Timestamp.now(tz='UTC').isoformat(),raw_vehicles=len(fleet),raw_tracks=len(t),fleets=len(fs),raw_distance_km=float(t.distance_km.sum()),first_record=str(t.start_utc.min()),last_record=str(t.stop_utc.max()),observed_vehicle_days=len(daily),quality_eligible_cycles=int(c.scenario_eligible.sum()),quality_eligible_distance_km=float(c.loc[c.scenario_eligible,'distance_km'].sum()),quality_eligible_grid_energy_mwh=float(c.loc[c.scenario_eligible,'energy_grid_kwh'].sum()/1000),baseline_profile_cycles=len(sel),baseline_profile_vehicles=int(sel.vehicle_id.nunique()),baseline_grid_energy_mwh=float(sel.energy_grid_kwh.sum()/1000),baseline_profile_energy_coverage=float(sel.energy_grid_kwh.sum()/c.loc[c.scenario_eligible,'energy_grid_kwh'].sum()),demo_date=demo_date,demo_vehicle_count=int(dc.iloc[0].vehicles),demo_event_count=int(dc.iloc[0].events),demo_immediate_peak_kw=float(demo.p_immediate_kw.max()),demo_uniform_peak_kw=float(demo.p_uniform_kw.max()),grid_model='1-MV-urban--0-sw',grid_profile_demo_date=str(grid_day.date()),grid_counts={k:len(v) for k,v in grids.items()},parameters=P,validation_checks=checks)
(ROOT/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
