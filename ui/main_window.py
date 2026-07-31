"""
主窗口 — 包含左侧竖向导航、暗黑/亮白模式切换、窗口最小化与叫号集成
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel, QWidget, QVBoxLayout, QPushButton, QHBoxLayout
)
from PyQt5.QtCore import QTimer, Qt
from datetime import datetime

from core.database import Database
from ui.sale_widget import SaleWidget
from ui.history_widget import HistoryWidget
from ui.settings_widget import SettingsWidget
from ui.styles import DARK_STYLE, LIGHT_STYLE


class MainWindow(QMainWindow):
    """应用主窗口"""

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.db = Database()
        self.is_dark_mode = True

        self._init_window()
        self._build_ui()
        self._setup_clock()

    def _init_window(self):
        shop_name = self.config.get("shop_name", u"杨国福麻辣烫")
        self.setWindowTitle(u"%s · 独立称重与小票打印系统" % shop_name)
        self.setMinimumSize(920, 620)
        self.resize(1150, 760)
        self.setStyleSheet(DARK_STYLE)

    def _build_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 1. 核心竖向 QTabWidget (最左侧 West 布局) ──
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.West)

        # 1. 核心称重收银页
        self.sale_page = SaleWidget(self.config, self.db)
        self.tabs.addTab(self.sale_page, u" 称重收银 ")

        # 2. 历史交易数据页
        self.history_page = HistoryWidget(self.db)
        self.tabs.addTab(self.history_page, u" 历史记录 ")

        # 3. 系统参数设置页
        self.settings_page = SettingsWidget(self.config)
        self.tabs.addTab(self.settings_page, u" 系统设置 ")

        main_layout.addWidget(self.tabs, stretch=1)

        # ── 2. 左侧栏底部快捷控制区域 ──
        side_controls = QWidget(self.tabs)
        side_layout = QVBoxLayout(side_controls)
        side_layout.setContentsMargins(8, 8, 8, 12)
        side_layout.setSpacing(8)

        # 主题切换按钮
        self.btn_theme = QPushButton(u"🌙 模式")
        self.btn_theme.setToolTip(u"切换 暗黑 / 亮白 视觉模式")
        self.btn_theme.setStyleSheet(
            "QPushButton { background: #1E293B; color: #F9FAFB; border: 1px solid #374151; "
            "border-radius: 8px; font-weight: bold; font-size: 13px; min-height: 38px; padding: 4px; }"
            "QPushButton:hover { background: #374151; color: #F97316; }"
        )
        self.btn_theme.clicked.connect(self._toggle_theme)
        side_layout.addWidget(self.btn_theme)

        # 最小化按钮
        btn_min = QPushButton(u"🗕 最小化")
        btn_min.setToolTip(u"最小化窗口到任务栏")
        btn_min.setStyleSheet(
            "QPushButton { background: #1E293B; color: #9CA3AF; border: 1px solid #374151; "
            "border-radius: 8px; font-weight: bold; font-size: 13px; min-height: 38px; padding: 4px; }"
            "QPushButton:hover { background: #374151; color: #FFFFFF; }"
        )
        btn_min.clicked.connect(self.showMinimized)
        side_layout.addWidget(btn_min)

        # 定位在 TabBar 最下方
        self.tabs.setCornerWidget(side_controls, Qt.BottomLeftCorner)

        # 切换标签页触发逻辑
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # 底部状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("color: #9CA3AF; font-size: 13px; font-weight: bold; padding-right: 16px;")
        self.status.addPermanentWidget(self.lbl_clock)

        self.status.showMessage(u" ● 系统运行正常  |  官方称重日志实时同步模式  |  本地数据安全防护")

    def _toggle_theme(self):
        """切换深色 / 浅色视觉主题"""
        self.is_dark_mode = not self.is_dark_mode
        if self.is_dark_mode:
            self.setStyleSheet(DARK_STYLE)
            self.btn_theme.setText(u"🌙 模式")
            self.btn_theme.setStyleSheet(
                "QPushButton { background: #1E293B; color: #F9FAFB; border: 1px solid #374151; "
                "border-radius: 8px; font-weight: bold; font-size: 13px; min-height: 38px; padding: 4px; }"
                "QPushButton:hover { background: #374151; color: #F97316; }"
            )
        else:
            self.setStyleSheet(LIGHT_STYLE)
            self.btn_theme.setText(u"☀️ 模式")
            self.btn_theme.setStyleSheet(
                "QPushButton { background: #FFFFFF; color: #111827; border: 1px solid #D1D5DB; "
                "border-radius: 8px; font-weight: bold; font-size: 13px; min-height: 38px; padding: 4px; }"
                "QPushButton:hover { background: #E5E7EB; color: #EA580C; }"
            )

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
