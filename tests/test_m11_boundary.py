from types import SimpleNamespace

from um_charging import energy_boundary as eb, m11_boundary


def permits(variant, chains, rows):
    period = SimpleNamespace(chains=chains)
    m = eb.Matrix()
    levels = m11_boundary._levels(variant, m, period, eb.DEFAULT_SPEC, eb.B, set(rows), True)
    values = [None] * len(m.cost)
    for key, columns in levels.items():
        for col, value in zip(columns, rows[key], strict=True):
            values[col] = value
    totals = [0.] * len(m.lb)
    for row, col, coef in zip(m.row, m.col, m.data, strict=True):
        totals[row] += coef*values[col]
    return all(lo <= n <= hi for lo, n, hi in zip(m.lower, values, m.upper, strict=True)) and all(
        lo <= n <= hi for lo, n, hi in zip(m.lb, totals, m.ub, strict=True))


def test_weekly_conserves_at_registration_and_record_gaps_per_truck():
    a, b, c = [(str(d), "1") for d in (1, 2, 4)]
    other = ("4", "2")
    chains = [[a, b], [c], [other]]
    rows = {a:(1,150,80), b:(0,80,80), c:(1,80,151), other:(1,150,150)}
    assert permits("weekly", chains, rows)
    assert not permits("weekly", chains, {**rows, c:(1,150,151)})
    assert not permits("weekly", chains, {**rows, other:(1,150,149)})


def test_open_boundary_resets_after_gap_but_links_adjacent_service():
    a, b, c, d = [(str(n), "1") for n in (1, 2, 3, 5)]
    rows = {a:(1,150,50), b:(1,50,45), c:(0,150,150), d:(1,150,30)}
    assert permits("open", [[a,b,c],[d]], rows)
    assert not permits("open", [[a,b,c],[d]], {**rows,b:(1,150,45)})
    assert not permits("open", [[a,b,c],[d]], {**rows,d:(1,45,30)})
