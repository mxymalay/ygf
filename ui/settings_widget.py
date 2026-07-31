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
        lbl_info.setStyleSheet("color: #2ecc71; font-size: 14px; line-height: 1.5; padding: 4px;")
        sig_layout.addWidget(lbl_info)
        layout.addWidget(scale_info_group)

        # ── 打印机设置 ──
        printer_group = QGroupBox(u"小票打印机设置 (XP-A160M / XP-80C)")
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

        bg.addWidget(QLabel(u"麻辣烫单价："), 4, 0)
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
            "min-height: 48px;"
        )
        btn_save.clicked.connect(self._on_save)
        btn_bar.addWidget(btn_save)

        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

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

        save_config(self.config)

        # 触发主界面单价刷新
        parent_mw = self.window()
        if hasattr(parent_mw, 'sale_page'):
            parent_mw.sale_page.refresh_unit_price_info()

        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"系统设置已成功保存！")
