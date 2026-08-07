import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from core.call_number_manager import CallNumberManager


class _ReceiptDb:
    def __init__(self, rows):
        self.rows = rows

    def get_official_receipts(self, limit=2000):
        return list(self.rows)


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 8, 8, 12, 0, 0)


class CallNumberManagerOfficialOffsetTests(unittest.TestCase):
    def _row(self, number, hours, days=0):
        observed = datetime.now() - timedelta(hours=hours, days=days)
        return {
            "order_no": "#%s" % number,
            "observed_at": observed.strftime("%Y-%m-%d %H:%M:%S"),
            "payment_status": "paid",
        }

    def test_old_official_range_and_current_offset_are_combined(self):
        config = {
            "call_mode": CallNumberManager.MODE_OFFICIAL_OFFSET,
            "call_used_numbers": [],
        }
        db = _ReceiptDb([
            {"order_no": "#10", "observed_at": "2026-08-08 07:00:00", "payment_status": "paid"},
            {"order_no": "#20", "observed_at": "2026-08-08 11:00:00", "payment_status": "paid"},
        ])
        manager = CallNumberManager(config, official_db=db)
        with patch("core.call_number_manager.save_config"), patch("core.call_number_manager.datetime", _FixedDateTime):
            context = manager._official_number_context()
            self.assertEqual(context["old_max"], 10)
            self.assertEqual(context["current_max"], 20)
            self.assertTrue(set(range(1, 11)).issubset(context["reusable"]))
            self.assertEqual(min(context["high"]), 50)
            self.assertEqual(max(context["high"]), 80)
            chosen = manager.get_next_number()
        self.assertTrue(chosen in set(range(1, 11)) | set(range(50, 81)))

    def test_previous_day_low_numbers_are_not_recycled_before_today_starts(self):
        config = {
            "call_mode": CallNumberManager.MODE_OFFICIAL_OFFSET,
            "call_used_numbers": [],
        }
        manager = CallNumberManager(config, official_db=_ReceiptDb([
            {"order_no": "#10", "observed_at": "2026-08-07 12:00:00", "payment_status": "paid"},
        ]))
        with patch("core.call_number_manager.save_config"), patch("core.call_number_manager.datetime", _FixedDateTime):
            context = manager._official_number_context()
        self.assertEqual(context["old_max"], 0)
        self.assertEqual(context["reusable"], set())
        self.assertEqual((min(context["high"]), max(context["high"])), (40, 70))

    def test_no_official_data_never_guesses_a_low_number(self):
        config = {
            "call_mode": CallNumberManager.MODE_OFFICIAL_OFFSET,
            "call_used_numbers": [],
        }
        manager = CallNumberManager(config, official_db=_ReceiptDb([]))
        with patch("core.call_number_manager.save_config"):
            chosen = manager.get_next_number()
        self.assertIsNone(chosen)
        self.assertFalse(manager.official_mode_ready())


if __name__ == "__main__":
    unittest.main()
