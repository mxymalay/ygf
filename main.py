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


def main():
    app = QApplication(sys.argv)

    # 设置默认字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    # 加载配置
    config = load_config()

    # 首次运行时保存默认配置
    if not os.path.exists(os.path.join(os.path.dirname(__file__), "data", "settings.json")):
        save_config(config)

    # 1. 弹出登录与检测界面
    login_dlg = LoginWindow()
    if login_dlg.exec_() != QDialog.Accepted:
        # 用户点击退出或直接关闭窗口
        sys.exit(0)

    # 2. 验证通过 (或选择跳过进入模拟调试)，打开主系统
    window = MainWindow(config)
    window.showMaximized()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
