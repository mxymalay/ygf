"""
销售/称重界面 — 包含叫号牌管理与 1-10元 快捷加价功能
PyQt5 + Python 3.8 兼容
"""
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QSpinBox, QCheckBox, QGridLayout, QGroupBox
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
        self.extra_fee = 0.0  # 附加快捷加价

        self._build_ui()
        self._setup_scale()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── 左侧：重量与金额核心展示区 ──
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

        # 静态单价胶囊
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

        # 核心重量卡片
        weight_card = QFrame()
        weight_card.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #172136, stop:1 #0B0F19);"
            "border: 1px solid #263352; border-radius: 20px; }"
        )
        wc_layout = QVBoxLayout(weight_card)
        wc_layout.setAlignment(Qt.AlignCenter)
        wc_layout.setContentsMargins(20, 20, 20, 20)

        lbl_title = QLabel(u"实测重量")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("color: #9CA3AF; font-size: 20px; font-weight: bold;")
        wc_layout.addWidget(lbl_title)

        self.lbl_weight = QLabel("0.000")
        self.lbl_weight.setObjectName("lbl_weight")
        self.lbl_weight.setAlignment(Qt.AlignCenter)
        self.lbl_weight.setStyleSheet(
            "font-size: 88px; font-weight: 900; color: #F9FAFB;"
            "letter-spacing: -2px; font-family: 'Segoe UI', 'Consolas', sans-serif;"
        )
        wc_layout.addWidget(self.lbl_weight)

        self.lbl_weight_unit = QLabel("kg")
        self.lbl_weight_unit.setObjectName("lbl_unit")
        self.lbl_weight_unit.setAlignment(Qt.AlignCenter)
        self.lbl_weight_unit.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #06B6D4;"
            "padding: 2px 16px; background: #1E293B; border-radius: 12px;"
        )
        wc_layout.addWidget(self.lbl_weight_unit)

        self.lbl_stable = QLabel("")
        self.lbl_stable.setAlignment(Qt.AlignCenter)
        self.lbl_stable.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #10B981; margin-top: 4px;"
        )
        wc_layout.addWidget(self.lbl_stable)

        left.addWidget(weight_card, stretch=4)

        # 核心金额卡片 (含加价显示)
        price_card = QFrame()
        price_card.setStyleSheet(
            "QFrame { background: #172136; border: 1px solid #263352;"
            "border-radius: 16px; }"
        )
        pc_layout = QVBoxLayout(price_card)
        pc_layout.setAlignment(Qt.AlignCenter)
        pc_layout.setContentsMargins(16, 12, 16, 12)

        p_top_layout = QHBoxLayout()
        p_top_layout.setAlignment(Qt.AlignCenter)

        lbl_ptitle = QLabel(u"应收总金额")
        lbl_ptitle.setStyleSheet("color: #9CA3AF; font-size: 18px; font-weight: bold;")
        p_top_layout.addWidget(lbl_ptitle)

        self.lbl_extra_info = QLabel("")
        self.lbl_extra_info.setStyleSheet("color: #F97316; font-size: 15px; font-weight: bold;")
        p_top_layout.addWidget(self.lbl_extra_info)

        pc_layout.addLayout(p_top_layout)

        self.lbl_price = QLabel(u"￥0.00")
        self.lbl_price.setObjectName("lbl_price")
        self.lbl_price.setAlignment(Qt.AlignCenter)
        self.lbl_price.setStyleSheet(
            "font-size: 58px; font-weight: 900; color: #F59E0B;"
            "letter-spacing: -1px; font-family: 'Segoe UI', sans-serif;"
        )
        pc_layout.addWidget(self.lbl_price)

        left.addWidget(price_card, stretch=2)

        layout.addLayout(left, stretch=4)

        # ── 右侧：叫号牌 + 1-10元快捷加价 + 打印操作 ──
        right = QVBoxLayout()
        right.setSpacing(14)

        # 1. 取餐叫号牌卡片
        call_group = QGroupBox(u"取餐叫号牌设置")
        cg_layout = QVBoxLayout(call_group)
        cg_layout.setSpacing(8)

        cg_top = QHBoxLayout()
        cg_top.addWidget(QLabel(u"叫号牌："))

        self.spin_call_no = QSpinBox()
        self.spin_call_no.setRange(1, 999)
        self.spin_call_no.setValue(1)
        self.spin_call_no.setStyleSheet("font-size: 22px; font-weight: bold; color: #F97316;")
        cg_top.addWidget(self.spin_call_no, stretch=1)

        btn_minus = QPushButton(u"-1")
        btn_minus.clicked.connect(lambda: self.spin_call_no.setValue(max(1, self.spin_call_no.value() - 1)))
        cg_top.addWidget(btn_minus)

        btn_plus = QPushButton(u"+1")
        btn_plus.clicked.connect(lambda: self.spin_call_no.setValue(self.spin_call_no.value() + 1))
        cg_top.addWidget(btn_plus)

        cg_layout.addLayout(cg_top)

        self.chk_auto_inc = QCheckBox(u"打印后自动跳下一号 (+1号)")
        self.chk_auto_inc.setChecked(True)
        self.chk_auto_inc.setStyleSheet("color: #9CA3AF; font-size: 14px;")
        cg_layout.addWidget(self.chk_auto_inc)

        right.addWidget(call_group)

        # 2. 快捷加价网格 (1元 ~ 10元)
        add_group = QGroupBox(u"快捷加价 (打包/餐盒/饮料)")
        ag_grid = QGridLayout(add_group)
        ag_grid.setSpacing(8)

        for i in range(1, 11):
            btn_add = QPushButton(u"+%d元" % i)
            btn_add.setStyleSheet(
                "background: #1E293B; color: #F9FAFB; border: 1px solid #374151;"
                "border-radius: 8px; font-weight: bold; font-size: 14px; min-height: 38px;"
            )
            # 点击添加费用
            fee_val = float(i)
            btn_add.clicked.connect(lambda checked, v=fee_val: self._add_extra_fee(v))

            row = (i - 1) // 5
            col = (i - 1) % 5
            ag_grid.addWidget(btn_add, row, col)

        # 清空加价按钮
        btn_reset_fee = QPushButton(u"清空加价")
        btn_reset_fee.setStyleSheet(
            "background: #78350F; color: #FBBF24; border: 1px solid #F59E0B;"
            "border-radius: 8px; font-weight: bold; font-size: 14px; min-height: 38px;"
        )
        btn_reset_fee.clicked.connect(self._clear_extra_fee)
        ag_grid.addWidget(btn_reset_fee, 2, 0, 1, 5)

        right.addWidget(add_group)

        # 3. 称重打印与清零
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

        layout.addLayout(right, stretch=3)

    def _add_extra_fee(self, fee):
        """累加快捷费用"""
        self.extra_fee += fee
        self._update_price_display()

    def _clear_extra_fee(self):
        """清空附加费用"""
        self.extra_fee = 0.0
        self._update_price_display()

    def _update_price_display(self):
        """重新计算并更新总金额显示"""
        unit_price = self.config.get("unit_price", 32.00)
        price_unit = self.config.get("price_unit", "per_jin")
        base_price = calculate_price(self.current_weight, unit_price, price_unit)
        total = base_price + self.extra_fee

        if self.extra_fee > 0:
            self.lbl_extra_info.setText(u"(含附加 +￥%.2f)" % self.extra_fee)
        else:
            self.lbl_extra_info.setText("")

        self.lbl_price.setText(u"￥%.2f" % total)

    # ─── 刷新单价显示及服务 ───────────────────────
    def refresh_unit_price_info(self):
        unit_price = self.config.get("unit_price", 32.00)
        pu_label = price_unit_label(self.config.get("price_unit", "per_jin"))
        self.lbl_unit_info.setText(u"麻辣烫单价：%.2f %s" % (unit_price, pu_label))
        self._update_price_display()

    def restart_scale(self):
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
        self._update_price_display()

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
        base_price = calculate_price(weight, unit_price, price_unit)
        total_price = base_price + self.extra_fee

        call_no_str = "%02d" % self.spin_call_no.value()

        record = self.db.insert_sale(
            weight_kg=weight,
            unit_price=unit_price,
            price_unit=price_unit,
            total_price=total_price,
            remark=u"叫号:#%s 加价:￥%.2f" % (call_no_str, self.extra_fee)
        )

        sale_data = dict(record)
        sale_data["shop_name"] = self.config.get("shop_name", u"杨国福麻辣烫")
        sale_data["shop_subtitle"] = self.config.get("shop_subtitle", "")
        sale_data["receipt_footer"] = self.config.get("receipt_footer", u"谢谢惠顾！")
        sale_data["call_no"] = call_no_str
        sale_data["extra_fee"] = self.extra_fee

        success = self.printer.print_receipt(sale_data)

        if success:
            self.lbl_stable.setText(u"● [已打印小票] 叫号牌 #%s | 单号 %s" % (call_no_str, record["sale_no"]))
            self.lbl_stable.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #38BDF8;"
                "padding: 4px 12px; background: #0369A1; border-radius: 6px;"
            )

            # 如果开启了自动跳号
            if self.chk_auto_inc.isChecked():
                self.spin_call_no.setValue(self.spin_call_no.value() + 1)
        else:
            self.lbl_stable.setText(u"[X] 打印失败")
            self.lbl_stable.setStyleSheet("font-size: 15px; color: #EF4444;")
            QMessageBox.warning(self, u"打印失败", u"小票打印失败，请检查打印机连接！\n记录已保存。")

    def _on_clear(self):
        """清空附加加价项目与提示（始终保持物理电子秤真实读数）"""
        self.extra_fee = 0.0
        self.lbl_extra_info.setText("")
        self.lbl_stable.setText("")
        self._update_price_display()

    def cleanup(self):
        if hasattr(self, 'scale'):
            self.scale.stop()
