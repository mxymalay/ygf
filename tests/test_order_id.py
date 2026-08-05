import re
import unittest
from datetime import datetime
from unittest.mock import patch

from ui.sale_widget import generate_order_id, is_receipt_order_id


class OrderIdTests(unittest.TestCase):
    def test_order_id_matches_official_receipt_length_and_shape(self):
        stamp = datetime(2026, 8, 5, 15, 34, 56, 267000)
        with patch("ui.sale_widget.uuid.uuid4") as uuid4:
            uuid4.return_value.int = 637650011
            order_id = generate_order_id(stamp)

        self.assertEqual(order_id, "2608051534562670637650011")
        self.assertEqual(len(order_id), 25)
        self.assertRegex(order_id, re.compile(r"^\d{25}$"))
        self.assertTrue(is_receipt_order_id(order_id))

    def test_legacy_ids_are_not_treated_as_current_receipt_ids(self):
        self.assertFalse(is_receipt_order_id("a" * 32))
        self.assertFalse(is_receipt_order_id("LEGACY-1"))
        self.assertTrue(is_receipt_order_id("2608051534562670637650011"))


if __name__ == "__main__":
    unittest.main()
