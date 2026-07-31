"""
全局 QSS 样式 — 旗舰级极简现代 POS 视觉主题
针对 Windows 7 触控屏及高对比度排版深度优化
"""

COLORS = {
    "bg_primary": "#0B0F19",       # 极深曜石黑背景
    "bg_secondary": "#111827",     # 容器黑灰
    "bg_card": "#172136",          # 悬浮卡片靛蓝
    "bg_card_active": "#1E293B",   # 激活卡片背景
    "bg_input": "#1E293B",         # 输入框深灰
    "accent": "#EF4444",           # 品牌麻辣红 (杨国福主色)
    "accent_orange": "#F97316",    # 琥珀燃橙
    "accent_hover": "#F87171",
    "accent2": "#06B6D4",          # 霓虹青
    "accent2_hover": "#22D3EE",
    "success": "#10B981",          # 薄荷翡翠绿
    "success_bg": "#064E3B",
    "warning": "#F59E0B",          # 暖阳金
    "danger": "#EF4444",
    "text_primary": "#F9FAFB",     # 高亮纯白文字
    "text_secondary": "#9CA3AF",   # 次要灰字
    "text_dim": "#6B7280",         # 暗灰字
    "border": "#263352",           # 质感蓝灰边框
    "border_light": "#374151",
}

GLOBAL_STYLE = f"""
/* ─── 全局基础 ──────────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {COLORS['bg_primary']};
    color: {COLORS['text_primary']};
    font-family: "Microsoft YaHei", "微软雅黑", "Segoe UI", sans-serif;
    font-size: 14px;
}}

/* ─── 导航标签页 ─────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
    background: {COLORS['bg_secondary']};
    margin-top: -1px;
}}

QTabBar::tab {{
    background: {COLORS['bg_card']};
    color: {COLORS['text_secondary']};
    padding: 14px 36px;
    margin-right: 6px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    font-size: 16px;
    font-weight: bold;
    min-width: 120px;
}}

QTabBar::tab:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS['accent']}, stop:1 {COLORS['accent_orange']});
    color: #FFFFFF;
    border-bottom: none;
}}

QTabBar::tab:hover:!selected {{
    background: {COLORS['bg_card_active']};
    color: {COLORS['text_primary']};
}}

/* ─── 卡片面板 ──────────────────────────────────── */
QGroupBox {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 14px;
    margin-top: 12px;
    padding-top: 18px;
    font-size: 16px;
    font-weight: bold;
    color: {COLORS['text_primary']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 16px;
    padding: 2px 10px;
    background-color: {COLORS['bg_card']};
    border-radius: 6px;
    color: {COLORS['accent_orange']};
}}

/* ─── 触控级通用按钮 ─────────────────────────────── */
QPushButton {{
    background-color: {COLORS['bg_card']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 10px 22px;
    font-size: 15px;
    font-weight: bold;
    min-height: 42px;
}}

QPushButton:hover {{
    background-color: {COLORS['bg_card_active']};
    border-color: {COLORS['accent_orange']};
    color: #FFFFFF;
}}

QPushButton:pressed {{
    background-color: {COLORS['accent']};
}}

/* 核心称重打印按钮 (大号醒目触控) */
QPushButton#btn_print {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #EF4444, stop:0.5 #F97316, stop:1 #DC2626);
    color: #FFFFFF;
    font-size: 24px;
    font-weight: 900;
    min-height: 72px;
    border: none;
    border-radius: 16px;
    letter-spacing: 2px;
}}

QPushButton#btn_print:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #F87171, stop:0.5 #FB923C, stop:1 #EF4444);
}}

QPushButton#btn_print:pressed {{
    background: #B91C1C;
}}

QPushButton#btn_print:disabled {{
    background: #374151;
    color: #9CA3AF;
}}

/* 重置清零按钮 */
QPushButton#btn_clear {{
    background: {COLORS['bg_card']};
    color: {COLORS['warning']};
    border: 1px solid {COLORS['warning']};
    font-size: 16px;
    min-height: 46px;
    border-radius: 10px;
}}

QPushButton#btn_clear:hover {{
    background: #78350F;
    color: #FBBF24;
}}

/* ─── 输入框 (高度防护 & Win7 字体挤压解决) ────── */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{
    background-color: {COLORS['bg_input']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 15px;
    min-height: 40px;
}}

QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {COLORS['accent_orange']};
}}

QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    width: 32px;
    border: none;
    background: {COLORS['border']};
    border-radius: 4px;
}}

QComboBox::drop-down {{
    border: none;
    width: 32px;
}}

QComboBox QAbstractItemView {{
    background: {COLORS['bg_card']};
    color: {COLORS['text_primary']};
    selection-background-color: {COLORS['accent']};
    border: 1px solid {COLORS['border']};
    padding: 8px;
}}

/* ─── 表格控件 ──────────────────────────────────── */
QTableWidget {{
    background-color: {COLORS['bg_card']};
    gridline-color: {COLORS['border']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
    color: {COLORS['text_primary']};
    font-size: 14px;
    selection-background-color: {COLORS['accent']};
    selection-color: white;
}}

QHeaderView::section {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_secondary']};
    padding: 10px;
    border: none;
    border-bottom: 2px solid {COLORS['border']};
    font-weight: bold;
    font-size: 15px;
}}

QTableWidget::item {{
    padding: 8px 12px;
    border-bottom: 1px solid {COLORS['border']};
}}

QTableWidget::item:alternate {{
    background-color: {COLORS['bg_card_active']};
}}

/* ─── 滚动条 ──────────────────────────────────── */
QScrollBar:vertical {{
    background: {COLORS['bg_primary']};
    width: 12px;
    border-radius: 6px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: {COLORS['border_light']};
    min-height: 24px;
    border-radius: 6px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLORS['accent_orange']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* ─── 状态栏 ──────────────────────────────────── */
QStatusBar {{
    background-color: {COLORS['bg_primary']};
    color: {COLORS['text_secondary']};
    border-top: 1px solid {COLORS['border']};
    font-size: 13px;
}}
"""
