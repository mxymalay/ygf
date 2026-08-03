"""
系统设置界面 — 高端左侧导航栏 + 卡片化极简 UI
PyQt5 + Python 3.8 兼容
"""
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QMessageBox, QScrollArea, QStackedWidget, QButtonGroup,
    QFileDialog
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence

from config import DATA_DIR, save_config, reset_module_config, export_config_bundle, import_config_bundle
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
        ("danger", u"⚠️  还原与重置"),
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
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(18)

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
        sidebar.setFixedWidth(190)
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

        # 全局触控下拉框、选择框与数字框统一美化
        from ui.styles import apply_touch_combo_style, apply_touch_checkbox_style, apply_touch_spinbox_style
        from PyQt5.QtWidgets import QCheckBox
        for combo in self.findChildren(QComboBox):
            apply_touch_combo_style(combo, item_height=48)
        for chk in self.findChildren(QCheckBox):
            apply_touch_checkbox_style(chk)
        for spin in self.findChildren((QSpinBox, QDoubleSpinBox)):
            apply_touch_spinbox_style(spin)

        self._disable_wheel_events()

    def _wrap_in_scroll(self, card_widget):
        """将卡片包裹在滚动区域中，防止低分辨率挤压"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: #0B1120; }")
        
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(20, 20, 20, 20)
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
        self.lbl_scale_port = self._make_label(u"秤串口 (COM端口)：")
        grid.addWidget(self.lbl_scale_port, 1, 0)
        self.cmb_scale_port = QComboBox()
        self.cmb_scale_port.setEditable(True)
        self._refresh_scale_com_ports()
        grid.addWidget(self.cmb_scale_port, 1, 1)

        self.btn_refresh_scale_ports = QPushButton(u"🔄 扫描COM端口")
        self.btn_refresh_scale_ports.setCursor(Qt.PointingHandCursor)
        self.btn_refresh_scale_ports.setStyleSheet("""
            QPushButton { background: #334155; color: #F8FAFC; border: 1px solid #475569; border-radius: 8px; padding: 10px 18px; font-weight: bold; }
            QPushButton:hover { background: #38BDF8; color: #0F172A; }
        """)
        self.btn_refresh_scale_ports.clicked.connect(lambda: self._refresh_scale_com_ports(show_toast=True))
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

        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        self.btn_test_scale_com = QPushButton(u"⚡ 测试串口连接")
        self.btn_test_scale_com.setCursor(Qt.PointingHandCursor)
        self.btn_test_scale_com.setStyleSheet("""
            QPushButton {
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #0369A1;
            }
        """)
        self.btn_test_scale_com.clicked.connect(self._test_scale_com)
        btn_box.addWidget(self.btn_test_scale_com)

        self.btn_scale_bridge_status = QPushButton(u"🔎 查看桥接服务状态")
        self.btn_scale_bridge_status.setCursor(Qt.PointingHandCursor)
        self.btn_scale_bridge_status.setStyleSheet("""
            QPushButton {
                background-color: #334155; color: #F8FAFC; border: 1px solid #475569;
                border-radius: 8px; padding: 10px 18px; font-weight: bold;
            }
            QPushButton:hover { background-color: #475569; }
        """)
        self.btn_scale_bridge_status.clicked.connect(self._show_scale_bridge_status)
        btn_box.addWidget(self.btn_scale_bridge_status)

        btn_box.addStretch()

        btn_save_scale = QPushButton(u"💾 保存称重设置")
        self._style_save_btn(btn_save_scale)
        btn_save_scale.clicked.connect(self._on_save_scale)
        btn_box.addWidget(btn_save_scale)

        layout.addLayout(btn_box)

        # ScaleBridge is deliberately kept separate from the normal POS
        # settings above: saving it must never silently replace a live VSPD
        # split or install/modify a Windows driver.
        bridge_panel = QFrame()
        bridge_panel.setObjectName("ScaleBridgePanel")
        bridge_panel.setStyleSheet("""
            QFrame#ScaleBridgePanel {
                background: #132235; border: 1px solid #2563EB; border-radius: 12px;
            }
            QLineEdit, QComboBox { background: #0F172A; }
        """)
        bridge_layout = QVBoxLayout(bridge_panel)
        bridge_layout.setContentsMargins(16, 16, 16, 16)
        bridge_layout.setSpacing(12)

        bridge_title = QLabel(u"🔀 ScaleBridge 双 POS 串口服务（迁移配置）")
        bridge_title.setStyleSheet("font-size: 16px; color: #60A5FA; font-weight: bold;")
        bridge_layout.addWidget(bridge_title)
        bridge_desc = QLabel(
            u"仅配置未来的 Windows 服务，不会触碰当前 VSPD。服务唯一打开物理秤口；"
            u"官方/私有 POS 分别使用虚拟端口。"
        )
        bridge_desc.setWordWrap(True)
        bridge_desc.setStyleSheet("color: #CBD5E1; font-size: 12px;")
        bridge_layout.addWidget(bridge_desc)

        bridge_grid = QGridLayout()
        bridge_grid.setHorizontalSpacing(12)
        bridge_grid.setVerticalSpacing(10)
        bridge_grid.setColumnStretch(1, 1)
        bridge_grid.setColumnStretch(3, 1)

        bridge_grid.addWidget(self._make_label(u"物理秤端口："), 0, 0)
        self.cmb_bridge_physical_port = QComboBox()
        self.cmb_bridge_physical_port.setEditable(True)
        bridge_grid.addWidget(self.cmb_bridge_physical_port, 0, 1)
        self.btn_refresh_bridge_devices = QPushButton(u"🔄 识别物理设备")
        self.btn_refresh_bridge_devices.setCursor(Qt.PointingHandCursor)
        self.btn_refresh_bridge_devices.clicked.connect(self._refresh_scale_bridge_devices)
        bridge_grid.addWidget(self.btn_refresh_bridge_devices, 0, 2, 1, 2)

        bridge_grid.addWidget(self._make_label(u"官方 POS："), 1, 0)
        self.txt_bridge_official_pos = QLineEdit()
        self.txt_bridge_official_pos.setPlaceholderText("例如 COM2")
        bridge_grid.addWidget(self.txt_bridge_official_pos, 1, 1)
        bridge_grid.addWidget(self._make_label(u"服务官方对端："), 1, 2)
        self.txt_bridge_official_peer = QLineEdit()
        self.txt_bridge_official_peer.setPlaceholderText("例如 CNCB0")
        bridge_grid.addWidget(self.txt_bridge_official_peer, 1, 3)

        bridge_grid.addWidget(self._make_label(u"私有 POS："), 2, 0)
        self.txt_bridge_private_pos = QLineEdit()
        self.txt_bridge_private_pos.setPlaceholderText("例如 COM3")
        bridge_grid.addWidget(self.txt_bridge_private_pos, 2, 1)
        bridge_grid.addWidget(self._make_label(u"服务私有对端："), 2, 2)
        self.txt_bridge_private_peer = QLineEdit()
        self.txt_bridge_private_peer.setPlaceholderText("例如 CNCB1")
        bridge_grid.addWidget(self.txt_bridge_private_peer, 2, 3)

        bridge_grid.addWidget(self._make_label(u"收钱吧 POS 端："), 3, 0)
        self.txt_bridge_payment_pos = QLineEdit()
        self.txt_bridge_payment_pos.setPlaceholderText("例如 COM10")
        bridge_grid.addWidget(self.txt_bridge_payment_pos, 3, 1)
        bridge_grid.addWidget(self._make_label(u"支付插件对端："), 3, 2)
        self.txt_bridge_payment_peer = QLineEdit()
        self.txt_bridge_payment_peer.setPlaceholderText("例如 COM11")
        bridge_grid.addWidget(self.txt_bridge_payment_peer, 3, 3)
        bridge_layout.addLayout(bridge_grid)

        self.lbl_scale_bridge_config = QLabel("")
        self.lbl_scale_bridge_config.setWordWrap(True)
        self.lbl_scale_bridge_config.setStyleSheet(
            "color: #BFDBFE; font-size: 12px; padding: 8px 10px; background: #0F172A; border-radius: 8px;"
        )
        bridge_layout.addWidget(self.lbl_scale_bridge_config)

        bridge_buttons = QHBoxLayout()
        bridge_buttons.setSpacing(10)
        self.btn_save_scale_bridge = QPushButton(u"💾 保存桥接配置")
        self._style_save_btn(self.btn_save_scale_bridge)
        self.btn_save_scale_bridge.clicked.connect(self._save_scale_bridge_config)
        bridge_buttons.addWidget(self.btn_save_scale_bridge)
        self.btn_check_scale_bridge_pairs = QPushButton(u"🔗 检查虚拟端口配对")
        self.btn_check_scale_bridge_pairs.setCursor(Qt.PointingHandCursor)
        self.btn_check_scale_bridge_pairs.clicked.connect(self._check_scale_bridge_pairs)
        bridge_buttons.addWidget(self.btn_check_scale_bridge_pairs)
        bridge_buttons.addStretch()
        bridge_layout.addLayout(bridge_buttons)
        layout.addWidget(bridge_panel)

        self._load_scale_bridge_form()

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
        btn_rp.clicked.connect(lambda: self._refresh_printers(show_toast=True))
        grid.addWidget(btn_rp, 1, 2)

        grid.addWidget(self._make_label(u"网络 IP："), 2, 0)
        
        net_box = QHBoxLayout()
        net_box.setSpacing(10)
        self.txt_ip = QLineEdit(self.config.get("printer_ip", "192.168.1.100"))
        net_box.addWidget(self.txt_ip, stretch=2)

        lbl_port = self._make_label(u"端口：")
        lbl_port.setStyleSheet("color: #94A3B8; font-size: 14px; font-weight: 600; background: transparent; padding-left: 8px; padding-right: 4px;")
        net_box.addWidget(lbl_port)

        self.spin_net_port = QSpinBox()
        self.spin_net_port.setRange(1, 65535)
        self.spin_net_port.setValue(self.config.get("printer_port", 9100))
        net_box.addWidget(self.spin_net_port, stretch=1)

        grid.addLayout(net_box, 2, 1, 1, 2)

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

        grid.addWidget(self._make_label(u"计价方式："), 2, 0)
        self.cmb_unit = QComboBox()
        self.cmb_unit.addItems(["per_jin - 按斤计价", "per_kg - 按公斤计价"])
        pu = self.config.get("price_unit", "per_jin")
        for i in range(self.cmb_unit.count()):
            if self.cmb_unit.itemText(i).startswith(pu):
                self.cmb_unit.setCurrentIndex(i)
                break
        grid.addWidget(self.cmb_unit, 2, 1, 1, 2)

        grid.addWidget(self._make_label(u"标准汤底单价："), 3, 0)
        self.spin_default_price = QDoubleSpinBox()
        self.spin_default_price.setRange(0.01, 999.99)
        self.spin_default_price.setValue(self.config.get("unit_price", 47.60))
        self.spin_default_price.setDecimals(2)
        grid.addWidget(self.spin_default_price, 3, 1, 1, 2)

        grid.addWidget(self._make_label(u"精品汤底单价："), 4, 0)
        self.spin_special_price = QDoubleSpinBox()
        self.spin_special_price.setRange(0.01, 999.99)
        self.spin_special_price.setValue(self.config.get("special_soup_price", 50.00))
        self.spin_special_price.setDecimals(2)
        grid.addWidget(self.spin_special_price, 4, 1, 1, 2)

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
        btn_refresh_ports.clicked.connect(lambda: self._refresh_com_ports(show_toast=True))
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

        # ── 收钱吧插件配置要点指南 ──
        tip_frame = QFrame()
        tip_frame.setObjectName("SqbTipFrame")
        tip_frame.setStyleSheet("""
            QFrame#SqbTipFrame {
                background-color: #0F172A;
                border: 1px solid #0284C7;
                border-radius: 10px;
            }
            QFrame#SqbTipFrame QLabel {
                border: none;
                background: transparent;
            }
        """)
        tip_layout = QVBoxLayout(tip_frame)
        tip_layout.setContentsMargins(16, 14, 16, 14)
        tip_layout.setSpacing(8)

        lbl_tip_title = QLabel(u"💡 收钱吧 PC 助手 / 插件配置必备说明：")
        lbl_tip_title.setStyleSheet("color: #38BDF8; font-size: 15px; font-weight: 900; border: none; background: transparent;")
        tip_layout.addWidget(lbl_tip_title)

        tips = [
            u"📌 <b>插件 - 打印机设置</b>：应选择为 <b>USB 模式</b>，不要选择兼容模式。",
            u"📌 <b>插件 - 获取金额</b>：应使用<b>虚拟端口软件</b>将本 POS 设置的端口和插件设置的端口配对。",
            u"📌 <b>插件 - 调出菜单</b>：应选择<b>快捷键菜单</b>，并且和本系统设置【唤起快捷键】保持一致。",
        ]
        for tip in tips:
            lbl_tip_item = QLabel(tip)
            lbl_tip_item.setWordWrap(True)
            lbl_tip_item.setStyleSheet("color: #E2E8F0; font-size: 13px; border: none; background: transparent; line-height: 140%;")
            tip_layout.addWidget(lbl_tip_item)

        layout.addWidget(tip_frame)
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
            u"⚠️", u"配置导入导出与模块化还原", u"按需分别还原各模块配置，或导入导出完整设置文件"
        )
        card.setStyleSheet("""
            QFrame#SettingCard {
                background-color: #1E293B;
                border-radius: 16px;
                border: 2px solid #DC2626;
            }
        """)

        # ── 1. 配置文件导入与导出卡片 ──
        io_box = QFrame()
        io_box.setStyleSheet("QFrame { background-color: #0F172A; border-radius: 12px; border: 1px solid #0284C7; padding: 14px; }")
        io_layout = QVBoxLayout(io_box)
        io_layout.setSpacing(10)

        lbl_io_title = QLabel(u"📦 配置文件导入与导出 (快捷一键备份/还原分店设置)")
        lbl_io_title.setStyleSheet("font-size: 15px; font-weight: 900; color: #38BDF8; border: none; background: transparent;")
        io_layout.addWidget(lbl_io_title)

        lbl_io_desc = QLabel(u"将系统设置、外卖中继规则、私域门限及收钱吧等配置导出为 JSON 或 Zip 压缩包，方便快速迁移至其他窗口设备。")
        lbl_io_desc.setWordWrap(True)
        lbl_io_desc.setStyleSheet("font-size: 13px; color: #94A3B8; border: none; background: transparent;")
        io_layout.addWidget(lbl_io_desc)

        btn_row = QHBoxLayout()
        btn_export = QPushButton(u"📤 导出设置文件")
        btn_export.setCursor(Qt.PointingHandCursor)
        btn_export.setStyleSheet("QPushButton { background-color: #0284C7; color: white; font-size: 14px; font-weight: bold; padding: 10px 22px; border-radius: 8px; border: none; } QPushButton:hover { background-color: #0369A1; }")
        btn_export.clicked.connect(self._on_export_config)
        btn_row.addWidget(btn_export)

        btn_import = QPushButton(u"📥 导入设置文件")
        btn_import.setCursor(Qt.PointingHandCursor)
        btn_import.setStyleSheet("QPushButton { background-color: #0D9488; color: white; font-size: 14px; font-weight: bold; padding: 10px 22px; border-radius: 8px; border: none; } QPushButton:hover { background-color: #0F766E; }")
        btn_import.clicked.connect(self._on_import_config)
        btn_row.addWidget(btn_import)
        btn_row.addStretch()
        io_layout.addLayout(btn_row)

        layout.addWidget(io_box)

        # ── 2. 模块化还原与重置管理 ──
        lbl_warn_title = QLabel(u"🚨 模块化还原与重置管理")
        lbl_warn_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #EF4444; background: transparent; margin-top: 10px;")
        layout.addWidget(lbl_warn_title)

        reset_items = [
            (
                u"⚙️", u"还原【系统与硬件配置】", 
                u"仅还原串口、打印机、开机自启等基础系统参数 (base.json) 为出厂默认设置。", 
                u"⚙️ 还原系统配置", 
                "background-color: #334155; color: #F8FAFC; font-size: 14px; font-weight: bold; padding: 10px 18px; border-radius: 8px; border: 1px solid #475569;",
                self._on_reset_sys_config
            ),
            (
                u"🛵", u"还原【外卖中继与排序规则】", 
                u"仅还原外卖分类、菜品关键字、匹配模式及打票字号规则 (takeout.json)。", 
                u"🛵 还原外卖规则", 
                "background-color: #334155; color: #F8FAFC; font-size: 14px; font-weight: bold; padding: 10px 18px; border-radius: 8px; border: 1px solid #475569;",
                self._on_reset_takeout_config
            ),
            (
                u"🧠", u"还原【私域切屏算法规则】", 
                u"仅还原私域截留目标百分比与称重触发门限参数 (algo.json)。", 
                u"🧠 还原算法规则", 
                "background-color: #334155; color: #F8FAFC; font-size: 14px; font-weight: bold; padding: 10px 18px; border-radius: 8px; border: 1px solid #475569;",
                self._on_reset_algo_config
            ),
            (
                u"💵", u"还原【收钱吧插件配置】", 
                u"仅还原收钱吧推送端口、解析格式及唤起热键参数 (shouqianba.json)。", 
                u"💵 还原收钱吧配置", 
                "background-color: #334155; color: #F8FAFC; font-size: 14px; font-weight: bold; padding: 10px 18px; border-radius: 8px; border: 1px solid #475569;",
                self._on_reset_sqb_config
            ),
            (
                u"🧹", u"清空运行与算法日志", 
                u"仅擦除系统运行日志与算法追溯文件 (app_events.jsonl)。不会影响交易账目和参数配置。", 
                u"🧹 清空运行日志", 
                "background-color: #334155; color: #F8FAFC; font-size: 14px; font-weight: bold; padding: 10px 18px; border-radius: 8px; border: 1px solid #475569;",
                self._on_reset_logs
            ),
            (
                u"📊", u"清空历史销售数据库", 
                u"仅清空本地 SQLite 销售数据库 (sales.db)，擦除所有历史点餐记录。下次开单将自动重建库。", 
                u"📊 清空销售数据库", 
                "background-color: #EA580C; color: white; font-size: 14px; font-weight: bold; padding: 10px 18px; border-radius: 8px; border: 1px solid #F97316;",
                self._on_reset_db
            ),
            (
                u"🔥", u"一键彻底重置所有数据", 
                u"高危全量操作！彻底擦除所有配置文件、销售数据库及日志文件。软件恢复最原始状态。", 
                u"🔥 一键彻底重置", 
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #DC2626, stop:1 #EF4444); color: white; font-size: 14px; font-weight: bold; padding: 10px 22px; border-radius: 8px; border: none;",
                self._on_reset
            ),
        ]

        for icon, title, desc, btn_txt, btn_style, slot_fn in reset_items:
            item_box = QFrame()
            item_box.setStyleSheet("""
                QFrame {
                    background-color: #0F172A;
                    border-radius: 12px;
                    border: 1px solid #334155;
                }
            """)
            h_layout = QHBoxLayout(item_box)
            h_layout.setContentsMargins(16, 12, 16, 12)
            h_layout.setSpacing(16)

            v_info = QVBoxLayout()
            v_info.setSpacing(4)

            t_lbl = QLabel(f"{icon} {title}")
            t_lbl.setStyleSheet("font-size: 15px; font-weight: 900; color: #F8FAFC; border: none; background: transparent;")
            d_lbl = QLabel(desc)
            d_lbl.setWordWrap(True)
            d_lbl.setStyleSheet("font-size: 13px; color: #94A3B8; border: none; background: transparent;")
            v_info.addWidget(t_lbl)
            v_info.addWidget(d_lbl)

            h_layout.addLayout(v_info, stretch=1)

            btn = QPushButton(btn_txt)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ {btn_style} }}
                QPushButton:hover {{ border-color: #38BDF8; }}
            """)
            btn.clicked.connect(slot_fn)
            h_layout.addWidget(btn, alignment=Qt.AlignVCenter)

            layout.addWidget(item_box)

        return self._wrap_in_scroll(card)

    def _disable_wheel_events(self):
        """禁止鼠标滚轮在控件上意外修改数值"""
        for widget in self.findChildren((QComboBox, QSpinBox, QDoubleSpinBox)):
            widget.wheelEvent = lambda event, w=widget: event.ignore()

    # ─── 刷新 COM 串口列表 ──────────────────────────
    def _refresh_com_ports(self, show_toast=False):
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

        if show_toast:
            from ui.custom_dialog import show_info, show_item_selection
            if ports:
                selected_port, ok = show_item_selection(
                    self, u"选择收钱吧串口", 
                    f"成功检测到 {len(ports)} 个活跃物理串口！请直接点击要启用的串口：", 
                    ports, self.cmb_sqb_port.currentText()
                )
                if ok and selected_port:
                    self.cmb_sqb_port.setCurrentText(selected_port)
            else:
                show_info(self, u"扫描提示", u"未检测到可用物理串口，已更新默认端口列表 COM1 ~ COM12。")

    # ─── 刷新打印机列表 ──────────────────────────────
    def _refresh_printers(self, show_toast=False):
        self.cmb_printer_name.clear()
        printers = scan_printers()
        for name in printers:
            self.cmb_printer_name.addItem(name)
        cur = self.config.get("printer_name", "shouyin")
        if cur and printers:
            for i in range(self.cmb_printer_name.count()):
                if self.cmb_printer_name.itemText(i) == cur:
                    self.cmb_printer_name.setCurrentIndex(i)
                    break

        if show_toast:
            from ui.custom_dialog import show_info, show_item_selection
            if printers:
                selected_printer, ok = show_item_selection(
                    self, u"选择小票打印机", 
                    f"成功检测到 {len(printers)} 台系统已安装打印机！请直接点击选择要使用的打印机：", 
                    printers, self.cmb_printer_name.currentText()
                )
                if ok and selected_printer:
                    for i in range(self.cmb_printer_name.count()):
                        if self.cmb_printer_name.itemText(i) == selected_printer:
                            self.cmb_printer_name.setCurrentIndex(i)
                            break
            else:
                show_info(self, u"打印机扫描提示", u"未检测到任何本地已安装的 Windows 打印机，请检查驱动是否已安装。")

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
        if hasattr(self, 'btn_test_scale_com'):
            self.btn_test_scale_com.setVisible(is_com)
        if is_com:
            self.lbl_scale_hint.setText(
                u"💡 私有 POS 串口模式：\n"
                u"• DIBAL ACS-G315 已验证参数：9600、8N1；程序每 200ms 发送 $ 查询重量。\n"
                u"• 使用分流/ScaleBridge 提供给私有 POS 的端口（建议 COM3），绝不填写物理秤口 COM1。\n"
                u"• 若采用 ScaleBridge，先点“查看桥接服务状态”确认服务已运行。"
            )
        else:
            self.lbl_scale_hint.setText(
                u"💡 官方模式 (推荐·零配置·无冲突)：\n"
                u"• 从官方收银软件生成的串口日志读取重量，官方软件必须保持运行。\n"
                u"• 若需要私有 POS 单独或并行读取，请切换为上方的 COM 串口直连模式。"
            )

    def _show_scale_bridge_status(self):
        """Read service status through its local named pipe; never opens a serial port."""
        from ui.custom_dialog import show_info, show_warning
        try:
            from scale_bridge.ipc import read_status
            status = read_status()
        except Exception as exc:
            show_warning(
                self, u"桥接服务未连接",
                u"无法读取 ScaleBridge 服务状态。\n\n"
                u"这不会影响当前 VSPD 分流；若已迁移到 ScaleBridge，请确认 Windows 服务已启动。\n\n"
                u"原因: " + str(exc),
            )
            return
        show_info(
            self, u"ScaleBridge 状态",
            u"模式: {mode}\n物理秤端口: {port}\n物理秤连接: {opened}\n"
            u"最近重量: {weight}\n私有查询抑制次数: {suppressed}\n异常帧: {invalid}\n"
            u"最近错误: {error}".format(
                mode=status.get("mode", "未知"),
                port=status.get("physical_port", ""),
                opened="是" if status.get("physical_open") else "否",
                weight=status.get("last_weight_kg", "无"),
                suppressed=status.get("suppressed_private_queries", 0),
                invalid=status.get("invalid_frames", 0),
                error=status.get("last_error") or "无",
            ),
        )

    @staticmethod
    def _bridge_port_text(value):
        """Extract the editable COM name from the device display text."""
        return str(value or "").split("[", 1)[0].strip().upper()

    def _scale_bridge_config_path(self):
        return os.path.join(DATA_DIR, "scale_bridge.json")

    def _load_scale_bridge_form(self):
        """Load only the independent bridge configuration; never alters POS settings."""
        from scale_bridge.configuration import load_config
        try:
            bridge_config = load_config(self._scale_bridge_config_path())
        except Exception:
            bridge_config = None

        if bridge_config is None:
            return
        self.txt_bridge_official_pos.setText(bridge_config.official_pos_virtual_port)
        self.txt_bridge_official_peer.setText(bridge_config.official_bridge_port or "CNCB0")
        self.txt_bridge_private_pos.setText(bridge_config.private_pos_virtual_port)
        self.txt_bridge_private_peer.setText(bridge_config.private_bridge_port or "CNCB1")
        self.txt_bridge_payment_pos.setText(bridge_config.payment_pos_port)
        self.txt_bridge_payment_peer.setText(bridge_config.payment_plugin_port)
        self._refresh_scale_bridge_devices(silent=True, preferred_port=bridge_config.physical_scale_port or "COM1")
        exists = os.path.isfile(self._scale_bridge_config_path())
        self.lbl_scale_bridge_config.setText(
            u"%s：%s。已验证秤协议固定为 9600 / 8N1 / DTR 开 / RTS 关。"
            % (u"已加载桥接配置" if exists else u"尚未保存桥接配置（显示默认值）", self._scale_bridge_config_path())
        )

    def _refresh_scale_bridge_devices(self, checked=False, silent=False, preferred_port=None):
        """Discover only physical serial candidates and retain hardware identity in item data."""
        # `checked` is accepted because this method is also a QPushButton slot.
        del checked
        from scale_bridge.device_discovery import enumerate_serial_ports
        from ui.custom_dialog import show_info, show_warning

        current_port = self._bridge_port_text(preferred_port or self.cmb_bridge_physical_port.currentText())
        try:
            candidates = enumerate_serial_ports(include_virtual=False)
        except Exception as exc:
            candidates = []
            scan_error = str(exc)
        else:
            scan_error = ""

        self.cmb_bridge_physical_port.clear()
        known_ports = set()
        for candidate in candidates:
            label = "%s  [%s]" % (candidate.port, candidate.friendly_name or candidate.port)
            self.cmb_bridge_physical_port.addItem(label, candidate)
            known_ports.add(candidate.port.upper())
        if current_port and current_port not in known_ports:
            # Keep a previously configured physical COM name visible even while
            # its USB adapter is unplugged; saving it intentionally clears no
            # existing identity unless the operator selects a different port.
            self.cmb_bridge_physical_port.addItem(current_port)
        if not self.cmb_bridge_physical_port.count():
            self.cmb_bridge_physical_port.addItem("COM1")
        if current_port:
            for index in range(self.cmb_bridge_physical_port.count()):
                if self._bridge_port_text(self.cmb_bridge_physical_port.itemText(index)) == current_port:
                    self.cmb_bridge_physical_port.setCurrentIndex(index)
                    break

        if not silent:
            if candidates:
                details = "\n".join("• %s — %s" % (item.port, item.friendly_name) for item in candidates)
                show_info(self, u"物理串口识别结果", u"已识别 %d 个非虚拟串口：\n\n%s" % (len(candidates), details))
            else:
                message = u"未识别到可作为物理秤的串口。VSPD/com0com 虚拟口会被刻意排除。"
                if scan_error:
                    message += u"\n\n原因: " + scan_error
                show_warning(self, u"未识别到物理秤", message)

    def _bridge_config_from_form(self):
        """Merge fields into the separate service config without writing it yet."""
        from scale_bridge.configuration import ScaleDeviceIdentity, load_config

        bridge_config = load_config(self._scale_bridge_config_path())
        physical_port = self._bridge_port_text(self.cmb_bridge_physical_port.currentText())
        candidate = self.cmb_bridge_physical_port.currentData()
        if candidate is not None and getattr(candidate, "port", "").upper() == physical_port:
            bridge_config.physical_scale = candidate.to_identity()
        elif bridge_config.physical_scale_port != physical_port:
            # A manually typed different port must not inherit another USB
            # adapter's PnP identity, or it could be re-bound unexpectedly.
            bridge_config.physical_scale = ScaleDeviceIdentity(port=physical_port)
        else:
            bridge_config.physical_scale.port = physical_port

        bridge_config.official_pos_virtual_port = self.txt_bridge_official_pos.text().strip().upper()
        bridge_config.official_bridge_port = self.txt_bridge_official_peer.text().strip().upper()
        bridge_config.private_pos_virtual_port = self.txt_bridge_private_pos.text().strip().upper()
        bridge_config.private_bridge_port = self.txt_bridge_private_peer.text().strip().upper()
        bridge_config.payment_pos_port = self.txt_bridge_payment_pos.text().strip().upper()
        bridge_config.payment_plugin_port = self.txt_bridge_payment_peer.text().strip().upper()
        bridge_config.baudrate = int(self.cmb_scale_baud.currentText().strip() or "9600")
        return bridge_config

    def _save_scale_bridge_config(self):
        from scale_bridge.configuration import save_config
        from ui.custom_dialog import show_error, show_info

        try:
            bridge_config = self._bridge_config_from_form()
            bridge_config.validate()
            save_config(bridge_config, self._scale_bridge_config_path())
        except Exception as exc:
            show_error(self, u"桥接配置无法保存", str(exc))
            return
        self.lbl_scale_bridge_config.setText(
            u"✓ 已保存桥接配置：%s。尚未启动服务，也未变更 VSPD 或任何 COM 映射。"
            % self._scale_bridge_config_path()
        )
        show_info(
            self, u"桥接配置已保存",
            u"已保存独立的 ScaleBridge 配置。\n\n"
            u"这一步不会切换当前 POS 的称来源、不会安装驱动，也不会创建或修改虚拟串口。\n"
            u"迁移时请将私有 POS 设置为“com / COM3”，并按部署说明在维护窗口启动服务。",
        )

    def _check_scale_bridge_pairs(self):
        """Read installed com0com pairs only; this button has no write side effect."""
        from scale_bridge.com0com import check_pair, list_pairs
        from ui.custom_dialog import show_error, show_info, show_warning

        try:
            bridge_config = self._bridge_config_from_form()
            bridge_config.validate()
            pairs = list_pairs()
        except Exception as exc:
            show_error(
                self, u"无法检查虚拟端口配对",
                u"未改动任何端口。请确认 com0com 已由管理员安装，然后再检查。\n\n原因: " + str(exc),
            )
            return
        checks = [
            (u"官方 POS", check_pair(bridge_config.official_pos_virtual_port, bridge_config.official_bridge_port, pairs)),
            (u"私有 POS", check_pair(bridge_config.private_pos_virtual_port, bridge_config.private_bridge_port, pairs)),
            (u"支付插件", check_pair(bridge_config.payment_pos_port, bridge_config.payment_plugin_port, pairs)),
        ]
        lines = []
        for name, item in checks:
            suffix = u"（配对 #%d）" % item.pair.index if item.pair else ""
            lines.append(u"%s：%s ↔ %s — %s %s" % (
                name, item.client_port, item.bridge_port, u"正常" if item.present else u"缺失", suffix
            ))
        message = u"\n".join(lines) + u"\n\n本检查仅读取 com0com 当前配置，不创建、删除或重命名端口。"
        if all(item.present for _name, item in checks):
            show_info(self, u"虚拟端口配对正常", message)
        else:
            show_warning(self, u"存在缺失的虚拟端口配对", message)

    def _test_scale_com(self):
        """实时测试当前配置的串口电子秤通信状态"""
        port_text = self.cmb_scale_port.currentText().strip()
        port = port_text.split("[")[0].strip()
        try:
            baudrate = int(self.cmb_scale_baud.currentText().strip())
        except Exception:
            baudrate = 9600

        from ui.custom_dialog import show_info, show_error, show_warning
        import time
        import serial

        # 若后台已存在运行中的称重线程独占此端口，先暂时挂起以防端口占用报错
        parent_mw = self.window()
        active_scale = None
        if hasattr(parent_mw, 'sale_page') and hasattr(parent_mw.sale_page, 'scale'):
            active_scale = parent_mw.sale_page.scale
            if active_scale and getattr(active_scale, '_running', False):
                active_scale.stop()
                time.sleep(0.3)

        try:
            ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.05,
                write_timeout=0.5,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            ser.dtr = True
            ser.rts = False
        except Exception as e:
            if active_scale:
                active_scale.start()
            show_error(
                self, u"串口连接失败",
                f"无法打开端口【{port}】！\n\n原因: {str(e)}\n\n"
                u"建议检查事项：\n"
                u"1. 电子秤 USB/串口连接线是否接入电脑。\n"
                u"2. 确认该串口未被其他收银软件或串口调试工具独占。"
            )
            return

        # 按官方 POS 已验证的 ACS-G315 协议测试：每 200ms 发送 '$' (0x24)。
        try:
            start_t = time.time()
            received_data = bytearray()
            weight_val = None
            next_poll_time = time.monotonic()
            temp_reader = None

            while time.time() - start_t < 2.0:
                if time.monotonic() >= next_poll_time:
                    ser.write(b"$")
                    ser.flush()
                    next_poll_time = time.monotonic() + 0.2

                data = ser.read(ser.in_waiting or 1)
                if data:
                    received_data.extend(data)
                    if b"\r" in received_data or b"\n" in received_data:
                        text = received_data.decode("ascii", errors="ignore")
                        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                        for line in lines:
                            line = line.strip()
                            if line:
                                from core.scale_reader import ScaleReader
                                if temp_reader is None:
                                    temp_reader = ScaleReader(self.config)
                                w = temp_reader._parse_com_weight(line)
                                if w is not None:
                                    weight_val = w
                                    break
                        if weight_val is not None:
                            break
                time.sleep(0.01)

            ser.close()

            if weight_val is not None:
                show_info(
                    self, u"测试连接成功",
                    f"🎉 成功连通电子秤串口【{port}】！\n\n"
                    f"• 通信端口: {port}\n"
                    f"• 通信波特率: {baudrate}\n"
                    f"• 捕获到的实时重量: {weight_val:.3f} kg\n\n"
                    u"硬件通信完全正常，可随时保存使用！"
                )
            elif received_data:
                show_warning(
                    self, u"数据未匹配",
                    f"⚠️ 已成功连通端口【{port}】并接收到数据，但未能解析为标准重量格式：\n\n"
                    f"原始接收数据: \"{received_data.decode('ascii', errors='replace')[:100]}\"\n\n"
                    u"建议检查波特率或电子秤通信协议。"
                )
            else:
                show_warning(
                    self, u"未接收到数据",
                    f"⚠️ 已成功打开端口【{port}】，但在 2 秒内未接收到有效数据。\n\n"
                    u"请检查：\n"
                    u"1. 电子秤电源是否已打开。\n"
                    u"2. 当前选择的是分流给私有 POS 的端口（建议 COM3）；官方 POS 在 COM2 可保持运行。"
                )

        except Exception as ex:
            try:
                ser.close()
            except Exception:
                pass
            show_error(self, u"测试过程异常", f"通信读取过程发生错误: {str(ex)}")
        finally:
            if active_scale:
                active_scale.start()

    def _refresh_scale_com_ports(self, show_toast=False):
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
        if show_toast:
            from ui.custom_dialog import show_info, show_item_selection
            if active_ports:
                selected_port, ok = show_item_selection(
                    self, u"选择电子秤串口", 
                    f"成功检测到 {len(active_ports)} 个活跃物理串口！请直接点击选择要连接的电子秤串口：", 
                    active_ports, self.cmb_scale_port.currentText().split("[")[0].strip()
                )
                if ok and selected_port:
                    for i in range(self.cmb_scale_port.count()):
                        if self.cmb_scale_port.itemText(i).startswith(selected_port):
                            self.cmb_scale_port.setCurrentIndex(i)
                            break
            else:
                show_info(self, u"串口扫描提示", u"未检测到任何活跃物理串口，已更新默认端口列表 COM1 ~ COM12。")

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

        parent_mw = self.window()
        if hasattr(parent_mw, 'sale_page') and hasattr(parent_mw.sale_page, 'restart_scale'):
            parent_mw.sale_page.restart_scale()

        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"称重数据源设置已保存并即时生效！")

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

    def _on_export_config(self):
        """导出配置文件包 (支持 Zip 或 JSON)"""
        from ui.custom_dialog import show_info, show_error
        file_path, _ = QFileDialog.getSaveFileName(
            self, u"导出系统设置包", "ygf_pos_settings.zip", "Zip 打包配置文件 (*.zip);;JSON 配置文件 (*.json)"
        )
        if not file_path:
            return
        try:
            export_config_bundle(self.config, file_path)
            show_info(self, u"导出成功", f"配置文件已成功导出至：\n{file_path}")
        except Exception as e:
            show_error(self, u"导出失败", f"导出配置文件包时发生错误: {e}")

    def _on_import_config(self):
        """导入配置文件包"""
        from ui.custom_dialog import show_question, show_info, show_error
        file_path, _ = QFileDialog.getOpenFileName(
            self, u"导入系统设置包", "", "设置包文件 (*.zip *.json)"
        )
        if not file_path:
            return
        if not show_question(self, u"导入确认", u"确定要导入并覆盖当前系统的配置参数吗？导入后系统将自动更新。"):
            return
        try:
            self.config = import_config_bundle(file_path)
            show_info(self, u"导入成功", u"设置文件已成功导入并刷新应用！请重新启动或刷新界面以套用新设置。")
        except Exception as e:
            show_error(self, u"导入失败", f"导入配置文件包时发生错误: {e}")

    def _on_reset_sys_config(self):
        """还原系统与硬件配置 (base.json)"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"还原确认", u"确定要将【系统与硬件配置】还原为出厂默认设置吗？"):
            return
        try:
            self.config = reset_module_config(self.config, "sys")
            show_info(self, u"还原成功", u"【系统与硬件配置】(data/settings/base.json) 已成功还原为出厂默认值！")
        except Exception as e:
            show_error(self, u"操作异常", f"还原配置时发生异常: {e}")

    def _on_reset_takeout_config(self):
        """还原外卖中继与排序规则 (takeout.json)"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"还原确认", u"确定要将【外卖中继与排序规则】还原为出厂默认设置吗？"):
            return
        try:
            self.config = reset_module_config(self.config, "takeout")
            show_info(self, u"还原成功", u"【外卖中继与排序规则】(data/settings/takeout.json) 已成功还原为出厂默认值！")
        except Exception as e:
            show_error(self, u"操作异常", f"还原配置时发生异常: {e}")

    def _on_reset_algo_config(self):
        """还原私域切屏算法规则 (algo.json)"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"还原确认", u"确定要将【私域切屏算法规则】还原为出厂默认设置吗？"):
            return
        try:
            self.config = reset_module_config(self.config, "algo")
            show_info(self, u"还原成功", u"【私域切屏算法规则】(data/settings/algo.json) 已成功还原为出厂默认值！")
        except Exception as e:
            show_error(self, u"操作异常", f"还原配置时发生异常: {e}")

    def _on_reset_sqb_config(self):
        """还原收钱吧插件配置 (shouqianba.json)"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"还原确认", u"确定要将【收钱吧插件配置】还原为出厂默认设置吗？"):
            return
        try:
            self.config = reset_module_config(self.config, "shouqianba")
            show_info(self, u"还原成功", u"【收钱吧插件配置】(data/settings/shouqianba.json) 已成功还原为出厂默认值！")
        except Exception as e:
            show_error(self, u"操作异常", f"还原配置时发生异常: {e}")

    def _on_reset_logs(self):
        """仅重置运行与算法日志"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"清空日志确认", u"确定要清空全部系统运行与算法操作日志 (app_events.jsonl) 吗？该操作不可撤销。"):
            return
        try:
            from core.app_logger import clear_all_logs
            ok = clear_all_logs()
            if ok:
                show_info(self, u"清空成功", u"全部运行与算法操作日志已成功清空！")
            else:
                show_error(self, u"清空失败", u"无法清除日志文件，请检查文件权限。")
        except Exception as e:
            show_error(self, u"操作异常", f"清空日志时发生错误: {e}")

    def _on_reset_db(self):
        """仅重置销售数据库"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"清空数据库确认", u"确定要删除本地所有的历史点餐与交易记录数据库 (pos.db) 吗？此操作不可逆！"):
            return
        try:
            import os
            from config import DB_PATH
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            show_info(self, u"清空成功", u"历史销售记录数据库已成功删除！下次开单时将自动建立新库。")
        except Exception as e:
            show_error(self, u"操作异常", f"清空数据库时发生错误: {e}")

    def _on_reset_config(self):
        """仅恢复默认配置"""
        from ui.custom_dialog import show_question, show_info, show_error
        if not show_question(self, u"恢复默认设置确认", u"确定要重置配置文件 (config.json) 为出厂默认参数吗？软件即将关闭以应用初始设置。"):
            return
        try:
            import os
            from config import CONFIG_FILE
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
            show_info(self, u"重置成功", u"系统设置已成功恢复默认！程序即刻关闭，请手动重新启动。")
            from PyQt5.QtWidgets import QApplication
            QApplication.quit()
        except Exception as e:
            show_error(self, u"操作异常", f"重置配置文件时发生错误: {e}")

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

            try:
                from core.app_logger import clear_all_logs
                clear_all_logs()
            except Exception as e:
                print(f"Failed to remove log file: {e}")
            
            QMessageBox.information(
                self, u"重置成功", 
                u"软件已成功重置所有数据！\n程序即将关闭，请手动重新打开以生成全新的环境。"
            )
            from PyQt5.QtWidgets import QApplication
            QApplication.quit()
            
        except Exception as e:
            QMessageBox.critical(self, u"重置失败", f"重置过程中出现意外错误:\n{e}")
