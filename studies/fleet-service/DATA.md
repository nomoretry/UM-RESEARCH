# German fleet duties for the UM two-site study

[duties.json](duties.json) contains 101 recorded trips across 21 vehicle-days and nine German service dates. The earliest six dates are for facility design. The last three measure service on later dates for the same three vehicles of the same carrier. Keep the trips of all vehicles on a date together when checking shared interfaces and grid capacity.

## From recording to model inputs

| Quantity | Meaning in this case |
|---|---|
| `track_id`, `vehicle_id`, `start_time`, `stop_time` | Anonymized source records. Times retain the source precision and offset. The service day runs between consecutive Berlin midnights. |
| `energy_consumption_kwh` | Per-trip battery energy from TUM's BETOS simulation, in kWh. No metered charging or driving energy is available here. UM retains the original numeric values. |
| `home_base`, `industrial_area` | TUM classifications for the previous trip's **end**. UM maps a home base to PORT, a non-home industrial endpoint to WAREHOUSE and every other endpoint to no charging. Multiple geographic endpoints can map to one modeled site. |
| Stop start/end | The upper bound is the interval between two consecutive recordings for the same vehicle. Its intersection with the calendar day is the model's stop interval. `arrival` and `next_departure` retain the original, unclipped timestamps. Missing adjacent recordings open zero additional time. |
| Plug availability | Site identity, continued presence, work release, plug-in and power delivery are scenario assumptions. Any release delay starts at the actual timestamp of the preceding track end, even if it falls before midnight. |

The input includes 59 PORT and 53 WAREHOUSE intervals and nine additional unmapped intervals. Counts are clipped vehicle-day intervals, so one overnight parking gap can contribute on two dates. All three vehicles have overlapping warehouse upper bounds on September 22. One mapped interval has a distance of at least 1 km between recorded tracks. On September 17, vehicle 3's records 4423 and 4425 are 45 min 12.192 s apart, with a source `track_gap` of 54,849.99581314 m. Assigning that entire gap to warehouse availability is especially optimistic. Track gaps are distances in metres. Stop durations here are differences between timestamps.

## Cohort and chronological split

Before optimizing, select the carrier with the lowest numeric `freight_forwarder` and its five lowest numeric vehicle IDs. Process all of their recordings. For a vehicle-date touched by any recorded trip, exclude the whole vehicle-day on the first applicable condition below.

1. A trip crosses local midnight, affecting both dates. This avoids inventing an energy allocation across midnight.
2. The day has 23 or 25 hours.
3. A trip duration is nonpositive or trips overlap.
4. An original trip energy is missing or nonfinite. The source's separate cleaned/imputed energy column remains unused.

Of the export's 42,701 trips, 6,888 belong to carrier 1 and 1,904 to vehicles 1–5. Of 446 observed vehicle-dates in that cohort, eight intersect a cross-midnight trip, one is a clock-change day, 217 lack original energy and 220 are complete. The first nine of 79 dates with at least two complete vehicles give the following sample. The other 199 complete vehicle-dates lie outside the nine selected dates. Thirteen additional observed but incomplete vehicle-days on the selected dates are listed in the JSON. An unobserved day contributes no transport task. Feasibility, prices and facility choices play no part in selection.

| Split | September 2021 dates | Vehicle IDs present | Vehicle-days | Trips |
|---|---|---|---:|---:|
| Design | 13, 14, 15, 16, 17, 20 | 3, 4, 5 | 13 | 56 |
| Holdout | 21, 22, 23 | 3, 4, 5 | 8 | 45 |

Total simulated battery energy is 3,254.041040 kWh. Missing-energy selection and a single carrier limit generalization. All retained trips model the published *recordings* of that vehicle on that day. The source does not certify complete freight service or measure charging access between recordings.

## Six later operating weeks for the second port connector

[operating_weeks.json](operating_weeks.json) contains the first six complete Monday–Sunday periods after the original holdout ended on 23 September 2021. The intervening partial week is outside the comparison. Selection used calendar dates and the original vehicle-day quality rules before facility dispatch or pricing. Each date with complete trips enters the service experiment, including dates with only one eligible vehicle. A date with missing or unusable duties stays in the calendar denominator. Its financial return is unknown. Operators evaluating these weeks can reproduce the supplied subset with [prepare_weeks.py](prepare_weeks.py).

