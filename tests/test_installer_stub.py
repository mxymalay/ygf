import unittest
from unittest.mock import patch

import installer_stub


class InstallerStubTests(unittest.TestCase):
    def test_install_complete_message_names_launcher_and_path(self):
        message = installer_stub._install_complete_message("门店 POS", r"C:\Store POS")

        self.assertIn("安装完成", message)
        self.assertIn("门店 POS", message)
        self.assertIn("启动.exe", message)
        self.assertIn(r"C:\Store POS", message)

    def test_no_tk_fallback_uses_selected_directory_and_name(self):
        with patch.object(installer_stub, "HAS_TKINTER", False), patch.object(
            installer_stub, "_existing_install_dir", return_value=""
        ), patch.object(
            installer_stub, "_native_select_folder", return_value=r"C:\Store POS"
        ), patch.object(
            installer_stub, "_native_prompt_string", return_value="门店称重助手"
        ), patch.object(installer_stub, "_install") as install, patch.object(
            installer_stub, "_native_showinfo"
        ):
            installer_stub.main()

        install.assert_called_once_with(r"C:\Store POS", "门店称重助手")

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
