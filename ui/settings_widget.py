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

from config import save_config
from utils.port_scanner import scan_printers


class SettingsWidget(QWidget):
    """系统设置界面"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._build_ui()

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
                font-size: 15px; font-weight: bold; color: #F9FAFB;
                border: 1px solid #334155; border-radius: 10px;
                margin-top: 12px; padding: 18px 14px 14px 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 2px 10px; color: #38BDF8;
            }
            QLabel { color: #D1D5DB; font-size: 14px; }
        """)
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── 称重服务状态说明 ──
        scale_info_group = QGroupBox(u"称重服务说明")
        sig_layout = QVBoxLayout(scale_info_group)
        lbl_info = QLabel(
            u"● 本系统已自动绑定【杨国福官方收银系统】称重服务。\n"
            u"● 无需手动配置串口号或波特率，启动官方收银软件后即可自动无缝读取电子秤重量。"
        )
        lbl_info.setStyleSheet("color: #34D399; font-size: 14px; line-height: 1.5; padding: 4px;")
        sig_layout.addWidget(lbl_info)
        layout.addWidget(scale_info_group)

        # ── 打印机设置 ──
        printer_group = QGroupBox(u"小票打印机设置")
        pg = QGridLayout(printer_group)
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

        layout.addWidget(printer_group)

        # ── 业务与计价设置 ──
        biz_group = QGroupBox(u"店铺与计价设置")
        bg = QGridLayout(biz_group)
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
        bg.addWidget(self.spin_default_price, 4, 1)

        bg.addWidget(QLabel(u"精品汤底单价："), 4, 2)
        self.spin_special_price = QDoubleSpinBox()
        self.spin_special_price.setRange(0.01, 999.99)
        self.spin_special_price.setValue(self.config.get("special_soup_price", 50.00))
        self.spin_special_price.setDecimals(2)
        bg.addWidget(self.spin_special_price, 4, 3)

        layout.addWidget(biz_group)

        # ── 收钱吧 PC收款助手设置 ──
        sqb_group = QGroupBox(u"收钱吧 PC收款助手设置")
        sg = QGridLayout(sqb_group)
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

        # ── 保存按钮 ──
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        btn_save = QPushButton(u"保存设置")
        btn_save.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #2ecc71, stop:1 #27ae60);"
            "color: white; font-size: 18px; font-weight: bold;"
            "padding: 14px 48px; border-radius: 10px; border: none;"
            "min-height: 48px;"
        )
        btn_save.clicked.connect(self._on_save)
        btn_bar.addWidget(btn_save)

        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

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
    def _on_save(self):
        pt_text = self.cmb_printer_type.currentText()
        self.config["printer_type"] = pt_text.split(" - ")[0].strip()
        self.config["printer_name"] = self.cmb_printer_name.currentText()
        self.config["printer_ip"] = self.txt_ip.text()
        self.config["printer_port"] = self.spin_net_port.value()

        self.config["shop_name"] = self.txt_shop.text()
        self.config["shop_subtitle"] = self.txt_sub.text()
        self.config["receipt_footer"] = self.txt_footer.text()

        pu_text = self.cmb_unit.currentText()
        self.config["price_unit"] = pu_text.split(" - ")[0].strip()
        self.config["unit_price"] = self.spin_default_price.value()
        self.config["special_soup_price"] = self.spin_special_price.value()

        # 保存收钱吧配置
        self.config["shouqianba_enabled"] = (self.cmb_sqb_enable.currentIndex() == 0)
        self.config["shouqianba_port"] = self.cmb_sqb_port.currentText().strip()
        try:
            self.config["shouqianba_baudrate"] = int(self.cmb_sqb_baud.currentText().strip())
        except Exception:
            self.config["shouqianba_baudrate"] = 2400
        fmt_text = self.cmb_sqb_fmt.currentText()
        self.config["shouqianba_format"] = fmt_text.split(" - ")[0].strip()

        save_config(self.config)

        # 触发主界面单价刷新
        parent_mw = self.window()
        if hasattr(parent_mw, 'sale_page'):
            parent_mw.sale_page.refresh_unit_price_info()

        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"系统设置已成功保存！")

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
