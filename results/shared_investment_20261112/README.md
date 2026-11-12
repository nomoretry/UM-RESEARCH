# One build across several service conditions

Choose hardware from the existing 54 combinations. One connector at each site and grid connections of 100 kW at PORT and 75 kW at WAREHOUSE are sunk. Report the synthetic cycle-equivalent cost of additions. A build must admit a separate schedule for **every** designated service condition. All six trip legs and the 100 kWh initial and final battery levels stay fixed. The planner knows the service set when investing. Dispatch knows the actual leg consumption, V1/V2 warehouse release and connector turnaround for its entire cycle. V3 keeps its original warehouse window. No probability or electricity bill enters this objective.

For service set S and feasible-build sets F(s), minimize the menu cost over the intersection of F(s) for s in S. The executable enumerates hardware and decomposes the dispatch MILP by service. See [model and runner](../../src/um_charging/shared_investment.py), [fixed-build dispatch](../../src/um_charging/changeover.py), [independent event/SOC replay](../../src/um_charging/changeover_check.py) and [selected results and two witness schedules](metrics.json).

## Synthetic service ranges and optimal investment

Each cell gives the cost of one build covering **both the indicated corner and all easier tested conditions**. The high-energy panel includes low energy. Each column is the maximum turnaround in minutes. A 60-minute release delay removes V1/V2 warehouse eligibility during their stop. Both vehicles still complete both trips.

| Maximum leg kWh | Maximum release delay (min) | 0 | 2 | 5 | 10 |
|---|---:|---:|---:|---:|---:|
| 20 | 0, 15, or 30 | 20 | 20 | 40 | 40 |
| 20 | 45 | 40 | 40 | 40 | 40 |
| 20 | 60 | 75 | 75 | 75 | 75 |
| 20.636628905957647 | 0, 15, or 30 | 20 | 20 | 40 | 40 |
| 20.636628905957647 | 45 | 50 | 50 | 70 | 70 |
| 20.636628905957647 | 60 | 75 | 75 | 75 | 75 |

| Investment | PORT plugs / kW | WAREHOUSE plugs / kW | Feasible primary conditions out of 40 |
|---:|---:|---:|---:|
| 20 | 2 / 100 | 1 / 75 | 12 |
| 40 | 3 / 100 | 1 / 75 | 28 |
| 50 | 2 / 100 | 2 / 75 | 26 |
| 60 | 2 / 100 | 2 / 100 | 27 |
| 70 | 3 / 100 | 2 / 75 | 32 |
| 75 | 3 / 150 | 1 / 75 | 40 |

All menus were examined through ties. Each tabulated optimum had one winning equipment combination. Multiple charging schedules can serve the same build. Service counts are unweighted counts over this design grid.

At 45 minutes release delay, covering (20 kWh, 10 minutes turnaround) alone costs 40 and covering (20.636628905957647 kWh, 2 minutes) alone costs 50. Covering **those two services together costs 70**. The first single-service build has insufficient warehouse access at the higher consumption. The second cannot turn plugs around quickly enough in the lower-consumption, longer-turnaround service. Reserving only the larger of the two amounts misses the joint requirement by 20.

## Which additions change the outcome?

* **Warehouse connection, investment 50 → 60.** For high energy E and 45-minute delayed release, a single warehouse plug supplies at most E/0.9 kWh to V3 (first-trip battery headroom) plus 12.5 kWh to one late truck. At least 5E/0.9 − 12.5 = 102.14794 kWh must then enter at the port in one hour. This exceeds 100 kWh even with a third port plug at the same connection. Two port plugs also limit power to 100 kW at 50 kW per truck, even if the grid connection expands. With two plugs at each site and 75 kW at the warehouse, the published threshold is 2.437979168 minutes. A 25 kW warehouse upgrade costs 10 and covers the archived 2.447979168 and 4.968989584 minute anchors. It supplies up to 100 kW during the two late trucks' shared 15-minute warehouse slot. At 4.978989584 minutes the least-cost build changes to three port plugs and two warehouse plugs with base power. The two anchors on either side of this last jump are 0.01 minute apart. The output includes a feasible physical assignment and the list of the 12 strictly cheaper menu configurations excluded at the first anchor.
* **Port plugs and connection, investment 70 → 75 when expanding the service set.** At 60-minute release delay only V3 can charge at the warehouse, up to E/0.9 kWh. The port needs at least 5E/0.9 = 114.64794 kWh during its one-hour window at high energy. Every build with at most two port plugs or a 100 kW port connection fails this bound. The minimum menu solution adds two port plugs and 50 kW to the original plant. A simple witness leaves the warehouse idle and dedicates a port plug to each truck at 2E/0.9 = 45.85918 kW for the full return hour. Total power is 137.57753 kW. All three finish at 100 kWh without a connector change. The five-unit difference compares independent greenfield choices from the same installed base; a warehouse plug built for the smaller service range cannot be sold back.

## Evidence and repeat command

The primary grid has 40 conditions. The three additional high-energy/45-minute release runs retain earlier threshold anchors. The archive-assisted run loaded 102 prior changeover results and made 884 new HiGHS feasibility solves. It checked 54 × 43 facility/service pairs, independently replaying all 1,126 feasible schedules. Feasible MILPs use zero objective and bound. Infeasibility uses solver status or a dominance bound from a proved infeasible condition. The full fixed-menu search supplies the investment lower bound. Input hashes, ties, maximal service points by build and corner witnesses appear in the JSON.

For equal-scope, equal-build comparison, the runner checks every accepted plan against its own trip and power limits. A schedule at higher energy can be transferred to lower energy by scaling delivered battery energy with the leg-energy ratio, preserving the fixed final target. Earlier release opens extra slots. After lowering turnaround the runner retains the occupied plug-slots and reassigns the same or reduced energy at a constant setpoint over each permitted slot suffix. Each transformed plug's maximum power is bounded by its original end-of-slot power, when all charging plugs could be active simultaneously. Added plugs or capacity can be unused. These properties are specific to this constant-capacity, full-initial-battery, proportional-duty example.

From the repository root with the project's SciPy environment active:

```powershell
$env:PYTHONPATH = 'src'
python -m um_charging.shared_investment
```

Expect a shared cost of 70 for the two incomparable conditions and 75 for the largest service range. The public command uses the published evidence and recomputes other statuses. An optional `--previous` can reuse the complete pre-existing changeover dispatch archive. An optional `--output` stores per-pair evidence in a fresh directory inside the separate no-remote records Git.
