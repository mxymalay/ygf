"""
全局 QSS 样式 — 现代深色主题，专为 Windows 7 POS 触屏优化
"""

COLORS = {
    "bg_primary": "#0f0f1a",
    "bg_secondary": "#1a1a2e",
    "bg_card": "#16213e",
    "bg_input": "#0f3460",
    "accent": "#e94560",
    "accent_hover": "#ff6b81",
    "accent2": "#00b4d8",
    "accent2_hover": "#48cae4",
    "success": "#2ecc71",
    "success_hover": "#27ae60",
    "warning": "#f39c12",
    "danger": "#e74c3c",
    "text_primary": "#f0f0f0",
    "text_secondary": "#a0a0b8",
    "text_dim": "#6c6c80",
    "border": "#2a2a4a",
    "border_light": "#3a3a5a",
}

GLOBAL_STYLE = f"""
/* ─── 全局 ──────────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {COLORS['bg_primary']};
    color: {COLORS['text_primary']};
    font-family: "Microsoft YaHei", "微软雅黑", "Segoe UI", sans-serif;
    font-size: 14px;
}}

/* ─── 标签页 ─────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    background: {COLORS['bg_secondary']};
    margin-top: -1px;
}}

QTabBar::tab {{
    background: {COLORS['bg_card']};
    color: {COLORS['text_secondary']};
    padding: 12px 28px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-size: 15px;
    font-weight: bold;
    min-width: 100px;
}}

QTabBar::tab:selected {{
    background: {COLORS['bg_secondary']};
    color: {COLORS['accent']};
    border-bottom: 3px solid {COLORS['accent']};
}}

QTabBar::tab:hover:!selected {{
    background: {COLORS['bg_input']};
    color: {COLORS['text_primary']};
}}

/* ─── 按钮 ──────────────────────────────────── */
QPushButton {{
    background-color: {COLORS['bg_card']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: bold;
    min-height: 36px;
}}

QPushButton:hover {{
    background-color: {COLORS['bg_input']};
    border-color: {COLORS['accent2']};
}}

QPushButton:pressed {{
    background-color: {COLORS['accent']};
}}

QPushButton#btn_print {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {COLORS['accent']}, stop:1 #c0392b);
    color: white;
    font-size: 22px;
    min-height: 60px;
    border: none;
    border-radius: 12px;
}}

QPushButton#btn_print:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {COLORS['accent_hover']}, stop:1 {COLORS['accent']});
}}

QPushButton#btn_print:disabled {{
    background: {COLORS['bg_card']};
    color: {COLORS['text_dim']};
}}

QPushButton#btn_clear {{
    background: {COLORS['bg_card']};
    color: {COLORS['warning']};
    border: 1px solid {COLORS['warning']};
    font-size: 16px;
    min-height: 40px;
}}

/* ─── 输入框 (彻底修复 Win7 挤压问题) ──────────── */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{
    background-color: {COLORS['bg_input']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 14px;
    min-height: 38px;
}}

QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {COLORS['accent2']};
}}

QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    width: 28px;
    border: none;
    background: {COLORS['border']};
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
}}

QComboBox QAbstractItemView {{
    background: {COLORS['bg_card']};
    color: {COLORS['text_primary']};
    selection-background-color: {COLORS['accent']};
    border: 1px solid {COLORS['border']};
    padding: 6px;
}}

/* ─── 表格 ──────────────────────────────────── */
QTableWidget {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
    gridline-color: {COLORS['border']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    font-size: 13px;
}}

QTableWidget::item {{
    padding: 8px;
    border-bottom: 1px solid {COLORS['border']};
}}

QTableWidget::item:selected {{
    background-color: {COLORS['accent']};
    color: white;
}}

QHeaderView::section {{
    background-color: {COLORS['bg_card']};
    color: {COLORS['accent2']};
    padding: 10px;
    border: none;
    border-bottom: 2px solid {COLORS['accent']};
    font-weight: bold;
    font-size: 13px;
}}

/* ─── 分组框 ─────────────────────────────────── */
QGroupBox {{
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    margin-top: 16px;
    padding-top: 20px;
    padding-bottom: 12px;
    font-weight: bold;
    color: {COLORS['accent2']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
}}

/* ─── 滚动条 ─────────────────────────────────── */
QScrollArea {{
    border: none;
    background-color: transparent;
}}

QScrollBar:vertical {{
    background: {COLORS['bg_primary']};
    width: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background: {COLORS['border_light']};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* ─── 标签 ──────────────────────────────────── */
QLabel#lbl_weight {{
    color: {COLORS['accent2']};
    font-size: 72px;
    font-weight: bold;
    padding: 20px;
}}

QLabel#lbl_price {{
    color: {COLORS['accent']};
    font-size: 48px;
    font-weight: bold;
    padding: 10px;
}}

QLabel#lbl_status {{
    color: {COLORS['success']};
    font-size: 13px;
    padding: 4px 8px;
    border-radius: 4px;
}}

QLabel#lbl_unit {{
    color: {COLORS['text_secondary']};
    font-size: 24px;
}}

/* ─── 状态栏 ─────────────────────────────────── */
QStatusBar {{
    background: {COLORS['bg_card']};
    color: {COLORS['text_secondary']};
    border-top: 1px solid {COLORS['border']};
    font-size: 12px;
}}

/* ─── 消息提示 ────────────────────────────────── */
QMessageBox {{
    background: {COLORS['bg_secondary']};
}}

QMessageBox QLabel {{
    color: {COLORS['text_primary']};
    font-size: 14px;
}}
"""
