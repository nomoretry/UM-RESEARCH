"""Build the stage-one count table and consume sealed, date-scoped record ranges."""
import importlib
import json
from pathlib import Path
import sys

from . import energy_boundary as eb, holdout_inputs as hi
from .m10_inputs import _prices
from .m11_external_seal import authorize, check, put, seal


STUDY = eb.ROOT / "studies" / "fleet-service"


def preparation():
    sys.path.insert(0, str(STUDY))
    try:
        return importlib.import_module("m11_external_prepare")
    finally:
        sys.path.pop(0)


def read(path):
    return json.loads(path.read_bytes())


def first(folder, path, cohort, registration, *, head, begin):
    from .m11_external_evidence import utc
    authorize(cohort, registration)
    prep = preparation()
    counts, bounds, sections = prep.index_source(path, cohort, registration)
    total = [sum(w["complete"] for w in weeks) for weeks in (counts[:12], counts[12:])]
    values = {"counts.json": dict(weeks=counts, selection=total[0], evaluation=total[1],
                                  passed=total[0] >= 68 and total[1] >= 28),
              "boundary.json": bounds, "selection_index.json": sections["selection"],
              "evaluation_index.json": sections["evaluation"],
              "execution.json": dict(source_commit=head,started=begin.isoformat(),finished=utc().isoformat(),
                                     seconds=(utc()-begin).total_seconds(),requests_started=0,requests_used=0)}
    for name, value in values.items():
        put(folder, name, value)
    return seal(folder, cohort, 1, values, None)


def prepare_phase(root, path, cohort, stage, registration=None):
    authorize(cohort, registration)
    prev = check(root / f"stage{stage-1}", cohort, stage-1)
    first_folder = root / "stage1"
    if stage == 3 and read(root/"stage2"/"manifest.json")["previous"] != check(first_folder, cohort, 1):
        raise ValueError("Selection results do not bind the count-stage seal")
    if not read(first_folder/"counts.json")["passed"]:
        return None, None, prev
    if stage == 3 and read(root/"stage2"/"selection.json")["registration_gate"] != "passed":
        return None, None, prev
    prep = preparation()
    name = {2: "selection", 3: "evaluation"}[stage]
    section = read(first_folder / (name+"_index.json"))
    bounds = read(first_folder / "boundary.json")
    vehicles = None
    if cohort == "1-5":
        _, vehicles = prep.identities(path, cohort)
    records = prep.read_period(path, section, vehicles, *prep.BOUNDS[name])
    preceding = None if stage == 2 else read(root/"stage2"/"last_selection_arrivals.json")
    days = prep.period_days(records, name, section, bounds, preceding=preceding)
    substituted = prep.period_days(records, name, section, bounds, preceding=preceding, truncate=True)
    if prep.effective_windows(days) != prep.effective_windows(substituted):
        raise ValueError("STOP: replacing the post-period departure changed an in-period window")
    if cohort == "1-5":
        published = (["operating_weeks.json", "holdout_weeks.json"] if stage == 2
                     else ["second_holdout_weeks.json"])
        expected = [d for filename in published for d in read(STUDY / filename)["days"]]
        if days != expected:
            raise ValueError("STOP: rehearsal duties differ from published tasks")
    return days, prep.latest_selection(records) if stage == 2 else None, prev


def periods(days):
    groups = []
    for i in range(0, len(days), 7):
        week = days[i:i+7]
        first_date = week[0]["date"]
        if first_date < "2021-11-08":
            source = eb.NATIVE
        elif first_date < "2021-12-20":
            source = hi.PRICES
        else:
            source = hi.PRICES.with_name("native_2022_second_holdout_prices.csv")
        groups.append(eb.Period(week, _prices(week, source)))
    return groups
