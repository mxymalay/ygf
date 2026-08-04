import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from ui.config_migration_dialog import ConfigMigrationDialog


class ConfigMigrationDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selective_choice_returns_checked_keys(self):
        dialog = ConfigMigrationDialog({"items": {"shop_name": "旧店", "unit_price": 88.0}})
        self.addCleanup(dialog.deleteLater)
        dialog.radio_selective.setChecked(True)
        dialog._checks["unit_price"].setChecked(False)
        dialog._confirm()
        self.assertEqual(dialog.choice, "selective")
        self.assertEqual(dialog.selected_keys, ["shop_name"])

    def test_rebuild_choice_has_no_selected_legacy_fields(self):
        dialog = ConfigMigrationDialog({"items": {"shop_name": "旧店"}})
        self.addCleanup(dialog.deleteLater)
        dialog.radio_rebuild.setChecked(True)
        dialog._confirm()
        self.assertEqual(dialog.choice, "rebuild")
        self.assertEqual(dialog.selected_keys, [])


if __name__ == "__main__":
    unittest.main()
