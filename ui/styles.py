"""
全局 QSS 样式 — 无框无死角极简现代 POS 视觉
兼容 Python 3.8+
"""

DARK_COLORS = {
    "bg_primary": "#0B0F19",       # 极深曜石黑背景
    "bg_secondary": "#111827",     # 容器黑灰
    "bg_card": "#172136",          # 悬浮卡片靛蓝
    "bg_card_active": "#1E293B",   # 激活卡片背景
    "bg_input": "#1E293B",         # 输入框深灰
    "accent": "#EF4444",           # 品牌麻辣红
    "accent_orange": "#EA580C",    # 琥珀燃橙
    "accent_hover": "#F87171",
    "accent2": "#06B6D4",          # 霓虹青
    "accent2_hover": "#22D3EE",
    "success": "#10B981",          # 薄荷翡翠绿
    "success_bg": "#064E3B",
    "warning": "#F59E0B",          # 暖阳金
    "danger": "#EF4444",
    "text_primary": "#F9FAFB",     # 高亮纯白文字
    "text_secondary": "#9CA3AF",   # 次要灰字
    "border": "transparent",       # 去掉大部分硬质边框
    "border_light": "transparent",
}

LIGHT_COLORS = {
    "bg_primary": "#F3F4F6",       # 极简柔灰背景
    "bg_secondary": "#FFFFFF",     # 容器纯白
    "bg_card": "#FFFFFF",          # 悬浮卡片纯白
    "bg_card_active": "#E5E7EB",   # 激活卡片背景
    "bg_input": "#F9FAFB",         # 输入框浅灰
    "accent": "#DC2626",           # 品牌麻辣红
    "accent_orange": "#EA580C",    # 琥珀燃橙
    "accent_hover": "#EF4444",
    "accent2": "#0284C7",          # 亮天蓝
    "accent2_hover": "#0369A1",
    "success": "#059669",          # 薄荷绿
    "success_bg": "#D1FAE5",
    "warning": "#D97706",          # 暖黄
    "danger": "#DC2626",
    "text_primary": "#111827",     # 深灰黑文字
    "text_secondary": "#4B5563",   # 次要文字
    "border": "transparent",
    "border_light": "transparent",
}


