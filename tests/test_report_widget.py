import unittest
from unittest.mock import patch

from ui.report_widget import ReportWidget


class _ReportDb:
    events = []

    def get_official_stats_by_date(self, start_date, end_date):
        return {"count": 2, "amount_sum": 73.50}

    def get_relay_mode_events(self, start_date, end_date, limit=500):
        return list(self.events)


class _DummyLabel:
    def __init__(self):
        self.text = None
        self.visible = None
        self.tooltip = None
        self.style = None

    def setText(self, value):
        self.text = value

    def setVisible(self, value):
        self.visible = value

    def setToolTip(self, value):
        self.tooltip = value

    def setStyleSheet(self, value):
        self.style = value


class _DummyCard:
    def __init__(self):
        self._report_status = _DummyLabel()
        self._report_amount = _DummyLabel()
        self._report_count = _DummyLabel()
        self._report_hint = _DummyLabel()
        self._report_question = _DummyLabel()


class ReportOfficialDataTests(unittest.TestCase):
    def test_verified_official_or_mixed_card_uses_green_check(self):
        card = _DummyCard()

        ReportWidget._set_channel_card(
            card, "数据状态：已验证", "¥ 73.50", "订单数量：2", "来源：官方 POS"
        )

        self.assertTrue(card._report_question.visible)
        self.assertEqual(card._report_question.text, "✓")
        self.assertIn("#16A34A", card._report_question.style)

    def test_incomplete_card_keeps_question_mark(self):
        card = _DummyCard()

        ReportWidget._set_channel_card(
            card, "数据状态：不完整风险", "¥ 73.50", "订单数量：2", "存在降级区间",
            risk_text="兼容模式期间可能漏单",
        )

        self.assertTrue(card._report_question.visible)
        self.assertEqual(card._report_question.text, "?")
        self.assertIn("#EA580C", card._report_question.style)

    def test_existing_official_rows_remain_visible_in_compatibility_mode(self):
        widget = ReportWidget.__new__(ReportWidget)
        widget.db = _ReportDb()
        widget.config = {"printer_relay_enabled": False}
        widget.start_date_str = "2026-08-08"
        widget.end_date_str = "2026-08-08"

        with patch("ui.report_widget.validate_relay_config", return_value={"errors": []}):
            result = widget._official_report_summary()

        self.assertTrue(result["available"])
        self.assertEqual(result["summary"]["count"], 2)
        self.assertIn("数据库中已入账", result["source_note"])

    def test_reliability_warning_lists_each_incomplete_interval(self):
        widget = ReportWidget.__new__(ReportWidget)
        widget.db = _ReportDb()
        widget.db.events = [
            {"previous_mode": "enhanced", "new_mode": "compatibility", "reason": "启动自检失败", "created_at": "2026-08-08 09:10:00"},
            {"previous_mode": "compatibility", "new_mode": "enhanced", "reason": "官方订单已验证", "created_at": "2026-08-08 09:30:00"},
            {"previous_mode": "enhanced", "new_mode": "degraded", "reason": "订单号缺失", "created_at": "2026-08-08 11:00:00"},
            {"previous_mode": "degraded", "new_mode": "enhanced", "reason": "恢复验证", "created_at": "2026-08-08 11:20:00"},
        ]
        widget.start_date_str = "2026-08-08"
        widget.end_date_str = "2026-08-08"

        details = widget._mode_reliability_details()

        self.assertEqual(len(details["periods"]), 2)
        self.assertIn("09:10:00", details["warning"])
        self.assertIn("11:00:00", details["warning"])
        self.assertIn("启动自检失败", details["warning"])


if __name__ == "__main__":
    unittest.main()
