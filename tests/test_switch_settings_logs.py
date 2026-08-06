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

    def test_log_groups_use_adjacent_five_minute_gaps(self):
        entries = [
            {"ts": "2026-08-06 21:10:00"},
            {"ts": "2026-08-06 21:07:00"},
            {"ts": "2026-08-06 20:49:53"},
            {"ts": "2026-08-06 20:46:42"},
            {"ts": "2026-08-06 20:30:00"},
        ]
        groups = SwitchSettingsWidget._log_groups(entries)
        self.assertEqual([len(group) for group in groups], [2, 2, 1])
        self.assertEqual(SwitchSettingsWidget._log_group_range_label(groups[0]), "21:07-21:10")
        self.assertEqual(SwitchSettingsWidget._log_group_range_label(groups[1]), "20:46-20:49")
        self.assertEqual(SwitchSettingsWidget._log_group_range_label(groups[2]), "20:30-20:30")


if __name__ == "__main__":
    unittest.main()
