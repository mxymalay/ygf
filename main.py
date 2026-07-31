"""
杨国福麻辣烫 · 独立称重打印系统
主入口
"""
import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from config import load_config, save_config
from ui.main_window import MainWindow


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

    # 创建主窗口（默认最大化适合收银屏）
    window = MainWindow(config)
    window.showMaximized()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