| Berlin week starting | Complete vehicle-days | Quality exclusions | Vehicle-dates with no trip records | Trips used |
|---|---:|---:|---:|---:|
| 27 Sep 2021 | 12 | 8 | 15 | 62 |
| 4 Oct | 13 | 10 | 12 | 59 |
| 11 Oct | 12 | 11 | 12 | 50 |
| 18 Oct | 14 | 6 | 15 | 73 |
| 25 Oct | 16 | 9 | 10 | 80 |
| 1 Nov | 6 | 12 | 17 | 31 |
| Total | 73 | 56 | 81 | 355 |

Thirty of the 42 dates contain at least one complete vehicle-day. Four contain records but only excluded vehicle-days. Eight contain no trip records from any of the five cohort vehicles. The 56 quality exclusions comprise 51 missing original simulated energy, four vehicle-dates touched by cross-midnight trips and one 25-hour clock-change date. All 355 transport track IDs are distinct from the 101 original design/holdout trips. This tests subsequent service in the same carrier. All five cohort vehicles appear, including IDs 1 and 2, which contributed no complete duty to the nine original dates.

The chronology yields 194 port-mapped, 172 warehouse-mapped and 62 unmapped stop intervals. Two source discontinuities span at least 1 km between adjacent tracks assigned to a charging site. Vehicle 5's 11.795 km gap between tracks 8843 and 8849 is clipped on both 12 and 13 October. Vehicle 2's 15.075 km gap between 2995 and 2997 affects 29 October. All three clipped intervals map to PORT. Their endpoints establish time bounds; occupancy, location throughout the interval, plug-in and power delivery remain unknown.

Source and redistribution terms are the same as for the nine-date input below. After obtaining the pinned source CSV, run the following in PowerShell from the repository root, using an unused output filename in the local cache.

```powershell
python studies/fleet-service/prepare_weeks.py $src --output (Join-Path $cache 'um-operating-weeks.json')
(Get-FileHash (Join-Path $cache 'um-operating-weeks.json') -Algorithm SHA256).Hash
$env:UM_TUM_TRACKS = $src
python -m pytest -q -p no:cacheprovider studies/fleet-service/test_prepare_weeks.py
```

The UTF-8 JSON SHA-256 is `901b0dcf25f3af092c3400bd4982498d9a0b026e56495d365f5c78be6abd2c07`. The source audit independently checks the classification of all 210 vehicle-date slots, every retained trip and every adjacent stop bound.

## Six holdout weeks for the fixed M8 facilities

[holdout_weeks.json](holdout_weeks.json) takes the first six complete Berlin Monday–Sunday weeks after the M8 period ended on 7 November 2021. It keeps carrier 1, vehicles 1–5, the original trip energies and the vehicle-day quality rules above. Selection uses calendar dates and source quality alone. All 42 dates and all 210 vehicle-date slots remain in the denominator. The 28 dates with transport tasks include six with only one complete vehicle-day. A further ten dates contain excluded records only, and four have no trip records for these vehicles.

| Week starting (2021) | Complete vehicle-days | Missing or nonfinite energy | Cross-midnight | No trip record | Trips | PORT stops | WAREHOUSE stops | Unmapped stops |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 Nov | 9 | 16 | 2 | 8 | 40 | 23 | 20 | 6 |
| 15 Nov | 16 | 10 | 0 | 9 | 66 | 35 | 37 | 10 |
| 22 Nov | 13 | 9 | 0 | 13 | 53 | 21 | 20 | 25 |
| 29 Nov | 8 | 10 | 2 | 15 | 35 | 29 | 10 | 4 |
| 6 Dec | 8 | 13 | 0 | 14 | 36 | 24 | 15 | 5 |
| 13 Dec | 9 | 12 | 0 | 14 | 52 | 28 | 26 | 7 |
| **Total** | **63** | **70** | **4** | **73** | **282** | **160** | **128** | **57** |

