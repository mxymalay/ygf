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


class _EveningDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 8, 8, 18, 0, 0)


class _MidnightDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 8, 8, 2, 0, 0)


class CallNumberManagerOfficialOffsetTests(unittest.TestCase):
    def _row(self, number, hours, days=0):
        observed = datetime.now() - timedelta(hours=hours, days=days)
        return {
            "order_no": "#%s" % number,
            "observed_at": observed.strftime("%Y-%m-%d %H:%M:%S"),
            "payment_status": "paid",
        }

    def test_three_hour_low_range_and_expanded_current_offset_are_combined(self):
        config = {
            "call_mode": CallNumberManager.MODE_OFFICIAL_OFFSET,
            "call_used_numbers": [],
        }
        db = _ReceiptDb([
            {"order_no": "#10", "observed_at": "2026-08-08 07:00:00", "payment_status": "paid"},
            {"order_no": "#15", "observed_at": "2026-08-08 09:00:00", "payment_status": "paid"},
            {"order_no": "#20", "observed_at": "2026-08-08 11:00:00", "payment_status": "paid"},
        ])
        manager = CallNumberManager(config, official_db=db)
        with patch("core.call_number_manager.save_config"), patch("core.call_number_manager.datetime", _FixedDateTime):
            context = manager._official_number_context()
            self.assertEqual(context["old_max"], 15)
            self.assertEqual(context["current_max"], 20)
            self.assertTrue(set(range(1, 16)).issubset(context["reusable"]))
            self.assertEqual(min(context["high"]), 50)
            self.assertEqual(max(context["high"]), 140)
            with patch.object(manager, "relay_enhanced_available", return_value=True):
                chosen = manager.get_next_number()
        self.assertTrue(chosen in set(range(1, 16)) | set(range(50, 141)))

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
        self.assertEqual((min(context["high"]), max(context["high"])), (40, 130))

    def test_no_official_data_never_guesses_a_low_number(self):
        config = {
            "call_mode": CallNumberManager.MODE_OFFICIAL_OFFSET,
            "call_used_numbers": [],
        }
        manager = CallNumberManager(config, official_db=_ReceiptDb([]))
        with patch("core.call_number_manager.save_config"):
            chosen = manager.get_next_number()
        # Compatibility fallback is automatic; mode one keeps the cashier
        # moving even before the first official POS ticket is observed.
        self.assertIsNotNone(chosen)
        self.assertEqual(config["call_mode"], CallNumberManager.MODE_SMART)
        self.assertFalse(manager.official_mode_ready())

    def test_compatibility_mode_cannot_use_official_relative_numbers(self):
        config = {
            "call_mode": CallNumberManager.MODE_OFFICIAL_OFFSET,
            "call_used_numbers": [],
        }
        manager = CallNumberManager(config, official_db=_ReceiptDb([self._row(20, 1)]))
        self.assertFalse(manager.relay_enhanced_available())
        with patch("core.call_number_manager.save_config"):
            self.assertIsNotNone(manager.peek_next_number())
        self.assertEqual(config["call_mode"], CallNumberManager.MODE_SMART)

    def test_enhanced_relay_automatically_selects_official_offset_mode(self):
        config = {"call_mode": CallNumberManager.MODE_SMART, "call_used_numbers": []}
        manager = CallNumberManager(config, official_db=_ReceiptDb([]))
        with patch.object(manager, "relay_enhanced_available", return_value=True), \
                patch("core.call_number_manager.save_config"):
            mode = manager.get_mode()
        self.assertEqual(mode, CallNumberManager.MODE_OFFICIAL_OFFSET)
        self.assertEqual(config["call_mode"], CallNumberManager.MODE_OFFICIAL_OFFSET)

    def test_official_offset_numbers_stay_at_least_ten_apart(self):
        config = {
            "call_mode": CallNumberManager.MODE_OFFICIAL_OFFSET,
            "call_used_numbers": [],
            "call_last_issued_no": 50,
        }
        manager = CallNumberManager(config, official_db=_ReceiptDb([
            {"order_no": "#20", "observed_at": "2026-08-08 11:00:00", "payment_status": "paid"},
        ]))
        with patch.object(manager, "relay_enhanced_available", return_value=True), \
                patch("core.call_number_manager.save_config"):
            chosen = manager.get_next_number()
        self.assertIsNotNone(chosen)
        self.assertGreaterEqual(abs(chosen - 50), 10)

    def test_official_offset_avoids_each_of_previous_five_numbers(self):
        config = {
            "call_mode": CallNumberManager.MODE_OFFICIAL_OFFSET,
            "call_used_numbers": [],
            "call_recent_numbers": [50, 70, 90, 110, 130],
        }
        manager = CallNumberManager(config)
        available = manager._official_offset_candidates(set(range(40, 141)))
        self.assertTrue(all(
            all(abs(number - previous) >= 10 for previous in config["call_recent_numbers"])
            for number in available
        ))
        self.assertNotIn(59, available)
        self.assertNotIn(121, available)

    def test_high_offset_pool_is_capped_at_200(self):
        config = {
            "call_mode": CallNumberManager.MODE_OFFICIAL_OFFSET,
            "call_used_numbers": [],
        }
        manager = CallNumberManager(config, official_db=_ReceiptDb([
            {"order_no": "#100", "observed_at": "2026-08-08 11:00:00", "payment_status": "paid"},
        ]))
        with patch("core.call_number_manager.datetime", _FixedDateTime):
            context = manager._official_number_context()
        self.assertEqual((min(context["high"]), max(context["high"])), (130, 200))

    def test_daily_pool_is_not_cleared_when_smart_slot_changes(self):
        config = {
            "call_mode": CallNumberManager.MODE_SMART,
            "call_used_numbers": [55],
            "call_pool_date": "2026-08-08",
        }
        manager = CallNumberManager(config)
        with patch("core.call_number_manager.datetime", _EveningDateTime), \
                patch("core.call_number_manager.save_config"):
            chosen = manager._gen_smart_number()
        self.assertIn(55, manager._used_numbers)
        self.assertGreaterEqual(chosen, 200)
        self.assertLessEqual(chosen, 300)

    def test_mode_switch_keeps_shared_daily_pool(self):
        config = {
            "call_mode": CallNumberManager.MODE_SMART,
            "call_used_numbers": [55],
            "call_pool_date": "2026-08-08",
            "custom_start_no": 50,
            "custom_end_no": 60,
            "custom_is_seq": False,
        }
        manager = CallNumberManager(config)
        with patch("core.call_number_manager.save_config"):
            manager.set_mode(CallNumberManager.MODE_CUSTOM)
            chosen = manager._gen_custom_number()
        self.assertIn(55, manager._used_numbers)
        self.assertIn(chosen, set(range(50, 61)))

    def test_pool_rolls_only_when_calendar_day_changes(self):
        config = {
            "call_mode": CallNumberManager.MODE_SMART,
            "call_used_numbers": [55, 66],
            "call_recent_numbers": [55, 66],
            "call_last_issued_no": 66,
            "call_pool_date": "2026-08-07",
        }
        with patch("core.call_number_manager.datetime", _FixedDateTime):
            manager = CallNumberManager(config)
        self.assertEqual(manager._used_numbers, set())
        self.assertEqual(manager._recent_issued_numbers, [])
        self.assertIsNone(manager._last_issued_number)

    def test_mode_one_early_morning_and_evening_boundaries(self):
        manager = CallNumberManager({"call_mode": CallNumberManager.MODE_SMART})
        with patch("core.call_number_manager.datetime", _MidnightDateTime):
            self.assertEqual(manager._get_current_time_slot(), "morning")
        with patch("core.call_number_manager.datetime", _EveningDateTime):
            self.assertEqual(manager._get_current_time_slot(), "evening")


if __name__ == "__main__":
    unittest.main()
