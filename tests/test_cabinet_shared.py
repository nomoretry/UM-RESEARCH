from itertools import combinations_with_replacement, product

import pytest

from um_charging import cabinet_model
from um_charging.cabinet_shared import add_shared_block, unpack_shared_block
from um_charging.energy_boundary import DEFAULT_SPEC, Matrix


@pytest.mark.parametrize("trucks", [2, 3])
@pytest.mark.parametrize("peak", [20, 35, 50])
def test_shared_block_matches_enumerated_quarters(trucks, peak):
    # In multiples of 5 kW the quarter limits and demands are integral.
    # For each physical mode pattern its transport-flow matrix is integral.
    # Enumerating integer 5 kW powers therefore also covers fractional modes
    # delivering these grid-aligned block totals.
    n = 2
    quarter = [p for p in product(range(0, peak+1, 5), repeat=trucks)
               if sum(p) <= peak and (sum(v > 0 for v in p) <= 1 or
                                       (sum(v > 0 for v in p) == 2 and max(p) <= 25))]
    possible = {tuple(map(sum, zip(*pair))) for pair in combinations_with_replacement(quarter, n)}
    for demand in product(range(0, n*peak+1, 5), repeat=trucks):
        result = unpack_shared_block(demand, n, peak)
        assert (result is not None) == (demand in possible)
        if result is None:
            continue
        assert [sum(kw for _,kw in slots) for slots in result] == pytest.approx(demand)
        for q in range(n):
            active = [kw for slots in result for slot, kw in slots if slot == q]
            assert sum(active) <= peak+1e-8
            assert len(active) <= 2
            assert len(active) <= 1 or max(active) <= 25.+1e-8


def test_variable_peak_shared_block_linearization():
    m = Matrix()
    peak = m.var(25., 50., 1.)
    decisions = add_shared_block(m, 2, (0, 15, ["a","b","c"]), peak)
    for (_, _, _, i, _), kw_sum in zip(decisions, (35., 20., 15.)):
        m.add([(i, 1)], kw_sum/4, kw_sum/4)
    result = m.solve()
    assert result.status == 0
    assert result.fun == pytest.approx(35.)


def test_actual_peak_rejects_relaxed_share_assignment():
    # Both quarters can carry 70 summed kW at a 35 kW demand ceiling.
    # Serving truck b, however, makes one of the quarters a shared one:
    # truck a then gets at most 35 + 25, short of its requested 65.
    part = (0, 15, ["a", "b"])
    for exact_meter, expected in [(False, 1.), (True, 60./65.)]:
        m = Matrix()
        peak = m.var(30., 50.)
        m.add([(peak, 1)], 35., 35.)
        served = m.var(0., 1., -1.)
        variables, modes = cabinet_model._limits(
            m, (2, [part], (2, 50., True), peak, DEFAULT_SPEC), True, meter_exact=exact_meter)
        for (_, _, _, i, _), kw in zip(variables, (65., 5.)):
            m.add([(i, 1), (served, -kw/4)], 0, 0)
        result = m.solve()
        assert result.status == 0 and -result.fun == pytest.approx(expected)
        group = ("day", "PORT", 2, [part], "two_shared_rule", peak, variables, modes)
        assert (cabinet_model._reconstruct(group, result.x, DEFAULT_SPEC) is not None) == exact_meter
