import unittest
from types import SimpleNamespace
from unittest.mock import patch

from config import DEFAULT_CONFIG
from ui.login_window import check_ygf_official_running
from utils.window_utils import (
    apply_official_window_selection,
    detect_foreground_pos_channel,
    is_official_window_configured,
)


class OfficialWindowSelectionTests(unittest.TestCase):
    def test_window_identity_requires_explicit_selection(self):
        config = dict(DEFAULT_CONFIG)
        self.assertFalse(is_official_window_configured(config))

        config["official_pos_window_keywords"] = [u"杨国福"]
        self.assertFalse(is_official_window_configured(config))

        config["official_pos_window_configured"] = True
        self.assertTrue(is_official_window_configured(config))

    def test_selection_persists_title_prefix_and_process(self):
        config = dict(DEFAULT_CONFIG)
        info = {
            "title": u"杨国福官方 POS - 收银台",
            "process_name": "yangguofu.exe",
            "class_name": "Qt5QWindowIcon",
            "pid": 1234,
            "hwnd": 5678,
        }
        self.assertTrue(apply_official_window_selection(config, info))
        self.assertTrue(is_official_window_configured(config))
        self.assertEqual(config["official_pos_window_keywords"], [u"杨国福官方 POS"])
        self.assertEqual(config["official_pos_process_keywords"], ["yangguofu.exe"])
        self.assertEqual(config["official_pos_window_title"], info["title"])

    def test_login_detection_delegates_to_configured_window(self):
        config = dict(DEFAULT_CONFIG)
        config["official_pos_window_configured"] = True
        config["official_pos_window_keywords"] = [u"官方"]
        with patch("ui.login_window.find_official_window_handle", return_value=100):
            self.assertTrue(check_ygf_official_running(config))
        with patch("ui.login_window.find_official_window_handle", return_value=None):
            self.assertFalse(check_ygf_official_running(config))

    def test_foreground_probe_distinguishes_private_and_official_windows(self):
        class FakeUser32:
            foreground = 200

            def GetForegroundWindow(self):
                return self.foreground

            def GetAncestor(self, hwnd, _flag):
                return hwnd

            def GetWindowTextLengthW(self, _hwnd):
                return len("Official POS")

            def GetWindowTextW(self, _hwnd, buffer, _length):
                buffer.value = "Official POS"

            def GetWindowThreadProcessId(self, _hwnd, pid):
                pid.value = 1234

            def GetClassNameW(self, _hwnd, buffer, _length):
                buffer.value = "Qt5QWindowIcon"
                return len(buffer.value)

        fake_user32 = FakeUser32()
        main_window = SimpleNamespace(winId=lambda: 100)
        config = {
            "official_pos_window_configured": True,
            "official_pos_window_keywords": ["official"],
        }
        with patch("utils.window_utils.user32", fake_user32):
            self.assertFalse(detect_foreground_pos_channel(main_window, config))
            fake_user32.foreground = 100
            self.assertTrue(detect_foreground_pos_channel(main_window, config))
            fake_user32.foreground = 300
            self.assertIsNone(detect_foreground_pos_channel(main_window, config))


if __name__ == "__main__":
    unittest.main()
