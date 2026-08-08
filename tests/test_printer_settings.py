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

    def test_non_soup_order_prints_compact_paid_ticket(self):
        printer = ReceiptPrinter(
            {
                "printer_chars_per_line": 48,
                "printer_auto_cut_enabled": False,
                "printer_feed_lines": 0,
            }
        )
        sale = {
            "call_no": "018",
            "created_at": "2026-08-08 12:45:17",
            "total_price": 12.50,
            "cart_items": [
                {"type": "drink", "name": "1元饮料", "qty": 1, "price": 1.00},
                {"type": "skewer", "name": "精品串", "qty": 2, "price": 11.50},
            ],
        }
        sent = []
        with patch.object(printer, "_send_raw_to_windows", side_effect=lambda raw: sent.append(raw) or True):
            self.assertTrue(printer.print_receipt(sale))
        self.assertEqual(len(sent), 1)
        raw = sent[0]
        self.assertIn("成功收款：12.50元".encode("gbk"), raw)
        self.assertIn("取餐号： 018".encode("gbk"), raw)
        self.assertIn("类型：此订单不含汤底".encode("gbk"), raw)
        self.assertIn("下单时间：2026-08-08 12:45:17".encode("gbk"), raw)
        self.assertIn(ReceiptPrinter.DOUBLE_SIZE, raw)
        self.assertEqual(raw.count(ReceiptPrinter.INIT), 1)

    def test_non_soup_ticket_uses_editable_template(self):
        printer = ReceiptPrinter(
            {
                "printer_non_soup_template": (
                    "[C][B]收款:{amount}\n[L][S]取号:{call_no}\n"
                    "[L][S]{order_type}\n[L][S]时间:{created_at}"
                ),
                "printer_auto_cut_enabled": False,
                "printer_feed_lines": 0,
            }
        )
        sale = {
            "call_no": "018",
            "created_at": "2026-08-08 12:45:17",
            "total_price": 12.5,
            "cart_items": [{"type": "drink", "name": "饮料", "qty": 1, "price": 12.5}],
        }
        raw = printer._build_non_soup_receipt(sale)
        self.assertIn("收款:12.50".encode("gbk"), raw)
        self.assertIn("取号:018".encode("gbk"), raw)
        self.assertIn("此订单不含汤底".encode("gbk"), raw)
        self.assertIn("时间:2026-08-08 12:45:17".encode("gbk"), raw)
        self.assertIn(ReceiptPrinter.FONT_SMALL, raw)

    def test_non_soup_ticket_can_be_disabled_without_affecting_manual_reprint(self):
        printer = ReceiptPrinter(
            {
                "printer_non_soup_enabled": False,
                "printer_auto_cut_enabled": False,
                "printer_feed_lines": 0,
            }
        )
        sale = {
            "call_no": "018",
            "total_price": 1.0,
            "cart_items": [{"type": "drink", "name": "饮料", "qty": 1, "price": 1.0}],
        }
        sent = []
        with patch.object(printer, "_send_raw_to_windows", side_effect=lambda raw: sent.append(raw) or True):
            self.assertTrue(printer.print_receipt(sale))
            self.assertTrue(printer.print_receipt(sale, respect_settings=False))
        self.assertEqual(len(sent), 1)

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
        self.assertNotIn("0.200 kg".encode("gbk"), kitchen)
        self.assertIn(b"\x1d\x21\x11", customer)
        self.assertIn(b"\x1d\x21\x11", kitchen)
        self.assertNotIn("重量：".encode("gbk"), kitchen)

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
        self.assertIn("POS#12".encode("gbk"), first_raw)
        self.assertIn("POS#12".encode("gbk"), second_raw)
        self.assertNotIn("POS#12 - 1".encode("gbk"), first_raw)
        self.assertNotIn("POS#12 - 2".encode("gbk"), second_raw)

    def test_official_v3_uses_captured_logo_and_official_labels(self):
        printer = ReceiptPrinter(
            {
                "printer_template_profile": "official_v3",
                "printer_logo_enabled": True,
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
        self.assertIn(b"\x1d\x76\x30\x03\x1e\x00\x4a\x00", customer)
        self.assertIn("取餐号:0012    [POS点餐]".encode("gbk"), customer)
        self.assertIn("订单号:  ORDER-123".encode("gbk"), customer)
        self.assertIn("加盟咨询热线：400-6058-777".encode("gbk"), customer)
        self.assertIn("取餐号:0012".encode("gbk"), kitchen)
        self.assertIn("操作人:   操作员甲".encode("gbk"), kitchen)


if __name__ == "__main__":
    unittest.main()