The other quality rules exclude zero vehicle-days in this period. All 282 retained trip IDs are distinct, with zero overlap against the 101 trips in the original nine days and the 355 trips in M8. The pinned source has 220 complete vehicle-days for vehicles 1–5 across the full recording. Of these, 21 occur in the original nine days and 73 in M8, leaving 126 including this holdout.

There are 24 day-clipped intervals with a recorded distance of at least 1 km between neighboring tracks, spanning 21 distinct track pairs. The 20 mapped intervals all belong to vehicle 5. The largest mapped discontinuity is 10.516 km at the port on 7 December. The largest unmapped discontinuity is 226.095 km for vehicle 1 on 15 November. The elapsed time between the two recordings bounds parking time. Remaining at a modeled site and having access to a plug are assumptions. The two lists under `parking_bounds` identify every affected date, vehicle, track pair, mapping and distance in metres. [Interval records](holdout_weeks.json)

<details>
<summary>Track pairs at least 1 km apart</summary>

| Affected Berlin dates | Vehicle | Mapping | Arrival → next track | Gap (km) |
|---|---:|---|---|---:|
| 2021-11-15 | 1 | Unmapped | 594 → 598 | 226.095 |
| 2021-11-15 | 5 | WAREHOUSE | 9625 → 9627 | 4.572 |
| 2021-11-16 | 5 | WAREHOUSE | 9642 → 9644 | 1.070 |
| 2021-11-17 | 5 | Unmapped | 9653 → 9654 | 1.658 |
| 2021-11-17, 2021-11-18 | 5 | PORT | 9656 → 9658 | 5.650 |
| 2021-11-18 | 5 | WAREHOUSE | 9662 → 9667 | 5.460 |
| 2021-11-19 | 5 | PORT | 9678 → 9679 | 1.978 |
| 2021-11-19, 2021-11-22 | 5 | PORT | 9682 → 9705 | 8.309 |
| 2021-12-07 | 5 | PORT | 9844 → 9847 | 10.516 |
| 2021-12-07 | 5 | WAREHOUSE | 9849 → 9850 | 2.131 |
| 2021-12-07 | 5 | PORT | 9852 → 9853 | 1.703 |
| 2021-12-13 | 5 | WAREHOUSE | 9904 → 9905 | 1.991 |
| 2021-12-13 | 5 | Unmapped | 9905 → 9906 | 3.425 |
| 2021-12-13 | 5 | Unmapped | 9906 → 9907 | 6.734 |
| 2021-12-15 | 5 | PORT | 9919 → 9924 | 5.090 |
| 2021-12-15 | 5 | PORT | 9924 → 9926 | 1.905 |
| 2021-12-15, 2021-12-16 | 5 | PORT | 9930 → 9935 | 2.666 |
| 2021-12-16 | 5 | WAREHOUSE | 9936 → 9937 | 3.865 |
| 2021-12-16 | 5 | WAREHOUSE | 9937 → 9939 | 4.636 |
| 2021-12-16 | 5 | WAREHOUSE | 9939 → 9940 | 2.128 |
| 2021-12-16 | 5 | PORT | 9943 → 9947 | 7.430 |

</details>

The six weeks contain 1,008 native DE-LU day-ahead delivery hours from 8 November 00:00 through 20 December 00:00 (end exclusive), all in CET. SMARD series 4169 averages €206.16/MWh over the holdout, from €21.83 to €425.00. The M8 six weeks average €138.23/MWh, from −€2.02 to €442.90, across 1,009 hours including the October clock change. Compare invoices across facilities serving the same holdout duties under the same prices. Phase 2 preregisters weekly scheduling with all tasks and prices for that week known after the facilities are fixed. Phase 1 establishes the inputs only. [Hourly prices](../day-ahead/native_2021_holdout_prices.csv) · [SMARD URLs and raw file hashes](../day-ahead/native_2021_holdout_source.json)

