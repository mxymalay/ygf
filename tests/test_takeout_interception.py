import os
import socket
import tempfile
import time
import unittest
from unittest import mock

from PyQt5.QtCore import QCoreApplication

from core.takeout_interceptor import (
    TakeoutPrintInterceptor,
    build_takeout_escpos_ticket,
    escpos_payload_to_text,
    parse_and_sort_takeout_text,
    parse_official_pos_text,
)
from core.takeout_jobs import TakeoutJobStore
from core.takeout_capture import capture_print_payload
from core.takeout_proxy_host import TakeoutProxyHost, _is_process_alive
from core.takeout_relay import MODE_COMPATIBILITY, enhanced_mode_eligibility, validate_relay_config


SAMPLE = """美团外卖 #18存根联
[菜品明细]
1. 肥牛 x 2 ￥30.00
2. 可乐 x 1 ￥4.50
实付：￥34.50
地址：测试路 1 号
订单号：100088921831920
"""


class TakeoutInterceptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_parser_excludes_metadata_and_keeps_quantity(self):
        result = parse_and_sort_takeout_text(SAMPLE)
        self.assertTrue(result["is_waimai"])
        self.assertEqual(result["full_order_id"], "100088921831920")
        self.assertEqual(result["item_count"], 3)
        self.assertIn("肥牛", result["sorted_text"])
        self.assertNotIn("订单号：100088921831920\n  •", result["sorted_text"])

    def test_raw_print_capture_writes_binary_and_metadata_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            parsed = parse_and_sort_takeout_text(SAMPLE)
            path = capture_print_payload(
                b"\x1b@" + SAMPLE.encode("gbk") + b"\x1dV\x01",
                dict(parsed, payload_type="raw_escpos"),
                {"takeout_capture_enabled": True, "takeout_capture_max_files": 4},
                capture_dir=directory,
            )
            self.assertTrue(path.endswith(".bin"))
            self.assertTrue(os.path.exists(path))
            metadata_path = path[:-4] + ".json"
            self.assertTrue(os.path.exists(metadata_path))
            with open(metadata_path, "r", encoding="utf-8") as stream:
                metadata = __import__("json").load(stream)
            self.assertEqual(metadata["payload_type"], "raw_escpos")
            self.assertEqual(metadata["payload_size"], os.path.getsize(path))
    def test_amount_is_available_but_payment_without_explicit_evidence_is_unknown(self):
        result = parse_and_sort_takeout_text(SAMPLE)
        self.assertEqual(result["order_amount"], 34.50)
        self.assertTrue(result["amount_valid"])
        self.assertEqual(result["payment_status"], "unknown")

    def test_official_v2_visible_labels_are_used_without_template_variables(self):
        text = ("美团外卖\n订单号：OFFICIAL-1\n订单时间：2026-08-07 12:00:00\n"
                "肥牛 x 1\n合计 45.50\n应付 45.50\n实付 45.50")
        result = parse_and_sort_takeout_text(text)
        self.assertEqual(result["order_amount"], 45.50)
        self.assertTrue(result["amount_valid"])
        self.assertEqual(result["payment_status"], "unknown")

    def test_dinein_official_receipt_uses_generic_key_and_keeps_payment_unknown(self):
        text = ("POS点餐 堂食\n订单号：DINE-1\n肥牛 x 1\n"
                "合计 45.50\n应付 45.50\n实付 45.50")
        result = parse_official_pos_text(text)
        self.assertEqual(result["receipt_kind"], "dinein")
        self.assertEqual(result["receipt_key"], "official:DINE-1")
        self.assertEqual(result["order_amount"], 45.50)
        self.assertEqual(result["payment_status"], "unknown")
        self.assertEqual(result["key_confidence"], "high")

    def test_custom_official_pos_field_mapping_can_translate_vendor_labels(self):
        text = "POS点餐\n流水号：VENDOR-7\n应收金额：¥28.00\n状态：已结账\n肥牛 x 1"
        result = parse_official_pos_text(text, {
            "official_pos_field_mapping": {
                "order_id_labels": ["流水号"],
                "amount_labels": ["应收金额"],
                "paid_keywords": ["状态：已结账"],
                "dinein_keywords": ["POS点餐"],
            }
        })
        self.assertEqual(result["receipt_kind"], "dinein")
        self.assertEqual(result["full_order_id"], "VENDOR-7")
        self.assertEqual(result["order_amount"], 28.0)
        self.assertEqual(result["payment_status"], "paid")

    def test_generic_receipt_allows_enhanced_mode_only_with_explicit_paid_marker(self):
        text = ("POS点餐 堂食\n订单号：DINE-2\n肥牛 x 1\n"
                "合计 45.50\n应付 45.50\n实付 45.50\n支付成功")
        parsed = parse_official_pos_text(text)
        eligible = enhanced_mode_eligibility(
            {"takeout_interceptor_enabled": True}, {"running": True}, parsed
        )
        self.assertTrue(eligible["eligible"])

    def test_unknown_external_print_can_be_confirmed_by_later_paid_print(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TakeoutJobStore(os.path.join(directory, "jobs.json"))
            first = parse_official_pos_text(
                "美团外卖\n订单号：TRANS-1\n肥牛 x 1\n合计 12.00\n实付 12.00"
            )
            job, created = store.create_or_get(first, first["raw_text"])
            self.assertTrue(created)
            paid = dict(first, payment_status="paid", payment_status_confidence="high", payment_status_evidence="支付成功")
            updated, created_again = store.create_or_get(paid, paid["raw_text"])
            self.assertFalse(created_again)
            self.assertEqual(updated["payment_status"], "paid")
            self.assertFalse(updated.get("conflict_detected", False))

    def test_explicit_payment_marker_is_required_for_enhanced_mode(self):
        parsed = parse_and_sort_takeout_text(SAMPLE + "\n支付成功")
        self.assertEqual(parsed["payment_status"], "paid")
        eligible = enhanced_mode_eligibility(
            {"takeout_interceptor_enabled": True},
            {"running": True},
            parsed,
        )
        self.assertTrue(eligible["eligible"])

    def test_missing_payment_evidence_stays_compatibility(self):
        parsed = parse_and_sort_takeout_text(SAMPLE)
        eligible = enhanced_mode_eligibility(
            {"takeout_interceptor_enabled": True},
            {"running": True},
            parsed,
        )
        self.assertFalse(eligible["eligible"])
        self.assertEqual(eligible["mode"], MODE_COMPATIBILITY)

    def test_relay_validation_blocks_queue_physical_loop(self):
        report = validate_relay_config({
            "takeout_proxy_port": 9101,
            "takeout_proxy_queue_name": "Same",
            "printer_name": "same",
        }, check_windows=False)
        self.assertFalse(report["ok"])
        self.assertTrue(any("回环" in item for item in report["errors"]))

    def test_escpos_text_and_ticket_keep_printable_content(self):
        raw = b"\x1b@" + SAMPLE.encode("gbk") + b"\x1dV\x01"
        text = escpos_payload_to_text(raw)
        self.assertIn("肥牛", text)
        ticket = build_takeout_escpos_ticket("【美团外卖 #18 制作单】\n肥牛", {}, "kitchen")
        self.assertIn("肥牛".encode("gbk"), ticket)

    def test_local_proxy_receives_raw_order(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        proxy = TakeoutPrintInterceptor({"takeout_interceptor_enabled": True, "takeout_proxy_port": port})
        received = []
        proxy.order_intercepted.connect(received.append)
        self.assertTrue(proxy.start())
        try:
            client = socket.create_connection(("127.0.0.1", port), timeout=2)
            client.sendall(SAMPLE.encode("gbk"))
            client.close()
            deadline = time.time() + 2
            while not received and time.time() < deadline:
                self.app.processEvents()
                time.sleep(0.02)
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0]["order_no"], "#18")
        finally:
            proxy.stop()

    def test_job_store_deduplicates_without_touching_sales_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TakeoutJobStore(os.path.join(directory, "jobs.json"))
            parsed = parse_and_sort_takeout_text(SAMPLE)
            first, created = store.create_or_get(parsed, SAMPLE)
            second, created_again = store.create_or_get(parsed, SAMPLE)
            self.assertTrue(created)
            self.assertFalse(created_again)
            self.assertEqual(first["id"], second["id"])
            updated = store.update_print_result(first["id"], True, 2)
            self.assertEqual(updated["last_result"], "PRINTED")
            self.assertEqual(updated["print_count"], 2)

    def test_job_store_uses_stable_fingerprint_when_raw_print_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TakeoutJobStore(os.path.join(directory, "jobs.json"))
            first = parse_and_sort_takeout_text(SAMPLE)
            second = dict(first)
            second["raw_text"] = SAMPLE.replace("实付：￥34.50", "实付：￥34.50\n打印时间：12:01")
            one, created = store.create_or_get(first, SAMPLE)
            two, created_again = store.create_or_get(second, second["raw_text"])
            self.assertTrue(created)
            self.assertFalse(created_again)
            self.assertEqual(one["id"], two["id"])

    def test_verified_amount_total_excludes_unknown_payment_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TakeoutJobStore(os.path.join(directory, "jobs.json"))
            parsed = parse_and_sort_takeout_text(SAMPLE + "\n支付成功")
            paid, _ = store.create_or_get(parsed, SAMPLE + "\n支付成功")
            unknown_parsed = parse_and_sort_takeout_text(SAMPLE)
            store.create_or_get(unknown_parsed, SAMPLE + "-unknown")
            self.assertEqual(store.get_verified_amount_total(), paid["order_amount"])

    def test_same_order_amount_change_is_audited_without_recounting(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TakeoutJobStore(os.path.join(directory, "jobs.json"))
            first = parse_and_sort_takeout_text(SAMPLE + "\n支付成功")
            second = dict(first)
            second["order_amount"] = 99.0
            one, _ = store.create_or_get(first, SAMPLE + "\n支付成功")
            two, created = store.create_or_get(second, SAMPLE + "\n打印重试")
            self.assertFalse(created)
            self.assertEqual(one["id"], two["id"])
            self.assertTrue(two.get("conflict_detected"))

    def test_detached_host_forwards_without_a_widget(self):
        """The host owns forwarding; the PyQt page is not in this path."""
        config = {
            "takeout_interceptor_enabled": True,
            "takeout_proxy_port": 19091,
            "takeout_proxy_queue_name": "YGF 外卖中继",
            "printer_name": "真实热敏打印机",
            "takeout_auto_print": True,
            "takeout_kitchen_copies": 1,
            "takeout_cust_copies": 1,
            "takeout_categories": [{"id": "food", "name": "菜品", "keywords": ["牛", "可乐"]}],
        }

        class FakePrinter:
            sent = []
            last_error = ""

            def __init__(self, _config):
                pass

            def print_raw(self, data):
                self.sent.append(data)
                return True

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("core.takeout_proxy_host.load_config", return_value=config), \
                    mock.patch("core.takeout_proxy_host.ReceiptPrinter", FakePrinter):
                host = TakeoutProxyHost()
                host.jobs = TakeoutJobStore(os.path.join(directory, "jobs.json"))
                host._handle_order({"raw_text": SAMPLE})

            job = host.jobs.get_recent(1)[0]
            self.assertEqual(job["last_result"], "PRINTED")
            self.assertEqual(job["print_count"], 2)
            self.assertEqual(len(FakePrinter.sent), 1)
            self.assertIn("肥牛".encode("gbk"), FakePrinter.sent[0])

    def test_parse_failure_forwards_original_payload(self):
        config = {
            "takeout_interceptor_enabled": True,
            "takeout_proxy_port": 19092,
            "takeout_proxy_queue_name": "YGF 外卖中继",
            "printer_name": "真实热敏打印机",
        }

        class FakePrinter:
            sent = []
            last_error = ""

            def __init__(self, _config):
                pass

            def print_raw(self, data):
                self.sent.append(data)
                return True

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("core.takeout_proxy_host.load_config", return_value=config), \
                    mock.patch("core.takeout_proxy_host.ReceiptPrinter", FakePrinter):
                host = TakeoutProxyHost()
                host.jobs = TakeoutJobStore(os.path.join(directory, "jobs.json"))
                host.running = True
                host._handle_order({"raw_text": "binary", "raw_payload": b"ORIGINAL", "parse_failed": True})
            self.assertEqual(FakePrinter.sent, [b"ORIGINAL"])

    def test_stale_relay_pid_system_error_is_treated_as_not_running(self):
        # Win7/PyInstaller can surface SystemError from os.kill(pid, 0) for
        # a stale detached-host PID.  That state must not abort POS startup.
        with mock.patch("core.takeout_proxy_host.os.kill", side_effect=SystemError("kill error")):
            self.assertFalse(_is_process_alive(12345))


if __name__ == "__main__":
    unittest.main()
