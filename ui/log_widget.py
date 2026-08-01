"""
运营日志查看器 (Operation Log Viewer)
高级暗色系日志管理界面：
- 顶部筛选工具栏：分类过滤 + 关键词搜索 + 手动清理
- 主体日志列表：按时间倒序，彩色分类标签，清晰分条展示
- 触屏友好：大按钮、大文字
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QFrame, QScrollArea, QGridLayout, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from core.app_logger import (
    read_logs, cleanup_old_logs,
    CAT_ORDER, CAT_SCALE, CAT_PRINT, CAT_DECISION, CAT_SWITCH, CAT_PANIC, CAT_SYSTEM, CAT_USER,
    ALL_CATEGORIES
)

# 分类中文名映射
CAT_DISPLAY = {
    "":          "全部分类",
    CAT_ORDER:   "💰 订单交易",
    CAT_USER:    "👤 用户操作",
    CAT_SCALE:   "⚖️ 称重",
    CAT_PRINT:   "🖨️ 小票打印",
    CAT_DECISION:"🤖 智能决策",
    CAT_SWITCH:  "🔄 系统切换",
    CAT_PANIC:   "🛡️ 避险",
    CAT_SYSTEM:  "💻 系统",
}

# 分类颜色样式
CAT_COLORS = {
    CAT_ORDER:    ("#EC4899", "#831843"),  # pink
    CAT_USER:     ("#FBBF24", "#78350F"),  # amber
    CAT_SCALE:    ("#34D399", "#064E3B"),  # emerald
    CAT_PRINT:    ("#38BDF8", "#0C4A6E"),  # sky
    CAT_DECISION: ("#A78BFA", "#4C1D95"),  # violet
    CAT_SWITCH:   ("#FB923C", "#7C2D12"),  # orange
    CAT_PANIC:    ("#F87171", "#7F1D1D"),  # red
    CAT_SYSTEM:   ("#94A3B8", "#1E293B"),  # slate
}


class LogEntryCard(QFrame):
    """单条日志卡片"""
    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border-radius: 8px;
                border: 1px solid #334155;
            }
        """)
        self.setMinimumHeight(54)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # 分类标签
        cat = entry.get("cat", "SYSTEM")
        fg, bg = CAT_COLORS.get(cat, ("#94A3B8", "#1E293B"))
        cat_display = CAT_DISPLAY.get(cat, cat)
        lbl_cat = QLabel(cat_display)
        lbl_cat.setFixedWidth(90)
        lbl_cat.setAlignment(Qt.AlignCenter)
        lbl_cat.setStyleSheet(f"""
            QLabel {{
                color: {fg}; background-color: {bg};
                font-size: 11px; font-weight: bold;
                padding: 3px 6px; border-radius: 5px;
                border: 1px solid {fg};
            }}
        """)
        layout.addWidget(lbl_cat)

        # 时间戳
        lbl_ts = QLabel(entry.get("ts", ""))
        lbl_ts.setFixedWidth(130)
        lbl_ts.setStyleSheet("color: #64748B; font-size: 12px; font-weight: bold; border: none;")
        layout.addWidget(lbl_ts)

        # 消息文本
        msg = entry.get("msg", "")
        detail = entry.get("detail", "")
        full_text = msg
        if detail:
            full_text += f"  ·  {detail}"
        lbl_msg = QLabel(full_text)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("color: #E2E8F0; font-size: 13px; border: none;")
        layout.addWidget(lbl_msg, stretch=1)


