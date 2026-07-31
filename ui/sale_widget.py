"""
销售/称重界面 — 主操作页面
PyQt5 + Python 3.8 兼容
"""
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSlot

from core.calculator import calculate_price, weight_display, price_unit_label
from core.database import Database
from core.printer import ReceiptPrinter
from core.scale_reader import ScaleReader


class SaleWidget(QWidget):
    """主销售界面"""

    def __init__(self, config, db, parent=None):
        super().__init__(parent)
        self.config = config
        self.db = db
        self.printer = ReceiptPrinter(config)
        self.current_weight = 0.0
        self._stable_weight = 0.0
        self._is_stable = False

        self._build_ui()
        self._setup_scale()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── 左侧：称重显示区 ──
        left = QVBoxLayout()
        left.setSpacing(12)

        # 称重状态与当前单价展示
        status_bar = QHBoxLayout()
        self.lbl_conn = QLabel(u"● 正在连接称重秤...")
        self.lbl_conn.setObjectName("lbl_status")
        self.lbl_conn.setWordWrap(True)
        self.lbl_conn.setStyleSheet("color: #f39c12; font-size: 13px; font-weight: bold;")
        status_bar.addWidget(self.lbl_conn, stretch=1)

        # 显示从设置页面配置的当前单价
        unit_price = self.config.get("unit_price", 32.00)
        pu_label = price_unit_label(self.config.get("price_unit", "per_jin"))
        self.lbl_unit_info = QLabel(u"单价：%.2f %s" % (unit_price, pu_label))
        self.lbl_unit_info.setStyleSheet(
            "color: #00b4d8; font-size: 15px; font-weight: bold;"
            "padding: 4px 12px; background: #16213e; border-radius: 6px;"
        )
        status_bar.addWidget(self.lbl_unit_info)

        left.addLayout(status_bar)

        # 重量显示卡片
        weight_card = QFrame()
        weight_card.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #16213e, stop:1 #1a1a2e);"
            "border: 1px solid #2a2a4a; border-radius: 16px; }"
        )
        wc_layout = QVBoxLayout(weight_card)
        wc_layout.setAlignment(Qt.AlignCenter)
        wc_layout.setContentsMargins(20, 20, 20, 20)

        lbl_title = QLabel(u"当前重量")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("color: #a0a0b8; font-size: 18px;")
        wc_layout.addWidget(lbl_title)

        self.lbl_weight = QLabel("0.000")
        self.lbl_weight.setObjectName("lbl_weight")
        self.lbl_weight.setAlignment(Qt.AlignCenter)
        wc_layout.addWidget(self.lbl_weight)

        self.lbl_weight_unit = QLabel("kg")
        self.lbl_weight_unit.setObjectName("lbl_unit")
        self.lbl_weight_unit.setAlignment(Qt.AlignCenter)
        wc_layout.addWidget(self.lbl_weight_unit)

        # 稳定指示
        self.lbl_stable = QLabel("")
        self.lbl_stable.setAlignment(Qt.AlignCenter)
        self.lbl_stable.setStyleSheet("font-size: 14px; color: #6c6c80;")
        wc_layout.addWidget(self.lbl_stable)

        left.addWidget(weight_card, stretch=3)

        # 金额显示
        price_card = QFrame()
        price_card.setStyleSheet(
            "QFrame { background: #16213e; border: 1px solid #2a2a4a;"
            "border-radius: 12px; }"
        )
        pc_layout = QVBoxLayout(price_card)
        pc_layout.setAlignment(Qt.AlignCenter)

        lbl_ptitle = QLabel(u"应收金额")
        lbl_ptitle.setAlignment(Qt.AlignCenter)
        lbl_ptitle.setStyleSheet("color: #a0a0b8; font-size: 16px;")
        pc_layout.addWidget(lbl_ptitle)

        self.lbl_price = QLabel(u"￥0.00")
        self.lbl_price.setObjectName("lbl_price")
        self.lbl_price.setAlignment(Qt.AlignCenter)
        pc_layout.addWidget(self.lbl_price)

        left.addWidget(price_card, stretch=1)

        layout.addLayout(left, stretch=3)

        # ── 右侧：操作按键 ──
        right = QVBoxLayout()
        right.setSpacing(16)

        right.addStretch()

        # 操作按钮
        self.btn_print = QPushButton(u"称重并打印小票")
        self.btn_print.setObjectName("btn_print")
        self.btn_print.clicked.connect(self._on_print)
        right.addWidget(self.btn_print)

        self.btn_clear = QPushButton(u"清零/重置")
        self.btn_clear.setObjectName("btn_clear")
        self.btn_clear.clicked.connect(self._on_clear)
        right.addWidget(self.btn_clear)

        right.addStretch()

        layout.addLayout(right, stretch=2)

    # ─── 刷新单价显示及重启串口 ───────────────────────
    def refresh_unit_price_info(self):
        """从配置更新单价提示标签"""
        unit_price = self.config.get("unit_price", 32.00)
        pu_label = price_unit_label(self.config.get("price_unit", "per_jin"))
        self.lbl_unit_info.setText(u"单价：%.2f %s" % (unit_price, pu_label))

    def restart_scale(self):
        """刷新配置并重新连接电子秤"""
        self.refresh_unit_price_info()
        if hasattr(self, 'scale'):
            self.scale.restart()

    # ─── 称重秤连接 ──────────────────────────────────
    def _setup_scale(self):
        self.scale = ScaleReader(self.config)
        self.scale.weight_updated.connect(self._on_weight_update)
        self.scale.status_changed.connect(self._on_status_change)
        self.scale.weight_stable.connect(self._on_weight_stable)
        self.scale.error_occurred.connect(self._on_error)
        self.scale.start()

    @pyqtSlot(float)
    def _on_weight_update(self, weight_kg):
        self.current_weight = weight_kg
        self.lbl_weight.setText("%.3f" % weight_kg)

        unit_price = self.config.get("unit_price", 32.00)
        price_unit = self.config.get("price_unit", "per_jin")
        total = calculate_price(weight_kg, unit_price, price_unit)
        self.lbl_price.setText(u"￥%.2f" % total)

        if self._is_stable and abs(weight_kg - self._stable_weight) > 0.05:
            self._is_stable = False
            self.lbl_stable.setText("")

    @pyqtSlot(bool, str)
    def _on_status_change(self, connected, msg):
        if connected:
            self.lbl_conn.setText(u"● %s" % msg)
            self.lbl_conn.setStyleSheet("color: #2ecc71; font-size: 13px; font-weight: bold;")
        else:
            self.lbl_conn.setText(u"● %s" % msg)
            self.lbl_conn.setStyleSheet("color: #e74c3c; font-size: 13px; font-weight: bold;")

    @pyqtSlot(float)
    def _on_weight_stable(self, weight_kg):
        if weight_kg > 0.02:
            self._is_stable = True
            self._stable_weight = weight_kg
            self.lbl_stable.setText(u"[OK] 重量已稳定")
            self.lbl_stable.setStyleSheet("font-size: 14px; color: #2ecc71;")

    @pyqtSlot(str)
    def _on_error(self, msg):
        self.lbl_conn.setText(u"[!] %s" % msg)
        self.lbl_conn.setStyleSheet("color: #e74c3c; font-size: 13px; font-weight: bold;")

    # ─── 操作 ──────────────────────────────────────
    def _on_print(self):
        """称重并打印小票"""
        weight = self.current_weight
        if weight < 0.01:
            QMessageBox.warning(self, u"提示", u"当前重量为零，请先放上食材！")
            return

        unit_price = self.config.get("unit_price", 32.00)
        price_unit = self.config.get("price_unit", "per_jin")
        total_price = calculate_price(weight, unit_price, price_unit)

        record = self.db.insert_sale(
            weight_kg=weight,
            unit_price=unit_price,
            price_unit=price_unit,
            total_price=total_price
        )

        sale_data = dict(record)
        sale_data["shop_name"] = self.config.get("shop_name", u"杨国福麻辣烫")
        sale_data["shop_subtitle"] = self.config.get("shop_subtitle", "")
        sale_data["receipt_footer"] = self.config.get("receipt_footer", u"谢谢惠顾！")

        success = self.printer.print_receipt(sale_data)

        if success:
            self.lbl_stable.setText(u"[OK] 已打印 %s" % record["sale_no"])
            self.lbl_stable.setStyleSheet("font-size: 14px; color: #2ecc71;")
        else:
            self.lbl_stable.setText(u"[X] 打印失败")
            self.lbl_stable.setStyleSheet("font-size: 14px; color: #e74c3c;")
            QMessageBox.warning(self, u"打印失败", u"小票打印失败，请检查打印机连接！\n记录已保存。")

    def _on_clear(self):
        self.current_weight = 0.0
        self._is_stable = False
        self._stable_weight = 0.0
        self.lbl_weight.setText("0.000")
        self.lbl_price.setText(u"￥0.00")
        self.lbl_stable.setText("")

    def cleanup(self):
        """关闭时清理资源"""
        if hasattr(self, 'scale'):
            self.scale.stop()