def build_qss(c):
    return f"""
/* ─── 全局无框极简风格 ────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {c['bg_primary']};
    color: {c['text_primary']};
    font-family: "Microsoft YaHei", "微软雅黑", "Segoe UI", sans-serif;
    font-size: 14px;
}}

QLabel {{
    border: none;
    background: transparent;
    background-color: transparent;
    padding: 0px;
    margin: 0px;
}}

/* ─── 杨国福原生火焰红侧边导航栏 ─────────────── */
SideNavBar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #DC2626, stop:0.4 #EA580C, stop:1 #B91C1C);
    border: none;
}}

SideNavItem {{
    background: transparent;
    border: none;
    border-radius: 8px;
    margin: 2px 4px;
}}

SideNavItem:hover {{
    background: rgba(255, 255, 255, 0.22);
}}

SideNavItem:checked {{
    background: #7F1D1D;
    border: none;
}}

/* ─── 开单面板自适应容器 ─────────────────────── */
QFrame#left_card_frame {{
    background-color: {c['bg_secondary']};
    border-radius: 14px;
    border: none;
}}

QFrame#call_detail_box {{
    background-color: {c['bg_card']};
    border-radius: 8px;
    border: none;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

/* ─── 卡片面板 (全面去除外框线) ─────────────────── */
QGroupBox {{
    background-color: {c['bg_card']};
    border: none;
    border-radius: 12px;
    margin-top: 10px;
    padding-top: 16px;
    font-size: 15px;
    font-weight: bold;
    color: {c['text_primary']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 2px 6px;
    background-color: transparent;
    color: {c['accent_orange']};
}}

/* ─── 触控级通用按钮 ─────────────────────────────── */
QPushButton {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 14px;
    font-weight: bold;
    min-height: 38px;
}}

QPushButton:hover {{
    background-color: {c['bg_card_active']};
    color: {c['accent_orange']};
}}

QPushButton:pressed {{
    background-color: {c['accent']};
    color: white;
}}

/* 核心称重打印按钮 */
QPushButton#btn_print {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #EF4444, stop:0.5 #F97316, stop:1 #DC2626);
    color: #FFFFFF;
    font-size: 22px;
    font-weight: 900;
    min-height: 60px;
    border: none;
    border-radius: 12px;
    letter-spacing: 1px;
}}

QPushButton#btn_print:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #F87171, stop:0.5 #FB923C, stop:1 #EF4444);
}}

/* 现金收款按钮 */
QPushButton#btn_cash {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #10B981, stop:0.5 #34D399, stop:1 #059669);
    color: #FFFFFF;
    font-size: 22px;
    font-weight: 900;
    min-height: 60px;
    border: none;
    border-radius: 12px;
    letter-spacing: 1px;
}}

QPushButton#btn_cash:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #34D399, stop:0.5 #6EE7B7, stop:1 #10B981);
}}

/* 其他渠道按钮 */
QPushButton#btn_other {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #6D28D9, stop:0.5 #7C3AED, stop:1 #5B21B6);
    color: #FFFFFF;
    font-size: 15px;
    font-weight: 900;
    min-height: 60px;
    border: none;
    border-radius: 12px;
    padding: 0px 4px;
}}

QPushButton#btn_other:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #7C3AED, stop:0.5 #8B5CF6, stop:1 #6D28D9);
}}

/* 重置清零与开钱箱按钮 */
QPushButton#btn_clear, QPushButton#btn_open_drawer {{
    background: {c['bg_card']};
    color: {c['warning']};
    border: none;
    font-size: 15px;
    min-height: 42px;
    border-radius: 8px;
    font-weight: bold;
}}

QPushButton#btn_clear:hover, QPushButton#btn_open_drawer:hover {{
    background: #334155;
}}

/* ─── 单选框与复选框 (透明背景去黑条) ──────────── */
QRadioButton, QCheckBox {{
    background: transparent;
    background-color: transparent;
    border: none;
    outline: none;
}}

/* ─── 输入框 ──────────────────────────────────── */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{
    background-color: {c['bg_input']};
    color: {c['text_primary']};
    border: none;
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 14px;
    min-height: 38px;
}}

QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{
    border: none;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}}

/* ─── 表格 ──────────────────────────────────── */
QTableWidget {{
    background-color: {c['bg_card']};
    gridline-color: transparent;
    border: none;
    border-radius: 12px;
    color: {c['text_primary']};
    font-size: 14px;
    selection-background-color: {c['accent']};
    selection-color: white;
}}

QHeaderView::section {{
    background-color: {c['bg_secondary']};
    color: {c['text_secondary']};
    padding: 8px;
    border: none;
    font-weight: bold;
    font-size: 14px;
}}

QStatusBar {{
    background-color: {c['bg_primary']};
    color: {c['text_secondary']};
    border: none;
    font-size: 13px;
}}

/* ─── 日历控件 (完整深色/浅色主题适配，彻底消除星期表头白条) ─────────────── */
QCalendarWidget {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    border: 1px solid #334155;
    border-radius: 10px;
}}

QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: {c['bg_secondary']};
    border-bottom: 1px solid #334155;
    min-height: 42px;
}}

QCalendarWidget QToolButton {{
    color: {c['text_primary']};
    background-color: transparent;
    font-weight: bold;
    font-size: 14px;
    border-radius: 6px;
    padding: 4px 8px;
    margin: 2px;
}}

QCalendarWidget QToolButton:hover {{
    background-color: {c['bg_card_active']};
}}

QCalendarWidget QToolButton::menu-indicator {{
    image: none;
    width: 0px;
}}

/* 星期表头 (周一~周日) 解决原生 Windows 白条与灰色背景 */
QCalendarWidget QHeaderView {{
    background-color: {c['bg_secondary']};
    border: none;
}}

QCalendarWidget QHeaderView::section {{
    background-color: {c['bg_secondary']};
    color: {c['text_secondary']};
    font-weight: bold;
    font-size: 12px;
    border: none;
    border-bottom: 1px solid #334155;
    padding: 6px 0px;
}}

QCalendarWidget QTableView {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    selection-background-color: {c['accent_orange']};
    selection-color: #FFFFFF;
    border: none;
    outline: none;
    gridline-color: #334155;
}}

QCalendarWidget QAbstractItemView {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    selection-background-color: {c['accent_orange']};
    selection-color: #FFFFFF;
    border: none;
    outline: none;
}}

QCalendarWidget QAbstractItemView:enabled {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
}}

QCalendarWidget QAbstractItemView:disabled {{
    color: #64748B;
}}

QCalendarWidget QMenu {{
    background-color: {c['bg_secondary']};
    color: {c['text_primary']};
    border: 1px solid #334155;
}}

QCalendarWidget QSpinBox {{
    background-color: {c['bg_secondary']};
    color: {c['text_primary']};
    border: 1px solid #334155;
    border-radius: 4px;
}}
"""

DARK_STYLE = build_qss(DARK_COLORS)
LIGHT_STYLE = build_qss(LIGHT_COLORS)
GLOBAL_STYLE = DARK_STYLE


