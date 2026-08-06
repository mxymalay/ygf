import os
import sqlite3
import tempfile
import time
import unittest

from core.database import Database, PRINT_FAILED, PRINTED, REFUNDED


class DatabaseLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "sales.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def _insert(self, order_id="order-1"):
        return self.db.insert_sale(
            weight_kg=0.35,
            unit_price=47.6,
            price_unit="per_jin",
            total_price=16.66,
            remark="test",
            cart_items_json="[]",
            payment_method="cash",
            order_id=order_id,
        )

    def test_same_order_id_cannot_create_two_sales(self):
        first, created = self._insert()
        second, created_again = self._insert()

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.db.get_recent_sales()), 1)

    def test_print_and_refund_are_audited_without_deleting_order(self):
        record, _ = self._insert()
        self.db.mark_print_result(record["id"], False, "offline")
        failed = self.db.get_sale_by_order_id("order-1")
        self.assertEqual(failed["print_status"], PRINT_FAILED)

        self.db.mark_print_result(record["id"], True)
        printed = self.db.get_sale_by_order_id("order-1")
        self.assertEqual(printed["print_status"], PRINTED)
        self.assertTrue(self.db.refund_sale(record["id"], "test refund"))

        refunded = self.db.get_sale_by_order_id("order-1")
        self.assertEqual(refunded["payment_status"], REFUNDED)
        self.assertEqual(self.db.get_stats_by_date(refunded["created_at"][:10])["count"], 0)
        self.assertEqual(self.db.get_refund_stats_by_date(refunded["created_at"][:10])["count"], 1)

    def test_legacy_sales_table_without_order_id_is_migrated(self):
        """Opening a pre-order-id database must not crash during index creation."""
        path = os.path.join(self.tmp.name, "legacy.db")
        conn = sqlite3.connect(path)
        conn.execute(
            """CREATE TABLE sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_no TEXT UNIQUE NOT NULL,
                weight_kg REAL NOT NULL,
                unit_price REAL NOT NULL,
                price_unit TEXT NOT NULL DEFAULT 'per_jin',
                total_price REAL NOT NULL,
                remark TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                printed INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.commit()
        conn.close()

        migrated = Database(path)
        conn = migrated._get_conn()
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sales)")}
        conn.close()
        self.assertIn("order_id", columns)

    def test_weighing_route_lifecycle_keeps_payment_truth_separate(self):
        private = self.db.create_weighing_route_event(0.42, True, "quota", order_id="order-1")
        official = self.db.create_weighing_route_event(0.31, False, "forced_official")
        self.assertEqual(private["status"], "PENDING")
        self.assertEqual(official["channel"], "official")

        self.assertEqual(
            self.db.resolve_pending_private_weighing_events("PRIVATE_PAID", "order-1"),
            1,
        )
        self.assertEqual(
            self.db.resolve_pending_weighing_events(
                channel="official", status="OFFICIAL_UNKNOWN", note="no callback"
            ),
            1,
        )
        summary = {(row["channel"], row["status"]): row for row in self.db.get_weighing_route_summary()}
        self.assertEqual(summary[("private", "PRIVATE_PAID")]["weight_kg"], 0.42)
        self.assertEqual(summary[("official", "OFFICIAL_UNKNOWN")]["count"], 1)

    def test_private_route_resolution_never_claims_another_order(self):
        first = self.db.create_weighing_route_event(0.42, True, "quota", order_id="order-a")
        second = self.db.create_weighing_route_event(0.51, True, "quota", order_id="order-b")

        self.assertTrue(first["event_key"])
        self.assertTrue(second["event_key"])
        self.assertEqual(
            self.db.resolve_pending_private_weighing_events("PRIVATE_PAID", "order-a"),
            1,
        )
        events = {row["order_id"]: row for row in self.db.get_weighing_route_events()}
        self.assertEqual(events["order-a"]["status"], "PRIVATE_PAID")
        self.assertEqual(events["order-b"]["status"], "PENDING")

    def test_route_must_be_claimed_before_a_later_payment_can_confirm_it(self):
        unused = self.db.create_weighing_route_event(0.42, True, "quota")
        selected = self.db.create_weighing_route_event(0.51, True, "quota")

        self.assertTrue(
            self.db.assign_weighing_route_event_order(selected["event_key"], "order-a")
        )
        self.assertFalse(
            self.db.assign_weighing_route_event_order(selected["event_key"], "order-b")
        )
        self.assertEqual(
            self.db.resolve_pending_private_weighing_events("PRIVATE_PAID", "order-a"),
            1,
        )

        events = {row["event_key"]: row for row in self.db.get_weighing_route_events()}
        self.assertEqual(events[selected["event_key"]]["status"], "PRIVATE_PAID")
        self.assertEqual(events[unused["event_key"]]["status"], "PENDING")

    def test_resolution_keeps_the_order_id_already_bound_to_a_route(self):
        event = self.db.create_weighing_route_event(0.42, True, "quota", order_id="order-a")
        self.assertTrue(
            self.db.resolve_weighing_route_event(
                event["event_key"], "NOT_PAID", note="basket cleared"
            )
        )
        row = self.db.get_weighing_route_events()[0]
        self.assertEqual(row["order_id"], "order-a")
        self.assertEqual(row["status"], "NOT_PAID")

    def test_official_continuation_lock_timestamp_survives_database_reopen(self):
        timestamp = time.time()
        self.db.set_last_official_route_at(timestamp)
        self.assertAlmostEqual(self.db.get_last_official_route_at(), timestamp, places=3)

        self.db.clear_last_official_route_at()
        self.assertEqual(self.db.get_last_official_route_at(), 0.0)


if __name__ == "__main__":
    unittest.main()
