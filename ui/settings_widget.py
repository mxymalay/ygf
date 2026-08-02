"""
设置界面 — 打印机/业务参数配置
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QMessageBox, QScrollArea
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
                border: 2px solid #38BDF8;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 15px;
                font-weight: bold;
            }
            QLineEdit:focus {
                border: 2px solid #F97316;
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

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._build_ui()

    def _style_save_btn(self, btn):
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background: #10B981; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; border: none; font-size: 14px; }"
            "QPushButton:hover { background: #059669; }"
        )

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 添加 QScrollArea 防止低分辨率屏幕挤压
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("""
            QGroupBox {
                background-color: #1E293B; border-radius: 12px; border: 1px solid #334155;
                margin-top: 24px; padding-top: 24px;
                font-size: 15px; font-weight: bold; color: #F9FAFB;
            }
            QGroupBox::title {
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 4px 12px; color: #38BDF8; font-size: 16px; font-weight: bold;
                background-color: #0F172A; border-radius: 8px; border: 1px solid #334155;
            }
            QLabel { color: #D1D5DB; font-size: 14px; background: transparent; }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                background-color: #0F172A; color: #F8FAFC; border: 1px solid #334155;
                border-radius: 6px; padding: 6px 10px; font-size: 14px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #38BDF8;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {
                background-color: #1E293B; border: 1px solid #334155; border-radius: 2px; width: 20px;
            }
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #334155;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── 称重数据源设置 ──
        scale_group = QGroupBox(u"称重数据源设置")
        scg = QGridLayout(scale_group)
        scg.setContentsMargins(20, 30, 20, 20)
        scg.setSpacing(12)

        scg.addWidget(QLabel(u"数据来源："), 0, 0)
        self.cmb_scale_source = QComboBox()
        self.cmb_scale_source.addItems([
            u"official - 官方收银系统 (OCR读取日志)",
            u"com - 串口直连电子秤 (COM口)"
        ])
        source = self.config.get("scale_source", "official")
        if source == "com":
            self.cmb_scale_source.setCurrentIndex(1)
        self.cmb_scale_source.currentIndexChanged.connect(self._on_scale_source_changed)
        scg.addWidget(self.cmb_scale_source, 0, 1, 1, 2)

        # COM口配置 (仅串口模式可见)
        self.lbl_scale_port = QLabel(u"秤串口 (COM)：")
        scg.addWidget(self.lbl_scale_port, 1, 0)
        self.cmb_scale_port = QComboBox()
        self.cmb_scale_port.setEditable(True)
        self._refresh_scale_com_ports()
        scg.addWidget(self.cmb_scale_port, 1, 1)

        self.btn_refresh_scale_ports = QPushButton(u"扫描COM口")
        self.btn_refresh_scale_ports.clicked.connect(self._refresh_scale_com_ports)
        scg.addWidget(self.btn_refresh_scale_ports, 1, 2)

        self.lbl_scale_baud = QLabel(u"波特率：")
        scg.addWidget(self.lbl_scale_baud, 2, 0)
        self.cmb_scale_baud = QComboBox()
        self.cmb_scale_baud.addItems(["2400", "4800", "9600", "19200", "38400", "115200"])
        cur_baud = str(self.config.get("scale_baudrate", 9600))
        self.cmb_scale_baud.setCurrentText(cur_baud)
        scg.addWidget(self.cmb_scale_baud, 2, 1, 1, 2)

        # 提示信息
        self.lbl_scale_hint = QLabel("")
        self.lbl_scale_hint.setWordWrap(True)
        self.lbl_scale_hint.setStyleSheet("color: #94A3B8; font-size: 12px; padding: 4px;")
        scg.addWidget(self.lbl_scale_hint, 3, 0, 1, 3)

        btn_save_scale = QPushButton(u"保存称重设置 (需重启)")
        self._style_save_btn(btn_save_scale)
        btn_save_scale.clicked.connect(self._on_save_scale)
        scg.addWidget(btn_save_scale, 4, 0, 1, 3, Qt.AlignRight)

        layout.addWidget(scale_group)

        # 初始化显示/隐藏
        self._on_scale_source_changed(self.cmb_scale_source.currentIndex())

        # ── 打印机设置 ──
        printer_group = QGroupBox(u"小票打印机设置")
        pg = QGridLayout(printer_group)
        pg.setContentsMargins(20, 30, 20, 20)
        pg.setSpacing(12)

        pg.addWidget(QLabel(u"打印方式："), 0, 0)
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
        pg.addWidget(self.cmb_printer_type, 0, 1, 1, 2)

        pg.addWidget(QLabel(u"打印机名称："), 1, 0)
        self.cmb_printer_name = QComboBox()
        self.cmb_printer_name.setEditable(True)
        self._refresh_printers()
        pg.addWidget(self.cmb_printer_name, 1, 1, 1, 2)

        btn_rp = QPushButton(u"刷新打印机")
        btn_rp.clicked.connect(self._refresh_printers)
        pg.addWidget(btn_rp, 1, 3)

        pg.addWidget(QLabel(u"网络 IP："), 2, 0)
        self.txt_ip = QLineEdit(self.config.get("printer_ip", "192.168.1.100"))
        pg.addWidget(self.txt_ip, 2, 1)

        pg.addWidget(QLabel(u"端口："), 2, 2)
        self.spin_net_port = QSpinBox()
        self.spin_net_port.setRange(1, 65535)
        self.spin_net_port.setValue(self.config.get("printer_port", 9100))
        pg.addWidget(self.spin_net_port, 2, 3)

        btn_save_printer = QPushButton(u"保存打印机设置")
        self._style_save_btn(btn_save_printer)
        btn_save_printer.clicked.connect(self._on_save_printer)
        pg.addWidget(btn_save_printer, 3, 0, 1, 4, Qt.AlignRight)

        layout.addWidget(printer_group)

        # ── 业务与计价设置 ──
        biz_group = QGroupBox(u"店铺与计价设置")
        bg = QGridLayout(biz_group)
        bg.setContentsMargins(20, 30, 20, 20)
        bg.setSpacing(12)

        bg.addWidget(QLabel(u"店名："), 0, 0)
        self.txt_shop = QLineEdit(self.config.get("shop_name", u"杨国福麻辣烫"))
        bg.addWidget(self.txt_shop, 0, 1, 1, 2)

        bg.addWidget(QLabel(u"分店名称："), 1, 0)
        self.txt_sub = QLineEdit(self.config.get("shop_subtitle", u""))
        self.txt_sub.setPlaceholderText(u"例如：杨国福(肥西水晶城店)")
        bg.addWidget(self.txt_sub, 1, 1, 1, 2)

        bg.addWidget(QLabel(u"小票底部文字："), 2, 0)
        self.txt_footer = QLineEdit(self.config.get("receipt_footer", u"谢谢惠顾！"))
        self.txt_footer.setPlaceholderText(u"例如：谢谢惠顾！")
        bg.addWidget(self.txt_footer, 2, 1, 1, 2)

        bg.addWidget(QLabel(u"计价方式："), 3, 0)
        self.cmb_unit = QComboBox()
        self.cmb_unit.addItems(["per_jin - 按斤计价", "per_kg - 按公斤计价"])
        pu = self.config.get("price_unit", "per_jin")
        for i in range(self.cmb_unit.count()):
            if self.cmb_unit.itemText(i).startswith(pu):
                self.cmb_unit.setCurrentIndex(i)
                break
        bg.addWidget(self.cmb_unit, 3, 1, 1, 2)

        bg.addWidget(QLabel(u"标准汤底单价："), 4, 0)
        self.spin_default_price = QDoubleSpinBox()
        self.spin_default_price.setRange(0.01, 999.99)
        self.spin_default_price.setValue(self.config.get("unit_price", 47.60))
        self.spin_default_price.setDecimals(2)
        bg.addWidget(self.spin_default_price, 4, 1, 1, 2)

        bg.addWidget(QLabel(u"精品汤底单价："), 5, 0)
        self.spin_special_price = QDoubleSpinBox()
        self.spin_special_price.setRange(0.01, 999.99)
        self.spin_special_price.setValue(self.config.get("special_soup_price", 50.00))
        self.spin_special_price.setDecimals(2)
        bg.addWidget(self.spin_special_price, 5, 1, 1, 2)

        btn_save_biz = QPushButton(u"保存店铺与计价设置")
        self._style_save_btn(btn_save_biz)
        btn_save_biz.clicked.connect(self._on_save_biz)
        bg.addWidget(btn_save_biz, 6, 0, 1, 4, Qt.AlignRight)

        layout.addWidget(biz_group)

        # ── 系统运行设置 ──
        sys_group = QGroupBox(u"系统运行设置 (双系统无缝流转与悬浮球)")
        syg = QGridLayout(sys_group)
        syg.setContentsMargins(20, 30, 20, 20)
        syg.setSpacing(12)

        syg.addWidget(QLabel(u"开机自启动："), 0, 0)
        self.cmb_auto_start = QComboBox()
        self.cmb_auto_start.addItems([u"开启 - 随 Windows 启动并打开点餐系统", u"关闭 - 仅允许手动启动"])
        if not self.config.get("auto_start_enabled", True):
            self.cmb_auto_start.setCurrentIndex(1)
        syg.addWidget(self.cmb_auto_start, 0, 1, 1, 2)

        syg.addWidget(QLabel(u"自启缓冲延迟："), 1, 0)
        self.spin_auto_start_delay = QSpinBox()
        self.spin_auto_start_delay.setRange(0, 60)
        self.spin_auto_start_delay.setSuffix(u" 秒")
        self.spin_auto_start_delay.setToolTip(u"设置软件随系统开机后静默等待的秒数，用于等待网卡和串口驱动加载完毕。")
        self.spin_auto_start_delay.setValue(self.config.get("auto_start_delay", 8))
        syg.addWidget(self.spin_auto_start_delay, 1, 1, 1, 2)

        syg.addWidget(QLabel(u"桌面常驻触屏悬浮球："), 2, 0)
        self.cmb_floating_ball = QComboBox()
        self.cmb_floating_ball.addItems([u"开启 - 在屏幕边缘显示半透明触屏切换球", u"关闭 - 隐藏悬浮球"])
        if not self.config.get("floating_ball_enabled", True):
            self.cmb_floating_ball.setCurrentIndex(1)
        syg.addWidget(self.cmb_floating_ball, 2, 1, 1, 2)

        btn_save_sys = QPushButton(u"保存系统设置")
        self._style_save_btn(btn_save_sys)
        btn_save_sys.clicked.connect(self._on_save_sys)
        syg.addWidget(btn_save_sys, 3, 0, 1, 4, Qt.AlignRight)

        layout.addWidget(sys_group)

        # ── 收钱吧 PC收款助手设置 ──
        sqb_group = QGroupBox(u"收钱吧 PC收款助手设置")
        sg = QGridLayout(sqb_group)
        sg.setContentsMargins(20, 30, 20, 20)
        sg.setSpacing(12)

        sg.addWidget(QLabel(u"自动推送金额："), 0, 0)
        self.cmb_sqb_enable = QComboBox()
        self.cmb_sqb_enable.addItems([u"开启 - 自动推送结账金额到收钱吧", u"关闭 - 不推送"])
        if not self.config.get("shouqianba_enabled", True):
            self.cmb_sqb_enable.setCurrentIndex(1)
        sg.addWidget(self.cmb_sqb_enable, 0, 1, 1, 2)

        sg.addWidget(QLabel(u"串口 (COM端口)："), 1, 0)
        self.cmb_sqb_port = QComboBox()
        self.cmb_sqb_port.setEditable(True)
        self._refresh_com_ports()
        sg.addWidget(self.cmb_sqb_port, 1, 1)

        btn_refresh_ports = QPushButton(u"扫描COM端口")
        btn_refresh_ports.clicked.connect(self._refresh_com_ports)
        sg.addWidget(btn_refresh_ports, 1, 2)

        sg.addWidget(QLabel(u"波特率 (Baudrate)："), 2, 0)
        self.cmb_sqb_baud = QComboBox()
        self.cmb_sqb_baud.addItems(["2400", "9600", "19200", "38400", "115200"])
        cur_baud = str(self.config.get("shouqianba_baudrate", 2400))
        self.cmb_sqb_baud.setCurrentText(cur_baud)
        sg.addWidget(self.cmb_sqb_baud, 2, 1, 1, 2)

        sg.addWidget(QLabel(u"解析规则："), 3, 0)
        self.cmb_sqb_fmt = QComboBox()
        self.cmb_sqb_fmt.addItems([
            u"QA - QA标记 (例如 QA12.50)",
            u"FLOAT - 纯数字 (例如 12.50)"
        ])
        fmt = self.config.get("shouqianba_format", "QA")
        if fmt == "FLOAT":
            self.cmb_sqb_fmt.setCurrentIndex(1)
        sg.addWidget(self.cmb_sqb_fmt, 3, 1, 1, 2)

        sg.addWidget(QLabel(u"唤起快捷键："), 4, 0)
        
        hk_box = QHBoxLayout()
        self.txt_sqb_hotkey = HotKeyRecorderEdit()
        cur_hk = str(self.config.get("shouqianba_hotkey", "Shift+Q"))
        self.txt_sqb_hotkey.setText(cur_hk)
        hk_box.addWidget(self.txt_sqb_hotkey, stretch=2)

        # 快速预设按钮
        for hk_item in ["无(纯串口)", "Shift+Q", "F12", "Ctrl+F12"]:
            btn_hk = QPushButton(hk_item)
            btn_hk.setCursor(Qt.PointingHandCursor)
            btn_hk.setStyleSheet("""
                QPushButton {
                    background: #334155; color: #F8FAFC; border: 1px solid #475569;
                    border-radius: 6px; padding: 4px 8px; font-weight: bold;
                }
                QPushButton:hover { background: #38BDF8; color: #0F172A; }
            """)
            if hk_item == "无(纯串口)":
                btn_hk.clicked.connect(lambda chk: self.txt_sqb_hotkey.setText(""))
            else:
                btn_hk.clicked.connect(lambda chk, t=hk_item: self.txt_sqb_hotkey.setText(t))
            hk_box.addWidget(btn_hk)

        sg.addLayout(hk_box, 4, 1, 1, 2)

        btn_save_sqb = QPushButton(u"保存收钱吧设置")
        self._style_save_btn(btn_save_sqb)
        btn_save_sqb.clicked.connect(self._on_save_sqb)
        sg.addWidget(btn_save_sqb, 5, 0, 1, 4, Qt.AlignRight)

        layout.addWidget(sqb_group)

        # ── 危险操作区 ──
        danger_group = QGroupBox(u"危险操作 (Danger Zone)")
        danger_group.setStyleSheet("""
            QGroupBox { border: 1px solid #DC2626; color: #DC2626; }
            QGroupBox::title { color: #DC2626; }
        """)
        dg_layout = QHBoxLayout(danger_group)
        
        lbl_danger = QLabel(u"⚠️ 警告：重置软件将清空所有配置和历史销售数据库，不可恢复！")
        lbl_danger.setStyleSheet("color: #F87171; font-size: 13px;")
        dg_layout.addWidget(lbl_danger, stretch=1)
        
        btn_reset = QPushButton(u"重置软件数据")
        btn_reset.setCursor(Qt.PointingHandCursor)
        btn_reset.setStyleSheet(
            "QPushButton { background: #DC2626; color: white; font-weight: bold; padding: 10px 20px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #B91C1C; }"
        )
        btn_reset.clicked.connect(self._on_reset)
        dg_layout.addWidget(btn_reset)
        
        layout.addWidget(danger_group)

        from ui.styles import apply_touch_combo_style
        for combo in self.findChildren(QComboBox):
            apply_touch_combo_style(combo, item_height=48)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)
        
        self._disable_wheel_events()

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
        # 将 COM1 ~ COM12 加入可选列表，方便使用虚拟串口
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
        # 触发主界面单价刷新
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

        # 1. 立即应用自动启动配置
        from utils.system_utils import apply_auto_start_settings
        apply_auto_start_settings(
            self.config["auto_start_enabled"], 
            self.config["auto_start_delay"]
        )

        # 2. 刷新主界面智能控制器与悬浮球
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
            # 在活跃端口后面加标记
            if p in active_ports:
                self.cmb_scale_port.addItem(f"{p}  [已连接]")
            else:
                self.cmb_scale_port.addItem(p)
        cur = self.config.get("scale_port", "COM2")
        if cur:
            # 尝试匹配带标记的项
            for i in range(self.cmb_scale_port.count()):
                if self.cmb_scale_port.itemText(i).startswith(cur):
                    self.cmb_scale_port.setCurrentIndex(i)
                    break
        # 显示扫描反馈
        if hasattr(self, 'lbl_scale_hint'):
            if active_ports:
                self.lbl_scale_hint.setText(u"扫描完成！检测到活跃端口: %s" % ", ".join(active_ports))
                self.lbl_scale_hint.setStyleSheet("color: #34D399; font-size: 12px; padding: 4px;")
            else:
                self.lbl_scale_hint.setText(u"扫描完成，未检测到任何活跃的COM端口。请检查串口线是否连接。")
                self.lbl_scale_hint.setStyleSheet("color: #FBBF24; font-size: 12px; padding: 4px;")

    def _on_save_scale(self):
        """保存称重数据源设置"""
        source_text = self.cmb_scale_source.currentText()
        self.config["scale_source"] = source_text.split(" - ")[0].strip()
        # 去除端口名后面可能带的 [已连接] 标记
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
        # 第一重确认
        r1 = QMessageBox.warning(
            self, u"严重警告", 
            u"您正在进行危险操作！\n这将会清除所有的本地设置以及所有的历史订单数据！\n您确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if r1 != QMessageBox.Yes:
            return

        # 第二重确认
        r2 = QMessageBox.warning(
            self, u"最后警告", 
            u"数据一旦删除将【永远无法恢复】。\n您真的确定要删除数据库和配置文件吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if r2 != QMessageBox.Yes:
            return
        
        # 第三重确认
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
            
            # 删除数据库
            if os.path.exists(DB_PATH):
                try:
                    os.remove(DB_PATH)
                except Exception as e:
                    print(f"Failed to remove DB: {e}")
                    
            # 删除配置文件
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
