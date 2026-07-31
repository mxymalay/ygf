"""
销售/称重界面 — 主操作页面
PyQt5 + Python 3.8 兼容
"""
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QFrame, QDoubleSpinBox, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot

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
        self._refresh_summary()

        # 每 30 秒刷新一次汇总
        self._summary_timer = QTimer(self)
        self._summary_timer.timeout.connect(self._refresh_summary)
        self._summary_timer.start(30000)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── 左侧：称重显示区 ──
        left = QVBoxLayout()
        left.setSpacing(12)

        # 称重状态
        status_bar = QHBoxLayout()
        self.lbl_conn = QLabel(u"● 未连接")
        self.lbl_conn.setObjectName("lbl_status")
        self.lbl_conn.setStyleSheet("color: #e74c3c;")
        self.lbl_sim_badge = QLabel(u"[模拟模式]")
        self.lbl_sim_badge.setStyleSheet(
            "background: #f39c12; color: #1a1a2e; padding: 4px 12px;"
            "border-radius: 10px; font-size: 12px; font-weight: bold;"
        )
        if not self.config.get("simulation_mode", True):
            self.lbl_sim_badge.hide()
        status_bar.addWidget(self.lbl_conn)
        status_bar.addStretch()
        status_bar.addWidget(self.lbl_sim_badge)
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
        wc_layout.setContentsMargins(20, 30, 20, 30)

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

        # ── 右侧：操作区 ──
        right = QVBoxLayout()
        right.setSpacing(12)

        # 单价设置
        price_group = QGroupBox(u"单价设置")
        pg_layout = QGridLayout(price_group)

        pg_layout.addWidget(QLabel(u"单价："), 0, 0)
        self.spin_price = QDoubleSpinBox()
        self.spin_price.setRange(0.01, 999.99)
        self.spin_price.setValue(self.config.get("unit_price", 32.00))
        self.spin_price.setSuffix(
            " %s" % price_unit_label(self.config.get("price_unit", "per_jin"))
        )
        self.spin_price.setDecimals(2)
        self.spin_price.setSingleStep(0.5)
        self.spin_price.valueChanged.connect(self._on_price_changed)
        pg_layout.addWidget(self.spin_price, 0, 1)

        right.addWidget(price_group)

        # 操作按钮
        self.btn_print = QPushButton(u"称重并打印小票")
        self.btn_print.setObjectName("btn_print")
        self.btn_print.clicked.connect(self._on_print)
        right.addWidget(self.btn_print)

        self.btn_clear = QPushButton(u"清零/重置")
        self.btn_clear.setObjectName("btn_clear")
        self.btn_clear.clicked.connect(self._on_clear)
        right.addWidget(self.btn_clear)

        right.addSpacing(8)

        # 今日汇总
        summary_group = QGroupBox(u"今日汇总")
        sg_layout = QGridLayout(summary_group)

        sg_layout.addWidget(self._dim_label(u"笔数"), 0, 0)
        self.lbl_count = QLabel("0")
        self.lbl_count.setStyleSheet("color: #00b4d8; font-size: 24px; font-weight: bold;")
        sg_layout.addWidget(self.lbl_count, 0, 1)
        sg_layout.addWidget(self._dim_label(u"笔"), 0, 2)

        sg_layout.addWidget(self._dim_label(u"总重"), 1, 0)
        self.lbl_total_weight = QLabel("0.00")
        self.lbl_total_weight.setStyleSheet("color: #00b4d8; font-size: 24px; font-weight: bold;")
        sg_layout.addWidget(self.lbl_total_weight, 1, 1)
        sg_layout.addWidget(self._dim_label("kg"), 1, 2)

        sg_layout.addWidget(self._dim_label(u"营收"), 2, 0)
        self.lbl_total_amount = QLabel(u"￥0.00")
        self.lbl_total_amount.setStyleSheet("color: #e94560; font-size: 28px; font-weight: bold;")
        sg_layout.addWidget(self.lbl_total_amount, 2, 1, 1, 2)

        right.addWidget(summary_group)

        # 最近记录
        recent_group = QGroupBox(u"最近记录")
        self.recent_layout = QVBoxLayout(recent_group)
        self.recent_layout.setSpacing(4)
        self._refresh_recent()
        right.addWidget(recent_group, stretch=1)

        layout.addLayout(right, stretch=2)

    def _dim_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #6c6c80; font-size: 14px;")
        return lbl

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

        unit_price = self.spin_price.value()
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
            self.lbl_conn.setStyleSheet("color: #2ecc71; font-size: 13px;")
        else:
            self.lbl_conn.setText(u"● %s" % msg)
            self.lbl_conn.setStyleSheet("color: #e74c3c; font-size: 13px;")

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
        self.lbl_conn.setStyleSheet("color: #e74c3c; font-size: 13px;")

    # ─── 操作 ──────────────────────────────────────
    def _on_price_changed(self, value):
        self.config["unit_price"] = value
        price_unit = self.config.get("price_unit", "per_jin")
        total = calculate_price(self.current_weight, value, price_unit)
        self.lbl_price.setText(u"￥%.2f" % total)

    def _on_print(self):
        """称重并打印小票"""
        weight = self.current_weight
        if weight < 0.01:
            QMessageBox.warning(self, u"提示", u"当前重量为零，请先放上食材！")
            return

        unit_price = self.spin_price.value()
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

        self._refresh_summary()
        self._refresh_recent()

    def _on_clear(self):
        self.current_weight = 0.0
        self._is_stable = False
        self._stable_weight = 0.0
        self.lbl_weight.setText("0.000")
        self.lbl_price.setText(u"￥0.00")
        self.lbl_stable.setText("")

    # ─── 数据刷新 ─────────────────────────────────
    def _refresh_summary(self):
        summary = self.db.get_today_summary()
        self.lbl_count.setText(str(summary["count"]))
        self.lbl_total_weight.setText("%.2f" % summary["total_weight"])
        self.lbl_total_amount.setText(u"￥%.2f" % summary["total_amount"])

    def _refresh_recent(self):
        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        records = self.db.get_recent_sales(limit=5)
        if not records:
            lbl = QLabel(u"暂无记录")
            lbl.setStyleSheet("color: #6c6c80; font-size: 13px; padding: 8px;")
            self.recent_layout.addWidget(lbl)
            return

        for r in records:
            pu = r.get("price_unit", "per_jin")
            if pu == "per_jin":
                w_str = "%.2f斤" % (r["weight_kg"] * 2)
            else:
                w_str = "%.3fkg" % r["weight_kg"]
            t = r["created_at"].split(" ")[1][:5] if " " in r["created_at"] else ""
            text = "%s  %s  ￥%.2f" % (t, w_str, r["total_price"])
            lbl = QLabel(text)
            lbl.setStyleSheet(
                "color: #a0a0b8; font-size: 13px; padding: 4px 8px;"
                "background: #0f0f1a; border-radius: 4px;"
            )
            self.recent_layout.addWidget(lbl)

        self.recent_layout.addStretch()

    def cleanup(self):
        """关闭时清理资源"""
        if hasattr(self, 'scale'):
            self.scale.stop()
        if hasattr(self, '_summary_timer'):
            self._summary_timer.stop()
