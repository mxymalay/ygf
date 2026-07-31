"""
主窗口 — 1:1 杨国福 POS 布局 (左侧导航栏 + 触控框架)
"""
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QStackedWidget, QStatusBar, QLabel, QFrame
)
from PyQt5.QtCore import QTimer, Qt
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
        self.setWindowTitle(u"杨国福麻辣烫 POS 收银系统")
        self.setMinimumSize(960, 600)
        self.resize(1280, 800)
        self.setStyleSheet(GLOBAL_STYLE)

    def _build_ui(self):
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 1. 左侧杨国福品牌橙色导航栏 ──
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(80)

        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        self.btn_nav_sale = self._make_nav_btn(u"💴\n收银台", True)
        self.btn_nav_history = self._make_nav_btn(u"📑\n订单查询", False)
        self.btn_nav_settings = self._make_nav_btn(u"⚙️\n更多设置", False)

        self.btn_nav_sale.clicked.connect(lambda: self._switch_tab(0))
        self.btn_nav_history.clicked.connect(lambda: self._switch_tab(1))
        self.btn_nav_settings.clicked.connect(lambda: self._switch_tab(2))

        sb_layout.addWidget(self.btn_nav_sale)
        sb_layout.addWidget(self.btn_nav_history)
        sb_layout.addWidget(self.btn_nav_settings)
        sb_layout.addStretch()

        main_layout.addWidget(sidebar)

        # ── 2. 右侧主工作区 (QStackedWidget) ──
        self.stack = QStackedWidget()

        self.sale_page = SaleWidget(self.config, self.db)
        self.history_page = HistoryWidget(self.db)
        self.settings_page = SettingsWidget(self.config)

        self.stack.addWidget(self.sale_page)
        self.stack.addWidget(self.history_page)
        self.stack.addWidget(self.settings_page)

        main_layout.addWidget(self.stack, stretch=1)

        self.setCentralWidget(main_widget)

        # 状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("color: #666666; padding-right: 16px; font-weight: bold;")
        self.status.addPermanentWidget(self.lbl_clock)

        self.status.showMessage(u"  已连接称重硬件 (COM1)  |  杨国福麻辣烫独立收银系统")

    def _make_nav_btn(self, text, is_active):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(is_active)
        btn.setProperty("class", "sidebar-btn")
        btn.setMinimumHeight(80)
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    def _switch_tab(self, index):
        self.stack.setCurrentIndex(index)
        self.btn_nav_sale.setChecked(index == 0)
        self.btn_nav_history.setChecked(index == 1)
        self.btn_nav_settings.setChecked(index == 2)

        if index == 1:
            self.history_page._on_query()

    def _setup_clock(self):
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.lbl_clock.setText(now)

    def closeEvent(self, event):
        self.sale_page.cleanup()
        super().closeEvent(event)
