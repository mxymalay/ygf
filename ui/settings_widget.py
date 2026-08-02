"""
系统设置界面 — 高端左侧导航栏 + 卡片化极简 UI
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QMessageBox, QScrollArea, QStackedWidget, QButtonGroup
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence

from config import save_config
from utils.port_scanner import scan_printers


class HotKeyRecorderEdit(QLineEdit):
    """按键实时录制框：鼠标点击后直接在键盘上敲击组合键 (如 Shift+Q 或 F12) 自动录制"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(u"点击此处并按快捷键 (如 Shift+Q 或 F12)")
        self.setStyleSheet("""
            QLineEdit {
                background-color: #0F172A;
                color: #38BDF8;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 10px 16px;
                font-size: 14px;
                font-weight: bold;
            }
            QLineEdit:focus {
                border: 2px solid #38BDF8;
                background-color: #1E293B;
            }
        """)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return

        modifiers = event.modifiers()
        parts = []
        if modifiers & Qt.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.AltModifier:
            parts.append("Alt")

        key_str = ""
        if Qt.Key_F1 <= key <= Qt.Key_F12:
            key_str = f"F{key - Qt.Key_F1 + 1}"
        else:
            txt = event.text().upper()
            if txt and (txt.isalnum() or txt in "+-*/"):
                key_str = txt
            else:
                key_str = QKeySequence(key).toString().upper()

        if key_str:
            parts.append(key_str)
            hk_text = "+".join(parts)
            self.setText(hk_text)


