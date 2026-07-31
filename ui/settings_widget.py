"""
设置界面 — 串口/打印机/业务参数配置
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QMessageBox
)

from config import save_config
from utils.port_scanner import scan_ports, scan_printers


class SettingsWidget(QWidget):
    """系统设置界面"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── 称重秤设置 ──
        scale_group = QGroupBox(u"称重秤设置 (DIBAL ACS-G315)")
        sg = QGridLayout(scale_group)
        sg.setSpacing(10)

        sg.addWidget(QLabel(u"串口："), 0, 0)
        self.cmb_scale_port = QComboBox()
        self._refresh_ports()
        sg.addWidget(self.cmb_scale_port, 0, 1)

        btn_refresh = QPushButton(u"刷新端口")
        btn_refresh.clicked.connect(self._refresh_ports)
        sg.addWidget(btn_refresh, 0, 2)

        sg.addWidget(QLabel(u"波特率："), 1, 0)
        self.cmb_baudrate = QComboBox()
        for br in ["9600", "4800", "19200", "38400", "57600", "115200"]:
            self.cmb_baudrate.addItem(br)
        self.cmb_baudrate.setCurrentText(str(self.config.get("scale_baudrate", 9600)))
        sg.addWidget(self.cmb_baudrate, 1, 1)

        self.chk_sim = QCheckBox(u"启用模拟模式（无硬件时使用）")
        self.chk_sim.setChecked(self.config.get("simulation_mode", True))
        self.chk_sim.setStyleSheet("color: #f39c12; font-size: 14px;")
        sg.addWidget(self.chk_sim, 2, 0, 1, 3)

        layout.addWidget(scale_group)

        # ── 打印机设置 ──
        printer_group = QGroupBox(u"打印机设置 (Xprinter XP-A160M)")
        pg = QGridLayout(printer_group)
        pg.setSpacing(10)

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

        # ── 业务设置 ──
        biz_group = QGroupBox(u"业务设置")
        bg = QGridLayout(biz_group)
        bg.setSpacing(10)

        bg.addWidget(QLabel(u"店名："), 0, 0)
        self.txt_shop = QLineEdit(self.config.get("shop_name", u"杨国福麻辣烫"))
        bg.addWidget(self.txt_shop, 0, 1, 1, 2)

        bg.addWidget(QLabel(u"副标题："), 1, 0)
        self.txt_sub = QLineEdit(self.config.get("shop_subtitle", u"好吃不贵 · 健康美味"))
        bg.addWidget(self.txt_sub, 1, 1, 1, 2)

        bg.addWidget(QLabel(u"小票底部："), 2, 0)
        self.txt_footer = QLineEdit(self.config.get("receipt_footer", u"谢谢惠顾！欢迎下次光临"))
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

        bg.addWidget(QLabel(u"默认单价："), 4, 0)
        self.spin_default_price = QDoubleSpinBox()
        self.spin_default_price.setRange(0.01, 999.99)
        self.spin_default_price.setValue(self.config.get("unit_price", 32.00))
        self.spin_default_price.setDecimals(2)
        bg.addWidget(self.spin_default_price, 4, 1)

        layout.addWidget(biz_group)

        # ── 保存按钮 ──
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        btn_save = QPushButton(u"保存设置")
        btn_save.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #2ecc71, stop:1 #27ae60);"
            "color: white; font-size: 18px; font-weight: bold;"
            "padding: 14px 48px; border-radius: 10px; border: none;"
        )
        btn_save.clicked.connect(self._on_save)
        btn_bar.addWidget(btn_save)

        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        layout.addStretch()

    # ─── 刷新列表 ──────────────────────────────────
    def _refresh_ports(self):
        self.cmb_scale_port.clear()
        ports = scan_ports()
        for p in ports:
            self.cmb_scale_port.addItem(
                "%s - %s" % (p["device"], p["description"]),
                p["device"]
            )
        cur = self.config.get("scale_port", "COM3")
        for i in range(self.cmb_scale_port.count()):
            if self.cmb_scale_port.itemData(i) == cur:
                self.cmb_scale_port.setCurrentIndex(i)
                break

    def _refresh_printers(self):
        self.cmb_printer_name.clear()
        printers = scan_printers()
        for name in printers:
            self.cmb_printer_name.addItem(name)
        cur = self.config.get("printer_name", "")
        if cur:
            self.cmb_printer_name.setCurrentText(cur)

    # ─── 保存 ──────────────────────────────────────
    def _on_save(self):
        self.config["scale_port"] = self.cmb_scale_port.currentData() or "COM3"
        self.config["scale_baudrate"] = int(self.cmb_baudrate.currentText())
        self.config["simulation_mode"] = self.chk_sim.isChecked()

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

        save_config(self.config)

        QMessageBox.information(
            self, u"保存成功",
            u"设置已保存！\n部分设置需要重启程序才能生效。"
        )
