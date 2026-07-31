"""
主窗口 — 原生竖向侧边栏布局 (收银台、订单查询、叫号设置、系统设置)
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QMainWindow, QStackedWidget, QStatusBar, QLabel, QWidget, QHBoxLayout
)
from PyQt5.QtCore import QTimer, Qt
from datetime import datetime

from core.database import Database
from core.call_number_manager import CallNumberManager
from ui.sidebar import SideNavBar
from ui.sale_widget import SaleWidget
from ui.history_widget import HistoryWidget
from ui.queue_widget import QueueWidget
from ui.settings_widget import SettingsWidget
from ui.styles import DARK_STYLE, LIGHT_STYLE


class MainWindow(QMainWindow):
    """应用主窗口"""

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.db = Database()
        self.call_mgr = CallNumberManager(config)
        self.is_dark_mode = True

        self._init_window()
        self._build_ui()
        self._setup_clock()

    def _init_window(self):
        shop_name = self.config.get("shop_name", u"杨国福麻辣烫")
        self.setWindowTitle(u"%s · 独立称重与小票打印系统" % shop_name)
        self.setMinimumSize(960, 640)
        self.resize(1180, 760)
        self.setStyleSheet(DARK_STYLE)

    def _build_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. 经典杨国福红 竖向固定侧边栏 (SideNavBar)
        self.sidebar = SideNavBar()
        self.sidebar.page_changed.connect(self._on_page_changed)
        self.sidebar.update_requested.connect(self._on_auto_update)
        self.sidebar.minimized_requested.connect(self.showMinimized)
        self.sidebar.exit_requested.connect(self.close)

        main_layout.addWidget(self.sidebar)

        # 2. 页面堆栈容器 (QStackedWidget)
        self.stack = QStackedWidget()

        # 页面 0: 称重收银 (收银台)
        self.sale_page = SaleWidget(self.config, self.db, self.call_mgr)
        self.stack.addWidget(self.sale_page)

        # 页面 1: 订单查询
        self.history_page = HistoryWidget(self.db)
        self.stack.addWidget(self.history_page)

        # 页面 2: 叫号设置 (独立叫号避重菜单)
        self.queue_page = QueueWidget(self.config, self.call_mgr)
        self.stack.addWidget(self.queue_page)

        # 页面 3: 系统设置
        self.settings_page = SettingsWidget(self.config)
        self.stack.addWidget(self.settings_page)

        main_layout.addWidget(self.stack, stretch=1)

        # 3. 底部状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("color: #9CA3AF; font-size: 13px; font-weight: bold; padding-right: 16px;")
        self.status.addPermanentWidget(self.lbl_clock)

        self.status.showMessage(u" ● 系统运行正常  |  官方称重日志实时同步模式  |  智能避重叫号引擎就绪")



    def _on_auto_update(self):
        """一键自动 Git 更新并无缝重启 POS 程序"""
        from PyQt5.QtWidgets import QMessageBox
        import subprocess
        import sys
        import os

        reply = QMessageBox.question(
            self, u"系统在线更新", u"确定要检查并自动拉取 GitHub 最新版本代码吗？\n更新完成后 POS 系统将自动重新启动。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            try:
                # 释放硬件资源
                if hasattr(self, 'sale_page'):
                    self.sale_page.cleanup()

                bat_path = os.path.join(os.getcwd(), "auto_update.bat")
                with open(bat_path, "w", encoding="gbk") as f:
                    f.write("@echo off\n")
                    f.write("chcp 936 >nul\n")
                    f.write("title 杨国福 POS 系统 - 自动更新中...\n")
                    f.write("echo ============================================\n")
                    f.write("echo           正在在线拉取最新程序代码...\n")
                    f.write("echo ============================================\n")
                    f.write("git pull\n")
                    f.write("echo.\n")
                    f.write("echo ============================================\n")
                    f.write("echo           更新完毕！正在重启 POS 系统...\n")
                    f.write("echo ============================================\n")
                    f.write(f'start "" "{sys.executable}" main.py\n')
                    f.write("exit\n")

                subprocess.Popen(["cmd.exe", "/c", bat_path], shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
                sys.exit(0)
            except Exception as e:
                QMessageBox.critical(self, u"更新错误", f"启动更新逻辑失败: {str(e)}")

    def _setup_clock(self):
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.lbl_clock.setText(now)

    def _on_page_changed(self, index):
        self.stack.setCurrentIndex(index)
        if index == 0:
            self.sale_page.restart_scale()
        elif index == 1:
            self.history_page._on_query()
        elif index == 2:
            self.queue_page._load_settings()

    def closeEvent(self, event):
        self.sale_page.cleanup()
        super().closeEvent(event)
