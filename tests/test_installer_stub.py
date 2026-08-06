import unittest
import os
import tempfile
from unittest.mock import patch

import installer_stub


class InstallerStubTests(unittest.TestCase):
    def test_install_complete_message_names_launcher_and_path(self):
        message = installer_stub._install_complete_message("门店 POS", r"C:\Store POS")

        self.assertIn("安装完成", message)
        self.assertIn("门店 POS", message)
        self.assertIn("启动.exe", message)
        self.assertIn(r"C:\Store POS", message)

    def test_shortcut_command_sets_win7_icon_location(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(installer_stub, "_run_hidden") as run_hidden:
            run_hidden.return_value.returncode = 0
            shortcut = os.path.join(temp_dir, "YGF.lnk")
            self.assertTrue(
                installer_stub._create_shortcut(
                    shortcut,
                    r"C:\YGF-POS\启动.exe",
                    r"C:\YGF-POS",
                    "YGF POS",
                    r"C:\YGF-POS\data\assets\app_icon_yangguofu.ico",
                )
            )
        command = run_hidden.call_args.args[0][-1]
        self.assertIn("IconLocation", command)
        self.assertIn("app_icon_yangguofu.ico,0", command)

    def test_update_current_shortcut_icon_rewrites_both_shortcuts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(os.path.join(temp_dir, "data", "assets"))
            open(os.path.join(temp_dir, "启动.exe"), "wb").close()
            open(os.path.join(temp_dir, "data", "assets", "app_icon_google.ico"), "wb").close()
            with patch.object(installer_stub, "_existing_install_dir", return_value=temp_dir), patch.object(
                installer_stub, "_registry_display_name", return_value="门店称重助手"
            ), patch.object(
                installer_stub, "_shortcut_paths", return_value=("desktop.lnk", "start.lnk", "uninstall.lnk")
            ), patch.object(installer_stub, "_create_shortcut", return_value=True) as create, patch.object(
                installer_stub, "winreg", None
            ):
                ok, message = installer_stub.update_current_shortcut_icon("google")

        self.assertTrue(ok)
        self.assertIn("已更新", message)
        self.assertEqual(create.call_count, 2)
        self.assertIn("app_icon_google.ico", create.call_args_list[0].args[-1])

    def test_no_tk_fallback_uses_selected_directory_and_name(self):
        with patch.object(installer_stub, "HAS_TKINTER", False), patch.object(
            installer_stub, "_existing_install_dir", return_value=""
        ), patch.object(
            installer_stub, "_native_select_folder", return_value=r"C:\Store POS"
        ), patch.object(
            installer_stub, "_native_prompt_string", return_value="门店称重助手"
        ), patch.object(
            installer_stub, "_native_prompt_choice", return_value="google"
        ), patch.object(installer_stub, "_install") as install, patch.object(
            installer_stub, "_native_install_complete"
        ):
            installer_stub.main()

        install.assert_called_once_with(r"C:\Store POS", "门店称重助手", "google")

    def test_no_tk_fallback_can_cancel_before_install(self):
        with patch.object(installer_stub, "HAS_TKINTER", False), patch.object(
            installer_stub, "_native_select_folder", return_value=None
        ), patch.object(installer_stub, "_install") as install, patch.object(
            installer_stub, "_native_showinfo"
        ):
            installer_stub.main()

        install.assert_not_called()

    def test_no_tk_fallback_rejects_invalid_name(self):
        with patch.object(installer_stub, "HAS_TKINTER", False), patch.object(
            installer_stub, "_native_select_folder", return_value=r"C:\Store POS"
        ), patch.object(
            installer_stub, "_native_prompt_string", return_value="bad/name"
        ), patch.object(installer_stub, "_install") as install, patch.object(
            installer_stub, "_native_showerror"
        ) as show_error:
            installer_stub.main()

        install.assert_not_called()
        show_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
