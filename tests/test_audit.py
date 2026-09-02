import json
import tempfile
import unittest
from pathlib import Path

from pyspark.sql import SparkSession
from snowflake.snowpark import Session

from audit.clean import COLUMNS, EVENT_SCHEMA, resolve
from audit.reconcile import carrier_summary, price


class TestRevisionHandling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (SparkSession.builder.master("local[2]").appName("revision-tests")
                     .config("spark.sql.shuffle.partitions", "2")
                     .config("spark.ui.enabled", "false").getOrCreate())

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def read_events(self, rows):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "events.jsonl"
        with path.open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(dict(zip(COLUMNS, row))) + "\n")
        return self.spark.read.schema(EVENT_SCHEMA).json(str(path))

    def test_late_retry_conflict_and_invalid_correction(self):
        base = ("P1", 1, "Amber", "A", 1000, 850)
        rows = [
            ("P1", 2, "Amber", "A", 1000, 800), base, base,
            ("P2", 1, "Amber", "A", 1000, 850),
            ("P2", 1, "Amber", "A", 1000, 870),
            ("P3", 1, "Amber", "A", 1000, 850),
            ("P3", 2, "Amber", "A", 0, 850),
        ]
        good, bad = resolve(self.read_events(rows))
        self.assertEqual([("P1", 2, 800)], [tuple(row) for row in
                         good.select("parcel_id", "revision", "billed_cents").collect()])
        reasons = sorted(tuple(row) for row in bad.select("parcel_id", "reason").collect())
        self.assertEqual(reasons, [("P2", "conflicting_revision")] * 2 +
                         [("P3", "invalid_charge")])

    def test_unkeyed_rows_fail_batch(self):
        row = (None, 1, "Amber", "A", 500, 100)
        with self.assertRaisesRegex(ValueError, "parcel ID"):
            resolve(self.read_events([row]))


class TestContractPricing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = Session.builder.config("local_testing", True).create()

    @classmethod
    def tearDownClass(cls):
        cls.session.close()

    def setUp(self):
        self.inputs = self.session.create_dataframe([
            ("P1", 1, "Amber", "A", 1000, 850), ("P2", 1, "Amber", "A", 1001, 1000),
            ("P3", 1, "Amber", "A", 2000, 950), ("P4", 1, "Amber", "C", 500, 800),
        ], ["parcel_id", "revision", "carrier", "zone", "weight_g", "billed_cents"])
        self.rate_cols = ["carrier", "zone", "base_cents", "extra_kg_cents"]
        self.rate = ("Amber", "A", 850, 130)

    def test_weight_boundaries_missing_rate_and_signed_variance(self):
        tariffs = self.session.create_dataframe([self.rate], self.rate_cols)
        priced = price(self.inputs, tariffs)
        rows = priced.sort("parcel_id").select("status", "variance_cents").collect()
        self.assertEqual([tuple(r) for r in rows], [
            ("MATCH", 0), ("OVERBILLED", 20), ("UNDERBILLED", -30), ("NEEDS_RATE", None),
        ])
        summary = carrier_summary(priced).collect()[0]
        self.assertEqual((summary["PARCELS"], summary["OVERBILLED"], summary["MISSING_RATES"],
                          summary["DISPUTABLE_CENTS"], summary["UNDERBILLED_CENTS"]),
                         (4, 1, 1, 20, 30))

    def test_duplicate_tariff_fails(self):
        tariffs = self.session.create_dataframe([self.rate, self.rate], self.rate_cols)
        with self.assertRaisesRegex(ValueError, "unique"):
            price(self.inputs, tariffs)

    def test_negative_tariff_fails(self):
        tariffs = self.session.create_dataframe([("Amber", "A", -100, 10)], self.rate_cols)
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            price(self.inputs, tariffs)
