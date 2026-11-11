"""Independent energy and capacity checks on the published sensitivity cases."""
import json
import unittest
from pathlib import Path

from run import coefficient


class TransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        summary = json.loads(Path(__file__).with_name("metrics.json").read_text(encoding="utf-8"))
        cls.source = summary["source"]
        cls.rows = {(row["payload_t"], row["aux_kw"]): row for row in summary["cases"]}

    def test_identity_and_coverage(self):
        self.assertEqual(coefficient(self.source, 1, 5), 1)
        row = self.rows[19.3, 5]
        self.assertEqual((row["leg_kwh"], row["investment"]), (20, 40))
        self.assertAlmostEqual(row["operating_cost"], 400 / 3)
        self.assertEqual(self.source["tracks_with_original_energy"] + self.source["excluded_missing_energy"],
                         self.source["published_tracks"])

    def test_energy_and_all_hardware_costs(self):
        self.assertEqual(len(self.rows), 9)
        for row in self.rows.values():
            with self.subTest(payload=row["payload_t"], aux=row["aux_kw"]):
                self.assertAlmostEqual(row["operating_cost"], 6 * row["leg_kwh"] / 0.9)
                self.assertAlmostEqual(row["objective"], row["operating_cost"] + row["investment"])
                self.assertEqual(row["configurations_checked"], 54)
                self.assertEqual(len(row["optima"]), 1)
                port, warehouse = row["optima"][0]
                cost = ((port["connectors"] - 1) * 20 + (warehouse["connectors"] - 1) * 30
                        + {0: 0, 50: 35, 75: 65}[port["added_kw"]]
                        + {0: 0, 25: 10}[warehouse["added_kw"]])
                self.assertEqual(row["investment"], cost)

    def test_one_warehouse_connector_crosses_port_capacity(self):
        base, higher = self.rows[19.3, 5], self.rows[19.3, 7]
        self.assertLess(5 * base["leg_kwh"] / 0.9 - 12.5, 100)
        self.assertGreater(5 * higher["leg_kwh"] / 0.9 - 12.5, 100)
        self.assertEqual([s["connectors"] for s in base["optima"][0]], [3, 1])
        self.assertEqual([s["connectors"] for s in higher["optima"][0]], [2, 2])
