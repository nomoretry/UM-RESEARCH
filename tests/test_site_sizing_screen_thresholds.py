from um_charging.site_sizing import Design
from um_charging.site_sizing_screen_thresholds import quote_threshold_ranges


def test_screened_rival_sets_reversal_floor_and_hyc50_ceiling():
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
