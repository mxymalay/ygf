import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.switch_settings_widget import SwitchSettingsWidget


class SwitchSettingsLogTests(unittest.TestCase):
    def test_gap_label_is_added_only_after_five_minutes(self):
        newer = {"ts": "2026-08-06 20:20:00"}
        five_minutes = {"ts": "2026-08-06 20:15:00"}
        older = {"ts": "2026-08-06 20:14:59"}

        self.assertEqual(SwitchSettingsWidget._log_gap_label(newer, older), "20:14-20:20")
        self.assertEqual(SwitchSettingsWidget._log_gap_label(newer, five_minutes), "")

    def test_gap_label_handles_invalid_timestamps(self):
        self.assertEqual(
            SwitchSettingsWidget._log_gap_label({"ts": "bad"}, {"ts": "2026-08-06 20:20:00"}),
            "",
        )


if __name__ == "__main__":
    unittest.main()
