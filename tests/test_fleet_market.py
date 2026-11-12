from datetime import date, timedelta
import unittest

from um_charging.fleet_market import next_hardware, paired_bill, prices_for_day, summarize_run


class FleetMarketChecks(unittest.TestCase):
    def test_local_weekday_and_complete_hour_curve(self):
        monday = date(2025,1,6)
        prices = [{"start_berlin": f"{monday+timedelta(days=d)}T{h:02}:00:00+01:00", "eur_per_mwh": d*24+h}
                  for d in range(7) for h in range(24)]
        stamp, rates = prices_for_day(prices,"2021-09-22")
        self.assertEqual(stamp,"2025-01-08")
        self.assertEqual(rates,list(range(48,72)))
        with self.assertRaises(ValueError):
            prices_for_day(prices[:50],"2021-09-22")

    def test_cross_hour_and_tied_low_prices(self):
        prices = [-2.]*7 + [5.]*17
        audit = {"passed":True,"purchase_eur":.0015,"vehicles_completed":1,"trips_completed":1,
                 "site_peak_kw":{"PORT":1.,"WAREHOUSE":0.}}
        raw = {"audit":audit,"schedule":[{"start_min":390,"end_min":450,"power_kw":1.}],"status":"optimal"}
        cell = summarize_run(raw,prices,True)
        self.assertAlmostEqual(cell["cheap_kwh"],.5)
        self.assertEqual(cell["cheap_hours"],list(range(7)))
        self.assertAlmostEqual(cell["purchase_eur"],.0015)
        self.assertIsNone(paired_bill({**cell,"service_complete":False},cell))
        with self.assertRaises(ValueError):
            paired_bill({**cell,"grid_kwh":2.},cell)

    def test_one_menu_dimension_changes(self):
        hardware={"PORT":{"interfaces":1,"power_kw":100},"WAREHOUSE":{"interfaces":1,"power_kw":75}}
        higher={"PORT":{"interfaces":3,"power_kw":150},"WAREHOUSE":{"interfaces":2,"power_kw":100}}
        middle={"PORT":{"interfaces":2,"power_kw":100},"WAREHOUSE":hardware["WAREHOUSE"]}
        variants=dict(next_hardware(hardware,[(0,hardware),(20,middle),(90,higher)]))
        self.assertEqual(variants["PORT_interfaces"]["PORT"]["interfaces"],2)
        for adjusted in variants.values():
            self.assertEqual(sum(adjusted[s][k] != v for s,items in hardware.items() for k,v in items.items()),1)
