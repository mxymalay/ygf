import json
import os
import tempfile
import unittest
from unittest.mock import patch

import config


class ModularConfigMigrationTests(unittest.TestCase):
    def _paths(self, root):
        settings = os.path.join(root, "settings")
        os.makedirs(settings)
        modules = {
            "sys": os.path.join(settings, "base.json"),
            "printer_relay": os.path.join(settings, "printer_relay.json"),
            "algo": os.path.join(settings, "algo.json"),
            "shouqianba": os.path.join(settings, "shouqianba.json"),
        }
        return settings, modules

    def test_old_full_file_is_split_and_unknown_fields_are_removed(self):
        with tempfile.TemporaryDirectory() as root:
            settings, modules = self._paths(root)
            legacy = os.path.join(root, "settings.json")
            with open(legacy, "w", encoding="utf-8") as stream:
                json.dump(
                    {
                        "scale_port": "COM9",
                        "call_mode": "manual",
                        "call_used_numbers": [12],
                        "obsolete_plugin_setting": "must-not-survive",
                        "simulation_mode": "temporary",
                    },
                    stream,
                )
            template = os.path.join(root, "template.json")
            with patch.object(config, "DATA_DIR", root), patch.object(
                config, "DB_DIR", os.path.join(root, "db")
            ), patch.object(config, "DB_PATH", os.path.join(root, "db", "sales.db")), patch.object(
                config, "LEGACY_DB_PATH", os.path.join(root, "sales.db")
            ), patch.object(
                config, "SETTINGS_DIR", settings
            ), patch.object(config, "CONFIG_FILE", legacy), patch.object(
                config, "TEMPLATE_FILE", template
            ), patch.object(config, "MODULE_FILES", modules):
                loaded = config.load_config()

            self.assertEqual(loaded["scale_port"], "COM9")
            self.assertEqual(loaded["call_mode"], "manual")
            self.assertEqual(loaded["call_used_numbers"], [12])
            self.assertNotIn("obsolete_plugin_setting", loaded)
            self.assertNotIn("simulation_mode", loaded)
            self.assertFalse(os.path.exists(legacy))
            for path in modules.values():
                with open(path, "r", encoding="utf-8") as stream:
                    self.assertNotIn("obsolete_plugin_setting", json.load(stream))

    def test_legacy_single_daily_limit_migrates_to_both_periods(self):
        with tempfile.TemporaryDirectory() as root:
            settings, modules = self._paths(root)
            legacy = os.path.join(root, "settings.json")
            with open(legacy, "w", encoding="utf-8") as stream:
                json.dump({"max_daily_revenue_limit": 123.0}, stream)
            with patch.object(config, "DATA_DIR", root), patch.object(
                config, "DB_DIR", os.path.join(root, "db")
            ), patch.object(config, "DB_PATH", os.path.join(root, "db", "sales.db")), patch.object(
                config, "LEGACY_DB_PATH", os.path.join(root, "sales.db")
            ), patch.object(config, "SETTINGS_DIR", settings), patch.object(
                config, "CONFIG_FILE", legacy
            ), patch.object(config, "TEMPLATE_FILE", os.path.join(root, "template.json")), patch.object(
                config, "MODULE_FILES", modules
            ):
                loaded = config.load_config()
            self.assertEqual(loaded["weekday_max_daily_revenue_limit"], 123.0)
            self.assertEqual(loaded["weekend_max_daily_revenue_limit"], 123.0)
            self.assertEqual(loaded["mon_thu_max_daily_revenue_limit"], 123.0)
            self.assertEqual(loaded["friday_max_daily_revenue_limit"], 123.0)
            self.assertEqual(loaded["saturday_max_daily_revenue_limit"], 123.0)
            self.assertEqual(loaded["sunday_max_daily_revenue_limit"], 123.0)

    def test_save_does_not_persist_runtime_or_foreign_fields(self):
        with tempfile.TemporaryDirectory() as root:
            settings, modules = self._paths(root)
            with patch.object(config, "DATA_DIR", root), patch.object(
                config, "DB_DIR", os.path.join(root, "db")
            ), patch.object(config, "DB_PATH", os.path.join(root, "db", "sales.db")), patch.object(
                config, "LEGACY_DB_PATH", os.path.join(root, "sales.db")
            ), patch.object(
                config, "SETTINGS_DIR", settings
            ), patch.object(config, "MODULE_FILES", modules):
                value = dict(config.DEFAULT_CONFIG)
                value["is_mock_mode"] = True
                value["foreign_extension_key"] = {"x": 1}
                config.save_config(value)
                # Runtime simulation state must remain in the shared in-memory
                # config so a settings save cannot switch the running POS to
                # real hardware mode.  It is still excluded from disk.
                self.assertTrue(value["is_mock_mode"])
                self.assertNotIn("foreign_extension_key", value)
                with open(modules["sys"], "r", encoding="utf-8") as stream:
                    persisted = json.load(stream)
                self.assertNotIn("is_mock_mode", persisted)
                self.assertNotIn("foreign_extension_key", persisted)

    def test_selective_migration_keeps_only_checked_legacy_fields(self):
        with tempfile.TemporaryDirectory() as root:
            settings, modules = self._paths(root)
            legacy = os.path.join(root, "settings.json")
            with open(legacy, "w", encoding="utf-8") as stream:
                json.dump({"shop_name": "旧店名", "unit_price": 88.0}, stream)
            with patch.object(config, "DATA_DIR", root), patch.object(
                config, "DB_DIR", os.path.join(root, "db")
            ), patch.object(config, "DB_PATH", os.path.join(root, "db", "sales.db")), patch.object(
                config, "LEGACY_DB_PATH", os.path.join(root, "sales.db")
            ), patch.object(config, "SETTINGS_DIR", settings), patch.object(
                config, "CONFIG_FILE", legacy
            ), patch.object(config, "TEMPLATE_FILE", os.path.join(root, "template.json")), patch.object(
                config, "MODULE_FILES", modules
            ):
                loaded = config.load_config("selective", selected_keys=["shop_name"])
            self.assertEqual(loaded["shop_name"], "旧店名")
            self.assertEqual(loaded["unit_price"], config.DEFAULT_CONFIG["unit_price"])
            self.assertFalse(os.path.exists(legacy))
            self.assertTrue(os.path.isdir(os.path.join(root, "backups")))

    def test_rebuild_uses_defaults_and_does_not_touch_database(self):
        with tempfile.TemporaryDirectory() as root:
            settings, modules = self._paths(root)
            legacy = os.path.join(root, "settings.json")
            database = os.path.join(root, "db", "sales.db")
            os.makedirs(os.path.dirname(database))
            with open(legacy, "w", encoding="utf-8") as stream:
                json.dump({"shop_name": "旧店名"}, stream)
            with open(database, "wb") as stream:
                stream.write(b"sales")
            with patch.object(config, "DATA_DIR", root), patch.object(
                config, "DB_DIR", os.path.join(root, "db")
            ), patch.object(config, "DB_PATH", database), patch.object(
                config, "LEGACY_DB_PATH", os.path.join(root, "sales.db")
            ), patch.object(config, "SETTINGS_DIR", settings), patch.object(
                config, "CONFIG_FILE", legacy
            ), patch.object(config, "TEMPLATE_FILE", os.path.join(root, "template.json")), patch.object(
                config, "MODULE_FILES", modules
            ):
                loaded = config.load_config("rebuild")
            self.assertEqual(loaded["shop_name"], config.DEFAULT_CONFIG["shop_name"])
            self.assertTrue(os.path.isfile(database))
            self.assertFalse(os.path.exists(legacy))

    def test_database_relocation_does_not_create_a_backup_or_delete_data(self):
        with tempfile.TemporaryDirectory() as root:
            old_path = os.path.join(root, "sales.db")
            new_path = os.path.join(root, "db", "sales.db")
            with open(old_path, "wb") as stream:
                stream.write(b"sqlite-placeholder")
            with patch.object(config, "DATA_DIR", root), patch.object(
                config, "DB_DIR", os.path.join(root, "db")
            ), patch.object(config, "DB_PATH", new_path), patch.object(
                config, "LEGACY_DB_PATH", old_path
            ):
                self.assertTrue(config.migrate_legacy_database())
            self.assertTrue(os.path.isfile(new_path))
            self.assertFalse(os.path.exists(old_path))
            self.assertFalse(os.path.isdir(os.path.join(root, "backups")))


if __name__ == "__main__":
    unittest.main()
