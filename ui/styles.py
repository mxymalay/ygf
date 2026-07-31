"""
杨国福麻辣烫官方风格 QSS 样式 — 亮色/经典橙色系统
1:1 复刻杨国福 POS 收银台视觉主题
"""

COLORS = {
    "brand_orange": "#FF5500",      # 杨国福招牌橙
    "sidebar_bg": "#E64A19",        # 侧边栏热烈橙
    "sidebar_hover": "#D84315",      # 侧边栏 Hover
    "bg_main": "#F2F3F7",           # 全局浅灰底色
    "card_bg": "#FFFFFF",           # 白色卡片背景
    "card_border": "#E0E2E8",       # 卡片边框
    "text_dark": "#222222",         # 主文字深灰
    "text_muted": "#666666",        # 次要文字
    "text_light": "#999999",        # 辅助文字
    "price_orange": "#FF5500",      # 价格橙
    "btn_gray": "#F5F6FA",          # 浅灰按钮背景
    "btn_border": "#DCDFE6",        # 按钮边框
}

GLOBAL_STYLE = f"""
/* ─── 全局 ──────────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {COLORS['bg_main']};
    color: {COLORS['text_dark']};
    font-family: "Microsoft YaHei", "微软雅黑", "Segoe UI", sans-serif;
    font-size: 14px;
}}

/* ─── 侧边栏 ─────────────────────────────────── */
QFrame#sidebar {{
    background-color: {COLORS['sidebar_bg']};
    border: none;
}}

QPushButton.sidebar-btn {{
    background-color: transparent;
    color: #FFFFFF;
    border: none;
    border-radius: 0px;
    padding: 16px 8px;
    font-size: 13px;
    font-weight: bold;
    text-align: center;
}}

QPushButton.sidebar-btn:hover {{
    background-color: {COLORS['sidebar_hover']};
}}

QPushButton.sidebar-btn:checked {{
    background-color: #FFFFFF;
    color: {COLORS['brand_orange']};
}}

/* ─── 橙色电子秤重量显示盒 ────────────────────── */
QFrame#weight_led_box {{
    background-color: {COLORS['brand_orange']};
    border-radius: 10px;
    padding: 12px;
}}

QLabel#lbl_weight_led {{
    color: #FFFFFF;
    font-size: 38px;
    font-weight: bold;
    font-family: "Consolas", "Courier New", monospace;
}}

/* ─── 按钮 ──────────────────────────────────── */
QPushButton {{
    background-color: {COLORS['card_bg']};
    color: {COLORS['text_dark']};
    border: 1px solid {COLORS['btn_border']};
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 500;
}}

QPushButton:hover {{
    border-color: {COLORS['brand_orange']};
    color: {COLORS['brand_orange']};
}}

QPushButton:pressed {{
    background-color: #FFF0EB;
}}

/* 常用分类激活态按钮 */
QPushButton.cat-btn-active {{
    background-color: {COLORS['brand_orange']};
    color: #FFFFFF;
    border: none;
    font-weight: bold;
}}

/* 产品卡片按钮 */
QPushButton.product-card {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['card_border']};
    border-radius: 8px;
    padding: 8px;
    text-align: left;
}}

QPushButton.product-card:hover {{
    border: 2px solid {COLORS['brand_orange']};
    background-color: #FFF9F7;
}}

/* 橙色大打印按钮 */
QPushButton#btn_print {{
    background-color: {COLORS['brand_orange']};
    color: #FFFFFF;
    font-size: 20px;
    font-weight: bold;
    border: none;
    border-radius: 8px;
    padding: 14px;
}}

QPushButton#btn_print:hover {{
    background-color: #FF661A;
}}

QPushButton#btn_print:pressed {{
    background-color: #E64A19;
}}

/* ─── 输入框 ─────────────────────────────────── */
QLineEdit, QDoubleSpinBox, QSpinBox {{
    background-color: #FFFFFF;
    color: {COLORS['text_dark']};
    border: 1px solid {COLORS['btn_border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 14px;
}}

QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border-color: {COLORS['brand_orange']};
}}

/* ─── 下拉框 ─────────────────────────────────── */
QComboBox {{
    background-color: #FFFFFF;
    color: {COLORS['text_dark']};
    border: 1px solid {COLORS['btn_border']};
    border-radius: 6px;
    padding: 6px 10px;
}}

QComboBox QAbstractItemView {{
    background: #FFFFFF;
    selection-background-color: {COLORS['brand_orange']};
    selection-color: #FFFFFF;
}}

/* ─── 表格 ──────────────────────────────────── */
QTableWidget {{
    background-color: #FFFFFF;
    color: {COLORS['text_dark']};
    gridline-color: #EFEFEF;
    border: 1px solid {COLORS['card_border']};
    border-radius: 8px;
    font-size: 13px;
}}

QHeaderView::section {{
    background-color: #F8F9FB;
    color: {COLORS['text_muted']};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {COLORS['card_border']};
    font-weight: bold;
}}

/* ─── 状态栏 ─────────────────────────────────── */
QStatusBar {{
    background: #FFFFFF;
    color: {COLORS['text_muted']};
    border-top: 1px solid {COLORS['card_border']};
    font-size: 12px;
}}
"""
