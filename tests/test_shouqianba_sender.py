import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ShouqianbaSenderImportTests(unittest.TestCase):
    def test_hotkey_must_contain_only_supported_keys(self):
        from core import shouqianba_sender as sender
        # Avoid exercising Windows keyboard injection in a unit test; validate
        # the supported vocabulary instead.
        self.assertTrue(sender.is_supported_hotkey("Shift+Q"))
        self.assertFalse(sender.is_supported_hotkey("Ctrl+BadKey"))

    def test_keyboard_dependency_is_optional(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = r'''
import builtins

real_import = builtins.__import__

def import_without_keyboard(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "keyboard":
        raise ImportError("simulated missing optional keyboard package")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = import_without_keyboard
import core.shouqianba_sender as sender
assert sender.keyboard is None
'''
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_query_transport_success_is_still_waiting_until_order_is_paid(self):
        from core import shouqianba_sender as sender
        line = (
            '"biz_response":{"result_code":"SUCCESS","data":{'
            '"status":"IN_PROG","order_status":"CREATED",'
            '"total_amount":"100"}}'
        )
        self.assertEqual(sender._classify_sqb_log_text(line, 100, "info"), "WAITING")

    def test_paid_info_record_matches_integer_cent_amount(self):
        from core import shouqianba_sender as sender
        line = (
            '"data":{"status":"SUCCESS","order_status":"PAID",'
            '"total_amount":"100","sn":"7895217483435486"}'
        )
        self.assertEqual(sender._classify_sqb_log_text(line, 100, "info"), "SUCCESS")
        self.assertEqual(sender._classify_sqb_log_text(line, 200, "info"), "UNKNOWN")

    def test_debug_receipt_is_success_only_for_the_expected_yuan_amount(self):
        from core import shouqianba_sender as sender
        text = "ui.upaySuccess:334\n订单总金额：1.00元\n商户订单号：7895217483435486"
        self.assertEqual(sender._classify_sqb_log_text(text, 100, "debug"), "SUCCESS")
        self.assertEqual(sender._classify_sqb_log_text(text, 200, "debug"), "UNKNOWN")

    def test_generic_paycancel_after_success_is_not_a_failure(self):
        from core import shouqianba_sender as sender
        text = "ui.upaySuccess:334\n订单总金额：1.00元\npayCancel ..."
        self.assertEqual(sender._classify_sqb_log_text(text, 100, "debug"), "SUCCESS")
        self.assertEqual(
            sender._classify_sqb_log_text("upay failed:PAY_CANCEL", 100, "debug"),
            "FAILED",
        )

    def test_install_root_discovers_newest_version_logs_without_biz_log(self):
        from core import shouqianba_sender as sender
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "smskv3"
            info_log = root / "v4.0.4" / "logs" / "info" / "info.log"
            debug_log = root / "v4.0.4" / "logs" / "debug" / "debug.log"
            biz_log = root / "v4.0.4" / "logs" / "biz" / "biz.log"
            for path in (info_log, debug_log, biz_log):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")

            config = {"shouqianba_install_dir": str(root)}
            self.assertEqual(sender.discover_shouqianba_install_dir(config), str(root))
            paths = sender.get_shouqianba_log_paths(config)
            self.assertEqual(set(paths), {str(info_log), str(debug_log)})
            self.assertNotIn(str(biz_log), paths)
            valid, message = sender.validate_shouqianba_install_dir(str(root))
            self.assertTrue(valid, message)

    def test_log_tail_ignores_history_then_observes_waiting_and_paid(self):
        from core import shouqianba_sender as sender
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "smskv3"
            info_log = root / "v4.0.4" / "logs" / "info" / "info.log"
            debug_log = root / "v4.0.4" / "logs" / "debug" / "debug.log"
            info_log.parent.mkdir(parents=True, exist_ok=True)
            debug_log.parent.mkdir(parents=True, exist_ok=True)
            # This historical success must be ignored by the initial EOF snapshot.
            info_log.write_text(
                '"status":"SUCCESS","order_status":"PAID","total_amount":"100"\n',
                encoding="utf-8",
            )
            debug_log.write_text("", encoding="utf-8")
            config = {"shouqianba_install_dir": str(root)}

            sender._begin_sqb_log_probe(1.00, config)
            self.assertEqual(sender._get_sqb_log_payment_status(config), "UNKNOWN")

            with info_log.open("a", encoding="utf-8") as handle:
                handle.write(
                    '"status":"IN_PROG","order_status":"CREATED",'
                    '"total_amount":"100"\n'
                )
            self.assertEqual(sender._get_sqb_log_payment_status(config), "WAITING")

            with info_log.open("a", encoding="utf-8") as handle:
                handle.write(
                    '"status":"SUCCESS","order_status":"PAID",'
                    '"total_amount":"100"\n'
                )
            self.assertEqual(sender._get_sqb_log_payment_status(config), "SUCCESS")


if __name__ == "__main__":
    unittest.main()
