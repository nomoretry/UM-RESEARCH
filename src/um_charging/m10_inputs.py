"""Build the twelve M10 planning weeks and their published main service, without optimization."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from zoneinfo import ZoneInfo

from . import energy_boundary as eb
from . import holdout_inputs as hi
from .__main__ import digest


M8_REGISTRATION = eb.WEEKS.with_name("energy_boundary.json")
M9_REGISTRATION = hi.WEEKS.with_name("holdout_test.json")


@dataclass
class PlanningInputs:
    periods: list
    main_reference: frozenset
    excluded_intervals: list
    source_sha256: dict

    @property
    def registered(self):
        """Only the main window rule has an established twelve-week registration."""
        return None if self.excluded_intervals else self.main_reference


def _prices(days, source):
    """Keep actual elapsed delivery hours, including both offsets on the autumn transition."""
    deliveries = defaultdict(list)
    for row in eb.csv_rows(source):
        deliveries[row["start_berlin"][:10]].append(row)
    curves = {}
    berlin = ZoneInfo("Europe/Berlin")
    for day in days:
        date = day["date"]
        rows = deliveries[date]
        start, end = [datetime.fromisoformat(day[k]).astimezone(timezone.utc) for k in ("start", "end")]
        count = (end - start) // timedelta(hours=1)
        expected = [(start + timedelta(hours=i)).astimezone(berlin).isoformat() for i in range(count)]
        if [row["start_berlin"] for row in rows] != expected:
            raise ValueError(f"Native hourly deliveries differ from the Berlin calendar on {date}")
        if count != 24 and day["vehicles"]:
            raise ValueError(f"The fleet minute model needs a 24-hour day for active duties on {date}")
        values = [float(row["eur_per_mwh"]) for row in rows]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"Nonfinite native price on {date}")
        curves[date] = values
    return curves


def load_inputs(sensitivity=False):
    """Build 12 independent boundary-B calendar weeks with the original input hashes."""
    main8, main9 = eb.read_json(M8_REGISTRATION), eb.read_json(M9_REGISTRATION)
    sources = (eb.WEEKS, eb.NATIVE, M8_REGISTRATION, hi.WEEKS, hi.PRICES, M9_REGISTRATION)
    hashes = {p.relative_to(eb.ROOT).as_posix(): digest(p) for p in sources}
    for path in (eb.WEEKS, eb.NATIVE, hi.WEEKS, hi.PRICES):
        name = path.relative_to(eb.ROOT).as_posix()
        expected = (main8["inputs_sha256"][name] if path in (eb.WEEKS, eb.NATIVE)
                    else main9["inputs_sha256"][path.name])
        if hashes[name] != expected:
            raise ValueError(f"Published study input has changed: {name}")
    m8, m9 = eb.read_json(eb.WEEKS), eb.read_json(hi.WEEKS)
    prices = {**_prices(m8["days"], eb.NATIVE), **_prices(m9["days"], hi.PRICES)}
    days = m8["days"] + m9["days"]
    dates = [d["date"] for d in days]
    first = datetime.fromisoformat("2021-09-27")
    if dates != [(first + timedelta(days=i)).date().isoformat() for i in range(84)]:
        raise ValueError("The fixed M8 and M9 inputs do not cover the consecutive twelve-week calendar")

    row, = [r for r in main8["full"] if (r["facility"], r["spec"], r["rule"]) == ("one", "S300", eb.B)]
    ref8 = {tuple(key) for key in row["selected"]}
    ref9 = {(r["date"], v) for r in main9["main"]["daily"] for v in r["registered"]}
    chains, links, _ = eb.calendar(days)
    excluded = []
    if sensitivity:
        field = "mapped_intervals_at_least_1km"
        excluded = m8["parking_bounds"][field] + m9["parking_bounds"][field]
        hi._exclude_mapped_intervals(days, excluded, expected_count=23, expected_vehicles={"2", "5"})
        if eb.calendar(days)[:2] != (chains, links):
            raise ValueError("Window exclusion changed continuous-day SOC links")
    weeks = eb.components(days, links)
    if len(weeks) != 12 or any(len(w) != 7 or len({d["week_start"] for d in w}) != 1 for w in weeks):
        raise ValueError("A carry-over chain crosses a weekly planning boundary")
    periods = [eb.Period(week, {d["date"]: prices[d["date"]] for d in week}) for week in weeks]
    for batch, registered, complete, served in ((periods[:6], ref8, 73, 54), (periods[6:], ref9, 63, 52)):
        keys = set.union(*(p.keys for p in batch))
        if len(keys) != complete or len(registered) != served or not registered <= keys:
            raise ValueError("Published service registration differs from the original cohort")
    return PlanningInputs(periods, frozenset(ref8 | ref9), excluded, hashes)


def input_summary():
    """Summarize input counts, the two registrations, and all eleven weekly cuts."""
    main, sensitive = load_inputs(), load_inputs(sensitivity=True)
    term = main.main_reference
    weeks, boundaries = [], []
    for p, q in zip(main.periods, sensitive.periods, strict=True):
        def windows(period):
            return sum(len(t["windows"]) for case in period.cases.values() for t in case["trucks"].values())
        weeks.append(dict(week=p.days[0]["week_start"], vehicle_days=len(p.keys), registered=len(p.keys & term),
                          native_price_hours=sum(map(len, p.prices.values())),
                          within_week_links=len(p.links), removed_released_windows=windows(p) - windows(q)))
    for p, q in zip(main.periods, main.periods[1:]):
        def side(period, day):
            date = day["date"]
            return dict(date=date, availability=day["availability"],
                        vehicle_ids=sorted(v for d, v in period.keys if d == date),
                        registered_ids=sorted(v for d, v in term if d == date))
        boundaries.append(dict(sunday=side(p, p.days[-1]), monday=side(q, q.days[0])))
    return dict(weeks=weeks, weekly_boundaries=boundaries,
                totals={key: sum(w[key] for w in weeks) for key in weeks[0] if key != "week"},
                excluded_day_intervals=len(sensitive.excluded_intervals),
                sensitivity_registered=sensitive.registered, source_sha256=main.source_sha256)


if __name__ == "__main__":
    print(json.dumps(input_summary(), indent=2, allow_nan=False))
