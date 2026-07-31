"""
销售/称重界面 — 1:1 复刻杨国福官方 POS 视觉界面
PyQt5 + Python 3.8 兼容
"""
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QLineEdit, QHeaderView,
    QAbstractItemView, QMessageBox, QGridLayout
)
from PyQt5.QtCore import Qt, pyqtSlot, QSize
from PyQt5.QtGui import QFont, QColor

from core.calculator import calculate_price, weight_display, price_unit_label
from core.database import Database
from core.printer import ReceiptPrinter
from core.scale_reader import ScaleReader


class SaleWidget(QWidget):
    """主销售界面 — 1:1 复刻杨国福官方 POS 布局"""

    def __init__(self, config, db, parent=None):
        super().__init__(parent)
        self.config = config
        self.db = db
        self.printer = ReceiptPrinter(config)
        self.current_weight = 0.0
        self._stable_weight = 0.0
        self._is_stable = False
        self.selected_product = u"经典草本骨汤 (KG)"

        self._build_ui()
        self._setup_scale()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ═════════════════════════════════════════════════
        # ── 1. 左侧：订单与称重显示区 (占 3.5 份) ──
        # ═════════════════════════════════════════════════
        left_box = QVBoxLayout()
        left_box.setSpacing(8)

        # 顶部单号信息
        top_info = QHBoxLayout()
        self.lbl_sale_no = QLabel(u"单号：%s" % datetime.now().strftime("%Y%m%d%H%M%S"))
        self.lbl_sale_no.setStyleSheet("color: #666666; font-size: 13px; font-weight: bold;")
        top_info.addWidget(self.lbl_sale_no)
        top_info.addStretch()

        self.lbl_conn = QLabel(u"● 秤：正在连接...")
        self.lbl_conn.setStyleSheet("color: #f39c12; font-size: 12px;")
        top_info.addWidget(self.lbl_conn)
        left_box.addLayout(top_info)

        # 亮橙色 LED 重量显示框 (1:1 还原杨国福顶栏橙框)
        led_box = QFrame()
        led_box.setObjectName("weight_led_box")
        led_layout = QHBoxLayout(led_box)
        led_layout.setContentsMargins(16, 12, 16, 12)

        self.lbl_weight_icon = QLabel(u"⏳")
        self.lbl_weight_icon.setStyleSheet("color: white; font-size: 32px;")
        led_layout.addWidget(self.lbl_weight_icon)

        self.lbl_weight_led = QLabel("00.000")
        self.lbl_weight_led.setObjectName("lbl_weight_led")
        led_layout.addWidget(self.lbl_weight_led)

        self.lbl_weight_unit = QLabel("KG")
        self.lbl_weight_unit.setStyleSheet("color: white; font-size: 20px; font-weight: bold;")
        led_layout.addWidget(self.lbl_weight_unit)

        led_layout.addStretch()

        # 右侧应收总价
        self.lbl_total_price_led = QLabel(u"￥0.00")
        self.lbl_total_price_led.setStyleSheet("color: white; font-size: 32px; font-weight: bold;")
        led_layout.addWidget(self.lbl_total_price_led)

        left_box.addWidget(led_box)

        # 堂食 / 会员信息 标头
        tab_header = QHBoxLayout()
        btn_dine_in = QPushButton(u"堂食 ∨")
        btn_dine_in.setStyleSheet(
            "background: white; border: 1px solid #E0E0E0; font-weight: bold; padding: 6px 16px;"
        )
        btn_member = QPushButton(u"会员信息")
        btn_member.setStyleSheet("background: white; border: 1px solid #E0E0E0; color: #666666; padding: 6px 16px;")
        tab_header.addWidget(btn_dine_in)
        tab_header.addWidget(btn_member)
        tab_header.addStretch()
        left_box.addLayout(tab_header)

        # 购物车/订单明细表格
        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(4)
        self.cart_table.setHorizontalHeaderLabels([u"商品名称", u"重量/数量", u"单价", u"小计"])
        h = self.cart_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.cart_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cart_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cart_table.verticalHeader().setVisible(False)

        left_box.addWidget(self.cart_table, stretch=1)

        # 底部操作栏：称重并打印小票
        btn_print_box = QHBoxLayout()
        self.btn_print = QPushButton(u"称重并打印小票 (Space)")
        self.btn_print.setObjectName("btn_print")
        self.btn_print.clicked.connect(self._on_print)
        btn_print_box.addWidget(self.btn_print, stretch=1)
        left_box.addLayout(btn_print_box)

        main_layout.addLayout(left_box, stretch=35)

        # ═════════════════════════════════════════════════
        # ── 2. 中间：功能按键条 (占 0.8 份) ──
        # ═════════════════════════════════════════════════
        mid_box = QVBoxLayout()
        mid_box.setSpacing(6)

        action_names = [
            u"扫商品券", u"9折", u"88折", u"+", u"-",
            u"打折", u"赠", u"删", u"一键清空", u"改价"
        ]
        for name in action_names:
            btn = QPushButton(name)
            btn.setStyleSheet(
                "background: white; border: 1px solid #DCDFE6; padding: 10px 4px;"
                "font-size: 13px; font-weight: 500; min-width: 60px;"
            )
            if name == u"一键清空":
                btn.setStyleSheet(
                    "background: #FFF2F0; border: 1px solid #FFCCC7; color: #FF4D4F;"
                    "font-size: 13px; font-weight: bold; padding: 10px 4px;"
                )
                btn.clicked.connect(self._on_clear)
            mid_box.addWidget(btn)

        mid_box.addStretch()
        main_layout.addLayout(mid_box, stretch=8)

        # ═════════════════════════════════════════════════
        # ── 3. 右侧：分类标签 + 数字行 + 产品卡片网格 (占 5.7 份) ──
        # ═════════════════════════════════════════════════
        right_box = QVBoxLayout()
        right_box.setSpacing(8)

        # 分类导航按钮行
        cat_layout = QHBoxLayout()
        cat_layout.setSpacing(4)

        categories = [
            (u"常用分类", True),
            (u"必选好汤", False),
            (u"串品小食", False),
            (u"爽口饮品", False),
            (u"精致涮品", False),
            (u"方便食品", False),
            (u"其他类", False),
            (u"套餐", False),
            (u"营销活动", False),
        ]
        for cat_name, is_act in categories:
            c_btn = QPushButton(cat_name)
            if is_act:
                c_btn.setProperty("class", "cat-btn-active")
                c_btn.setStyleSheet(
                    "background: #FF5500; color: white; border: none; font-weight: bold; padding: 8px 12px;"
                )
            else:
                c_btn.setStyleSheet(
                    "background: #EFEFEF; color: #444444; border: none; padding: 8px 12px;"
                )
            cat_layout.addWidget(c_btn)

        right_box.addLayout(cat_layout)

        # 数字键盘横条 (1 2 3 4 5 6 7 8 9 0 ⌫)
        num_layout = QHBoxLayout()
        num_layout.setSpacing(4)
        nums = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "✓", "⌫"]
        for n in nums:
            n_btn = QPushButton(n)
            n_btn.setStyleSheet(
                "background: white; border: 1px solid #DCDFE6; font-size: 15px; font-weight: bold;"
                "padding: 6px 12px; min-width: 32px;"
            )
            num_layout.addWidget(n_btn)

        right_box.addLayout(num_layout)

        # 核心产品卡片网格 (4列 x 4行)
        grid_frame = QFrame()
        grid_frame.setStyleSheet("background: white; border: 1px solid #E0E2E8; border-radius: 8px; padding: 6px;")
        grid_layout = QGridLayout(grid_frame)
        grid_layout.setSpacing(8)

        products = [
            (u"经典草本骨汤 (KG)", 47.60, u"/KG", "#FF5500"),
            (u"酸甜番茄汤 (KG)", 47.60, u"/KG", "#FF5500"),
            (u"石磨醇香麻辣拌", 47.60, u"/KG", "#FF5500"),
            (u"1元串/小食", 1.00, u"/份", "#E64A19"),
            (u"打包盒 (小)", 1.00, u"/个", "#FF5500"),
            (u"1元饮料", 1.00, u"/瓶", "#FF5500"),
            (u"2元饮料", 2.00, u"/瓶", "#FF5500"),
            (u"3元饮料", 3.00, u"/瓶", "#FF5500"),
            (u"4元饮料", 4.00, u"/瓶", "#FF5500"),
            (u"5元饮料", 5.00, u"/瓶", "#FF5500"),
            (u"6元饮料", 6.00, u"/瓶", "#FF5500"),
            (u"7元饮料", 7.00, u"/瓶", "#FF5500"),
            (u"8元饮料", 8.00, u"/瓶", "#FF5500"),
            (u"9元饮料", 9.00, u"/瓶", "#FF5500"),
            (u"10元饮料", 10.00, u"/瓶", "#FF5500"),
            (u"米饭 (大份)", 2.00, u"/碗", "#FF5500"),
        ]

        row, col = 0, 0
        for name, price, unit, color in products:
            card_btn = self._make_product_card(name, price, unit, color)
            grid_layout.addWidget(card_btn, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1

        right_box.addWidget(grid_frame, stretch=1)

        # 底部搜索与分页
        bottom_bar = QHBoxLayout()
        txt_search = QLineEdit()
        txt_search.setPlaceholderText(u"🔍 请输入简写")
        bottom_bar.addWidget(txt_search, stretch=1)

        btn_prev = QPushButton(u"上一页")
        lbl_page = QLabel(u"1/1")
        lbl_page.setStyleSheet("color: #666666; padding: 0 8px;")
        btn_next = QPushButton(u"下一页")

        bottom_bar.addWidget(btn_prev)
        bottom_bar.addWidget(lbl_page)
        bottom_bar.addWidget(btn_next)

        right_box.addLayout(bottom_bar)

        main_layout.addLayout(right_box, stretch=57)

        # 初始化刷新订单明细表
        self._update_cart_display()

    def _make_product_card(self, name, price, unit, title_color):
        btn = QPushButton()
        btn.setProperty("class", "product-card")
        btn.setMinimumHeight(64)
        btn.setCursor(Qt.PointingHandCursor)

        l = QVBoxLayout(btn)
        l.setContentsMargins(8, 6, 8, 6)
        l.setSpacing(2)

        lbl_name = QLabel(name)
        lbl_name.setStyleSheet("color: %s; font-size: 13px; font-weight: bold;" % title_color)
        lbl_name.setWordWrap(True)
        l.addWidget(lbl_name)

        lbl_price = QLabel(u"￥%.2f%s" % (price, unit))
        lbl_price.setStyleSheet("color: #666666; font-size: 12px;")
        l.addWidget(lbl_price)

        # 点击产品卡片时，更新选中的单价与名称
        btn.clicked.connect(lambda: self._select_product(name, price, unit))
        return btn

    def _select_product(self, name, price, unit):
        self.selected_product = name
        if "/KG" in unit or "kg" in unit:
            # 自动换算按斤
            self.config["price_unit"] = "per_jin"
            self.config["unit_price"] = round(price / 2.0, 2)
        else:
            self.config["unit_price"] = price

        self._update_cart_display()

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
        self.lbl_weight_led.setText("%06.3f" % weight_kg)
        self._update_cart_display()

    @pyqtSlot(bool, str)
    def _on_status_change(self, connected, msg):
        if connected:
            self.lbl_conn.setText(u"● 秤：%s" % msg)
            self.lbl_conn.setStyleSheet("color: #2ecc71; font-size: 12px; font-weight: bold;")
        else:
            self.lbl_conn.setText(u"● 秤：%s" % msg)
            self.lbl_conn.setStyleSheet("color: #e74c3c; font-size: 12px; font-weight: bold;")

    @pyqtSlot(float)
    def _on_weight_stable(self, weight_kg):
        if weight_kg > 0.02:
            self._is_stable = True
            self._stable_weight = weight_kg
            self.lbl_weight_icon.setText(u"⚖️")

    @pyqtSlot(str)
    def _on_error(self, msg):
        self.lbl_conn.setText(u"[!] %s" % msg)
        self.lbl_conn.setStyleSheet("color: #e74c3c; font-size: 12px;")

    def _update_cart_display(self):
        weight = self.current_weight
        unit_price = self.config.get("unit_price", 23.80)
        price_unit = self.config.get("price_unit", "per_jin")

        total = calculate_price(weight, unit_price, price_unit)
        self.lbl_total_price_led.setText(u"￥%.2f" % total)

        self.cart_table.setRowCount(1)

        pu_label = "元/斤" if price_unit == "per_jin" else "元/KG"
        w_label = "%.2f 斤" % (weight * 2) if price_unit == "per_jin" else "%.3f kg" % weight

        item_name = QTableWidgetItem(self.selected_product)
        item_weight = QTableWidgetItem(w_label)
        item_price = QTableWidgetItem("%.2f %s" % (unit_price, pu_label))
        item_total = QTableWidgetItem(u"￥%.2f" % total)

        item_total.setForeground(QColor("#FF5500"))
        font = QFont()
        font.setBold(True)
        item_total.setFont(font)

        self.cart_table.setItem(0, 0, item_name)
        self.cart_table.setItem(0, 1, item_weight)
        self.cart_table.setItem(0, 2, item_price)
        self.cart_table.setItem(0, 3, item_total)

    # ─── 操作 ──────────────────────────────────────
    def _on_print(self):
        """称重并打印小票"""
        weight = self.current_weight
        if weight < 0.01:
            QMessageBox.warning(self, u"提示", u"当前重量为零，请先在电子秤上放上食材！")
            return

        unit_price = self.config.get("unit_price", 23.80)
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
            QMessageBox.information(
                self, u"打印成功",
                u"小票已成功送往打印机！\n单号：%s\n金额：￥%.2f" % (record["sale_no"], total_price)
            )
            # 更新单号
            self.lbl_sale_no.setText(u"单号：%s" % datetime.now().strftime("%Y%m%d%H%M%S"))
        else:
            QMessageBox.warning(self, u"打印失败", u"小票打印失败，请检查打印机连接！\n记录已保存。")

    def _on_clear(self):
        self.current_weight = 0.0
        self.lbl_weight_led.setText("00.000")
        self.lbl_total_price_led.setText(u"￥0.00")
        self.cart_table.setRowCount(0)

    def cleanup(self):
        """关闭时清理资源"""
        if hasattr(self, 'scale'):
            self.scale.stop()
