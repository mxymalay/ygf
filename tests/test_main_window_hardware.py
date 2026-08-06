import unittest
from unittest.mock import patch

from ui.main_window import MainWindow
from ui.sale_widget import SaleWidget


class _StatusButton:
    def __init__(self):
        self.text = ""
        self.styles = []

    def setText(self, text):
        self.text = text

    def setStyleSheet(self, style):
        self.styles.append(style)


class _RecheckButton:
    def hide(self):
        pass

    def show(self):
        pass

    def setStyleSheet(self, _style):
        pass


class MainWindowHardwareTests(unittest.TestCase):
    def _runner(self):
        runner = MainWindow.__new__(MainWindow)
        runner.config = {
            "official_pos_window_configured": True,
            "official_pos_window_keywords": ["杨国福"],
            "scale_source": "com",
            "scale_port": "COM3",
            "shouqianba_port": "COM10",
        }
        runner.lbl_hw_status = _StatusButton()
        runner.btn_hw_recheck = _RecheckButton()
        runner._hardware_check_running = False
        runner._hardware_check_step = 0
        runner._hardware_check_state = {}
        runner.hardware_warnings = []
        return runner

    def test_click_rechecks_all_hardware_stages_and_reports_current_stage(self):
        runner = self._runner()
        with patch("ui.main_window.QTimer.singleShot"), patch(
            "ui.login_window.check_ygf_official_running", return_value=True
        ), patch(
            "utils.window_utils.is_official_window_configured", return_value=True
        ), patch(
            "ui.login_window.probe_dibal_scale_connection", return_value=(True, "COM3 正常")
        ), patch("utils.port_scanner.scan_printers", return_value=["Receipt"]), patch(
            "core.shouqianba_sender.test_shouqianba_port", return_value=(True, "COM10 正常")
        ):
            runner._on_hardware_status_clicked()
            self.assertTrue(runner._hardware_check_running)
            self.assertIn("官方 POS", runner.lbl_hw_status.text)

            for _ in range(5):
                runner._run_hardware_check_step()

        self.assertFalse(runner._hardware_check_running)
        self.assertEqual([], runner.hardware_warnings)
        self.assertIn("硬件设备连接良好", runner.lbl_hw_status.text)

    def test_scale_icon_diagnoses_unconfigured_official_source(self):
        widget = SaleWidget.__new__(SaleWidget)
        widget.config = {"scale_source": "official", "official_pos_log_dir": ""}
        widget._scale_status_message = "没有可用读数"
        with patch("ui.custom_dialog.show_info") as show_info, patch(
            "utils.window_utils.is_official_window_configured", return_value=False
        ):
            widget._show_scale_diagnostic_dialog()

        message = show_info.call_args.args[2]
        self.assertIn("未配置", message)
        self.assertIn("官方 POS 窗口识别", message)

    def test_scale_icon_diagnoses_missing_com_port(self):
        widget = SaleWidget.__new__(SaleWidget)
        widget.config = {"scale_source": "com", "scale_port": ""}
        widget._scale_status_message = "串口打开失败"
        with patch("ui.custom_dialog.show_info") as show_info:
            widget._show_scale_diagnostic_dialog()

        message = show_info.call_args.args[2]
        self.assertIn("COM 端口：未配置", message)
        self.assertIn("没有配置电子秤 COM 端口", message)


if __name__ == "__main__":
    unittest.main()
