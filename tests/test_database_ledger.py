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

    def test_verified_official_revenue_is_separate_and_idempotent(self):
        self.assertTrue(self.db.record_official_revenue(
            "meituan:1001", "美团", "1001", 28.5,
            created_at="2026-08-07 12:00:00"
        ))
        self.assertFalse(self.db.record_official_revenue(
            "meituan:1001", "美团", "1001", 28.5,
            created_at="2026-08-07 12:01:00"
        ))
        stats = self.db.get_official_stats_by_date("2026-08-07")
        self.assertEqual(stats["count"], 1)
        self.assertEqual(stats["amount_sum"], 28.5)
        self.assertEqual(self.db.get_stats_by_date("2026-08-07")["count"], 0)

    def test_official_call_number_is_saved_and_refund_links_by_normalized_call(self):
        self.assertTrue(self.db.record_official_revenue(
            "official:LONG-1", "官方POS-堂食", "2608080015202670637650001", 2.0,
            created_at="2026-08-08 00:16:28", order_no="#0001",
        ))
        result = self.db.record_official_refund(
            "official:dinein:#001", "official:dinein:#001", "#001", -2.0,
            observed_at="2026-08-08 00:18:14",
        )
        self.assertTrue(result["linked"])
        self.assertEqual(result["original_order_id"], "2608080015202670637650001")
        self.assertEqual(self.db.get_official_stats_by_date("2026-08-08")["count"], 0)
        self.assertEqual(self.db.get_official_revenue_by_date("2026-08-08"), [])
        history_rows = self.db.get_official_revenue_by_date(
            "2026-08-08", include_refunded=True
        )
        self.assertEqual(len(history_rows), 1)
        self.assertEqual(history_rows[0]["payment_status"], REFUNDED)
        conn = self.db._get_conn()
        try:
            row = conn.execute(
                "SELECT order_no, payment_status, refund_amount FROM official_pos_revenue"
            ).fetchone()
            self.assertEqual(row["order_no"], "#0001")
            self.assertEqual(row["payment_status"], "REFUNDED")
            self.assertAlmostEqual(row["refund_amount"], 2.0, places=2)
        finally:
            conn.close()

    def test_generic_official_receipt_tracks_reprints_without_recounting(self):
        parsed = {
            "receipt_kind": "dinein",
            "platform": "官方POS-堂食",
            "full_order_id": "DINE-1001",
            "order_no": "#1001",
            "order_amount": 32.0,
            "amount_valid": True,
            "payment_status": "unknown",
            "payment_status_confidence": "unknown",
            "key_confidence": "high",
        }
        created, row = self.db.record_official_receipt(
            "official:DINE-1001", parsed, payload_type="escpos",
            observed_at="2026-08-07 12:00:00",
        )
        self.assertTrue(created)
        self.assertEqual(row["receipt_kind"], "dinein")
        created_again, row_again = self.db.record_official_receipt(
            "official:DINE-1001", parsed, payload_type="escpos",
            observed_at="2026-08-07 12:01:00",
        )
        self.assertFalse(created_again)
        self.assertEqual(row_again["print_count"], 2)
        self.assertEqual(self.db.get_official_stats_by_date("2026-08-07")["count"], 0)

        paid = dict(parsed, payment_status="paid", payment_status_confidence="high")
        _created_paid, paid_row = self.db.record_official_receipt("official:DINE-1001", paid)
        self.assertEqual(paid_row["payment_status"], "paid")

    def test_official_revenue_query_includes_receipt_items(self):
        parsed = {
            "receipt_kind": "dinein",
            "platform": "官方POS-堂食",
            "full_order_id": "DINE-ITEMS",
            "order_no": "#1002",
            "order_amount": 32.0,
            "amount_valid": True,
            "payment_status": "paid",
            "payment_status_confidence": "high",
            "key_confidence": "high",
            "item_count": 2,
            "item_names": ["肥牛", "可乐"],
        }
        self.db.record_official_receipt(
            "official:DINE-ITEMS", parsed, observed_at="2026-08-07 12:00:00"
        )
        self.assertTrue(self.db.record_official_revenue(
            "official:DINE-ITEMS", "官方POS-堂食", "DINE-ITEMS", 32.0,
            created_at="2026-08-07 12:00:00", order_no="#1002",
        ))
        rows = self.db.get_official_revenue_by_date("2026-08-07")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item_count"], 2)
        self.assertEqual(rows[0]["item_names_json"], '["肥牛", "可乐"]')

    def test_official_takeout_revenue_query_uses_takeout_items(self):
        parsed = {
            "platform": "美团",
            "full_order_id": "1003",
            "order_no": "#1003",
            "order_amount": 19.9,
            "amount_valid": True,
            "payment_status": "paid",
            "payment_status_confidence": "high",
            "key_confidence": "high",
            "item_count": 1,
            "item_names": ["肥牛"],
        }
        self.db.record_takeout_order(
            "美团:1003", parsed,
            {"key": "美团:1003", "platform": "美团", "full_order_id": "1003",
             "order_no": "#1003", "order_amount": 19.9,
             "amount_valid": True, "payment_status": "paid",
             "payment_status_confidence": "high", "key_confidence": "high",
             "created_at": "2026-08-07 12:01:00"},
        )
        self.assertTrue(self.db.record_official_revenue(
            "美团:1003", "美团", "1003", 19.9,
            created_at="2026-08-07 12:01:00",
        ))
        rows = self.db.get_official_revenue_by_date("2026-08-07")
        row = next(item for item in rows if item["order_key"] == "美团:1003")
        self.assertEqual(row["item_count"], 1)
        self.assertEqual(row["item_names_json"], '["肥牛"]')

    def test_generic_official_receipt_marks_amount_change_as_conflict(self):
        base = {
            "receipt_kind": "dinein", "platform": "官方POS-堂食",
            "full_order_id": "DINE-CONFLICT", "order_amount": 20.0,
            "amount_valid": True, "payment_status": "paid",
            "payment_status_confidence": "high", "key_confidence": "high",
        }
        self.db.record_official_receipt("official:DINE-CONFLICT", base)
        changed = dict(base, order_amount=21.0)
        _created, row = self.db.record_official_receipt("official:DINE-CONFLICT", changed)
        self.assertEqual(row["conflict_detected"], 1)

    def test_route_event_keeps_amount_basis_and_mode(self):
        event = self.db.create_weighing_route_event(
            0.5, False, "amount", routing_basis="amount",
            operating_mode="enhanced", estimated_amount=23.8,
            official_receipt_key="official:DINE-1001",
        )
        self.assertEqual(event["routing_basis"], "amount")
        self.assertEqual(event["operating_mode"], "enhanced")
        self.assertAlmostEqual(event["estimated_amount"], 23.8, places=2)

    def test_relay_mode_transitions_are_audited(self):
        self.assertTrue(self.db.record_relay_mode_event(
            "compatibility", "enhanced", "auto", "官方金额和付款状态已验证",
            "2026-08-07 12:00:00",
        ))
        events = self.db.get_relay_mode_events("2026-08-07")
        self.assertEqual(events[0]["new_mode"], "enhanced")

    def test_takeout_order_metadata_has_its_own_sqlite_ledger(self):
        parsed = {
            "platform": "美团",
            "full_order_id": "1002",
            "order_no": "#1002",
            "order_amount": 19.9,
            "amount_valid": True,
            "payment_status": "unknown",
            "payment_status_confidence": "unknown",
            "item_count": 1,
            "item_names": ["肥牛"],
        }
        job = {
            "key": "meituan:1002",
            "platform": "美团",
            "full_order_id": "1002",
            "order_no": "#1002",
            "order_amount": 19.9,
            "amount_valid": True,
            "payment_status": "unknown",
            "key_confidence": "high",
            "created_at": "2026-08-07 12:00:00",
        }
        self.assertTrue(self.db.record_takeout_order(job["key"], parsed, job))
        self.assertFalse(self.db.record_takeout_order(job["key"], parsed, job, duplicate=True))
        rows = self.db.get_takeout_orders_by_date("2026-08-07")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["payment_status"], "unknown")
        self.assertEqual(self.db.get_stats_by_date("2026-08-07")["count"], 0)

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
