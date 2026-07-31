"""
销售/称重界面 — 杨国福原生精美小票开单卡片式布局
PyQt5 + Python 3.8 兼容
"""
import random
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QSpinBox, QCheckBox, QGridLayout, QGroupBox,
    QScrollArea
)
from PyQt5.QtCore import Qt, pyqtSlot

from core.calculator import calculate_price, weight_display, price_unit_label
from core.database import Database
from core.printer import ReceiptPrinter
from core.scale_reader import ScaleReader
from core.call_number_manager import CallNumberManager


class OrderItemCard(QFrame):
    """原生 POS 风格订单细项卡片"""

    def __init__(self, title, subline, tag="", is_active=False, parent=None):
        super().__init__(parent)
        self.setObjectName("OrderItemCard")
        border_color = "#EA580C" if is_active else "#374151"
        bg_color = "#1F2937" if is_active else "#172136"

        self.setStyleSheet(
            f"QFrame#OrderItemCard {{ background: {bg_color}; border: 1px solid {border_color}; "
            f"border-radius: 8px; margin-bottom: 6px; padding: 6px 10px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 商品名称
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB;")
        layout.addWidget(lbl_title)

        # 数量、单价与小计行
        lbl_sub = QLabel(subline)
        lbl_sub.setStyleSheet("font-size: 13px; color: #D1D5DB; font-family: 'Consolas', monospace;")
        layout.addWidget(lbl_sub)

        # 标签 (如: 微辣/)
        if tag:
            lbl_tag = QLabel(tag)
            lbl_tag.setStyleSheet("font-size: 12px; color: #9CA3AF;")
            layout.addWidget(lbl_tag)


class SaleWidget(QWidget):
    """主销售界面"""

    def __init__(self, config, db, call_mgr: CallNumberManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.db = db
        self.call_mgr = call_mgr
        self.printer = ReceiptPrinter(config)

        self.current_weight = 0.0
        self._stable_weight = 0.0
        self._is_stable = False
        
        # 附加项目购物车: list of {"name": str, "price": float, "qty": int}
        self.extra_items = []
        self.temp_order_no = self._gen_temp_order_no()

        self._build_ui()
        self._setup_scale()
        self.refresh_call_number_display()

    def _gen_temp_order_no(self):
        return "%05d" % random.randint(10000, 99999)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(14, 14, 14, 14)

        # ── 左侧：完全参照杨国福原版设计的开单卡片面板 ──
        left_card = QFrame()
        left_card.setStyleSheet(
            "QFrame { background: #111827; border: 1px solid #263352; border-radius: 14px; }"
        )
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        # 1. 顶栏：单号与电子秤橙色 LED 读数横幅
        top_bar = QHBoxLayout()
        self.lbl_order_no = QLabel(u"单号：%s 📋" % self.temp_order_no)
        self.lbl_order_no.setStyleSheet("font-size: 14px; font-weight: bold; color: #9CA3AF;")
        top_bar.addWidget(self.lbl_order_no)

        top_bar.addStretch()

        self.lbl_conn = QLabel(u"● 官方秤同步中")
        self.lbl_conn.setStyleSheet("font-size: 13px; color: #10B981;")
        top_bar.addWidget(self.lbl_conn)

        left_layout.addLayout(top_bar)

        # 原版橙色重量 LED 横幅卡片
        led_banner = QFrame()
        led_banner.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #EA580C, stop:1 #C2410C); border-radius: 8px; padding: 6px 12px; }"
        )
        led_layout = QHBoxLayout(led_banner)
        led_layout.setContentsMargins(12, 4, 12, 4)

        lbl_icon = QLabel(u"⚖️")
        lbl_icon.setStyleSheet("font-size: 24px; color: #FFFFFF;")
        led_layout.addWidget(lbl_icon)

        self.lbl_weight = QLabel("00.000")
        self.lbl_weight.setStyleSheet(
            "font-size: 38px; font-weight: 900; color: #FFFFFF; "
            "font-family: 'Segoe UI', 'Consolas', sans-serif; letter-spacing: 2px;"
        )
        led_layout.addWidget(self.lbl_weight, stretch=1, alignment=Qt.AlignRight)

        left_layout.addWidget(led_banner)

        # 子标题选项条 (堂食 / 会员信息)
        sub_header = QHBoxLayout()
        lbl_dine = QLabel(u"堂食 ∨")
        lbl_dine.setStyleSheet("font-size: 14px; font-weight: bold; color: #F9FAFB;")
        sub_header.addWidget(lbl_dine)

        sub_header.addStretch()

        lbl_vip = QLabel(u"会员信息")
        lbl_vip.setStyleSheet("font-size: 14px; color: #9CA3AF;")
        sub_header.addWidget(lbl_vip)

        left_layout.addLayout(sub_header)

        # 2. 订单消费卡片列表 (ScrollArea)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cart_container = QWidget()
        self.cart_layout = QVBoxLayout(self.cart_container)
        self.cart_layout.setContentsMargins(0, 0, 0, 0)
        self.cart_layout.setSpacing(6)
        self.cart_layout.setAlignment(Qt.AlignTop)

        scroll.setWidget(self.cart_container)
        left_layout.addWidget(scroll, stretch=1)

        # 3. 翻页与结算底栏
        page_bar = QHBoxLayout()
        btn_prev = QPushButton(u"上一页")
        btn_prev.setStyleSheet(
            "background: #EA580C; color: white; font-weight: bold; border-radius: 6px; min-height: 36px;"
        )
        page_bar.addWidget(btn_prev)

        btn_next = QPushButton(u"下一页")
        btn_next.setStyleSheet(
            "background: #EA580C; color: white; font-weight: bold; border-radius: 6px; min-height: 36px;"
        )
        page_bar.addWidget(btn_next)
        left_layout.addLayout(page_bar)

        # 结算金额栏
        footer_line1 = QHBoxLayout()
        footer_line1.addWidget(QLabel(u"商品金额："))
        footer_line1.addStretch()
        self.lbl_subtotal = QLabel(u"￥0.00")
        self.lbl_subtotal.setStyleSheet("font-size: 15px; font-weight: bold; color: #D1D5DB;")
        footer_line1.addWidget(self.lbl_subtotal)
        left_layout.addLayout(footer_line1)

        footer_line2 = QHBoxLayout()
        self.lbl_item_count = QLabel(u"共 1 件，需付款：")
        self.lbl_item_count.setStyleSheet("font-size: 16px; font-weight: bold; color: #F9FAFB;")
        footer_line2.addWidget(self.lbl_item_count)

        footer_line2.addStretch()

        self.lbl_price = QLabel(u"￥0.00")
        self.lbl_price.setStyleSheet("font-size: 28px; font-weight: 900; color: #F97316;")
        footer_line2.addWidget(self.lbl_price)

        left_layout.addLayout(footer_line2)

        layout.addWidget(left_card, stretch=5)

        # ── 右侧：叫号牌 + 1-10元快捷加价 + 打印操作 ──
        right = QVBoxLayout()
        right.setSpacing(12)

        # 1. 叫号牌预显面板
        call_group = QGroupBox(u"取餐叫号牌 (避重引擎预分配)")
        cg_layout = QVBoxLayout(call_group)
        cg_layout.setSpacing(8)

        cg_top = QHBoxLayout()
        cg_top.addWidget(QLabel(u"本次打印叫号："))

        self.lbl_next_call_no = QLabel("# 50")
        self.lbl_next_call_no.setStyleSheet("font-size: 28px; font-weight: 900; color: #F97316;")
        cg_top.addWidget(self.lbl_next_call_no, stretch=1)

        btn_override = QPushButton(u"手动微调")
        btn_override.clicked.connect(self._manual_adjust_call_no)
        cg_top.addWidget(btn_override)

        cg_layout.addLayout(cg_top)

        self.lbl_mode_tip = QLabel(u"当前模式：智能避重模式")
        self.lbl_mode_tip.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        cg_layout.addWidget(self.lbl_mode_tip)

        right.addWidget(call_group)

        # 2. 快捷加价网格 (1元 ~ 10元)
        add_group = QGroupBox(u"快捷添加商品/打包 (1元~10元)")
        ag_grid = QGridLayout(add_group)
        ag_grid.setSpacing(6)

        item_names = {
            1: u"打包盒 (小) (个)",
            2: u"打包盒 (大) (个)",
            3: u"3元调料/汤底",
            4: u"4元饮料 (瓶)",
            5: u"5元饮料 (瓶)",
            6: u"6元自选加料",
            7: u"7元自选加料",
            8: u"8元自选加料",
            9: u"9元自选加料",
            10: u"10元小吃/加餐"
        }

        for i in range(1, 11):
            name = item_names.get(i, u"+%d元" % i)
            btn_add = QPushButton(u"+%d元" % i)
            btn_add.setToolTip(name)
            btn_add.setStyleSheet(
                "background: #1E293B; color: #F9FAFB; border: 1px solid #374151;"
                "border-radius: 8px; font-weight: bold; font-size: 14px; min-height: 36px;"
            )
            price_val = float(i)
            btn_add.clicked.connect(lambda checked, p=price_val, n=name: self._add_item_to_cart(n, p))

            row = (i - 1) // 5
            col = (i - 1) % 5
            ag_grid.addWidget(btn_add, row, col)

        btn_reset_fee = QPushButton(u"清空附加项目")
        btn_reset_fee.setStyleSheet(
            "background: #78350F; color: #FBBF24; border: 1px solid #F59E0B;"
            "border-radius: 8px; font-weight: bold; font-size: 14px; min-height: 36px;"
        )
        btn_reset_fee.clicked.connect(self._clear_extra_items)
        ag_grid.addWidget(btn_reset_fee, 2, 0, 1, 5)

        right.addWidget(add_group)

        # 3. 核心按键
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

        layout.addLayout(right, stretch=4)

        self._update_price_display()

    def _add_item_to_cart(self, name, price):
        """向购物车添加一个附加项目"""
        self.extra_items.append({"name": name, "price": price, "qty": 1})
        self._update_price_display()

    def _clear_extra_items(self):
        """清空所有附加项目"""
        self.extra_items.clear()
        self._update_price_display()

    def _update_price_display(self):
        """刷新购物明细卡片列表与金额"""
        # 清空容器中旧卡片
        while self.cart_layout.count() > 0:
            child = self.cart_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        unit_price = self.config.get("unit_price", 32.00)
        price_unit = self.config.get("price_unit", "per_jin")
        base_price = calculate_price(self.current_weight, unit_price, price_unit)
        pu_lbl = price_unit_label(price_unit)

        extra_total = sum(item["price"] for item in self.extra_items)
        total_price = base_price + extra_total

        # 1. 经典草本骨汤 (麻辣烫主项卡片)
        w_str = f"{self.current_weight:.3f}"
        sub_str = f"{w_str} kg   ¥{unit_price:.2f}/{pu_lbl}   堂食   x{w_str}   ¥{base_price:.2f}"
        card_main = OrderItemCard(u"经典草本骨汤 ( KG ) (KG)", sub_str, tag=u"微辣/", is_active=False)
        self.cart_layout.addWidget(card_main)

        # 2. 动态附加项目卡片
        for idx, item in enumerate(self.extra_items):
            is_last = (idx == len(self.extra_items) - 1)
            item_sub = f"1   ¥{item['price']:.2f}   堂食   x1   ¥{item['price']:.2f}"
            card_extra = OrderItemCard(item["name"], item_sub, is_active=is_last)
            self.cart_layout.addWidget(card_extra)

        # 3. 刷新底部统计
        item_count = 1 + len(self.extra_items)
        self.lbl_subtotal.setText(u"￥%.2f" % total_price)
        self.lbl_item_count.setText(u"共 %d 件，需付款：" % item_count)
        self.lbl_price.setText(u"￥%.2f" % total_price)

    def refresh_call_number_display(self):
        next_num = self.call_mgr.peek_next_number()
        self.lbl_next_call_no.setText("# %d" % next_num)

        mode = self.call_mgr.get_mode()
        if mode == CallNumberManager.MODE_SMART:
            slot = self.call_mgr._get_current_time_slot()
            slot_name = u"上午 (50-100)" if slot == "morning" else (u"下午 (100-200)" if slot == "afternoon" else u"晚上 (200-300)")
            self.lbl_mode_tip.setText(u"当前：智能避重模式 [%s]" % slot_name)
        elif mode == CallNumberManager.MODE_CUSTOM:
            self.lbl_mode_tip.setText(u"当前：自定义范围避重模式")
        else:
            self.lbl_mode_tip.setText(u"当前：手动模式")

    def _manual_adjust_call_no(self):
        from PyQt5.QtWidgets import QInputDialog
        curr = self.call_mgr.peek_next_number()
        val, ok = QInputDialog.getInt(self, u"微调叫号", u"请输入本次叫号牌号码：", curr, 1, 9999)
        if ok:
            self.call_mgr.set_manual_number(val)
            self.lbl_next_call_no.setText("# %d" % val)

    def refresh_unit_price_info(self):
        self._update_price_display()
        self.refresh_call_number_display()

    def restart_scale(self):
        self.refresh_unit_price_info()
        if hasattr(self, 'scale'):
            self.scale.restart()

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
        self.lbl_weight.setText("%06.3f" % weight_kg)
        self._update_price_display()

        if self._is_stable and abs(weight_kg - self._stable_weight) > 0.05:
            self._is_stable = False
            self.lbl_conn.setText(u"● 官方秤同步中")
            self.lbl_conn.setStyleSheet("color: #10B981; font-size: 13px;")

    @pyqtSlot(bool, str)
    def _on_status_change(self, connected, msg):
        if connected:
            self.lbl_conn.setText(u"● %s" % msg)
            self.lbl_conn.setStyleSheet("color: #10B981; font-size: 13px;")
        else:
            self.lbl_conn.setText(u"● %s" % msg)
            self.lbl_conn.setStyleSheet("color: #EF4444; font-size: 13px;")

    @pyqtSlot(float)
    def _on_weight_stable(self, weight_kg):
        if weight_kg > 0.02:
            self._is_stable = True
            self._stable_weight = weight_kg
            self.lbl_conn.setText(u"● [稳定就绪]")
            self.lbl_conn.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: bold;")

    @pyqtSlot(str)
    def _on_error(self, msg):
        self.lbl_conn.setText(u"[!] %s" % msg)
        self.lbl_conn.setStyleSheet("color: #EF4444; font-size: 13px;")

    def _on_print(self):
        """称重并打印小票"""
        weight = self.current_weight
        if weight < 0.01:
            QMessageBox.warning(self, u"提示", u"当前重量为零，请先放上食材！")
            return

        unit_price = self.config.get("unit_price", 32.00)
        price_unit = self.config.get("price_unit", "per_jin")
        base_price = calculate_price(weight, unit_price, price_unit)
        extra_total = sum(item["price"] for item in self.extra_items)
        total_price = base_price + extra_total

        assigned_num = self.call_mgr.get_next_number()
        call_no_str = "%02d" % assigned_num

        record = self.db.insert_sale(
            weight_kg=weight,
            unit_price=unit_price,
            price_unit=price_unit,
            total_price=total_price,
            remark=u"单号:%s 叫号:#%s 加价:￥%.2f" % (self.temp_order_no, call_no_str, extra_total)
        )

        sale_data = dict(record)
        sale_data["shop_name"] = self.config.get("shop_name", u"杨国福麻辣烫")
        sale_data["shop_subtitle"] = self.config.get("shop_subtitle", "")
        sale_data["receipt_footer"] = self.config.get("receipt_footer", u"谢谢惠顾！")
        sale_data["call_no"] = call_no_str
        sale_data["extra_fee"] = extra_total

        success = self.printer.print_receipt(sale_data)

        if success:
            self.lbl_conn.setText(u"● [已打印小票] #%s" % call_no_str)
            self.lbl_conn.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: bold;")
            
            # 生成新单号并刷新
            self.temp_order_no = self._gen_temp_order_no()
            self.lbl_order_no.setText(u"单号：%s 📋" % self.temp_order_no)
            self._clear_extra_items()
            self.refresh_call_number_display()
        else:
            QMessageBox.warning(self, u"打印失败", u"小票打印失败，请检查打印机连接！\n记录已保存。")

    def _on_clear(self):
        """清空附加项目与重新生成临时单号（不影响物理电子秤重量）"""
        self._clear_extra_items()
        self.temp_order_no = self._gen_temp_order_no()
        self.lbl_order_no.setText(u"单号：%s 📋" % self.temp_order_no)

    def cleanup(self):
        if hasattr(self, 'scale'):
            self.scale.stop()
