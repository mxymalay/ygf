import sys
import os
import time
import subprocess

# 屏蔽 Qt 框架在控制台输出的 png 色彩警告与窗口尺寸适应性提示
os.environ["QT_LOGGING_RULES"] = "qt.png=false;qt.qpa.window=false;*.warning=false"

from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from config import load_config, save_config
from ui.main_window import MainWindow
from ui.login_window import LoginWindow
from utils.system_utils import apply_auto_start_settings


def main():
    # 加载配置
    config = load_config()

    # 首次运行时保存默认配置
    if not os.path.exists(os.path.join(os.path.dirname(__file__), "data", "settings.json")):
        save_config(config)

    # 0. 尝试同步开机自启动设置
    apply_auto_start_settings(
        config.get("auto_start_enabled", True), 
        config.get("auto_start_delay", 8)
    )

    # 0.5 如果是被系统的“开机自启”拉起的，等待指定秒数让硬件驱动(串口/网卡)先加载完毕
    if "--delayed-start" in sys.argv:
        try:
            delay_idx = sys.argv.index("--delayed-start") + 1
            delay_sec = int(sys.argv[delay_idx])
        except (ValueError, IndexError):
            delay_sec = 8
        if delay_sec > 0:
            time.sleep(delay_sec)

    # 启用高分辨率屏幕(High DPI)自适应缩放支持 (必须在创建 QApplication 之前设置)
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    # 对于更新版本的 PyQt5，确保系统缩放策略生效
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)

    # 设置默认字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    # 1. 弹出登录与检测界面
    login_dlg = LoginWindow(config)
    if login_dlg.exec_() != QDialog.Accepted:
        # 用户点击退出或直接关闭窗口
        sys.exit(0)

    config["is_mock_mode"] = getattr(login_dlg, 'is_mock_mode', False)
    hw_warnings = getattr(login_dlg, 'hardware_warnings', [])

    # 2. 验证通过 (或选择跳过进入模拟调试)，打开主系统
    window = MainWindow(config, hardware_warnings=hw_warnings)
    window.showMaximized()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
