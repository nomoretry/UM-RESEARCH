import unittest
from datetime import datetime, timedelta

from um_charging.connector_value import aggregate, hourly_curve


class ConnectorValueChecks(unittest.TestCase):
    def test_settlement_requires_actual_local_delivery_and_keeps_negative_prices(self):
        start = datetime.fromisoformat("2021-09-21T00:00:00+02:00")
        day = {"date":"2021-09-21", "start":start.isoformat(), "end":(start+timedelta(days=1)).isoformat()}
        rows = [{"start_berlin":(start+timedelta(hours=h)).isoformat(), "eur_per_mwh":h-4} for h in range(24)]
        self.assertEqual(hourly_curve(rows,day),list(range(-4,20)))
        with self.assertRaises(ValueError):
            hourly_curve(rows[:8]+rows[9:],day)
        wrong = [dict(row) for row in rows]
        wrong[1]["start_berlin"] = "2021-09-21T01:00:00+01:00"
        with self.assertRaises(ValueError):
            hourly_curve(wrong,day)

    def test_missing_observations_and_infeasible_service_remain_in_denominators(self):
        cells = [{"required_ids":[], "required_trips":0, "observations":"no_recorded_tasks"},
                 {"required_ids":["2"],"required_trips":2,"matched_ids":[],"observations":"complete_tasks",
                  "facilities":{key:{"full_status":"infeasible","max_vehicle_days":0} for key in ("one","two")},
                  "prices":{}}]
        summary = aggregate(cells,"concurrent")
        self.assertEqual((summary["calendar_rows"],summary["modeled_dates"],summary["paired_dates"]),(2,1,0))
        self.assertEqual(summary["required_vehicle_days"],1)
        self.assertIsNone(summary["hardware_gain_eur"])
        self.assertIsNone(summary["one"]["scheduling_gain_eur"])
