import os
import unittest

from config import (
    APP_LOGO_PRESETS,
    APP_CATEGORY_OPTIONS,
    app_branding,
    app_logo_path,
)


class AppLogoPresetTests(unittest.TestCase):
    def test_every_logo_preset_resolves_to_a_bundled_asset(self):
        self.assertGreaterEqual(len(APP_LOGO_PRESETS), 13)
        for preset_id in APP_LOGO_PRESETS:
            self.assertTrue(
                os.path.isfile(app_logo_path(preset_id)),
                "missing Logo asset for %s" % preset_id,
            )

    def test_unknown_preset_falls_back_to_builtin_logo(self):
        self.assertEqual(app_logo_path("unknown"), app_logo_path("yangguofu"))

    def test_login_categories_cover_custom_shortcut_branding(self):
        self.assertGreaterEqual(len(APP_CATEGORY_OPTIONS), 15)
        music = app_branding({"app_category": "music"})
        self.assertEqual(music["category_id"], "music")
        self.assertIn("音乐", music["login_title"])

    def test_icon_category_is_used_when_category_is_missing(self):
        branding = app_branding({"shortcut_icon_preset": "google"})
        self.assertEqual(branding["category_id"], "google")
        self.assertIn("Google", branding["login_title"])


if __name__ == "__main__":
    unittest.main()
