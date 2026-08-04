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
            "takeout": os.path.join(settings, "takeout.json"),
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

    def test_save_does_not_persist_runtime_or_foreign_fields(self):
        with tempfile.TemporaryDirectory() as root:
            settings, modules = self._paths(root)
            with patch.object(config, "DATA_DIR", root), patch.object(
                config, "SETTINGS_DIR", settings
            ), patch.object(config, "MODULE_FILES", modules):
                value = dict(config.DEFAULT_CONFIG)
                value["is_mock_mode"] = True
                value["foreign_extension_key"] = {"x": 1}
                config.save_config(value)
                self.assertNotIn("is_mock_mode", value)
                self.assertNotIn("foreign_extension_key", value)
                with open(modules["sys"], "r", encoding="utf-8") as stream:
                    persisted = json.load(stream)
                self.assertNotIn("foreign_extension_key", persisted)


if __name__ == "__main__":
    unittest.main()
