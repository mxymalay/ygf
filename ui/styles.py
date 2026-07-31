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

/* 重置清零按钮 */
QPushButton#btn_clear {{
    background: {c['bg_card']};
    color: {c['warning']};
    border: none;
    font-size: 15px;
    min-height: 42px;
    border-radius: 8px;
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
"""

DARK_STYLE = build_qss(DARK_COLORS)
LIGHT_STYLE = build_qss(LIGHT_COLORS)
GLOBAL_STYLE = DARK_STYLE
