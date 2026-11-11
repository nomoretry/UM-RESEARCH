"""Closed-form checks for every January morning plus an equal-price tie."""
import unittest

from um_charging.day_ahead import STUDY, frozen_case, read_json
from um_charging.day_ahead_month import run_month
from um_charging.model import solve


class JanuaryMarketTests(unittest.TestCase):
    def test_cost_and_peak_for_every_delivery_date(self):
        rows = run_month()
        self.assertEqual(len(rows), 31)
        for row in rows:
            with self.subTest(date=row["date"]):
                warehouse, port = row["warehouse_eur_mwh"], row["port_eur_mwh"]
                # V3 can replace at most 20/.9 kWh of port draw with warehouse draw.
                # At either station the entire charging window lasts one hour.
                demand, shiftable = 120 / .9, 20 / .9
                cheapest_warehouse = shiftable if warehouse <= port else 0
                bill = (cheapest_warehouse * warehouse + (demand - cheapest_warehouse) * port) / 1000
                self.assertAlmostEqual(row["cost_eur"], bill, places=6)
                self.assertAlmostEqual(row["cost_then_peak_eur"], bill, places=6)
                self.assertAlmostEqual(row["cost_then_peak_port_kw"], demand - cheapest_warehouse, places=5)
                self.assertAlmostEqual(row["peak_port_kw"], demand - shiftable, places=5)
                self.assertAlmostEqual(row["arrival_port_kw"], 150, places=5)
                self.assertAlmostEqual(row["arrival_eur"], row["peak_eur"], places=6)
                self.assertGreater(row["physical_checks"], 0)

    def test_equal_negative_price_can_preserve_minimum_peak(self):
        case = frozen_case(read_json(STUDY / "case.json"))
        prices = [-1.0] * case["slot_count"]
        optimum = solve(case, market_prices_eur_per_mwh=prices)
        both = solve(case, minimize_site_peak=True, market_prices_eur_per_mwh=prices,
                     purchase_ceiling_eur=optimum["objective"])
        self.assertEqual(both["status"], "optimal")
        self.assertAlmostEqual(both["objective"], 100 / .9, places=5)
        with self.assertRaises(ValueError):
            solve(case, purchase_ceiling_eur=optimum["objective"])
