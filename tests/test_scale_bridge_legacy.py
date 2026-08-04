import json
import os
import tempfile
import unittest

from scale_bridge.configuration import ScaleBridgeConfig, load_config
from scale_bridge.lifecycle import find_hub4com


class ScaleBridgeLegacyConfigTests(unittest.TestCase):
    def test_snake_case_legacy_fields_are_accepted_and_unknown_fields_are_ignored(self):
        config = ScaleBridgeConfig.from_dict(
            {
                "physical_scale_port": "com7",
                "official_pos_virtual_port": "com2",
                "private_pos_virtual_port": "com3",
                "official_peer": "CNCB0",
                "private_peer": "CNCB1",
                "baudrate": "not-a-number",
                "foreign_field": "ignore",
            }
        )
        self.assertEqual(config.physical_scale_port, "COM7")
        self.assertEqual(config.official_bridge_port, "CNCB0")
        self.assertEqual(config.private_bridge_port, "CNCB1")
        self.assertEqual(config.baudrate, 9600)
        self.assertNotIn("foreign_field", config.to_dict())

    def test_new_scale_bridge_file_does_not_duplicate_payment_settings(self):
        config = ScaleBridgeConfig.from_dict(
            {
                "PhysicalScalePort": "COM7",
                "PaymentPosPort": "COM12",
                "PaymentPluginPort": "COM13",
            }
        )
        self.assertNotIn("PaymentPosPort", config.to_dict())
        self.assertNotIn("PaymentPluginPort", config.to_dict())

    def test_loading_valid_legacy_file_rewrites_it_without_payment_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "scale_bridge.json")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(
                    {
                        "PhysicalScalePort": "COM7",
                        "PaymentPosPort": "COM12",
                        "PaymentPluginPort": "COM13",
                        "foreign_field": "drop",
                    },
                    stream,
                )
            load_config(path)
            with open(path, "r", encoding="utf-8") as stream:
                saved = json.load(stream)
            self.assertEqual(saved["PhysicalScalePort"], "COM7")
            self.assertNotIn("PaymentPosPort", saved)
            self.assertNotIn("foreign_field", saved)

    def test_scale_setup_ignores_stale_legacy_payment_values(self):
        config = ScaleBridgeConfig.from_dict(
            {
                "PhysicalScalePort": "COM7",
                "PaymentPosPort": "not-a-com",
                "PaymentPluginPort": "",
            }
        )
        config.validate_for_setup()
        with self.assertRaises(ValueError):
            config.validate()

    def test_corrupt_file_is_backed_up_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "scale_bridge.json")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("{broken")
            config = load_config(path)
            self.assertIsInstance(config, ScaleBridgeConfig)
            self.assertTrue(any(name.startswith("scale_bridge.json.corrupt.") for name in os.listdir(directory)))

    def test_optional_hub4com_discovery_does_not_require_it_at_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "hub4com.exe")
            with open(path, "wb") as stream:
                stream.write(b"diagnostic stub")
            self.assertEqual(find_hub4com(path), os.path.abspath(path))


if __name__ == "__main__":
    unittest.main()
