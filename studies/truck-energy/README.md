# How much driving energy changes the charger decision · 行驶能耗与接口选型

Two trucks wait 45 minutes to connect at the warehouse. With the UM reference demand of 20 kWh per leg, three port connectors and one warehouse connector minimize investment. How sensitive is that choice to simulated freight energy demand?

## Upstream simulation and transfer

Use the [published driving-leg energy file](https://github.com/TUMFTM/truck_fleet_electrification/blob/2763d5aa04365958b54ec014c8b4cf47ea1a75fd/output/csvs/tracks_with_energy.csv) and [payload/auxiliary-load sensitivity cell](https://github.com/TUMFTM/truck_fleet_electrification/blob/2763d5aa04365958b54ec014c8b4cf47ea1a75fd/main_energy_sim.ipynb) of Paper et al., *Assessing battery electric truck feasibility in heavy-duty logistics fleets*. Their GPS-based operational data and BETOS simulations share a data lineage with the [DT-CARGO release](https://doi.org/10.5281/zenodo.16411298). The upstream sensitivity CSV gives shares of energy by charging location. The actual trip energy and duration columns supply the inputs used here.

Of 42,701 distinct published track IDs, 27,054 have a nonmissing `energy_consumption_kwh` for 150 trucks. We use this original simulation field with `duration_h` and `distance_km`. We exclude 15,647 rows where the original energy is missing, even though their upstream cleaned field has a value. All included distances and durations are positive. Signed net energy is retained, including eight nonpositive trips. The included tracks span 1,604,920 km and 31,355.56 hours. Missing energy can affect the composition of this sample.

For a payload multiplier f (0.8, 1.0 or 1.2 relative to 19.3 t) and auxiliary load a (3, 5 or 7 kW), compute the fleet ratio

```text
ratio = (f × sum(trip net kWh) + a × sum(trip hours))
      / (    sum(trip net kWh) + 5 × sum(trip hours))
UM leg energy = 20 kWh × ratio.
```

This is also the ratio of two distance-weighted fleet intensities on identical tracks; the distance denominator cancels. It follows the upstream additive auxiliary-power formula. The 19.3 t / 5 kW case reproduces the 20 kWh UM leg exactly. We transfer one factor to all six legs and retain the synthetic port timetable, 100/75 kW site capacities, plug access, prices and equipment menu. German simulated energy variation provides scenario inputs. No actual port payload, plug-in time, electricity-market price or probability is inferred.

## Investment with 45-minute plug-in delay

| Payload (t) | Aux (kW) | UM kWh/leg | Optimal port / warehouse connectors | Paid upgrade | Investment |
|---:|---:|---:|---|---|---:|
| 15.44 | 3 | 15.68 | 2 / 1 | none | 20 |
| 15.44 | 5 | 16.32 | 2 / 1 | none | 20 |
| 15.44 | 7 | 16.95 | 3 / 1 | none | 40 |
| 19.30 | 3 | 19.36 | 3 / 1 | none | 40 |
| 19.30 | 5 | 20.00 | 3 / 1 | none | 40 |
| 19.30 | 7 | 20.64 | 2 / 2 | none | 50 |
| 23.16 | 3 | 23.05 | 3 / 2 | port +50 kW | 105 |
| 23.16 | 5 | 23.68 | 3 / 2 | port +50 kW | 105 |
| 23.16 | 7 | 24.32 | 3 / 2 | port +50 kW | 105 |

费用为每个四小时合成周期的投资单位。两地原有接口各一把，新增港区接口费用 20，新增仓库接口费用 30，港区增加 50 kW 费用 35。每个情景都重新联合选型，并将 54 个可选设施组合逐一固定后检查调度与费用。九次联合求解均与枚举一致，各自只有一组最低成本设备。在等候 45 分钟、仓库单接口时，V3 最多从仓库购入 e/0.9 kWh，晚放行的两辆车共用最后 15 分钟，最多再取 12.5 kWh。全队要补回 6e/0.9 kWh，故返港后一小时至少还要购入 5e/0.9 − 12.5 kWh。当单程耗电从 20.00 增至 20.64 kWh，这个下界从 98.61 增至 102.15 kWh，超过原来港区 100 kW 的供电能力。改为两地各两把接口，是后一个情景中费用最低的配置。

## Run

Install the existing UM MILP environment. Download the pinned input to a folder outside the repository. The script verifies its SHA-256 before use. See the [upstream project](https://github.com/TUMFTM/truck_fleet_electrification/tree/2763d5aa04365958b54ec014c8b4cf47ea1a75fd) and [DT-CARGO v2 data record](https://zenodo.org/records/16411298) for attribution and database terms. The DT-CARGO v2 deposit is labeled ODbL 1.0. The energy field comes from the separate published BETOS simulation output. The raw file is kept outside this repository.

```powershell
$csv = Join-Path $env:TEMP 'tum-tracks-with-energy-2763d5a.csv'
Invoke-WebRequest 'https://raw.githubusercontent.com/TUMFTM/truck_fleet_electrification/2763d5aa04365958b54ec014c8b4cf47ea1a75fd/output/csvs/tracks_with_energy.csv' -OutFile $csv
python studies/truck-energy/run.py $csv
python -m unittest discover -s studies/truck-energy -p test_transfer.py
```

Use `--evidence PATH` to record each joint solution, all fixed-hardware operating solutions, their inputs and independent schedule checks in a fresh directory of the existing offline Git archive. Compare [metrics.json](metrics.json) for fleet coverage, electricity cost, hardware ties and feasible configuration counts.
