import os
import unittest

from config import APP_LOGO_PRESETS, app_logo_path


class AppLogoPresetTests(unittest.TestCase):
    def test_every_logo_preset_resolves_to_a_bundled_asset(self):
        self.assertGreaterEqual(len(APP_LOGO_PRESETS), 9)
        for preset_id in APP_LOGO_PRESETS:
            self.assertTrue(
                os.path.isfile(app_logo_path(preset_id)),
                "missing Logo asset for %s" % preset_id,
            )

    def test_unknown_preset_falls_back_to_builtin_logo(self):
        self.assertEqual(app_logo_path("unknown"), app_logo_path("yangguofu"))


if __name__ == "__main__":
    unittest.main()