The SHA-256 of the UTF-8 holdout duties is `6c4c4483961f957604b564ee7b1b423895d016526535e807d384be60cde69413`. The hourly CSV hashes to `28e3f8a242625ddd59338ec340e756d49c07d0d7ca8b6bbfb627906ee0c908dc`. From the repository root, an installation with the offline records can reproduce the duties, prices and source checks as follows.

```powershell
$records = (Get-Content -Raw -Encoding utf8 .um-records.local.json | ConvertFrom-Json).records_root
$runs = Join-Path $records 'conversations\0001_records\runs'
$env:UM_TUM_TRACKS = Join-Path $runs '20261112_fleet_inputs\tracks_with_energy.csv'
$env:UM_SMARD_HOLDOUT = Join-Path $runs '20261121_holdout_weeks\smard'
$rebuilt = Join-Path $env:TEMP ('um-holdout-' + [guid]::NewGuid().ToString('N') + '.json')
.\.venv\Scripts\python.exe studies/fleet-service/prepare_weeks.py $env:UM_TUM_TRACKS --after operating_weeks.json --output $rebuilt
Get-FileHash -LiteralPath $rebuilt
.\.venv\Scripts\python.exe studies/day-ahead/extract_native_2021.py $env:UM_SMARD_HOLDOUT --holdout
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider studies/fleet-service/test_prepare.py studies/fleet-service/test_prepare_weeks.py studies/day-ahead/test_native_2021_prices.py
```

## Source, attribution and reproduction

The sole trip input is the published TUMFTM export at commit `2763d5aa04365958b54ec014c8b4cf47ea1a75fd`, SHA-256 `d92ab77cafe21c1aad3e9be8de1e26b453846a677f91b07ee0ac5f652ec8c50e`. Anna Paper, Georg Balke, Philip Rosborough, Marcel Brödel, Niclas Klein, Tom Winkler and Markus Lienkamp provide the upstream analysis. Copyright © 2025–2026 Anna Paper and contributors. Their repository cites the underlying DT-CARGO v2 release by Georg Balke, Lennart Adenaw and Anna Paper. The local older DT-CARGO copy and flex-depot Fleet 3 add zero independent cohorts. [Pinned project and citation](https://github.com/TUMFTM/truck_fleet_electrification/tree/2763d5aa04365958b54ec014c8b4cf47ea1a75fd) · [DT-CARGO v2](https://doi.org/10.5281/zenodo.16411298) · [DT-CARGO field definitions](https://github.com/TUMFTM/dt-cargo#trackscsv)

This modified database excerpt, including the derived stops and split, is made available under ODbL 1.0. The DT-CARGO authors specify DbCL 1.0 for individual contents. The upstream TUM electrification repository also declares Apache 2.0, reproduced alongside the excerpt. [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) · [DbCL 1.0](https://opendatacommons.org/licenses/dbcl/1-0/) · [Upstream license](LICENSE-TUM.txt)

The committed duties can be used directly. To regenerate and audit them, run from the research repository root in PowerShell, with the project's Python environment active and an existing local cache directory. The commands below write the comparison file to the cache.

```powershell
$cache = [System.IO.Path]::GetTempPath()
$src = Join-Path $cache 'tracks_with_energy.csv'
if (!(Test-Path -LiteralPath $src)) {
    Invoke-WebRequest 'https://raw.githubusercontent.com/TUMFTM/truck_fleet_electrification/2763d5aa04365958b54ec014c8b4cf47ea1a75fd/output/csvs/tracks_with_energy.csv' -OutFile $src
}
$rebuilt = Join-Path $cache 'um-fleet-duties.json'
python studies/fleet-service/prepare.py $src --output $rebuilt
$env:UM_TUM_TRACKS = $src
python -m pytest -q -p no:cacheprovider studies/fleet-service/test_prepare.py
(Get-FileHash $rebuilt -Algorithm SHA256).Hash
```

Expected comparison hash is `634576e39fbcb031522a065a7f05e1c333e434800d81ae54e419a70b06d17e80` ignoring hex letter case. All four checks pass with the source file. The source-row check independently compares every trip, numeric energy, full trip sequence, paired recording, mapped site and clipped parking upper bound.