class SettingsWidget(QWidget):
    """系统设置界面"""

    NAV_ITEMS = [
        ("scale", u"⚖️  电子秤设置"),
        ("printer", u"🖨️  小票打印机"),
        ("biz", u"🏪  店铺与计价"),
        ("sys", u"⚙️  系统与流转"),
        ("sqb", u"💵  收钱吧插件"),
        ("danger", u"⚠️  重置与恢复"),
    ]

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.nav_buttons = []
        self._build_ui()

    def _make_label(self, text):
        """统一生成右对齐、无黑框颜色的优雅 Label"""
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl.setStyleSheet("color: #94A3B8; font-size: 14px; font-weight: 600; background: transparent; padding-right: 4px;")
        return lbl

    def _style_save_btn(self, btn):
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10B981);
                color: #FFFFFF;
                font-size: 15px;
                font-weight: bold;
                padding: 12px 28px;
                border-radius: 10px;
                border: none;
            }
            QPushButton:hover {
                background: #10B981;
            }
            QPushButton:pressed {
                background: #047857;
            }
        """)

    def _create_section_card(self, title_icon, title_text, subtitle_text=""):
        """创建一个高端卡片容器"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame#SettingCard {
                background-color: #1E293B;
                border-radius: 16px;
                border: 1px solid #334155;
            }
        """)
        card.setObjectName("SettingCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 28, 32, 32)
        card_layout.setSpacing(24)

        # 头部标题
        header_box = QVBoxLayout()
        header_box.setSpacing(6)
        
        lbl_head = QLabel(f"{title_icon} {title_text}")
        lbl_head.setStyleSheet("font-size: 22px; font-weight: 900; color: #F8FAFC; border: none; background: transparent;")
        header_box.addWidget(lbl_head)

        if subtitle_text:
            lbl_sub = QLabel(subtitle_text)
            lbl_sub.setStyleSheet("font-size: 13px; color: #94A3B8; border: none; background: transparent;")
            header_box.addWidget(lbl_sub)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #334155; border: none; min-height: 1px; max-height: 1px;")

        card_layout.addLayout(header_box)
        card_layout.addWidget(line)

        return card, card_layout

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ════════════════════════════════════════════════════════════
        # 左侧导航栏 (Left Sidebar)
        # ════════════════════════════════════════════════════════════
        sidebar = QFrame()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet("""
            QFrame#SettingsSidebar {
                background-color: #0F172A;
                border-right: 1px solid #1E293B;
            }
            QLabel {
                background: transparent;
            }
        """)
        sidebar.setObjectName("SettingsSidebar")

        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(16, 24, 16, 24)
        sb_layout.setSpacing(10)

        # 侧边栏标题
        lbl_sb_title = QLabel(u"⚙️ 系统设置")
        lbl_sb_title.setStyleSheet("font-size: 20px; font-weight: 900; color: #F8FAFC; padding-left: 8px; margin-bottom: 12px;")
        sb_layout.addWidget(lbl_sb_title)

        # 导航按钮组
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        for idx, (nav_id, label) in enumerate(self.NAV_ITEMS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 14px 16px;
                    font-size: 15px;
                    font-weight: 600;
                    color: #94A3B8;
                    background-color: transparent;
                    border-radius: 10px;
                    border: none;
                }
                QPushButton:hover {
                    color: #F1F5F9;
                    background-color: #1E293B;
                }
                QPushButton:checked {
                    color: #38BDF8;
                    background-color: #1E293B;
                    font-weight: bold;
                    border-left: 4px solid #38BDF8;
                }
            """)
            self.btn_group.addButton(btn, idx)
            self.nav_buttons.append(btn)
            sb_layout.addWidget(btn)

        sb_layout.addStretch()

        # 版本标记底栏
        lbl_ver = QLabel(u"v2.5 Pro 店面自动化版")
        lbl_ver.setStyleSheet("color: #475569; font-size: 12px; padding-left: 8px;")
        sb_layout.addWidget(lbl_ver)

        main_layout.addWidget(sidebar)

        # ════════════════════════════════════════════════════════════
        # 右侧 QStackedWidget (各个设置卡片)
        # ════════════════════════════════════════════════════════════
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet("""
            QStackedWidget {
                background-color: #0B1120;
            }
            QLabel {
                color: #E2E8F0;
                font-size: 14px;
                background: transparent;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 10px 16px;
                font-size: 14px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #38BDF8;
                background-color: #0F172A;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {
                width: 0px;
                height: 0px;
                border: none;
                background: transparent;
            }
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                width: 0px;
                height: 0px;
                border: none;
                background: transparent;
            }
        """)

        # 1. 称重设置页
        self.stacked_widget.addWidget(self._build_scale_page())
        # 2. 打印机设置页
        self.stacked_widget.addWidget(self._build_printer_page())
        # 3. 店铺与计价设置页
        self.stacked_widget.addWidget(self._build_biz_page())
        # 4. 系统与流转设置页
        self.stacked_widget.addWidget(self._build_sys_page())
        # 5. 收钱吧设置页
        self.stacked_widget.addWidget(self._build_sqb_page())
        # 6. 重置与恢复设置页
        self.stacked_widget.addWidget(self._build_danger_page())

        main_layout.addWidget(self.stacked_widget, stretch=1)

        # 绑定导航栏切换
        self.btn_group.buttonClicked[int].connect(self.stacked_widget.setCurrentIndex)
        self.nav_buttons[0].setChecked(True)

        # 全局触控下拉框统一美化
        from ui.styles import apply_touch_combo_style
        for combo in self.findChildren(QComboBox):
            apply_touch_combo_style(combo, item_height=48)

        self._disable_wheel_events()

    def _wrap_in_scroll(self, card_widget):
        """将卡片包裹在滚动区域中，防止低分辨率挤压"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #0B1120; }")
        
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(40, 36, 40, 36)
        wrapper_layout.addWidget(card_widget)
        wrapper_layout.addStretch()

        scroll.setWidget(wrapper)
        return scroll

    # ────────────────────────────────────────────────────────────
    # 页面 1: 称重数据源设置
    # ────────────────────────────────────────────────────────────
    def _build_scale_page(self):
        card, layout = self._create_section_card(
            u"⚖️", u"称重数据源设置", u"配置硬件电子秤接口或官方收银系统串口日志抓取"
        )
        grid = QGridLayout()
        grid.setSpacing(18)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._make_label(u"数据来源："), 0, 0)
        self.cmb_scale_source = QComboBox()
        self.cmb_scale_source.addItems([
            u"official - 官方收银系统 (OCR读取日志)",
            u"com - 串口直连电子秤 (COM口)"
        ])
        source = self.config.get("scale_source", "official")
        if source == "com":
            self.cmb_scale_source.setCurrentIndex(1)
        self.cmb_scale_source.currentIndexChanged.connect(self._on_scale_source_changed)
        grid.addWidget(self.cmb_scale_source, 0, 1, 1, 2)

        # COM口配置 (仅串口模式可见)
        self.lbl_scale_port = self._make_label(u"秤串口 (COM)：")
        grid.addWidget(self.lbl_scale_port, 1, 0)
        self.cmb_scale_port = QComboBox()
        self.cmb_scale_port.setEditable(True)
        self._refresh_scale_com_ports()
        grid.addWidget(self.cmb_scale_port, 1, 1)

        self.btn_refresh_scale_ports = QPushButton(u"🔄 扫描COM口")
        self.btn_refresh_scale_ports.setCursor(Qt.PointingHandCursor)
        self.btn_refresh_scale_ports.setStyleSheet("""
            QPushButton { background: #334155; color: #F8FAFC; border: 1px solid #475569; border-radius: 8px; padding: 10px 18px; font-weight: bold; }
            QPushButton:hover { background: #38BDF8; color: #0F172A; }
        """)
        self.btn_refresh_scale_ports.clicked.connect(self._refresh_scale_com_ports)
        grid.addWidget(self.btn_refresh_scale_ports, 1, 2)

        self.lbl_scale_baud = self._make_label(u"波特率：")
        grid.addWidget(self.lbl_scale_baud, 2, 0)
        self.cmb_scale_baud = QComboBox()
        self.cmb_scale_baud.addItems(["2400", "4800", "9600", "19200", "38400", "115200"])
        cur_baud = str(self.config.get("scale_baudrate", 9600))
        self.cmb_scale_baud.setCurrentText(cur_baud)
        grid.addWidget(self.cmb_scale_baud, 2, 1, 1, 2)

        # 提示信息
        self.lbl_scale_hint = QLabel("")
        self.lbl_scale_hint.setWordWrap(True)
        self.lbl_scale_hint.setStyleSheet("color: #94A3B8; font-size: 13px; padding: 10px 14px; background: #0F172A; border-radius: 10px; border: 1px solid #1E293B;")
        grid.addWidget(self.lbl_scale_hint, 3, 0, 1, 3)

        layout.addLayout(grid)

        btn_save_scale = QPushButton(u"💾 保存称重设置 (需重启)")
        self._style_save_btn(btn_save_scale)
        btn_save_scale.clicked.connect(self._on_save_scale)
        layout.addWidget(btn_save_scale, alignment=Qt.AlignRight)

        # 初始化显示/隐藏
        self._on_scale_source_changed(self.cmb_scale_source.currentIndex())

        return self._wrap_in_scroll(card)

    # ────────────────────────────────────────────────────────────
    # 页面 2: 打印机设置
    # ────────────────────────────────────────────────────────────
    def _build_printer_page(self):
        card, layout = self._create_section_card(
            u"🖨️", u"小票打印机设置", u"设置连接的厨打/后厨/前台小票打印机"
        )
        grid = QGridLayout()
        grid.setSpacing(18)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._make_label(u"打印方式："), 0, 0)
        self.cmb_printer_type = QComboBox()
        self.cmb_printer_type.addItems([
            "windows - Windows 驱动打印",
            "network - 网络打印",
            "serial - 串口打印",
        ])
        pt = self.config.get("printer_type", "windows")
        for i in range(self.cmb_printer_type.count()):
            if self.cmb_printer_type.itemText(i).startswith(pt):
                self.cmb_printer_type.setCurrentIndex(i)
                break
        grid.addWidget(self.cmb_printer_type, 0, 1, 1, 2)

        grid.addWidget(self._make_label(u"打印机名称："), 1, 0)
        self.cmb_printer_name = QComboBox()
        self.cmb_printer_name.setEditable(True)
        self._refresh_printers()
        grid.addWidget(self.cmb_printer_name, 1, 1)

        btn_rp = QPushButton(u"🔄 刷新打印机")
        btn_rp.setCursor(Qt.PointingHandCursor)
        btn_rp.setStyleSheet("""
            QPushButton { background: #334155; color: #F8FAFC; border: 1px solid #475569; border-radius: 8px; padding: 10px 18px; font-weight: bold; }
            QPushButton:hover { background: #38BDF8; color: #0F172A; }
        """)
        btn_rp.clicked.connect(self._refresh_printers)
        grid.addWidget(btn_rp, 1, 2)

        grid.addWidget(self._make_label(u"网络 IP："), 2, 0)
        self.txt_ip = QLineEdit(self.config.get("printer_ip", "192.168.1.100"))
        grid.addWidget(self.txt_ip, 2, 1)

        grid.addWidget(self._make_label(u"端口："), 2, 2)
        self.spin_net_port = QSpinBox()
        self.spin_net_port.setRange(1, 65535)
        self.spin_net_port.setValue(self.config.get("printer_port", 9100))
        grid.addWidget(self.spin_net_port, 2, 3)

        layout.addLayout(grid)

        btn_save_printer = QPushButton(u"💾 保存打印机设置")
        self._style_save_btn(btn_save_printer)
        btn_save_printer.clicked.connect(self._on_save_printer)
        layout.addWidget(btn_save_printer, alignment=Qt.AlignRight)

        return self._wrap_in_scroll(card)

    # ────────────────────────────────────────────────────────────
    # 页面 3: 店铺与计价设置
    # ────────────────────────────────────────────────────────────
    def _build_biz_page(self):
        card, layout = self._create_section_card(
            u"🏪", u"店铺与计价设置", u"设置小票头部标题、分店名称、单价与计价单位"
        )
        grid = QGridLayout()
        grid.setSpacing(18)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._make_label(u"店名："), 0, 0)
        self.txt_shop = QLineEdit(self.config.get("shop_name", u"杨国福麻辣烫"))
        grid.addWidget(self.txt_shop, 0, 1, 1, 2)

        grid.addWidget(self._make_label(u"分店名称："), 1, 0)
        self.txt_sub = QLineEdit(self.config.get("shop_subtitle", u""))
        self.txt_sub.setPlaceholderText(u"例如：杨国福(肥西水晶城店)")
        grid.addWidget(self.txt_sub, 1, 1, 1, 2)

        grid.addWidget(self._make_label(u"小票底部文字："), 2, 0)
        self.txt_footer = QLineEdit(self.config.get("receipt_footer", u"谢谢惠顾！"))
        self.txt_footer.setPlaceholderText(u"例如：谢谢惠顾！")
        grid.addWidget(self.txt_footer, 2, 1, 1, 2)

        grid.addWidget(self._make_label(u"计价方式："), 3, 0)
        self.cmb_unit = QComboBox()
        self.cmb_unit.addItems(["per_jin - 按斤计价", "per_kg - 按公斤计价"])
        pu = self.config.get("price_unit", "per_jin")
        for i in range(self.cmb_unit.count()):
            if self.cmb_unit.itemText(i).startswith(pu):
                self.cmb_unit.setCurrentIndex(i)
                break
        grid.addWidget(self.cmb_unit, 3, 1, 1, 2)

        grid.addWidget(self._make_label(u"标准汤底单价："), 4, 0)
        self.spin_default_price = QDoubleSpinBox()
        self.spin_default_price.setRange(0.01, 999.99)
        self.spin_default_price.setValue(self.config.get("unit_price", 47.60))
        self.spin_default_price.setDecimals(2)
        grid.addWidget(self.spin_default_price, 4, 1, 1, 2)

        grid.addWidget(self._make_label(u"精品汤底单价："), 5, 0)
        self.spin_special_price = QDoubleSpinBox()
        self.spin_special_price.setRange(0.01, 999.99)
        self.spin_special_price.setValue(self.config.get("special_soup_price", 50.00))
        self.spin_special_price.setDecimals(2)
        grid.addWidget(self.spin_special_price, 5, 1, 1, 2)

        layout.addLayout(grid)

        btn_save_biz = QPushButton(u"💾 保存店铺与计价设置")
        self._style_save_btn(btn_save_biz)
        btn_save_biz.clicked.connect(self._on_save_biz)
        layout.addWidget(btn_save_biz, alignment=Qt.AlignRight)

        return self._wrap_in_scroll(card)

    # ────────────────────────────────────────────────────────────
    # 页面 4: 系统与流转设置
    # ────────────────────────────────────────────────────────────
    def _build_sys_page(self):
        card, layout = self._create_section_card(
            u"⚙️", u"系统运行与触屏悬浮球", u"配置 Windows 开机自启、缓冲区延迟与桌面常驻悬浮球"
        )
        grid = QGridLayout()
        grid.setSpacing(18)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._make_label(u"开机自启动："), 0, 0)
        self.cmb_auto_start = QComboBox()
        self.cmb_auto_start.addItems([u"开启 - 随 Windows 启动并打开点餐系统", u"关闭 - 仅允许手动启动"])
        if not self.config.get("auto_start_enabled", True):
            self.cmb_auto_start.setCurrentIndex(1)
        grid.addWidget(self.cmb_auto_start, 0, 1, 1, 2)

        grid.addWidget(self._make_label(u"自启缓冲延迟："), 1, 0)
        self.spin_auto_start_delay = QSpinBox()
        self.spin_auto_start_delay.setRange(0, 60)
        self.spin_auto_start_delay.setSuffix(u" 秒")
        self.spin_auto_start_delay.setToolTip(u"设置软件随系统开机后静默等待的秒数，用于等待网卡和串口驱动加载完毕。")
        self.spin_auto_start_delay.setValue(self.config.get("auto_start_delay", 8))
        grid.addWidget(self.spin_auto_start_delay, 1, 1, 1, 2)

        grid.addWidget(self._make_label(u"桌面常驻触屏悬浮球："), 2, 0)
        self.cmb_floating_ball = QComboBox()
        self.cmb_floating_ball.addItems([u"开启 - 在屏幕边缘显示半透明触屏切换球", u"关闭 - 隐藏悬浮球"])
        if not self.config.get("floating_ball_enabled", True):
            self.cmb_floating_ball.setCurrentIndex(1)
        grid.addWidget(self.cmb_floating_ball, 2, 1, 1, 2)

        layout.addLayout(grid)

        btn_save_sys = QPushButton(u"💾 保存系统设置")
        self._style_save_btn(btn_save_sys)
        btn_save_sys.clicked.connect(self._on_save_sys)
        layout.addWidget(btn_save_sys, alignment=Qt.AlignRight)

        return self._wrap_in_scroll(card)

    # ────────────────────────────────────────────────────────────
    # 页面 5: 收钱吧设置
    # ────────────────────────────────────────────────────────────
    def _build_sqb_page(self):
        card, layout = self._create_section_card(
            u"💵", u"收钱吧 PC收款助手", u"配置自动向收钱吧软件推送金额及呼起热键"
        )
        grid = QGridLayout()
        grid.setSpacing(18)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._make_label(u"自动推送金额："), 0, 0)
        self.cmb_sqb_enable = QComboBox()
        self.cmb_sqb_enable.addItems([u"开启 - 自动推送结账金额到收钱吧", u"关闭 - 不推送"])
        if not self.config.get("shouqianba_enabled", True):
            self.cmb_sqb_enable.setCurrentIndex(1)
        grid.addWidget(self.cmb_sqb_enable, 0, 1, 1, 2)

        grid.addWidget(self._make_label(u"串口 (COM端口)："), 1, 0)
        self.cmb_sqb_port = QComboBox()
        self.cmb_sqb_port.setEditable(True)
        self._refresh_com_ports()
        grid.addWidget(self.cmb_sqb_port, 1, 1)

        btn_refresh_ports = QPushButton(u"🔄 扫描COM端口")
        btn_refresh_ports.setCursor(Qt.PointingHandCursor)
        btn_refresh_ports.setStyleSheet("""
            QPushButton { background: #334155; color: #F8FAFC; border: 1px solid #475569; border-radius: 8px; padding: 10px 18px; font-weight: bold; }
            QPushButton:hover { background: #38BDF8; color: #0F172A; }
        """)
        btn_refresh_ports.clicked.connect(self._refresh_com_ports)
        grid.addWidget(btn_refresh_ports, 1, 2)

        grid.addWidget(self._make_label(u"波特率 (Baudrate)："), 2, 0)
        self.cmb_sqb_baud = QComboBox()
        self.cmb_sqb_baud.addItems(["2400", "9600", "19200", "38400", "115200"])
        cur_baud = str(self.config.get("shouqianba_baudrate", 2400))
        self.cmb_sqb_baud.setCurrentText(cur_baud)
        grid.addWidget(self.cmb_sqb_baud, 2, 1, 1, 2)

        grid.addWidget(self._make_label(u"解析规则："), 3, 0)
        self.cmb_sqb_fmt = QComboBox()
        self.cmb_sqb_fmt.addItems([
            u"QA - QA标记 (例如 QA12.50)",
            u"FLOAT - 纯数字 (例如 12.50)"
        ])
        fmt = self.config.get("shouqianba_format", "QA")
        if fmt == "FLOAT":
            self.cmb_sqb_fmt.setCurrentIndex(1)
        grid.addWidget(self.cmb_sqb_fmt, 3, 1, 1, 2)

        grid.addWidget(self._make_label(u"唤起快捷键："), 4, 0)
        
        hk_box = QHBoxLayout()
        self.txt_sqb_hotkey = HotKeyRecorderEdit()
        cur_hk = str(self.config.get("shouqianba_hotkey", "Shift+Q"))
        self.txt_sqb_hotkey.setText(cur_hk)
        hk_box.addWidget(self.txt_sqb_hotkey, stretch=2)

        # 快速预设按钮
        for hk_item in ["Shift+Q", "F12", "Ctrl+F12", "Alt+S"]:
            btn_hk = QPushButton(hk_item)
            btn_hk.setCursor(Qt.PointingHandCursor)
            btn_hk.setStyleSheet("""
                QPushButton {
                    background: #334155; color: #F8FAFC; border: 1px solid #475569;
                    border-radius: 8px; padding: 8px 14px; font-weight: bold;
                }
                QPushButton:hover { background: #38BDF8; color: #0F172A; }
            """)
            btn_hk.clicked.connect(lambda chk, t=hk_item: self.txt_sqb_hotkey.setText(t))
            hk_box.addWidget(btn_hk)

        grid.addLayout(hk_box, 4, 1, 1, 2)

        layout.addLayout(grid)

        btn_save_sqb = QPushButton(u"💾 保存收钱吧设置")
        self._style_save_btn(btn_save_sqb)
        btn_save_sqb.clicked.connect(self._on_save_sqb)
        layout.addWidget(btn_save_sqb, alignment=Qt.AlignRight)

        return self._wrap_in_scroll(card)

    # ────────────────────────────────────────────────────────────
    # 页面 6: 危险操作与恢复
    # ────────────────────────────────────────────────────────────
    def _build_danger_page(self):
        card, layout = self._create_section_card(
            u"⚠️", u"危险操作与数据重置", u"清除本地全部配置及销售记录数据库"
        )
        card.setStyleSheet("""
            QFrame#SettingCard {
                background-color: #1E293B;
                border-radius: 16px;
                border: 2px solid #DC2626;
            }
        """)

        info_box = QVBoxLayout()
        info_box.setSpacing(12)

        lbl_warn_title = QLabel(u"🚨 高危警示")
        lbl_warn_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #EF4444; background: transparent;")
        info_box.addWidget(lbl_warn_title)

        lbl_danger = QLabel(u"点击“重置软件数据”将彻底清空本地的配置文件 (config.json) 以及所有的历史点餐销售数据库 (pos.db)。此操作不可逆！")
        lbl_danger.setWordWrap(True)
        lbl_danger.setStyleSheet("color: #FCA5A5; font-size: 14px; line-height: 1.6; background: #2C0F14; padding: 16px; border-radius: 10px; border: 1px solid #7F1D1D;")
        info_box.addWidget(lbl_danger)

        layout.addLayout(info_box)

        btn_reset = QPushButton(u"🔥 清空全部数据并重置软件")
        btn_reset.setCursor(Qt.PointingHandCursor)
        btn_reset.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #DC2626, stop:1 #EF4444);
                color: white; font-size: 15px; font-weight: bold; padding: 12px 28px; border-radius: 10px; border: none;
            }
            QPushButton:hover { background: #B91C1C; }
        """)
        btn_reset.clicked.connect(self._on_reset)
        layout.addWidget(btn_reset, alignment=Qt.AlignLeft)

        return self._wrap_in_scroll(card)

    def _disable_wheel_events(self):
        """禁止鼠标滚轮在控件上意外修改数值"""
        for widget in self.findChildren((QComboBox, QSpinBox, QDoubleSpinBox)):
            widget.wheelEvent = lambda event, w=widget: event.ignore()

    # ─── 刷新 COM 串口列表 ──────────────────────────
    def _refresh_com_ports(self):
        self.cmb_sqb_port.clear()
        try:
            from core.shouqianba_sender import get_available_com_ports
            ports = get_available_com_ports()
        except Exception:
            ports = []
        all_ports = [f"COM{i}" for i in range(1, 13)]
        for p in ports:
            if p not in all_ports:
                all_ports.append(p)
        for p in sorted(all_ports, key=lambda x: int(x.replace("COM", "")) if x.startswith("COM") and x[3:].isdigit() else 99):
            self.cmb_sqb_port.addItem(p)
        cur = self.config.get("shouqianba_port", "COM1")
        if cur:
            self.cmb_sqb_port.setCurrentText(cur)

    # ─── 刷新打印机列表 ──────────────────────────────
    def _refresh_printers(self):
        self.cmb_printer_name.clear()
        printers = scan_printers()
        for name in printers:
            self.cmb_printer_name.addItem(name)
        cur = self.config.get("printer_name", "shouyin")
        if cur:
            self.cmb_printer_name.setCurrentText(cur)

    # ─── 保存设置 ──────────────────────────────────
    def _on_save_printer(self):
        pt_text = self.cmb_printer_type.currentText()
        self.config["printer_type"] = pt_text.split(" - ")[0].strip()
        self.config["printer_name"] = self.cmb_printer_name.currentText()
        self.config["printer_ip"] = self.txt_ip.text()
        self.config["printer_port"] = self.spin_net_port.value()
        save_config(self.config)
        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"打印机设置已保存！")

    def _on_save_biz(self):
        self.config["shop_name"] = self.txt_shop.text()
        self.config["shop_subtitle"] = self.txt_sub.text()
        self.config["receipt_footer"] = self.txt_footer.text()
        pu_text = self.cmb_unit.currentText()
        self.config["price_unit"] = pu_text.split(" - ")[0].strip()
        self.config["unit_price"] = self.spin_default_price.value()
        self.config["special_soup_price"] = self.spin_special_price.value()
        save_config(self.config)
        parent_mw = self.window()
        if hasattr(parent_mw, 'sale_page'):
            parent_mw.sale_page.refresh_unit_price_info()
        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"店铺与计价设置已保存！")

    def _on_save_sys(self):
        self.config["auto_start_enabled"] = (self.cmb_auto_start.currentIndex() == 0)
        self.config["auto_start_delay"] = self.spin_auto_start_delay.value()
        self.config["floating_ball_enabled"] = (self.cmb_floating_ball.currentIndex() == 0)
        save_config(self.config)

        from utils.system_utils import apply_auto_start_settings
        apply_auto_start_settings(
            self.config["auto_start_enabled"], 
            self.config["auto_start_delay"]
        )

        parent_mw = self.window()
        if hasattr(parent_mw, 'switch_controller') and parent_mw.switch_controller:
            parent_mw.switch_controller.update_config(self.config)

        if hasattr(parent_mw, 'floating_ball') and parent_mw.floating_ball:
            if self.config["floating_ball_enabled"]:
                parent_mw.floating_ball.show()
            else:
                parent_mw.floating_ball.hide()

        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"系统运行与智能切换设置已保存！")

    def _on_scale_source_changed(self, index):
        """切换称重数据源时，显示/隐藏COM口配置"""
        is_com = (index == 1)
        self.lbl_scale_port.setVisible(is_com)
        self.cmb_scale_port.setVisible(is_com)
        self.btn_refresh_scale_ports.setVisible(is_com)
        self.lbl_scale_baud.setVisible(is_com)
        self.cmb_scale_baud.setVisible(is_com)
        if is_com:
            self.lbl_scale_hint.setText(
                u"串口模式：直接连接电子秤的COM口读取重量数据，无需启动官方收银软件。\n"
                u"请确认秤的串口线已正确连接，并选择对应的COM端口和波特率。"
            )
        else:
            self.lbl_scale_hint.setText(
                u"官方模式：自动从杨国福官方收银系统的串口日志中实时读取重量，需先启动官方收银软件。"
            )

    def _refresh_scale_com_ports(self):
        """扫描可用COM端口 (称重秤专用)"""
        self.cmb_scale_port.clear()
        active_ports = []
        try:
            import serial.tools.list_ports
            active_ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            pass
        all_ports = [f"COM{i}" for i in range(1, 13)]
        for p in active_ports:
            if p not in all_ports:
                all_ports.append(p)
        for p in sorted(all_ports, key=lambda x: int(x.replace("COM", "")) if x.startswith("COM") and x[3:].isdigit() else 99):
            if p in active_ports:
                self.cmb_scale_port.addItem(f"{p}  [已连接]")
            else:
                self.cmb_scale_port.addItem(p)
        cur = self.config.get("scale_port", "COM2")
        if cur:
            for i in range(self.cmb_scale_port.count()):
                if self.cmb_scale_port.itemText(i).startswith(cur):
                    self.cmb_scale_port.setCurrentIndex(i)
                    break
        if hasattr(self, 'lbl_scale_hint'):
            if active_ports:
                self.lbl_scale_hint.setText(u"扫描完成！检测到活跃端口: %s" % ", ".join(active_ports))
                self.lbl_scale_hint.setStyleSheet("color: #34D399; font-size: 13px; padding: 10px 14px; background: #0F172A; border-radius: 10px; border: 1px solid #1E293B;")
            else:
                self.lbl_scale_hint.setText(u"扫描完成，未检测到任何活跃的COM端口。请检查串口线是否连接。")
                self.lbl_scale_hint.setStyleSheet("color: #FBBF24; font-size: 13px; padding: 10px 14px; background: #0F172A; border-radius: 10px; border: 1px solid #1E293B;")

    def _on_save_scale(self):
        """保存称重数据源设置"""
        source_text = self.cmb_scale_source.currentText()
        self.config["scale_source"] = source_text.split(" - ")[0].strip()
        port_text = self.cmb_scale_port.currentText().strip()
        port_text = port_text.split("[")[0].strip()
        self.config["scale_port"] = port_text
        try:
            self.config["scale_baudrate"] = int(self.cmb_scale_baud.currentText().strip())
        except Exception:
            self.config["scale_baudrate"] = 9600
        save_config(self.config)
        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"称重数据源设置已保存！\n切换数据源需要重启软件才能生效。")

    def _on_save_sqb(self):
        self.config["shouqianba_enabled"] = (self.cmb_sqb_enable.currentIndex() == 0)
        self.config["shouqianba_port"] = self.cmb_sqb_port.currentText().strip()
        try:
            self.config["shouqianba_baudrate"] = int(self.cmb_sqb_baud.currentText().strip())
        except Exception:
            self.config["shouqianba_baudrate"] = 2400
        fmt_text = self.cmb_sqb_fmt.currentText()
        self.config["shouqianba_format"] = fmt_text.split(" - ")[0].strip()
        self.config["shouqianba_hotkey"] = self.txt_sqb_hotkey.text().strip()
        save_config(self.config)
        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"收钱吧设置已保存！")

    def _on_reset(self):
        """重置软件（危险操作）"""
        r1 = QMessageBox.warning(
            self, u"严重警告", 
            u"您正在进行危险操作！\n这将会清除所有的本地设置以及所有的历史订单数据！\n您确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if r1 != QMessageBox.Yes:
            return

        r2 = QMessageBox.warning(
            self, u"最后警告", 
            u"数据一旦删除将【永远无法恢复】。\n您真的确定要删除数据库和配置文件吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if r2 != QMessageBox.Yes:
            return
        
        r3 = QMessageBox.critical(
            self, u"最终确认", 
            u"这是最后一次确认机会。\n点击 Yes 将立即清除数据并关闭软件！",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if r3 != QMessageBox.Yes:
            return
        
        try:
            import os
            from config import DB_PATH, CONFIG_FILE
            
            if os.path.exists(DB_PATH):
                try:
                    os.remove(DB_PATH)
                except Exception as e:
                    print(f"Failed to remove DB: {e}")
                    
            if os.path.exists(CONFIG_FILE):
                try:
                    os.remove(CONFIG_FILE)
                except Exception as e:
                    print(f"Failed to remove config: {e}")
            
            QMessageBox.information(
                self, u"重置成功", 
                u"软件已成功重置所有数据！\n程序即将关闭，请手动重新打开以生成全新的环境。"
            )
            from PyQt5.QtWidgets import QApplication
            QApplication.quit()
            
        except Exception as e:
            QMessageBox.critical(self, u"重置失败", f"重置过程中出现意外错误:\n{e}")
