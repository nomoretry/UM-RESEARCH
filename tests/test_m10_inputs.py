from collections import Counter
from datetime import datetime, timedelta

from um_charging import m10_inputs as study


def test_twelve_weeks_reuse_each_published_registration_and_native_hour():
    plan = study.load_inputs()
    m8, m9 = [study.eb.read_json(path) for path in (study.M8_REGISTRATION, study.M9_REGISTRATION)]
    row, = [r for r in m8["full"] if r["spec"] == "S300" and r["facility"] == "one" and r["rule"] == "carry_over"]
    reference = {tuple(key) for key in row["selected"]}
    reference.update((day["date"], v) for day in m9["main"]["daily"] for v in day["registered"])
    assert plan.registered == plan.main_reference == reference and len(reference) == 106
    assert len(plan.periods) == 12
    assert [len(set.union(*(w.keys for w in batch))) for batch in (plan.periods[:6], plan.periods[6:])] == [73, 63]
    assert [len(w.keys & reference) for w in plan.periods[6:]] == [7, 13, 7, 8, 8, 9]
    for batch, path in ((plan.periods[:6], study.eb.NATIVE), (plan.periods[6:], study.hi.PRICES)):
        native = study.eb.csv_rows(path)
        for week in batch:
            for day in week.days:
                date = day["date"]
                rows = [r for r in native if r["start_berlin"][:10] == date]
                assert week.prices[date] == [float(r["eur_per_mwh"]) for r in rows]
                if date == "2021-10-31":
                    assert not day["vehicles"]
                    assert [r["start_berlin"] for r in rows if r["start_berlin"][11:13] == "02"] == [
                        "2021-10-31T02:00:00+02:00", "2021-10-31T02:00:00+01:00"]
    assert [sum(len(c) for w in batch for c in w.prices.values())
            for batch in (plan.periods[:6], plan.periods[6:])] == [1009, 1008]


def test_all_weekly_boundaries_and_original_holdout_transition():
    details = study.input_summary()
    assert details["totals"] == dict(vehicle_days=136, registered=106, native_price_hours=2017,
                                     within_week_links=71, removed_released_windows=18)
    boundaries = details["weekly_boundaries"]
    assert len(boundaries) == 11 and all(not b["sunday"]["registered_ids"] for b in boundaries)
    assert boundaries[5] == dict(
        sunday=dict(date="2021-11-07", availability="no_recorded_tasks", vehicle_ids=[], registered_ids=[]),
        monday=dict(date="2021-11-08", availability="complete_tasks", vehicle_ids=["1", "5"], registered_ids=["5"]))
    full_days = [d for p in study.load_inputs().periods for d in p.days]
    weeks = {d["date"]: d["week_start"] for d in full_days}
    _, links, _ = study.eb.calendar(full_days)
    assert len(links) == 71 and all(weeks[l["left"]] == weeks[l["right"]] for l in links)


def test_sensitive_inputs_drop_only_the_listed_released_windows():
    main, sensitive = study.load_inputs(), study.load_inputs(sensitivity=True)
    assert sensitive.registered is None and sensitive.main_reference == main.registered
    disabled = {(r["date"], r["vehicle_id"], r["site"], r["arrival_track_id"], r["next_track_id"])
                for r in sensitive.excluded_intervals}
    assert len(disabled) == 23
    seen = set()
    removed = []
    for p, q in zip(main.periods, sensitive.periods, strict=True):
        assert p.chains == q.chains and p.links == q.links and p.keys == q.keys and p.prices == q.prices
        n = 0
        for day in p.days:
            date = day["date"]
            for vehicle in day["vehicles"]:
                v = vehicle["vehicle_id"]
                a, b = [week.cases[date]["trucks"][v] for week in (p, q)]
                assert a["trips"] == b["trips"]
                expected = Counter()
                for stop in vehicle["stops"]:
                    key = date, v, stop["site"], stop["arrival_track_id"], stop["next_track_id"]
                    if key not in disabled:
                        continue
                    seen.add(key)
                    start, end, arrival = [datetime.fromisoformat(stop[k]) for k in ("start", "end", "arrival")]
                    start = max(start, arrival + timedelta(minutes=45 if stop["site"] == "WAREHOUSE" else 0))
                    origin = datetime.fromisoformat(day["start"])
                    if end > start:
                        expected[round((start - origin).total_seconds() / 60, 9),
                                 round((end - origin).total_seconds() / 60, 9), stop["site"]] += 1
                def normalized(windows):
                    return Counter((round(lo, 9), round(hi, 9), site) for lo, hi, site in windows)
                assert normalized(a["windows"]) == normalized(b["windows"]) + expected
                n += expected.total()
        removed.append(n)
    assert seen == disabled
    assert (sum(removed[:6]), sum(removed[6:])) == (3, 15)
