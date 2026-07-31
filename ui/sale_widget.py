"""
销售/称重界面 — 原生 4x4 菜单网格 + 汤底选择加入称重明细逻辑
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
    """无边框极简 POS 风格订单细项卡片"""

    def __init__(self, title, subline, tag="", is_active=False, parent=None):
        super().__init__(parent)
        self.setObjectName("OrderItemCard")
        bg_color = "#1E293B" if is_active else "#172136"

        self.setStyleSheet(
            f"QFrame#OrderItemCard {{ background: {bg_color}; border: none; "
            f"border-radius: 8px; margin-bottom: 6px; padding: 10px 12px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 商品名称
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB; border: none;")
        layout.addWidget(lbl_title)

        # 数量、单价与小计行
        lbl_sub = QLabel(subline)
        lbl_sub.setStyleSheet("font-size: 13px; color: #9CA3AF; font-family: 'Consolas', monospace; border: none;")
        layout.addWidget(lbl_sub)

        # 标签 (如: 微辣/)
        if tag:
            lbl_tag = QLabel(tag)
            lbl_tag.setStyleSheet("font-size: 12px; color: #F59E0B; border: none;")
            layout.addWidget(lbl_tag)


class MenuGridButton(QPushButton):
    """
    杨国福右侧原生菜单卡片按钮
    支持双行标题 + 价格副标题 + 右上角数字角标 (Badge)
    """

    def __init__(self, key_id, title, subtitle, price, is_soup=False, parent=None):
        super().__init__(parent)
        self.key_id = key_id
        self.title_str = title
        self.subtitle_str = subtitle
        self.price_val = price
        self.is_soup = is_soup
        self.count = 0

        self.setMinimumHeight(70)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        # 标题 (例如: 经典草本骨汤 / 4元饮料)
        self.lbl_title = QLabel(title)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setWordWrap(True)
        layout.addWidget(self.lbl_title)

        # 副标题价格 (例如: ¥ 47.60/KG / ¥ 4.00/瓶)
        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_sub)

        # 右上角数字角标 (Badge)
        self.lbl_badge = QLabel("", self)
        self.lbl_badge.setStyleSheet(
            "background: #EA580C; color: white; font-weight: bold; font-size: 11px; "
            "border-radius: 9px; padding: 1px 5px;"
        )
        self.lbl_badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lbl_badge.hide()

        self._update_style()

    def set_count(self, val: int):
        self.count = val
        if val > 0:
            self.lbl_badge.setText(str(val))
            self.lbl_badge.show()
            self.lbl_badge.adjustSize()
            self.lbl_badge.move(self.width() - self.lbl_badge.width() - 4, 4)
        else:
            self.lbl_badge.hide()
        self._update_style()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.count > 0:
            self.lbl_badge.move(self.width() - self.lbl_badge.width() - 4, 4)

    def _update_style(self):
        if self.count > 0:
            self.setStyleSheet(
                "QPushButton { background: #1E293B; border: 2px solid #EA580C; border-radius: 10px; }"
                "QPushButton:hover { background: #263352; }"
            )
            self.lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #F97316; border: none; background: transparent;")
            self.lbl_sub.setStyleSheet("font-size: 12px; color: #38BDF8; border: none; background: transparent;")
        else:
            self.setStyleSheet(
                "QPushButton { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 10px; }"
                "QPushButton:hover { background: #F3F4F6; }"
            )
            self.lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #C2410C; border: none; background: transparent;")
            self.lbl_sub.setStyleSheet("font-size: 12px; color: #4B5563; border: none; background: transparent;")


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
        
        # 选中的汤底（未点击汤底时为 None，不计算称重价钱）
        self.selected_soup = None
        # 附加加价项目字典: { item_key: count }
        self.item_counts = {}
        
        self.menu_buttons = {}
        self.temp_order_no = self._gen_temp_order_no()
        self._detail_expanded = False

        self._build_ui()
        self._setup_scale()
        self.refresh_call_number_display()

    def _gen_temp_order_no(self):
        return "%05d" % random.randint(10000, 99999)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── 左侧：开单面板 ──
        left_card = QFrame()
        left_card.setStyleSheet("QFrame { background: #111827; border: none; border-radius: 14px; }")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)

        # 1. 顶栏：本次打印叫号模块 (带展开/折叠详细信息)
        call_header = QHBoxLayout()
        
        lbl_call_title = QLabel(u"本次打印叫号：")
        lbl_call_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #9CA3AF; border: none;")
        call_header.addWidget(lbl_call_title)

        self.lbl_next_call_no = QLabel("# 50")
        self.lbl_next_call_no.setStyleSheet("font-size: 26px; font-weight: 900; color: #F97316; border: none;")
        call_header.addWidget(self.lbl_next_call_no)

        self.btn_toggle_detail = QPushButton(u"详细信息 ∨")
        self.btn_toggle_detail.setStyleSheet(
            "background: #1E293B; color: #38BDF8; font-size: 13px; font-weight: bold; border-radius: 6px; padding: 4px 10px;"
        )
        self.btn_toggle_detail.clicked.connect(self._toggle_call_detail)
        call_header.addWidget(self.btn_toggle_detail)

        call_header.addStretch()

        left_layout.addLayout(call_header)

        # 展开可折叠的叫号避重详细面板
        self.call_detail_box = QFrame()
        self.call_detail_box.setVisible(False)
        self.call_detail_box.setStyleSheet("QFrame { background: #172136; border-radius: 8px; padding: 8px; }")
        cd_layout = QHBoxLayout(self.call_detail_box)
        cd_layout.setContentsMargins(8, 6, 8, 6)

        self.lbl_mode_tip = QLabel(u"模式：智能避重模式")
        self.lbl_mode_tip.setStyleSheet("color: #9CA3AF; font-size: 13px; border: none;")
        cd_layout.addWidget(self.lbl_mode_tip, stretch=1)

        btn_override = QPushButton(u"手动修改叫号")
        btn_override.setStyleSheet("font-size: 12px; min-height: 28px;")
        btn_override.clicked.connect(self._manual_adjust_call_no)
        cd_layout.addWidget(btn_override)

        left_layout.addWidget(self.call_detail_box)

        # 橙色重量 LED 横幅卡片
        led_banner = QFrame()
        led_banner.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #EA580C, stop:1 #C2410C); border-radius: 8px; padding: 8px 14px; border: none; }"
        )
        led_layout = QHBoxLayout(led_banner)
        led_layout.setContentsMargins(12, 4, 12, 4)

        # 状态指示图标: ⏳ (读取/未稳定) vs ✅ (稳定就绪对号)
        self.lbl_scale_status_icon = QLabel(u"⏳")
        self.lbl_scale_status_icon.setToolTip(u"读数计算中...")
        self.lbl_scale_status_icon.setStyleSheet("font-size: 26px; border: none;")
        led_layout.addWidget(self.lbl_scale_status_icon)

        self.lbl_weight = QLabel("00.000 kg")
        self.lbl_weight.setStyleSheet(
            "font-size: 36px; font-weight: 900; color: #FFFFFF; border: none; "
            "font-family: 'Segoe UI', 'Consolas', sans-serif; letter-spacing: 1px;"
        )
        led_layout.addWidget(self.lbl_weight, stretch=1, alignment=Qt.AlignRight)

        left_layout.addWidget(led_banner)

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

        # 3. 结算金额栏
        footer_line = QHBoxLayout()
        self.lbl_item_count = QLabel(u"共 0 件，需付款：")
        self.lbl_item_count.setStyleSheet("font-size: 16px; font-weight: bold; color: #9CA3AF; border: none;")
        footer_line.addWidget(self.lbl_item_count)

        footer_line.addStretch()

        self.lbl_price = QLabel(u"￥0.00")
        self.lbl_price.setStyleSheet("font-size: 32px; font-weight: 900; color: #F97316; border: none;")
        footer_line.addWidget(self.lbl_price)

        left_layout.addLayout(footer_line)

        layout.addWidget(left_card, stretch=5)

        # ── 右侧：参照原版 4x4 网格菜单 ──
        right = QVBoxLayout()
        right.setSpacing(12)

        menu_group = QGroupBox(u"请点选汤底与附加加价项目")
        mg_grid = QGridLayout(menu_group)
        mg_grid.setSpacing(8)

        unit_price = self.config.get("unit_price", 47.60)
        price_unit = self.config.get("price_unit", "per_jin")
        pu_lbl = price_unit_label(price_unit)

        # 定义参照参考图片的菜单列表 (4列 x 4行)
        menu_items_config = [
            # 行 1: 三种汤底 + 1元串/小食
            (0, 0, "soup_1", u"经典草本骨汤\n( KG )", f"¥ {unit_price:.2f}/{pu_lbl}", unit_price, True),
            (0, 1, "soup_2", u"酸甜番茄汤\n( KG )", f"¥ {unit_price:.2f}/{pu_lbl}", unit_price, True),
            (0, 2, "soup_3", u"石磨醇香麻辣拌\n( 干拌无汤 )", f"¥ {unit_price:.2f}/{pu_lbl}", unit_price, True),
            (0, 3, "item_串", u"1元串/小食", u"¥ 1.00/份", 1.0, False),

            # 行 2: 打包盒 + 1-3元饮料
            (1, 0, "item_box", u"打包盒 (小)", u"¥ 1.00/个", 1.0, False),
            (1, 1, "item_1", u"1元饮料", u"¥ 1.00/瓶", 1.0, False),
            (1, 2, "item_2", u"2元饮料", u"¥ 2.00/瓶", 2.0, False),
            (1, 3, "item_3", u"3元饮料", u"¥ 3.00/瓶", 3.0, False),

            # 行 3: 4-7元饮料
            (2, 0, "item_4", u"4元饮料", u"¥ 4.00/瓶", 4.0, False),
            (2, 1, "item_5", u"5元饮料", u"¥ 5.00/瓶", 5.0, False),
            (2, 2, "item_6", u"6元饮料", u"¥ 6.00/瓶", 6.0, False),
            (2, 3, "item_7", u"7元饮料", u"¥ 7.00/瓶", 7.0, False),

            # 行 4: 8-10元饮料
            (3, 0, "item_8", u"8元饮料", u"¥ 8.00/瓶", 8.0, False),
            (3, 1, "item_9", u"9元饮料", u"¥ 9.00/瓶", 9.0, False),
            (3, 2, "item_10", u"10元饮料", u"¥ 10.00/瓶", 10.0, False),
        ]

        for r, c, key_id, title, sub, price, is_soup in menu_items_config:
            btn = MenuGridButton(key_id, title, sub, price, is_soup)
            btn.clicked.connect(lambda checked, b=btn: self._on_menu_click(b))
            mg_grid.addWidget(btn, r, c)
            self.menu_buttons[key_id] = btn

        right.addWidget(menu_group)

        # 底部核心按键
        btn_box = QHBoxLayout()
        
        self.btn_clear = QPushButton(u"清空重置")
        self.btn_clear.setObjectName("btn_clear")
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.clicked.connect(self._on_clear)
        btn_box.addWidget(self.btn_clear, stretch=1)

        self.btn_print = QPushButton(u"称重并打印小票")
        self.btn_print.setObjectName("btn_print")
        self.btn_print.setCursor(Qt.PointingHandCursor)
        self.btn_print.clicked.connect(self._on_print)
        btn_box.addWidget(self.btn_print, stretch=2)

        right.addLayout(btn_box)

        layout.addLayout(right, stretch=5)

        self._update_price_display()

    def _on_menu_click(self, btn: MenuGridButton):
        """点击右侧菜单按钮"""
        if btn.is_soup:
            # 汤底按钮：取消其他汤底的选择，选中当前汤底
            for k, b in self.menu_buttons.items():
                if b.is_soup:
                    b.set_count(0)
            self.selected_soup = btn.title_str.replace("\n", " ")
            btn.set_count(1)
        else:
            # 加价/饮料项目：按一次累加 1
            curr = self.item_counts.get(btn.key_id, 0) + 1
            self.item_counts[btn.key_id] = curr
            btn.set_count(curr)

        self._update_price_display()

    def _toggle_call_detail(self):
        self._detail_expanded = not self._detail_expanded
        self.call_detail_box.setVisible(self._detail_expanded)
        if self._detail_expanded:
            self.btn_toggle_detail.setText(u"详细信息 ∧")
        else:
            self.btn_toggle_detail.setText(u"详细信息 ∨")

    def _update_price_display(self):
        """刷新购物明细卡片列表与金额"""
        while self.cart_layout.count() > 0:
            child = self.cart_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        unit_price = self.config.get("unit_price", 47.60)
        price_unit = self.config.get("price_unit", "per_jin")
        base_price = calculate_price(self.current_weight, unit_price, price_unit)
        pu_lbl = price_unit_label(price_unit)

        total_price = 0.0
        total_items = 0

        # 1. 只有当点击了汤底时，才加入称重麻辣烫项目！
        if self.selected_soup:
            w_str = f"{self.current_weight:.3f}"
            sub_str = f"{w_str} kg   ¥{unit_price:.2f}/{pu_lbl}   堂食   x{w_str}   ¥{base_price:.2f}"
            card_main = OrderItemCard(self.selected_soup, sub_str, tag=u"微辣/", is_active=True)
            self.cart_layout.addWidget(card_main)
            total_price += base_price
            total_items += 1
        else:
            # 没点击汤底时，在购物车顶部提示
            lbl_tip = QLabel(u"👈 请点选右侧汤底以加入称重食材")
            lbl_tip.setStyleSheet("color: #F59E0B; font-size: 14px; font-weight: bold; padding: 12px; border: none;")
            self.cart_layout.addWidget(lbl_tip)

        # 2. 动态附加加价/饮料项目卡片
        for key_id, count in self.item_counts.items():
            if count <= 0:
                continue
            btn = self.menu_buttons.get(key_id)
            if btn:
                item_total = btn.price_val * count
                item_sub = f"{count}   ¥{btn.price_val:.2f}   堂食   x{count}   ¥{item_total:.2f}"
                card_extra = OrderItemCard(btn.title_str.replace("\n", " "), item_sub, is_active=False)
                self.cart_layout.addWidget(card_extra)
                total_price += item_total
                total_items += count

        # 3. 刷新底部统计
        self.lbl_item_count.setText(u"共 %d 件，需付款：" % total_items)
        self.lbl_price.setText(u"￥%.2f" % total_price)

    def refresh_call_number_display(self):
        next_num = self.call_mgr.peek_next_number()
        self.lbl_next_call_no.setText("# %d" % next_num)

        mode = self.call_mgr.get_mode()
        if mode == CallNumberManager.MODE_SMART:
            slot = self.call_mgr._get_current_time_slot()
            slot_name = u"上午 (50-100)" if slot == "morning" else (u"下午 (100-200)" if slot == "afternoon" else u"晚上 (200-300)")
            self.lbl_mode_tip.setText(u"模式：智能避重 [%s]" % slot_name)
        elif mode == CallNumberManager.MODE_CUSTOM:
            self.lbl_mode_tip.setText(u"模式：自定义范围避重")
        else:
            self.lbl_mode_tip.setText(u"模式：手动指定")

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
        self.lbl_weight.setText("%06.3f kg" % weight_kg)
        self._update_price_display()

        # 连续两次读数之差 <= 0.005kg 即视为完全稳定，瞬间变为 ✅
        if abs(weight_kg - self._stable_weight) <= 0.005:
            self._is_stable = True
            self.lbl_scale_status_icon.setText(u"✅")
            self.lbl_scale_status_icon.setToolTip(u"读数稳定，可随时打印！")
        else:
            # 读数剧烈变动中 -> ⏳
            self._is_stable = False
            self._stable_weight = weight_kg
            self.lbl_scale_status_icon.setText(u"⏳")
            self.lbl_scale_status_icon.setToolTip(u"读数计算/变动中...")

    @pyqtSlot(bool, str)
    def _on_status_change(self, connected, msg):
        if not connected:
            self.lbl_scale_status_icon.setText(u"❌")
            self.lbl_scale_status_icon.setToolTip(u"官方秤未连接: %s" % msg)

    @pyqtSlot(float)
    def _on_weight_stable(self, weight_kg):
        self._is_stable = True
        self._stable_weight = weight_kg
        self.lbl_scale_status_icon.setText(u"✅")
        self.lbl_scale_status_icon.setToolTip(u"重量已稳定，可随时打印！")

    @pyqtSlot(str)
    def _on_error(self, msg):
        self.lbl_scale_status_icon.setText(u"❌")
        self.lbl_scale_status_icon.setToolTip(u"错误: %s" % msg)

    def _on_print(self):
        """称重并打印小票"""
        if not self.selected_soup:
            QMessageBox.warning(self, u"提示", u"请先点选汤底（如经典草本骨汤）以加入称重项目！")
            return

        weight = self.current_weight
        if weight < 0.01:
            QMessageBox.warning(self, u"提示", u"当前重量为零，请先放上食材！")
            return

        unit_price = self.config.get("unit_price", 47.60)
        price_unit = self.config.get("price_unit", "per_jin")
        base_price = calculate_price(weight, unit_price, price_unit)
        
        extra_total = 0.0
        for key_id, count in self.item_counts.items():
            btn = self.menu_buttons.get(key_id)
            if btn and count > 0:
                extra_total += btn.price_val * count

        total_price = base_price + extra_total

        assigned_num = self.call_mgr.get_next_number()
        call_no_str = "%02d" % assigned_num

        record = self.db.insert_sale(
            weight_kg=weight,
            unit_price=unit_price,
            price_unit=price_unit,
            total_price=total_price,
            remark=u"单号:%s 汤底:%s 叫号:#%s 加价:￥%.2f" % (self.temp_order_no, self.selected_soup, call_no_str, extra_total)
        )

        sale_data = dict(record)
        sale_data["shop_name"] = self.config.get("shop_name", u"杨国福麻辣烫")
        sale_data["shop_subtitle"] = self.config.get("shop_subtitle", "")
        sale_data["receipt_footer"] = self.config.get("receipt_footer", u"谢谢惠顾！")
        sale_data["call_no"] = call_no_str
        sale_data["soup_name"] = self.selected_soup
        sale_data["extra_fee"] = extra_total

        success = self.printer.print_receipt(sale_data)

        if success:
            self._on_clear()
            self.refresh_call_number_display()
        else:
            QMessageBox.warning(self, u"打印失败", u"小票打印失败，请检查打印机连接！\n记录已保存。")

    def _on_clear(self):
        """清空购物车与角标"""
        self.selected_soup = None
        self.item_counts.clear()
        for b in self.menu_buttons.values():
            b.set_count(0)
        self.temp_order_no = self._gen_temp_order_no()
        self._update_price_display()

    def cleanup(self):
        if hasattr(self, 'scale'):
            self.scale.stop()
