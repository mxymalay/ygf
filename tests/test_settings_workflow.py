import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from config import DEFAULT_CONFIG
from ui.login_window import LoginWindow
from ui.settings_widget import SettingsWidget, _MaintenanceBusyDialog
from PyQt5.QtCore import Qt


def _fake_scale_ports(widget, show_toast=False):
    del show_toast
    widget.cmb_scale_port.clear()
    widget.cmb_scale_port.addItem(widget.config.get("scale_port", "COM2"))


def _fake_sqb_ports(widget, show_toast=False):
    del show_toast
    widget.cmb_sqb_port.clear()
    widget.cmb_sqb_port.addItem(widget.config.get("shouqianba_port", "COM10"))


class SettingsWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _create_widget(self, bridge_ready=False):
        bridge_config = SimpleNamespace(
            private_pos_virtual_port="COM4",
            official_pos_virtual_port="COM2",
            physical_scale_port="COM1",
            official_bridge_port="CNCB0",
            private_bridge_port="CNCB1",
            baudrate=9600,
        )
        runtime = (bridge_config, bridge_ready, "桥接已就绪" if bridge_ready else "尚未初始化")
        config = dict(DEFAULT_CONFIG)
        with patch.object(SettingsWidget, "_refresh_scale_com_ports", _fake_scale_ports), patch.object(
            SettingsWidget, "_refresh_com_ports", _fake_sqb_ports
        ), patch.object(SettingsWidget, "_refresh_printers", lambda *_args, **_kwargs: None), patch.object(
            SettingsWidget, "_load_scale_bridge_form", lambda _self: None
        ), patch.object(SettingsWidget, "_scale_bridge_runtime_state", return_value=runtime):
            widget = SettingsWidget(config)
        # Keep the runtime fixture active after construction as well.  The
        # real workstation may have a user bridge file, which must not leak
        # into this UI workflow test when the source selector changes.
        widget._scale_bridge_runtime_state = lambda: runtime
        return widget

    def test_scale_modes_only_request_a_port_when_needed(self):
        widget = self._create_widget(bridge_ready=False)
        self.addCleanup(widget.deleteLater)

        self.assertTrue(widget.cmb_scale_port.isHidden())
        self.assertFalse(widget.txt_official_log_dir.isHidden())

        widget.cmb_scale_source.setCurrentIndex(1)
        self.assertFalse(widget.cmb_scale_port.isHidden())
        self.assertTrue(widget.txt_official_log_dir.isHidden())
        self.assertTrue(widget.cmb_scale_port.isEnabled())
        self.assertFalse(widget.btn_refresh_scale_ports.isHidden())

        widget.cmb_scale_source.setCurrentIndex(2)
        self.assertFalse(widget.cmb_scale_port.isHidden())
        self.assertFalse(widget.cmb_scale_port.isEnabled())
        self.assertEqual(widget.cmb_scale_port.currentText(), "COM4")
        self.assertTrue(widget.btn_refresh_scale_ports.isHidden())
        self.assertFalse(widget.btn_go_scale_bridge.isHidden())

    def test_shouqianba_pair_mode_exposes_only_relevant_actions(self):
        widget = self._create_widget()
        self.addCleanup(widget.deleteLater)

        self.assertFalse(widget.btn_initialize_payment_pair.isHidden())
        self.assertTrue(widget.btn_refresh_sqb_ports.isHidden())

        widget.cmb_sqb_pair_mode.setCurrentIndex(1)
        self.assertTrue(widget.btn_initialize_payment_pair.isHidden())
        self.assertFalse(widget.btn_refresh_sqb_ports.isHidden())
        self.assertTrue(widget.btn_remove_payment_pair.isHidden())

        widget.cmb_sqb_enable.setCurrentIndex(1)
        self.assertTrue(widget.cmb_sqb_enable.isEnabled())
        self.assertFalse(widget.cmb_sqb_port.isEnabled())
        self.assertFalse(widget.btn_check_payment_pair.isEnabled())

    def test_settings_use_large_touch_targets(self):
        widget = self._create_widget()
        self.addCleanup(widget.deleteLater)

        self.assertTrue(all(button.minimumHeight() >= 56 for button in widget.nav_buttons))
        self.assertGreaterEqual(widget.cmb_scale_source.minimumHeight(), 56)
        self.assertGreaterEqual(widget.cmb_sqb_port.minimumHeight(), 56)
        self.assertGreaterEqual(widget.txt_sqb_payment_peer.minimumHeight(), 56)
        self.assertGreaterEqual(widget.txt_sqb_install_dir.minimumHeight(), 56)
        self.assertGreaterEqual(widget.btn_browse_sqb_dir.minimumHeight(), 54)
        self.assertGreaterEqual(widget.btn_initialize_scale_bridge.minimumHeight(), 60)
        self.assertGreaterEqual(widget.btn_test_payment_pair.minimumHeight(), 56)
        self.assertTrue(
            all(button.minimumHeight() >= 54 for button in widget.sqb_hotkey_preset_buttons)
        )

    def test_maintenance_dialog_never_covers_windows_installer_prompt(self):
        dialog = _MaintenanceBusyDialog("维护中", "测试")
        self.addCleanup(dialog.deleteLater)

        self.assertFalse(bool(dialog.windowFlags() & Qt.WindowStaysOnTopHint))
        self.assertIn("最小化 POS", dialog.btn_minimize_for_windows.text())
        self.assertGreaterEqual(dialog.btn_minimize_for_windows.minimumHeight(), 52)

    def test_login_official_mode_does_not_probe_an_unrelated_com(self):
        config = dict(DEFAULT_CONFIG)
        config["scale_source"] = "official"
        dialog = LoginWindow(config)
        self.addCleanup(dialog.deleteLater)

        with patch("ui.login_window.check_ygf_official_running", return_value=True), patch(
            "ui.login_window.probe_dibal_scale_connection"
        ) as scale_probe, patch("ui.login_window.QTimer.singleShot"):
            dialog._do_check_official_software()

        scale_probe.assert_not_called()
        self.assertTrue(dialog.official_ok)
        self.assertIn("无需独立 COM", dialog.lbl_badge1_sub.text())

    def test_login_com_mode_uses_the_selected_scale_port(self):
        config = dict(DEFAULT_CONFIG)
        config["scale_source"] = "com"
        dialog = LoginWindow(config)
        self.addCleanup(dialog.deleteLater)

        with patch("ui.login_window.check_ygf_official_running", return_value=True), patch(
            "ui.login_window.probe_dibal_scale_connection", return_value=(False, "COM3 被其它程序占用")
        ) as scale_probe, patch("ui.login_window.QTimer.singleShot"):
            dialog._do_check_official_software()

        scale_probe.assert_called_once_with(config)
        self.assertTrue(dialog.official_ok)
        self.assertIn("被其它程序占用", dialog.lbl_badge1_sub.text())
        self.assertTrue(any("官方 POS 已运行" in item for item in dialog.hardware_warnings))


if __name__ == "__main__":
    unittest.main()
