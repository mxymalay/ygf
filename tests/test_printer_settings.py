import unittest
from unittest.mock import patch

from core.printer import ReceiptPrinter


class PrinterSettingsTests(unittest.TestCase):
    def setUp(self):
        self.sale = {
            "shop_name": "测试店",
            "shop_subtitle": "门店",
            "call_no": "12",
            "total_price": 10.0,
            "cart_items": [
                {
                    "type": "soup",
                    "name": "经典骨汤",
                    "weight": 0.2,
                    "unit_price": 50.0,
                    "price": 10.0,
                    "tag": "微辣",
                }
            ],
        }

    def test_narrow_paper_uses_configured_separator_width(self):
        printer = ReceiptPrinter(
            {
                "printer_chars_per_line": 32,
                "printer_paper_width_mm": 58,
                "printer_auto_cut_enabled": False,
                "printer_feed_lines": 0,
                "printer_customer_title": "顾客单 {call_no}",
            }
        )
        raw = printer._build_customer_receipt(self.sale)
        self.assertGreaterEqual(raw.count(b"-" * 32), 5)
        self.assertNotIn(b"-" * 48, raw)
        self.assertIn("顾客单 12".encode("gbk"), raw)

    def test_copies_and_document_switches_are_applied(self):
        config = {
            "printer_chars_per_line": 48,
            "printer_customer_enabled": False,
            "printer_kitchen_enabled": True,
            "printer_kitchen_copies": 2,
            "printer_auto_cut_enabled": False,
            "printer_feed_lines": 0,
        }
        printer = ReceiptPrinter(config)
        sent = []
        with patch.object(printer, "_send_raw_to_windows", side_effect=lambda raw: sent.append(raw) or True):
            self.assertTrue(printer.print_receipt(self.sale))
        self.assertEqual(len(sent), 1)
        # Each kitchen copy starts with ESC @; the disabled customer copy does
        # not contribute another ticket.
        self.assertEqual(sent[0].count(ReceiptPrinter.INIT), 2)

    def test_manual_reprint_can_override_automatic_switch(self):
        config = {
            "printer_customer_enabled": False,
            "printer_customer_copies": 1,
            "printer_auto_cut_enabled": False,
            "printer_feed_lines": 0,
        }
        printer = ReceiptPrinter(config)
        sent = []
        with patch.object(printer, "_send_raw_to_windows", side_effect=lambda raw: sent.append(raw) or True):
            self.assertTrue(
                printer.print_receipt(
                    self.sale, print_type="customer", respect_settings=False
                )
            )
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].count(ReceiptPrinter.INIT), 1)

    def test_official_v2_profile_contains_new_ticket_fields(self):
        printer = ReceiptPrinter(
            {
                "printer_template_profile": "official_v2",
                "printer_chars_per_line": 48,
                "printer_service_phone": "400-6058-777",
                "printer_operator": "操作员甲",
                "printer_auto_cut_enabled": False,
                "printer_feed_lines": 0,
            }
        )
        sale = dict(self.sale)
        sale.update({"payment_method": "shouqianba", "order_id": "ORDER-123"})
        customer = printer._build_customer_receipt(sale)
        kitchen = printer._build_kitchen_slip(sale, sale["cart_items"][0], 1)
        self.assertIn("订单号：ORDER-123".encode("gbk"), customer)
        self.assertIn("加盟电话：400-6058-777".encode("gbk"), customer)
        self.assertIn("实付".encode("gbk"), customer)
        self.assertIn("操作人：操作员甲".encode("gbk"), kitchen)
        self.assertIn("经典骨汤（KG）".encode("gbk"), kitchen)
        self.assertIn("0.200".encode("gbk"), kitchen)
        self.assertIn("重量：0.200 kg".encode("gbk"), kitchen)

    def test_bundled_logo_is_emitted_only_for_new_template(self):
        printer = ReceiptPrinter(
            {
                "printer_template_profile": "official_v2",
                "printer_logo_enabled": True,
                "printer_auto_cut_enabled": False,
                "printer_feed_lines": 0,
            }
        )
        raw = printer._build_customer_receipt(self.sale)
        self.assertIn(b"\x1d\x76\x30\x00", raw)

    def test_official_kitchen_numbers_multiple_slips(self):
        printer = ReceiptPrinter(
            {
                "printer_template_profile": "official_v2",
                "printer_logo_enabled": False,
                "printer_auto_cut_enabled": False,
                "printer_feed_lines": 0,
            }
        )
        second = {"type": "soup", "name": "酸汤", "weight": 0.3, "price": 15.0}
        sale = dict(self.sale)
        sale["cart_items"] = list(self.sale["cart_items"]) + [second]
        first_raw = printer._build_kitchen_slip(sale, sale["cart_items"][0], 1)
        second_raw = printer._build_kitchen_slip(sale, sale["cart_items"][1], 2)
        self.assertIn("取餐号：12 - 1".encode("gbk"), first_raw)
        self.assertIn("取餐号：12 - 2".encode("gbk"), second_raw)


if __name__ == "__main__":
    unittest.main()
