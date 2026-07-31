"""
销售/称重界面 — 实用 3 栏布局
左侧：菜单/订单清单  |  中间：称重与打印区  |  右侧：手动加钱快捷键 (+1元/+2元/打包盒)
PyQt5 + Python 3.8 兼容
"""
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox, QGridLayout, QGroupBox, QDoubleSpinBox
)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont, QColor

from core.calculator import calculate_price, price_unit_label
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
        self.extra_amount = 0.0  # 手动附加金额 (如打包盒、饮料等)
        self.extra_items = []    # 附加明细列表 [("打包盒", 1.0), ("饮料", 3.0)]

        self._build_ui()
        self._setup_scale()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # ═════════════════════════════════════════════════
        # ── 1. 左侧：菜单与订单清单 (占 3 份) ──
        # ═════════════════════════════════════════════════
        left_box = QVBoxLayout()
        left_box.setSpacing(8)

        # 订单头
        top_bar = QHBoxLayout()
        lbl_menu_title = QLabel(u"📋 订单明细")
        lbl_menu_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333333;")
        top_bar.addWidget(lbl_menu_title)
        top_bar.addStretch()

        left_box.addLayout(top_bar)

        # 单价配置行
        price_bar = QHBoxLayout()
        price_bar.addWidget(QLabel(u"称重单价："))
        self.spin_price = QDoubleSpinBox()
        self.spin_price.setRange(0.01, 999.99)
        self.spin_price.setValue(self.config.get("unit_price", 32.00))
        self.spin_price.setSuffix(" %s" % price_unit_label(self.config.get("price_unit", "per_jin")))
        self.spin_price.setDecimals(2)
        self.spin_price.setSingleStep(0.5)
        self.spin_price.valueChanged.connect(self._on_price_changed)
        price_bar.addWidget(self.spin_price)
        left_box.addLayout(price_bar)

        # 订单明细表格
        self.table_cart = QTableWidget()
        self.table_cart.setColumnCount(3)
        self.table_cart.setHorizontalHeaderLabels([u"项目", u"数量/重量", u"金额"])
        h = self.table_cart.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_cart.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_cart.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_cart.verticalHeader().setVisible(False)
        left_box.addWidget(self.table_cart, stretch=1)

        # 清除附加项按钮
        btn_clear_extra = QPushButton(u"清空附加项")
        btn_clear_extra.setStyleSheet("color: #E74C3C; border: 1px solid #E74C3C; background: white;")
        btn_clear_extra.clicked.connect(self._on_clear_extra)
        left_box.addWidget(btn_clear_extra)

        main_layout.addLayout(left_box, stretch=30)

        # ═════════════════════════════════════════════════
        # ── 2. 中间：称重显示与主操作区 (占 4 份) ──
        # ═════════════════════════════════════════════════
        mid_box = QVBoxLayout()
        mid_box.setSpacing(12)

        # 状态指示
        status_line = QHBoxLayout()
        self.lbl_conn = QLabel(u"● 秤：正在连接...")
        self.lbl_conn.setStyleSheet("color: #f39c12; font-size: 13px; font-weight: bold;")
        status_line.addWidget(self.lbl_conn)
        status_line.addStretch()
        mid_box.addLayout(status_line)

        # 重量显示大卡片
        weight_card = QFrame()
        weight_card.setStyleSheet(
            "QFrame { background: #FF5500; border-radius: 12px; padding: 16px; }"
        )
        wc_layout = QVBoxLayout(weight_card)
        wc_layout.setAlignment(Qt.AlignCenter)

        lbl_w_title = QLabel(u"当前重量")
        lbl_w_title.setStyleSheet("color: #FFE6DC; font-size: 16px;")
        wc_layout.addWidget(lbl_w_title)

        self.lbl_weight = QLabel("0.000")
        self.lbl_weight.setStyleSheet(
            "color: #FFFFFF; font-size: 64px; font-weight: bold;"
            "font-family: 'Consolas', monospace;"
        )
        self.lbl_weight.setAlignment(Qt.AlignCenter)
        wc_layout.addWidget(self.lbl_weight)

        self.lbl_weight_unit = QLabel("kg (0.00 斤)")
        self.lbl_weight_unit.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: bold;")
        self.lbl_weight_unit.setAlignment(Qt.AlignCenter)
        wc_layout.addWidget(self.lbl_weight_unit)

        self.lbl_stable = QLabel("")
        self.lbl_stable.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        self.lbl_stable.setAlignment(Qt.AlignCenter)
        wc_layout.addWidget(self.lbl_stable)

        mid_box.addWidget(weight_card, stretch=2)

        # 应收总价大卡片
        amount_card = QFrame()
        amount_card.setStyleSheet(
            "QFrame { background: #FFFFFF; border: 2px solid #FF5500; border-radius: 12px; padding: 12px; }"
        )
        ac_layout = QVBoxLayout(amount_card)
        ac_layout.setAlignment(Qt.AlignCenter)

        lbl_a_title = QLabel(u"应收总金额")
        lbl_a_title.setStyleSheet("color: #666666; font-size: 15px;")
        ac_layout.addWidget(lbl_a_title)

        self.lbl_total_amount = QLabel(u"￥0.00")
        self.lbl_total_amount.setStyleSheet("color: #FF5500; font-size: 42px; font-weight: bold;")
        self.lbl_total_amount.setAlignment(Qt.AlignCenter)
        ac_layout.addWidget(self.lbl_total_amount)

        mid_box.addWidget(amount_card, stretch=1)

        # 大打印按钮
        self.btn_print = QPushButton(u"🖨️ 称重并打印小票")
        self.btn_print.setObjectName("btn_print")
        self.btn_print.clicked.connect(self._on_print)
        mid_box.addWidget(self.btn_print)

        # 重置按钮
        btn_reset = QPushButton(u"🔄 清零 / 重置")
        btn_reset.setStyleSheet(
            "background: white; color: #666666; border: 1px solid #CCCCCC;"
            "padding: 10px; font-size: 15px; font-weight: bold; border-radius: 6px;"
        )
        btn_reset.clicked.connect(self._on_reset)
        mid_box.addWidget(btn_reset)

        main_layout.addLayout(mid_box, stretch=40)

        # ═════════════════════════════════════════════════
        # ── 3. 右侧：手动加钱快捷键 (占 3 份) ──
        # ═════════════════════════════════════════════════
        right_group = QGroupBox(u"➕ 手动加钱 / 额外小食")
        rg_layout = QVBoxLayout(right_group)
        rg_layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(8)

        extra_buttons = [
            (u"+1 元 (打包盒)", 1.0),
            (u"+2 元 (小食/米饭)", 2.0),
            (u"+3 元 (饮料)", 3.0),
            (u"+4 元", 4.0),
            (u"+5 元 (特饮)", 5.0),
            (u"+6 元", 6.0),
            (u"+8 元", 8.0),
            (u"+10 元", 10.0),
        ]

        r, c = 0, 0
        for label, val in extra_buttons:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "background: white; border: 1px solid #FF5500; color: #FF5500;"
                "font-size: 15px; font-weight: bold; min-height: 48px; border-radius: 8px;"
            )
            btn.clicked.connect(lambda checked, v=val, l=label: self._add_extra(l, v))
            grid.addWidget(btn, r, c)
            c += 1
            if c >= 2:
                c = 0
                r += 1

        rg_layout.addLayout(grid)

        # 自定义金额输入
        custom_box = QHBoxLayout()
        custom_box.addWidget(QLabel(u"自定义："))
        self.spin_custom = QDoubleSpinBox()
        self.spin_custom.setRange(0.5, 999.0)
        self.spin_custom.setValue(1.0)
        self.spin_custom.setSuffix(u" 元")
        custom_box.addWidget(self.spin_custom)

        btn_add_custom = QPushButton(u"添加")
        btn_add_custom.setStyleSheet("background: #FF5500; color: white; font-weight: bold;")
        btn_add_custom.clicked.connect(self._add_custom_extra)
        custom_box.addWidget(btn_add_custom)

        rg_layout.addLayout(custom_box)
        rg_layout.addStretch()

        main_layout.addWidget(right_group, stretch=30)

        # 初始化刷新订单明细
        self._update_display()

    # ─── 手动加钱逻辑 ──────────────────────────────────
    def _add_extra(self, label, amount):
        name = label.split(" ")[0]
        self.extra_items.append((name, amount))
        self.extra_amount += amount
        self._update_display()

    def _add_custom_extra(self):
        val = self.spin_custom.value()
        name = u"+%.1f元" % val
        self.extra_items.append((name, val))
        self.extra_amount += val
        self._update_display()

    def _on_clear_extra(self):
        self.extra_items.clear()
        self.extra_amount = 0.0
        self._update_display()

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
        self.lbl_weight_unit.setText("kg (%.2f 斤)" % (weight_kg * 2))
        self._update_display()

    @pyqtSlot(bool, str)
    def _on_status_change(self, connected, msg):
        if connected:
            self.lbl_conn.setText(u"● 秤：%s" % msg)
            self.lbl_conn.setStyleSheet("color: #2ecc71; font-size: 13px; font-weight: bold;")
        else:
            self.lbl_conn.setText(u"● 秤：%s" % msg)
            self.lbl_conn.setStyleSheet("color: #e74c3c; font-size: 13px; font-weight: bold;")

    @pyqtSlot(float)
    def _on_weight_stable(self, weight_kg):
        if weight_kg > 0.02:
            self._is_stable = True
            self._stable_weight = weight_kg
            self.lbl_stable.setText(u"[OK] 重量已稳定")

    @pyqtSlot(str)
    def _on_error(self, msg):
        self.lbl_conn.setText(u"[!] %s" % msg)
        self.lbl_conn.setStyleSheet("color: #e74c3c; font-size: 13px;")

    def _on_price_changed(self, value):
        self.config["unit_price"] = value
        self._update_display()

    # ─── 界面与计算刷新 ─────────────────────────────────
    def _update_display(self):
        weight = self.current_weight
        unit_price = self.spin_price.value()
        price_unit = self.config.get("price_unit", "per_jin")

        scale_total = calculate_price(weight, unit_price, price_unit)
        grand_total = round(scale_total + self.extra_amount, 2)

        self.lbl_total_amount.setText(u"￥%.2f" % grand_total)

        # 填充左侧订单明细表
        rows = 1 if weight > 0 else 0
        rows += len(self.extra_items)
        self.table_cart.setRowCount(rows)

        r_idx = 0
        if weight > 0:
            w_str = "%.2f 斤" % (weight * 2) if price_unit == "per_jin" else "%.3f kg" % weight
            u_str = "%.2f 元/斤" % unit_price if price_unit == "per_jin" else "%.2f 元/kg" % unit_price

            self.table_cart.setItem(r_idx, 0, QTableWidgetItem(u"麻辣烫 (称重)"))
            self.table_cart.setItem(r_idx, 1, QTableWidgetItem(w_str))

            amt_item = QTableWidgetItem(u"￥%.2f" % scale_total)
            amt_item.setForeground(QColor("#FF5500"))
            self.table_cart.setItem(r_idx, 2, amt_item)
            r_idx += 1

        for name, amt in self.extra_items:
            self.table_cart.setItem(r_idx, 0, QTableWidgetItem(name))
            self.table_cart.setItem(r_idx, 1, QTableWidgetItem("1"))
            amt_item = QTableWidgetItem(u"￥%.2f" % amt)
            amt_item.setForeground(QColor("#FF5500"))
            self.table_cart.setItem(r_idx, 2, amt_item)
            r_idx += 1

    # ─── 操作 ──────────────────────────────────────
    def _on_print(self):
        weight = self.current_weight
        unit_price = self.spin_price.value()
        price_unit = self.config.get("price_unit", "per_jin")

        scale_total = calculate_price(weight, unit_price, price_unit)
        grand_total = round(scale_total + self.extra_amount, 2)

        if grand_total < 0.01:
            QMessageBox.warning(self, u"提示", u"当前金额为零，请先称重或添加手动金额！")
            return

        record = self.db.insert_sale(
            weight_kg=weight,
            unit_price=unit_price,
            price_unit=price_unit,
            total_price=grand_total
        )

        sale_data = dict(record)
        sale_data["shop_name"] = self.config.get("shop_name", u"杨国福麻辣烫")
        sale_data["shop_subtitle"] = self.config.get("shop_subtitle", "")
        sale_data["receipt_footer"] = self.config.get("receipt_footer", u"谢谢惠顾！")

        success = self.printer.print_receipt(sale_data)

        if success:
            QMessageBox.information(
                self, u"打印成功",
                u"小票已发送至打印机！\n单号：%s\n总额：￥%.2f" % (record["sale_no"], grand_total)
            )
        else:
            QMessageBox.warning(self, u"打印失败", u"小票打印失败，请检查打印机连接！\n记录已保存。")

    def _on_reset(self):
        self.current_weight = 0.0
        self.extra_amount = 0.0
        self.extra_items.clear()
        self.lbl_weight.setText("0.000")
        self.lbl_weight_unit.setText("kg (0.00 斤)")
        self.lbl_stable.setText("")
        self._update_display()

    def cleanup(self):
        if hasattr(self, 'scale'):
            self.scale.stop()
