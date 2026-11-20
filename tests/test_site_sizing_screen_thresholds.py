import pytest
from types import SimpleNamespace

from um_charging.site_sizing import Design
from um_charging.site_sizing_known_peak_quotes import recompute_quote_thresholds
from um_charging.site_sizing_screen_thresholds import quote_threshold_ranges, select_quote_witnesses


@pytest.fixture
def published_case():
    incumbent = Design(1, 20, 0)
    alternative = Design(1, 30, 0)
    hyc50 = Design(1, 50, 0)
    key = ("N0", "new")
    publication = {
        "service": [dict(design=d.label, port_plugs=d.port_plugs, port_kw=d.port_kw, warehouse_kw=d.warehouse_kw)
                    for d in (incumbent, alternative, hyc50)],
        "investment": {"annual_charger_eur_2025_by_kw": {"20": 100, "30": 160, "50": 300}},
        "model_policy": {"equipment_cost_from_net_2026_to_annual_2025": 0.2},
        "cost_rows": [dict(design=d.label, scenario="N0", total_eur={"new": cost})
                      for d, cost in [(incumbent, 500), (alternative, 560), (hyc50, 620)]],
        "winners": [{
            "scenario": "N0", "connection_basis": "new", "design": incumbent.label, "annual_total_eur": 500,
            "price_reversal": {"annual_eur_per_unit_2025": 160, "net_equipment_eur_2026": 800},
            "port_only_hyc50_comparison": {"annual_total_eur": 620, "annual_eur_per_unit_2025": 220,
                                          "net_equipment_eur_2026": 1100, "hyc50_annual_eur_per_unit_2025": 180},
        }],
    }
    return publication, incumbent, alternative, hyc50, key


def test_screened_rival_sets_reversal_floor_and_hyc50_ceiling(published_case):
    publication, incumbent, alternative, hyc50, key = published_case
    screened = [
        (incumbent, (15, 0), {key: 501}),  # Same equipment count cannot change the reversal.
        (alternative, (25, 0), {key: 530}),
        (hyc50, (45, 0), {key: 540}),
    ]

    row, = quote_threshold_ranges(publication, screened)
    assert row["price_reversal"]["status"] == "interval"
    assert row["price_reversal"]["annual_eur_per_unit_2025_bounds"] == [130, 160]
    assert row["price_reversal"]["net_equipment_eur_2026_bounds"] == [650, 800]
    assert row["price_reversal"]["screened_bound_witness"] == {"design": alternative.label, "caps_kw": (25, 0)}
    assert row["incumbent_quote_vs_hyc50"]["annual_eur_per_unit_2025_bounds"] == [140, 220]
    assert row["hyc50_annual_break_even"]["annual_eur_per_unit_2025_bounds"] == [180, 260]
    assert row["hyc50_annual_break_even"]["screened_bound_witness"] == {"design": hyc50.label, "caps_kw": (45, 0)}

    row, = quote_threshold_ranges(publication, [screened[0], (hyc50, (45, 0), {key: float("inf")})])
    assert row["price_reversal"]["status"] == "unchanged"
    assert row["price_reversal"]["annual_eur_per_unit_2025_bounds"] == [160, 160]
    assert row["hyc50_annual_break_even"]["status"] == "unchanged"
    assert row["hyc50_annual_break_even"]["annual_eur_per_unit_2025_bounds"] == [180, 180]


def test_quote_witnesses_include_non_extremal_points_and_sort_by_lower_bill(published_case):
    publication, incumbent, alternative, hyc50, _ = published_case

    def point(design, caps, cost):
        return dict(design=design.label, caps_kw=caps, status="excluded_by_annual_lower_bound",
                    annual_comparison=[dict(scenario="N0", connection_basis="new", lower_eur=cost,
                                            no_relaxed_load_split=cost is None)])

    screening = {"points": [
        point(hyc50, (45, 0), 580),
        point(incumbent, (15, 0), 510),
        point(hyc50, (15, 0), None),
        point(alternative, (25, 0), 520),
        point(hyc50, (25, 0), 550),
    ]}
    result = select_quote_witnesses(publication, screening, limit=2)
    assert result["eligible_count"] == 3
    assert [(item["design"], item["caps_kw"]) for item in result["selected"]] == [
        (alternative.label, (25, 0)), (hyc50.label, (25, 0)),
    ]
    assert [item["caps_kw"] for item in result["unselected"]] == [(45, 0)]
    assert {item["metric"] for item in result["unselected"][0]["affected_thresholds"]} == {
        "incumbent_quote_vs_hyc50", "hyc50_annual_break_even",
    }


