import unittest

from um_charging.connector_cost import break_even


class ConnectorCostTest(unittest.TestCase):
    def test_annuity_matches_discounted_cashflows(self):
        result = break_even([0, 0, 10, 20, 30, 60])
        self.assertEqual(result["weekly_range_eur"], [0, 60])
        self.assertEqual(result["annual_cost_ceiling_eur"], 1040)
        self.assertAlmostEqual(result["annual_cost_ceiling_2025_eur"], 1040 * 121.9 / 103.1)
        discounted_years = sum(1 / 1.05 ** t for t in range(1, 11))
        self.assertAlmostEqual(result["capital_ceiling_zero_maintenance_eur"], 1040 * discounted_years)
        self.assertAlmostEqual(result["benchmark"]["annual_cost_2025_eur"],
                               27146.60 / discounted_years + 208.82)
        self.assertFalse(result["covers_benchmark_in_repeat_scenario"])

    def test_zero_and_both_sides_of_the_hurdle(self):
        zero = break_even([0] * 6, price_year=2025)
        self.assertEqual(zero["capital_ceiling_zero_maintenance_2025_eur"], 0)
        self.assertEqual(zero["conversion_to_2025_eur"], 1)
        weekly_hurdle = zero["benchmark"]["required_weekly_saving_2025_eur"]
        self.assertFalse(break_even([weekly_hurdle - .001] * 6, price_year=2025)["covers_benchmark_in_repeat_scenario"])
        self.assertTrue(break_even([weekly_hurdle + .001] * 6, price_year=2025)["covers_benchmark_in_repeat_scenario"])

    def test_unknown_weeks_are_not_counted_as_zero(self):
        for values in ([1] * 5, [0] * 5 + [None], [0] * 5 + [float("nan")], [-.01] * 6):
            with self.subTest(values=values), self.assertRaises(ValueError):
                break_even(values)
        with self.assertRaises(ValueError):
            break_even([1] * 6, price_year=2023)
