"""Verify delivered CSV data and optional file_manifest.csv. Read-only."""
from pathlib import Path
import json, hashlib
import pandas as pd
import numpy as np

H=Path(__file__).resolve().parent
R=H if (H/'raw').exists() else H/'Germany_Truck_Grid_Dataset_v1'
P=R/'processed'
for item in json.loads((R/'source_manifest.json').read_text()):
    f=R/item['path']
    assert hashlib.sha256(f.read_bytes()).hexdigest()==item['sha256'], item['path']
    assert f.stat().st_size==item['bytes'], item['path']
if (R/'file_manifest.csv').exists():
    for item in pd.read_csv(R/'file_manifest.csv').itertuples():
        f=R/item.path
        assert f.exists() and hashlib.sha256(f.read_bytes()).hexdigest()==item.sha256,item.path

t=pd.read_csv(P/'tracks_with_quality.csv')
raw=pd.read_csv(R/'raw/dt_cargo/tracks.csv')
v=pd.read_csv(P/'vehicles.csv')
c=pd.read_csv(P/'duty_cycle_scenarios.csv')
days=pd.read_csv(P/'vehicle_days.csv')
profiles=pd.read_csv(P/'charging_profiles_15min.csv')
assert len(t)==len(raw) and t.track_id.is_unique
assert t.vehicle_id.isin(v.vehicle_id).all()
assert c.cycle_id.is_unique
assert c.first_track_id.isin(t.track_id).all() and c.last_track_id.isin(t.track_id).all()
assert np.isclose(days.recorded_distance_km.sum(),t.distance_km.sum())
need=c.loc[c.baseline_profile_eligible,'energy_grid_kwh'].sum()
for col in ['p_immediate_kw','p_uniform_kw']:
    assert profiles[col].ge(0).all()
    assert np.isclose(profiles[col].sum()*0.25,need,rtol=1e-7)
assert not profiles.duplicated(['time_utc','fleet_test_id']).any()
n=pd.read_csv(P/'grid_node.csv')
line=pd.read_csv(P/'grid_line.csv')
mapping=pd.read_csv(P/'scenario_depot_grid_mapping.csv')
assert n.id.is_unique and line.nodeA.isin(n.id).all() and line.nodeB.isin(n.id).all()
assert mapping.grid_node.isin(n.id).all()
assert pd.read_csv(P/'validation_checks.csv').pass_.all()
print(json.dumps({'verified':True,'vehicles':len(v),'tracks':len(t),'cycles':len(c),
                  'quality_eligible_cycles':int(c.scenario_eligible.sum()),
                  'profile_cycles':int(c.baseline_profile_eligible.sum()),
                  'profile_energy_kwh':float(need)},ensure_ascii=False,indent=2))