def fix_calendar_header_style(calendar):
    """彻底解决 Windows 系统下 QCalendarWidget 原生白条表头问题"""
    if not calendar:
        return
    from PyQt5.QtWidgets import QCalendarWidget, QWidget, QHBoxLayout, QLabel, QVBoxLayout
    from PyQt5.QtCore import Qt

    calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
    calendar.setHorizontalHeaderFormat(QCalendarWidget.NoHorizontalHeader)

    if getattr(calendar, "_has_custom_dark_header", False):
        return
    calendar._has_custom_dark_header = True

    hdr = QWidget()
    hdr.setStyleSheet("background-color: #1E293B; border-bottom: 1px solid #334155;")
    hdr_layout = QHBoxLayout(hdr)
    hdr_layout.setContentsMargins(4, 6, 4, 6)
    hdr_layout.setSpacing(0)

    days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    for d in days:
        lbl = QLabel(d)
        lbl.setAlignment(Qt.AlignCenter)
        color = "#EF4444" if d in ["周六", "周日"] else "#9CA3AF"
        lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px; border: none; background: transparent;")
        hdr_layout.addWidget(lbl)

    cal_layout = calendar.layout()
    if isinstance(cal_layout, QVBoxLayout):
        cal_layout.insertWidget(1, hdr)


from PyQt5.QtWidgets import QStyledItemDelegate
from PyQt5.QtCore import QSize

class TouchItemDelegate(QStyledItemDelegate):
    """强制为 QComboBox 下拉选项提供最小高度的委托，无视 Windows 默认样式覆盖"""
    def __init__(self, height=48, parent=None):
        super().__init__(parent)
        self._item_height = height

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), self._item_height))
        return size

def apply_touch_combo_style(combo, item_height=52):
    """为 QComboBox 强行应用触屏与下拉列表美化
    
    解决下拉菜单选项文字靠边/顶格问题，增加内边距与 Hover 亮色反馈
    """
    if not combo:
        return
    from PyQt5.QtWidgets import QListView

    # 1. 先设 combo 自身样式（在替换 view 之前）
    combo.setStyleSheet("""
        QComboBox {
            background-color: #0F172A; color: #F8FAFC;
            border: 1px solid #334155; border-radius: 8px;
            padding: 8px 16px; font-size: 14px; font-weight: 500;
        }
        QComboBox:focus { border: 2px solid #38BDF8; background-color: #0F172A; }
        QComboBox::drop-down { border: none; width: 32px; }
        QComboBox QAbstractItemView {
            background-color: #1E293B;
            color: #F8FAFC;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 6px;
            outline: none;
        }
    """)

    # 2. 创建 view, 把 delegate 设在 view 上
    delegate = TouchItemDelegate(height=item_height, parent=combo)
    view = QListView()
    view.setItemDelegate(delegate)
    view.setStyleSheet("""
        QListView {
            background-color: #1E293B;
            color: #F8FAFC;
            outline: none;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 6px;
        }
        QListView::item {
            padding: 10px 16px;
            margin: 2px 4px;
            border-radius: 6px;
            min-height: 34px;
        }
        QListView::item:hover, QListView::item:selected {
            background-color: #38BDF8;
            color: #0F172A;
            font-weight: bold;
        }
    """)

    # 3. 最后才替换 view
    combo.setView(view)
    combo.setMaxVisibleItems(10)


def apply_touch_checkbox_style(chk):
    """为 QCheckBox 强行应用触屏大尺寸方形指示框与间距美化"""
    if not chk:
        return
    chk.setStyleSheet("""
        QCheckBox {
            color: #F8FAFC;
            font-size: 14px;
            font-weight: bold;
            spacing: 10px;
            min-height: 38px;
            background: transparent;
        }
        QCheckBox::indicator {
            width: 24px;
            height: 24px;
            border-radius: 6px;
            border: 2px solid #475569;
            background-color: #0F172A;
        }
        QCheckBox::indicator:hover {
            border-color: #38BDF8;
            background-color: #1E293B;
        }
        QCheckBox::indicator:checked {
            background-color: #10B981;
            border-color: #059669;
        }
    """)


def apply_touch_spinbox_style(spin):
    """为 QSpinBox / QDoubleSpinBox 强行应用触屏大字与加宽微调按钮"""
    if not spin:
        return
    spin.setStyleSheet("""
        QSpinBox, QDoubleSpinBox {
            background-color: #0F172A;
            color: #38BDF8;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 15px;
            font-weight: bold;
            min-height: 42px;
        }
        QSpinBox:focus, QDoubleSpinBox:focus {
            border: 2px solid #38BDF8;
            background-color: #1E293B;
        }
        QSpinBox::up-button, QDoubleSpinBox::up-button {
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 32px;
            height: 19px;
            background: #334155;
            border-top-right-radius: 7px;
            border: none;
            margin-right: 1px;
            margin-top: 1px;
        }
        QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
            background: #38BDF8;
        }
        QSpinBox::down-button, QDoubleSpinBox::down-button {
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 32px;
            height: 19px;
            background: #334155;
            border-bottom-right-radius: 7px;
            border: none;
            margin-right: 1px;
            margin-bottom: 1px;
        }
        QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
            background: #38BDF8;
        }
    """)
