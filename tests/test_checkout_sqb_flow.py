import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from ui.sale_widget import SaleWidget


class _FakeCallManager:
    def get_mode(self):
        return "smart"

    def peek_next_number(self):
        return 50


class CheckoutSqbFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_scan_code_starts_log_probe_before_sending_amount(self):
        config = {"unit_price": 47.6, "price_unit": "per_jin"}
        events = []

        with patch.object(SaleWidget, "_build_ui", lambda _self: None), patch.object(
            SaleWidget, "_restore_draft", lambda _self: None
        ), patch.object(SaleWidget, "_setup_scale", lambda _self: None), patch.object(
            SaleWidget, "refresh_call_number_display", lambda _self: None
        ), patch("ui.sale_widget.ReceiptPrinter", return_value=SimpleNamespace()), patch(
            "core.shouqianba_sender.begin_sqb_payment_probe",
            side_effect=lambda amount, cfg: events.append(("begin", amount, cfg)),
        ), patch(
            "core.shouqianba_sender.send_shouqianba_amount",
            side_effect=lambda amount, cfg: events.append(("send", amount, cfg)),
        ), patch(
            "ui.checkout_dialog.CheckoutDialog"
        ) as dialog_type:
            dialog_type.return_value.exec_.side_effect = lambda: events.append(("dialog",))
            widget = SaleWidget(config, SimpleNamespace(), _FakeCallManager())
            self.addCleanup(widget.deleteLater)
            widget.cart_items = [{"name": "1元饮料", "price": 1.0, "qty": 1}]

            widget._open_checkout_dialog(mode="SCAN_CODE")

        self.assertEqual([entry[0] for entry in events], ["begin", "send", "dialog"])
        self.assertEqual(events[0][1], 1.0)
        self.assertIs(events[0][2], config)


if __name__ == "__main__":
    unittest.main()
