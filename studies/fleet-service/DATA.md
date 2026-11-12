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

## Source, attribution and reproduction

The sole trip input is the published TUMFTM export at commit `2763d5aa04365958b54ec014c8b4cf47ea1a75fd`, SHA-256 `d92ab77cafe21c1aad3e9be8de1e26b453846a677f91b07ee0ac5f652ec8c50e`. Anna Paper, Georg Balke, Philip Rosborough, Marcel Brödel, Niclas Klein, Tom Winkler and Markus Lienkamp provide the upstream analysis. Copyright © 2025–2026 Anna Paper and contributors. Their repository cites the underlying DT-CARGO v2 release by Georg Balke, Lennart Adenaw and Anna Paper. The local older DT-CARGO copy and flex-depot Fleet 3 add zero independent cohorts. [Pinned project and citation](https://github.com/TUMFTM/truck_fleet_electrification/tree/2763d5aa04365958b54ec014c8b4cf47ea1a75fd) · [DT-CARGO v2](https://doi.org/10.5281/zenodo.16411298) · [DT-CARGO field definitions](https://github.com/TUMFTM/dt-cargo#trackscsv)

This modified database excerpt, including the derived stops and split, is made available under ODbL 1.0. The DT-CARGO authors specify DbCL 1.0 for individual contents. The upstream TUM electrification repository also declares Apache 2.0, reproduced alongside the excerpt. [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) · [DbCL 1.0](https://opendatacommons.org/licenses/dbcl/1-0/) · [Upstream license](LICENSE-TUM.txt)

The committed duties can be used directly. To regenerate and audit them, run from the research repository root in PowerShell, with the project's Python environment active and an existing local cache directory. The commands below write the comparison file to the cache.

```powershell
$cache = 'D:\UM_Project\tmp'
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
