import os
import tempfile
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


if __name__ == "__main__":
    unittest.main()
