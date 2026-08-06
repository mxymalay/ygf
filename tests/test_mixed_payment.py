import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QPushButton

from core.database import Database
from core.payment_utils import format_payment_breakdown, payment_display_label
from ui.cash_dialog import CashCalculatorDialog
from ui.checkout_dialog import MixedPaymentChoiceDialog


class MixedPaymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_payment_breakdown_formatting(self):
        breakdown = {"cash": 20, "shouqianba": 15}
        self.assertEqual(
            format_payment_breakdown(json.dumps(breakdown, ensure_ascii=False)),
            "现金 ¥20.00 + 收钱吧 ¥15.00",
        )
        self.assertEqual(
            payment_display_label("mixed", breakdown),
            "混合支付（现金 ¥20.00 + 收钱吧 ¥15.00）",
        )

    def test_mixed_payment_stats_split_amounts_by_component(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(os.path.join(folder, "sales.db"))
            record, created = db.insert_sale(
                weight_kg=0.2,
                unit_price=47.6,
                price_unit="per_jin",
                total_price=35.0,
                payment_method="mixed",
                payment_breakdown_json=json.dumps({"cash": 20, "shouqianba": 15}),
                order_id="mixed-1",
            )
            self.assertTrue(created)
            stats = {row["pm"]: row for row in db.get_payment_stats_by_date(record["created_at"][:10])}
            self.assertEqual(stats["cash"]["amt"], 20.0)
            self.assertEqual(stats["shouqianba"]["amt"], 15.0)

    def test_cash_dialog_accepts_partial_amount_only_in_partial_mode(self):
        received = []
        dialog = CashCalculatorDialog(
            {"total_price": 35.0},
            allow_partial=True,
            on_amount_confirm=received.append,
        )
        self.addCleanup(dialog.deleteLater)
        dialog.received_amount_str = "20"
        dialog._on_confirm()
        self.assertEqual(received, [20.0])
        self.assertEqual(dialog.result(), dialog.Accepted)

    def test_mixed_choice_dialog_has_distinct_scan_action(self):
        dialog = MixedPaymentChoiceDialog(20.0, 15.0)
        self.addCleanup(dialog.deleteLater)
        buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
        self.assertEqual(set(buttons), {"重输金额", "其他剩余", "扫码剩余"})
        self.assertGreater(buttons["扫码剩余"].minimumWidth(), buttons["其他剩余"].minimumWidth())
        buttons["扫码剩余"].click()
        self.assertEqual(dialog.choice, "scan")


if __name__ == "__main__":
    unittest.main()
