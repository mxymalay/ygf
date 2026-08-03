import os
import socket
import tempfile
import time
import unittest

from PyQt5.QtCore import QCoreApplication

from core.takeout_interceptor import (
    TakeoutPrintInterceptor,
    build_takeout_escpos_ticket,
    escpos_payload_to_text,
    parse_and_sort_takeout_text,
)
from core.takeout_jobs import TakeoutJobStore


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


if __name__ == "__main__":
    unittest.main()
