"""
自定义左侧竖向导航栏 — 完全遵循杨国福收银界面原生风格设计
图标上、文字下，含收银台、订单查询、叫号设置、系统设置及底部快捷控制
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QFrame, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont


class SideNavItem(QPushButton):
    """侧边栏导航按钮 (图标在上方，文字在下方)"""

    def __init__(self, icon_text, label_text, page_index, parent=None):
        super().__init__(parent)
        self.page_index = page_index
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 8, 2, 8)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        # 上图标
        self.lbl_icon = QLabel(icon_text)
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        self.lbl_icon.setStyleSheet("font-size: 20px; background: transparent;")
        layout.addWidget(self.lbl_icon)

        # 下文字 (紧凑排版)
        self.lbl_text = QLabel(label_text)
        self.lbl_text.setAlignment(Qt.AlignCenter)
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #FFFFFF; background: transparent;"
        )
        layout.addWidget(self.lbl_text)

        self.setLayout(layout)
        self.setFixedHeight(72)


class SideNavBar(QWidget):
    """左侧固定竖向导航栏"""

    page_changed = pyqtSignal(int)
    update_requested = pyqtSignal()
    minimized_requested = pyqtSignal()
    exit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(78)
        self._items = []

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignTop)

        # 1. 顶端品牌标识 Badge
        brand_frame = QFrame()
        brand_frame.setFixedHeight(64)
        brand_frame.setStyleSheet("background: transparent;")
        bf_layout = QVBoxLayout(brand_frame)
        bf_layout.setAlignment(Qt.AlignCenter)

        lbl_logo = QLabel(u"杨")
        lbl_logo.setAlignment(Qt.AlignCenter)
        lbl_logo.setStyleSheet(
            "font-size: 20px; font-weight: 900; color: #DC2626; "
            "background: #FFFFFF; border-radius: 20px; min-width: 40px; max-width: 40px; "
            "min-height: 40px; max-height: 40px;"
        )
        bf_layout.addWidget(lbl_logo)
        layout.addWidget(brand_frame)

        # 分割线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setStyleSheet("color: rgba(255, 255, 255, 0.2); margin: 0 8px;")
        layout.addWidget(line1)

        # 2. 核心导航项目按钮组
        # 0: 收银台
        item_cashier = SideNavItem(u"⚖", u"收银台", 0)
        item_cashier.clicked.connect(lambda: self._select_page(0))
        layout.addWidget(item_cashier)
        self._items.append(item_cashier)

        # 1: 订单查询
        item_history = SideNavItem(u"≡", u"订单查询", 1)
        item_history.clicked.connect(lambda: self._select_page(1))
        layout.addWidget(item_history)
        self._items.append(item_history)

        # 2: 叫号设置
        item_queue = SideNavItem(u"⚡", u"叫号设置", 2)
        item_queue.clicked.connect(lambda: self._select_page(2))
        layout.addWidget(item_queue)
        self._items.append(item_queue)

        # 3: 系统设置
        item_settings = SideNavItem(u"⚙", u"系统设置", 3)
        item_settings.clicked.connect(lambda: self._select_page(3))
        layout.addWidget(item_settings)
        self._items.append(item_settings)

        layout.addStretch()

        # 3. 底部快捷控制按钮组
        # 一键更新
        item_update = SideNavItem(u"↻", u"一键更新", -1)
        item_update.clicked.connect(lambda: self.update_requested.emit())
        layout.addWidget(item_update)

        # 最小化
        item_min = SideNavItem(u"—", u"最小化", -1)
        item_min.clicked.connect(lambda: self.minimized_requested.emit())
        layout.addWidget(item_min)

        # 退出程序
        item_exit = SideNavItem(u"✕", u"退出程序", -1)
        item_exit.clicked.connect(lambda: self.exit_requested.emit())
        layout.addWidget(item_exit)

        # 默认选中第一页
        self._select_page(0)

    def _select_page(self, index):
        for item in self._items:
            item.setChecked(item.page_index == index)
        self.page_changed.emit(index)

    def update_theme_icon(self, is_dark: bool):
        if is_dark:
            self.item_theme.lbl_icon.setText(u"🌙")
        else:
            self.item_theme.lbl_icon.setText(u"☀")