def test_quote_settlement_and_timeout_update_the_threshold_envelope(published_case):
    publication, _, alternative, hyc50, key = published_case
    row, = quote_threshold_ranges(
        publication, [(hyc50, (15, 0), {key: 525})],
        evaluated_points=[(alternative, (25, 0), {key: 550})],
        interval_points=[(hyc50, (25, 0), {key: 520}, {key: 545})],
        verify_published=False,
    )
    assert row["price_reversal"]["annual_eur_per_unit_2025_bounds"] == [120, 145]
    assert row["incumbent_quote_vs_hyc50"]["annual_eur_per_unit_2025_bounds"] == [120, 145]
    assert row["hyc50_annual_break_even"]["annual_eur_per_unit_2025_bounds"] == [255, 280]

    row, = quote_threshold_ranges(
        publication, [(hyc50, (15, 0), {key: 560})],
        evaluated_points=[(hyc50, (25, 0), {key: 550})], verify_published=False,
    )
    assert row["hyc50_annual_break_even"]["status"] == "unchanged"
    assert row["hyc50_annual_break_even"]["annual_eur_per_unit_2025_bounds"] == [250, 250]


def test_known_peak_quotes_keep_timeout_witness_and_apply_rank_intervals(published_case):
    publication, incumbent, alternative, hyc50, _ = published_case
    bills = lambda value: {"N0": {"new": value}}
    # The screened HYC50 witness has an accepted timeout. Its audited bill can
    # improve the attainable endpoint, but its actual threshold is an interval.
    # The uncertified rank point has a useful lower bill and no schedule for
    # all six weeks. It can affect the ordinary crossover.
    witness = dict(design=hyc50.label, caps_kw=[25, 0], kind="threshold", status="settled")
    rank = dict(design=alternative.label, caps_kw=[15, 0], kind="ranking", status="unresolved")
    screened = dict(design=hyc50.label, caps_kw=[25, 0], status="excluded_by_annual_lower_bound",
                    annual_comparison=[dict(scenario="N0", connection_basis="new", lower_eur=510,
                                            no_relaxed_load_split=False)])
    settled = SimpleNamespace(design=alternative, caps=(30, 0), totals=bills(550))
    absorbed = SimpleNamespace(week="first", proof="local/one", proof_sha256="hash", status="bounded")
    queried = []

    def bill_lower(design, caps, accepted, *, quotes):
        assert accepted == (absorbed,) and quotes
        queried.append((design, caps))
        return {"total_eur": bills(530 if design == hyc50 else 520)}

    archive = SimpleNamespace(
        evidence=SimpleNamespace(publication=publication, cases={d.label: d for d in (incumbent, alternative, hyc50)}),
        ranked_settlements=[settled], summary={"points": [witness, rank]}, screening={"points": [screened]},
        accepted=lambda row: (absorbed,), upper=lambda row: bills(545) if row is witness else None,
        bill_lower=bill_lower,
    )
    result = recompute_quote_thresholds(archive)
    row, = result["quote_thresholds"]
    assert queried == [(hyc50, (25, 0)), (alternative, (15, 0))]
    assert row["price_reversal"]["annual_eur_per_unit_2025_bounds"] == [120, 145]
    assert row["incumbent_quote_vs_hyc50"]["annual_eur_per_unit_2025_bounds"] == [130, 145]
    assert row["hyc50_annual_break_even"]["annual_eur_per_unit_2025_bounds"] == [255, 270]
    assert row["price_reversal"]["screened_bound_witness"]["design"] == alternative.label
    assert result["counts"]["hyc50_annual_break_even"] == {"exact": 0, "interval": 1}
