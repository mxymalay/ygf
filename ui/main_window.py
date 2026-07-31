"""
主窗口 — 旗舰级现代双视角导航与全局状态集成
PyQt5 + Python 3.8 兼容
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
        shop_name = self.config.get("shop_name", u"杨国福麻辣烫")
        self.setWindowTitle(u"%s · 专用于独立称重与小票打印系统" % shop_name)
        self.setMinimumSize(850, 550)
        self.resize(1080, 720)
        self.setStyleSheet(GLOBAL_STYLE)

    def _build_ui(self):
        # 顶部极简分栏 Tab
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)

        # 1. 核心称重收银页
        self.sale_page = SaleWidget(self.config, self.db)
        self.tabs.addTab(self.sale_page, u" 称重收银 ")

        # 2. 历史交易数据页
        self.history_page = HistoryWidget(self.db)
        self.tabs.addTab(self.history_page, u" 历史记录 ")

        # 3. 系统参数设置页
        self.settings_page = SettingsWidget(self.config)
        self.tabs.addTab(self.settings_page, u" 系统设置 ")

        self.setCentralWidget(self.tabs)

        # 切换标签页触发逻辑
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # 底部状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("color: #9CA3AF; font-size: 13px; font-weight: bold; padding-right: 16px;")
        self.status.addPermanentWidget(self.lbl_clock)

        self.status.showMessage(u" ● 系统运行正常  |  官方称重日志实时同步模式  |  本地数据已安全保护")

    def _setup_clock(self):
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.lbl_clock.setText(now)

    def _on_tab_changed(self, index):
        if index == 0:
            self.sale_page.restart_scale()
        elif index == 1:
            self.history_page._on_query()

    def closeEvent(self, event):
        self.sale_page.cleanup()
        super().closeEvent(event)
