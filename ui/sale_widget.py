"""
销售/称重界面 — 旗舰级现代 POS 主收银操作页面
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
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── 左侧：称重与金额核心展示区 ──
        left = QVBoxLayout()
        left.setSpacing(16)

        # 顶部状态与单价挂件
        status_bar = QHBoxLayout()
        self.lbl_conn = QLabel(u"● 正在连接官方称重服务...")
        self.lbl_conn.setObjectName("lbl_status")
        self.lbl_conn.setWordWrap(True)
        self.lbl_conn.setStyleSheet(
            "color: #F59E0B; font-size: 15px; font-weight: bold;"
            "padding: 8px 16px; background: #1E293B; border-radius: 8px;"
            "border: 1px solid #374151;"
        )
        status_bar.addWidget(self.lbl_conn, stretch=1)

        # 静态单价胶囊标签
        unit_price = self.config.get("unit_price", 32.00)
        pu_label = price_unit_label(self.config.get("price_unit", "per_jin"))
        self.lbl_unit_info = QLabel(u"麻辣烫单价：%.2f %s" % (unit_price, pu_label))
        self.lbl_unit_info.setStyleSheet(
            "color: #06B6D4; font-size: 16px; font-weight: bold;"
            "padding: 8px 18px; background: #1E293B; border-radius: 8px;"
            "border: 1px solid #0891B2;"
        )
        status_bar.addWidget(self.lbl_unit_info)

        left.addLayout(status_bar)

        # 核心重量 display 卡片
        weight_card = QFrame()
        weight_card.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #172136, stop:1 #0B0F19);"
            "border: 1px solid #263352; border-radius: 20px; }"
        )
        wc_layout = QVBoxLayout(weight_card)
        wc_layout.setAlignment(Qt.AlignCenter)
        wc_layout.setContentsMargins(24, 24, 24, 24)

        lbl_title = QLabel(u"实测重量")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("color: #9CA3AF; font-size: 20px; font-weight: bold; letter-spacing: 1px;")
        wc_layout.addWidget(lbl_title)

        # 大号高亮数值
        self.lbl_weight = QLabel("0.000")
        self.lbl_weight.setObjectName("lbl_weight")
        self.lbl_weight.setAlignment(Qt.AlignCenter)
        self.lbl_weight.setStyleSheet(
            "font-size: 96px; font-weight: 900; color: #F9FAFB;"
            "letter-spacing: -2px; font-family: 'Segoe UI', 'Consolas', sans-serif;"
        )
        wc_layout.addWidget(self.lbl_weight)

        # 单位提示
        self.lbl_weight_unit = QLabel("kg")
        self.lbl_weight_unit.setObjectName("lbl_unit")
        self.lbl_weight_unit.setAlignment(Qt.AlignCenter)
        self.lbl_weight_unit.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #06B6D4;"
            "padding: 2px 16px; background: #1E293B; border-radius: 12px;"
        )
        wc_layout.addWidget(self.lbl_weight_unit)

        # 稳定状态徽章
        self.lbl_stable = QLabel("")
        self.lbl_stable.setAlignment(Qt.AlignCenter)
        self.lbl_stable.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #10B981;"
            "margin-top: 6px;"
        )
        wc_layout.addWidget(self.lbl_stable)

        left.addWidget(weight_card, stretch=4)

        # 金额卡片
        price_card = QFrame()
        price_card.setStyleSheet(
            "QFrame { background: #172136; border: 1px solid #263352;"
            "border-radius: 16px; }"
        )
        pc_layout = QVBoxLayout(price_card)
        pc_layout.setAlignment(Qt.AlignCenter)
        pc_layout.setContentsMargins(16, 16, 16, 16)

        lbl_ptitle = QLabel(u"应收总金额")
        lbl_ptitle.setAlignment(Qt.AlignCenter)
        lbl_ptitle.setStyleSheet("color: #9CA3AF; font-size: 18px; font-weight: bold;")
        pc_layout.addWidget(lbl_ptitle)

        self.lbl_price = QLabel(u"￥0.00")
        self.lbl_price.setObjectName("lbl_price")
        self.lbl_price.setAlignment(Qt.AlignCenter)
        self.lbl_price.setStyleSheet(
            "font-size: 64px; font-weight: 900; color: #F59E0B;"
            "letter-spacing: -1px; font-family: 'Segoe UI', sans-serif;"
        )
        pc_layout.addWidget(self.lbl_price)

        left.addWidget(price_card, stretch=2)

        layout.addLayout(left, stretch=4)

        # ── 右侧：触控大按键操作区 ──
        right = QVBoxLayout()
        right.setSpacing(20)

        right.addStretch()

        # 核心按钮
        self.btn_print = QPushButton(u"称重并打印小票")
        self.btn_print.setObjectName("btn_print")
        self.btn_print.setCursor(Qt.PointingHandCursor)
        self.btn_print.clicked.connect(self._on_print)
        right.addWidget(self.btn_print)

        self.btn_clear = QPushButton(u"清零 / 重置")
        self.btn_clear.setObjectName("btn_clear")
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.clicked.connect(self._on_clear)
        right.addWidget(self.btn_clear)

        right.addStretch()

        layout.addLayout(right, stretch=3)

    # ─── 刷新单价显示及服务 ───────────────────────
    def refresh_unit_price_info(self):
        """从配置更新单价提示标签"""
        unit_price = self.config.get("unit_price", 32.00)
        pu_label = price_unit_label(self.config.get("price_unit", "per_jin"))
        self.lbl_unit_info.setText(u"麻辣烫单价：%.2f %s" % (unit_price, pu_label))

    def restart_scale(self):
        """刷新配置并重新开启服务监听"""
        self.refresh_unit_price_info()
        if hasattr(self, 'scale'):
            self.scale.restart()

    # ─── 称重秤服务连接 ──────────────────────────────
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
            self.lbl_conn.setText(u"%s" % msg)
            self.lbl_conn.setStyleSheet(
                "color: #10B981; font-size: 15px; font-weight: bold;"
                "padding: 8px 16px; background: #064E3B; border-radius: 8px;"
                "border: 1px solid #059669;"
            )
        else:
            self.lbl_conn.setText(u"%s" % msg)
            self.lbl_conn.setStyleSheet(
                "color: #EF4444; font-size: 15px; font-weight: bold;"
                "padding: 8px 16px; background: #7F1D1D; border-radius: 8px;"
                "border: 1px solid #DC2626;"
            )

    @pyqtSlot(float)
    def _on_weight_stable(self, weight_kg):
        if weight_kg > 0.02:
            self._is_stable = True
            self._stable_weight = weight_kg
            self.lbl_stable.setText(u"● [OK] 重量已稳定 (打印就绪)")
            self.lbl_stable.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #10B981;"
                "padding: 4px 12px; background: #064E3B; border-radius: 6px;"
            )

    @pyqtSlot(str)
    def _on_error(self, msg):
        self.lbl_conn.setText(u"[!] %s" % msg)
        self.lbl_conn.setStyleSheet(
            "color: #EF4444; font-size: 15px; font-weight: bold;"
            "padding: 8px 16px; background: #7F1D1D; border-radius: 8px;"
            "border: 1px solid #DC2626;"
        )

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
            self.lbl_stable.setText(u"● [已打印] 单号 %s" % record["sale_no"])
            self.lbl_stable.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #38BDF8;"
                "padding: 4px 12px; background: #0369A1; border-radius: 6px;"
            )
        else:
            self.lbl_stable.setText(u"[X] 打印失败")
            self.lbl_stable.setStyleSheet("font-size: 15px; color: #EF4444;")
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