class LogWidget(QWidget):
    """运营日志查看器页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        QTimer.singleShot(200, self._load_logs)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 12)
        root.setSpacing(16)

        # ── 顶部标题 ──
        header = QHBoxLayout()
        lbl_title = QLabel(u"📋 运营日志")
        lbl_title.setStyleSheet("color: #F8FAFC; font-size: 22px; font-weight: 900; letter-spacing: 1px;")
        header.addWidget(lbl_title)

        lbl_sub = QLabel(u"记录称重、打印、智能决策、系统切换等所有关键事件  ·  自动保留 3 天")
        lbl_sub.setStyleSheet("color: #64748B; font-size: 13px; padding-left: 12px;")
        header.addWidget(lbl_sub)
        header.addStretch()
        root.addLayout(header)

        # ── 筛选工具栏 ──
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(12)

        # 分类下拉
        lbl_filter = QLabel(u"分类:")
        lbl_filter.setStyleSheet("color: #94A3B8; font-size: 14px; font-weight: bold;")
        filter_bar.addWidget(lbl_filter)

        self.combo_cat = QComboBox()
        self.combo_cat.setMinimumWidth(140)
        self.combo_cat.setFixedHeight(36)
        self.combo_cat.addItem("全部分类", "")
        for cat in ALL_CATEGORIES:
            self.combo_cat.addItem(CAT_DISPLAY.get(cat, cat), cat)
        self.combo_cat.setStyleSheet("""
            QComboBox {
                background-color: #1E293B; color: #F8FAFC; font-size: 14px; font-weight: bold;
                padding: 4px 12px; border-radius: 8px; border: 1px solid #334155;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1E293B; color: #F8FAFC; selection-background-color: #334155;
                border: 1px solid #475569;
            }
        """)
        self.combo_cat.currentIndexChanged.connect(self._load_logs)
        filter_bar.addWidget(self.combo_cat)

        filter_bar.addSpacing(8)

        # 关键词搜索
        lbl_search = QLabel(u"搜索:")
        lbl_search.setStyleSheet("color: #94A3B8; font-size: 14px; font-weight: bold;")
        filter_bar.addWidget(lbl_search)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(u"输入关键词筛选...")
        self.txt_search.setFixedHeight(36)
        self.txt_search.setMinimumWidth(200)
        self.txt_search.setStyleSheet("""
            QLineEdit {
                background-color: #1E293B; color: #F8FAFC; font-size: 14px;
                padding: 4px 12px; border-radius: 8px; border: 1px solid #334155;
            }
            QLineEdit:focus { border: 1px solid #38BDF8; }
        """)
        self.txt_search.returnPressed.connect(self._load_logs)
        filter_bar.addWidget(self.txt_search)

        # 搜索按钮
        btn_search = QPushButton(u"🔍 筛选")
        btn_search.setFixedHeight(36)
        btn_search.setCursor(Qt.PointingHandCursor)
        btn_search.setStyleSheet("""
            QPushButton {
                background-color: #334155; color: #F8FAFC; font-size: 14px; font-weight: bold;
                padding: 4px 16px; border-radius: 8px; border: 1px solid #475569;
            }
            QPushButton:hover { background-color: #475569; }
            QPushButton:pressed { background-color: #1E293B; }
        """)
        btn_search.clicked.connect(self._load_logs)
        filter_bar.addWidget(btn_search)

        filter_bar.addStretch()

        # 日志统计标签
        self.lbl_count = QLabel(u"共 0 条")
        self.lbl_count.setStyleSheet("color: #64748B; font-size: 13px; font-weight: bold;")
        filter_bar.addWidget(self.lbl_count)

        filter_bar.addSpacing(8)

        # 手动清理按钮
        btn_cleanup = QPushButton(u"🗑️ 清理过期日志")
        btn_cleanup.setFixedHeight(36)
        btn_cleanup.setCursor(Qt.PointingHandCursor)
        btn_cleanup.setStyleSheet("""
            QPushButton {
                background-color: #7F1D1D; color: #FCA5A5; font-size: 13px; font-weight: bold;
                padding: 4px 14px; border-radius: 8px; border: 1px solid #DC2626;
            }
            QPushButton:hover { background-color: #991B1B; }
            QPushButton:pressed { background-color: #450A0A; }
        """)
        btn_cleanup.clicked.connect(self._on_cleanup)
        filter_bar.addWidget(btn_cleanup)

        root.addLayout(filter_bar)

        # ── 分割线 ──
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #334155;")
        root.addWidget(line)

        # ── 日志列表滚动区域 ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background-color: #0F172A; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #475569; border-radius: 4px; min-height: 40px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        root.addWidget(self.scroll_area, stretch=1)

        # 列表内容容器
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 8, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.list_container)

    def _load_logs(self):
        """加载/刷新日志列表"""
        cat_filter = self.combo_cat.currentData() or ""
        keyword = self.txt_search.text().strip()

        logs = read_logs(category_filter=cat_filter, keyword=keyword, limit=500)

        # 清空现有列表
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not logs:
            lbl_empty = QLabel(u"暂无匹配的日志记录")
            lbl_empty.setAlignment(Qt.AlignCenter)
            lbl_empty.setStyleSheet("color: #475569; font-size: 15px; padding: 40px;")
            self.list_layout.addWidget(lbl_empty)
            self.lbl_count.setText(u"共 0 条")
            return

        for entry in logs:
            card = LogEntryCard(entry)
            self.list_layout.addWidget(card)

        self.lbl_count.setText(f"共 {len(logs)} 条")

    def _on_cleanup(self):
        """手动触发过期日志清理"""
        removed = cleanup_old_logs()
        QMessageBox.information(self, u"日志清理", f"已清理 {removed} 条过期日志记录 (保留最近 3 天)")
        self._load_logs()
