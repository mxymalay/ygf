"""
主窗口 — 标签页导航
"""
from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel
)
from PyQt5.QtCore import QTimer
from datetime import datetime

from core.database import Database
from ui.sale_widget import SaleWidget
from ui.history_widget import HistoryWidget
from ui.settings_widget import SettingsWidget
from ui.styles import GLOBAL_STYLE


class MainWindow(QMainWindow):
    """应用主窗口"""

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.db = Database()

        self._init_window()
        self._build_ui()
        self._setup_clock()

    def _init_window(self):
        self.setWindowTitle(u"\U0001f35c 杨国福麻辣烫 · 称重打印系统")
        self.setMinimumSize(1024, 680)
        self.resize(1280, 800)
        self.setStyleSheet(GLOBAL_STYLE)

    def _build_ui(self):
        # 标签页
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)

        # 销售页
        self.sale_page = SaleWidget(self.config, self.db)
        self.tabs.addTab(self.sale_page, u"\u2696\ufe0f 称重收银")

        # 历史页
        self.history_page = HistoryWidget(self.db)
        self.tabs.addTab(self.history_page, u"\U0001f4ca 历史记录")

        # 设置页
        self.settings_page = SettingsWidget(self.config)
        self.tabs.addTab(self.settings_page, u"\u2699\ufe0f 系统设置")

        self.setCentralWidget(self.tabs)

        # 刷新历史页（切换标签时）
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # 状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("color: #a0a0b8; padding-right: 16px;")
        self.status.addPermanentWidget(self.lbl_clock)

        mode = u"[模拟模式]" if self.config.get("simulation_mode") else u"[硬件模式]"
        self.status.showMessage(u"  %s  |  数据存储于本地 SQLite  |  Win7 兼容" % mode)

    def _setup_clock(self):
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.lbl_clock.setText(now)

    def _on_tab_changed(self, index):
        if index == 1:
            self.history_page._on_query()

    def closeEvent(self, event):
        self.sale_page.cleanup()
        super().closeEvent(event)
