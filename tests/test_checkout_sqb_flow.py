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


class _TrackingCallManager(_FakeCallManager):
    def __init__(self, events):
        self.events = events

    def peek_next_number(self):
        self.events.append("peek")
        return 50

    def get_next_number(self):
        self.events.append("consume_call_no")
        return 50


class _PaymentCompletingDialog:
    def __init__(self, _sale_data, on_payment_callback, **_kwargs):
        self._on_payment_callback = on_payment_callback

    def exec_(self):
        return self._on_payment_callback("cash")


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

    def test_restored_order_toast_waits_until_sale_page_is_visible(self):
        config = {"unit_price": 47.6, "price_unit": "per_jin"}
        draft = {
            "order_id": "2608061200000000000000000",
            "temp_order_no": "TMP-1",
            "cart_items": [{"type": "item", "name": "测试菜品", "qty": 1}],
        }

        with patch.object(SaleWidget, "_build_ui", lambda _self: None), patch.object(
            SaleWidget, "_refresh_previous_order_card", lambda _self: None
        ), patch.object(SaleWidget, "_setup_scale", lambda _self: None), patch.object(
            SaleWidget, "refresh_call_number_display", lambda _self: None
        ), patch.object(SaleWidget, "_update_price_display", lambda _self: None), patch(
            "ui.sale_widget.ReceiptPrinter", return_value=SimpleNamespace()
        ), patch("ui.sale_widget.load_draft", return_value=draft), patch.object(
            SaleWidget, "_show_toast"
        ) as show_toast:
            widget = SaleWidget(config, SimpleNamespace(), _FakeCallManager())
            self.addCleanup(widget.deleteLater)

            self.assertTrue(widget._draft_restore_notice_pending)
            self.app.processEvents()
            show_toast.assert_not_called()

            widget.show_pending_draft_restore_notice()
            show_toast.assert_called_once_with(u"已恢复上次未结账订单，请核对后再收款")
            self.assertFalse(widget._draft_restore_notice_pending)

    def test_call_number_is_consumed_only_after_order_insert_succeeds(self):
        events = []

        class Db(object):
            def get_sale_by_order_id(self, _order_id):
                return None

            def insert_sale(self, **_kwargs):
                events.append("insert_sale")
                return {"id": 1}, True

            def mark_print_result(self, *_args):
                events.append("mark_print")

        printer = SimpleNamespace(print_receipt=lambda _sale: True, last_error="")
        with patch.object(SaleWidget, "_build_ui", lambda _self: None), patch.object(
            SaleWidget, "_restore_draft", lambda _self: None
        ), patch.object(SaleWidget, "_setup_scale", lambda _self: None), patch.object(
            SaleWidget, "refresh_call_number_display", lambda _self: None
        ), patch.object(SaleWidget, "_refresh_previous_order_card", lambda _self, *_args: None), patch.object(
            SaleWidget, "_on_clear", lambda _self, **_kwargs: None
        ), patch.object(SaleWidget, "_refresh_mixed_hint_after_checkout", lambda _self: None), patch(
            "ui.sale_widget.ReceiptPrinter", return_value=printer
        ), patch("ui.checkout_dialog.CheckoutDialog", _PaymentCompletingDialog):
            widget = SaleWidget({}, Db(), _TrackingCallManager(events))
            self.addCleanup(widget.deleteLater)
            widget.cart_items = [{"name": "测试菜品", "price": 1.0, "qty": 1}]
            widget._open_checkout_dialog(mode="CASH")

        self.assertLess(events.index("insert_sale"), events.index("consume_call_no"))

    def test_failed_order_insert_does_not_consume_a_call_number(self):
        events = []

        class Db(object):
            def get_sale_by_order_id(self, _order_id):
                return None

            def insert_sale(self, **_kwargs):
                events.append("insert_sale")
                raise OSError("disk full")

        with patch.object(SaleWidget, "_build_ui", lambda _self: None), patch.object(
            SaleWidget, "_restore_draft", lambda _self: None
        ), patch.object(SaleWidget, "_setup_scale", lambda _self: None), patch.object(
            SaleWidget, "refresh_call_number_display", lambda _self: None
        ), patch.object(SaleWidget, "_refresh_mixed_hint_after_checkout", lambda _self: None), patch(
            "ui.sale_widget.ReceiptPrinter", return_value=SimpleNamespace()
        ), patch("ui.checkout_dialog.CheckoutDialog", _PaymentCompletingDialog), patch(
            "ui.sale_widget.show_warning"
        ):
            widget = SaleWidget({}, Db(), _TrackingCallManager(events))
            self.addCleanup(widget.deleteLater)
            widget.cart_items = [{"name": "测试菜品", "price": 1.0, "qty": 1}]
            widget._open_checkout_dialog(mode="CASH")

        self.assertIn("insert_sale", events)
        self.assertNotIn("consume_call_no", events)


if __name__ == "__main__":
    unittest.main()
