"""
销售/称重界面 — 全面支持【曜石黑 / 极简光亮】双主题动态自适应
PyQt5 + Python 3.8 兼容
"""
import random
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QSpinBox, QCheckBox, QGridLayout, QGroupBox,
    QScrollArea, QDialog
)
from PyQt5.QtCore import Qt, pyqtSlot

from core.calculator import calculate_price, weight_display, price_unit_label
from core.database import Database
from core.printer import ReceiptPrinter
from core.scale_reader import ScaleReader
from core.call_number_manager import CallNumberManager


class TasteSelectionDialog(QDialog):
    """
    点击汤底时弹出的口味偏好对话框 (支持深浅视觉主题自适应)
    """

    def __init__(self, soup_name, is_dark_mode=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"选择口味 - {soup_name}")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Popup)
        
        bg_col = "#111827" if is_dark_mode else "#FFFFFF"
        border_col = "#EA580C"
        btn_bg = "#1F2937" if is_dark_mode else "#F3F4F6"
        btn_fg = "#D1D5DB" if is_dark_mode else "#374151"
        btn_border = "#374151" if is_dark_mode else "#D1D5DB"

        self.setStyleSheet(
            f"QDialog {{ background: {bg_col}; border: 2px solid {border_col}; border-radius: 12px; }}"
        )

        self.selected_spice = "微辣"
        self.selected_prefs = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        lbl_title = QLabel(f"🍲 请选择 【{soup_name}】 口味")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #F97316; border: none; background: transparent;")
        layout.addWidget(lbl_title)

        # 辣度选择 (单选)
        lbl_spicy = QLabel(u"辣度偏好：")
        lbl_spicy.setStyleSheet(f"font-size: 13px; color: {'#9CA3AF' if is_dark_mode else '#4B5563'}; border: none; background: transparent;")
        layout.addWidget(lbl_spicy)

        spicy_box = QHBoxLayout()
        spicy_box.setSpacing(8)
        self.spicy_btns = {}
        for s in [u"不辣", u"微辣", u"中辣", u"重辣"]:
            btn = QPushButton(s)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setChecked(s == self.selected_spice)
            btn.setStyleSheet(
                f"QPushButton {{ background: {btn_bg}; color: {btn_fg}; border: 1px solid {btn_border}; border-radius: 8px; padding: 8px 14px; font-weight: bold; font-size: 14px; }}"
                "QPushButton:checked { background: #EA580C; color: white; border: 1px solid #F97316; }"
            )
            btn.clicked.connect(lambda checked, val=s: self._select_spice(val))
            spicy_box.addWidget(btn)
            self.spicy_btns[s] = btn
        layout.addLayout(spicy_box)

        # 忌口偏好 (多选)
        lbl_pref = QLabel(u"附加避忌：")
        lbl_pref.setStyleSheet(f"font-size: 13px; color: {'#9CA3AF' if is_dark_mode else '#4B5563'}; border: none; background: transparent;")
        layout.addWidget(lbl_pref)

        pref_box = QHBoxLayout()
        pref_box.setSpacing(8)
        for p in [u"免蒜", u"免醋"]:
            btn = QPushButton(p)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background: {btn_bg}; color: {btn_fg}; border: 1px solid {btn_border}; border-radius: 8px; padding: 8px 14px; font-weight: bold; font-size: 14px; }}"
                "QPushButton:checked { background: #059669; color: white; border: 1px solid #10B981; }"
            )
            btn.clicked.connect(lambda checked, val=p: self._toggle_pref(val))
            pref_box.addWidget(btn)
        layout.addLayout(pref_box)

        # 确定按钮
        btn_confirm = QPushButton(u"确定加入订单")
        btn_confirm.setCursor(Qt.PointingHandCursor)
        btn_confirm.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #EA580C, stop:1 #C2410C); "
            "color: white; font-weight: bold; font-size: 15px; border-radius: 8px; min-height: 40px; margin-top: 6px; border: none; }"
            "QPushButton:hover { background: #EA580C; }"
        )
        btn_confirm.clicked.connect(self.accept)
        layout.addWidget(btn_confirm)

    def _select_spice(self, val):
        self.selected_spice = val
        for s, btn in self.spicy_btns.items():
            btn.setChecked(s == val)

    def _toggle_pref(self, val):
        if val in self.selected_prefs:
            self.selected_prefs.remove(val)
        else:
            self.selected_prefs.add(val)

    def get_tag_string(self):
        tags = [self.selected_spice] + sorted(list(self.selected_prefs))
        return " / ".join(tags) + " /"


class OrderItemCard(QFrame):
    """无边框极简 POS 风格订单细项卡片 (深浅主题自适应)"""

    def __init__(self, title, subline, price_val, tag="", is_dark=True, is_active=False, parent=None):
        super().__init__(parent)
        self.setObjectName("OrderItemCard")

        # 纯净无框，左右结构
        self.setStyleSheet(
            "QFrame#OrderItemCard { background: transparent; border: none; "
            "padding: 6px 2px; margin-bottom: 4px; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)

        left_vbox = QVBoxLayout()
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.setSpacing(3)

        title_col = "#F9FAFB" if is_dark else "#111827"
        sub_col = "#9CA3AF" if is_dark else "#4B5563"

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {title_col}; border: none; background: transparent;")
        left_vbox.addWidget(lbl_title)

        if subline:
            lbl_sub = QLabel(subline)
            lbl_sub.setStyleSheet(f"font-size: 13px; color: {sub_col}; font-family: 'Consolas', monospace; border: none; background: transparent;")
            left_vbox.addWidget(lbl_sub)

        if tag:
            lbl_tag = QLabel(tag)
            lbl_tag.setStyleSheet("font-size: 13px; font-weight: bold; color: #F59E0B; border: none; background: transparent;")
            left_vbox.addWidget(lbl_tag)

        layout.addLayout(left_vbox, stretch=1)

        # 右侧：右对齐高亮价格
        lbl_price = QLabel(f"￥{price_val:.2f}")
        lbl_price.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl_price.setStyleSheet("font-size: 18px; font-weight: 900; color: #EA580C; border: none; background: transparent;")
        layout.addWidget(lbl_price)


class MenuGridButton(QPushButton):
    """
    右侧菜单卡片按钮 — 深浅主题自适应
    """

    def __init__(self, key_id, title, subtitle, price, is_soup=False, is_dark_mode=True, parent=None):
        super().__init__(parent)
        self.key_id = key_id
        self.title_str = title
        self.subtitle_str = subtitle
        self.price_val = price
        self.is_soup = is_soup
        self.is_dark_mode = is_dark_mode
        self.count = 0

        self.setMinimumHeight(68)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        self.lbl_title = QLabel(title)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setWordWrap(True)
        layout.addWidget(self.lbl_title)

        if self.is_soup and subtitle:
            self.lbl_sub = QLabel(subtitle)
            self.lbl_sub.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.lbl_sub)
        else:
            self.lbl_sub = None

        self.lbl_badge = QLabel("", self)
        self.lbl_badge.setStyleSheet(
            "background: #DC2626; color: white; font-weight: bold; font-size: 11px; "
            "border-radius: 9px; padding: 1px 5px;"
        )
        self.lbl_badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lbl_badge.hide()

        self._update_style()

    def update_theme(self, is_dark_mode: bool):
        self.is_dark_mode = is_dark_mode
        self._update_style()

    def update_subtitle(self, new_subtitle: str):
        self.subtitle_str = new_subtitle
        if self.lbl_sub:
            self.lbl_sub.setText(new_subtitle)

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
        if self.is_soup:
            # ── 汤底专属高端暖色/亮橙样式 ──
            if self.count > 0:
                self.setStyleSheet(
                    "QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #EA580C, stop:1 #C2410C); "
                    "border: 2px solid #F97316; border-radius: 10px; }"
                    "QPushButton:hover { background: #EA580C; }"
                    "QLabel { color: #FFFFFF; font-size: 14px; font-weight: 900; background: transparent; border: none; }"
                )
            else:
                self.setStyleSheet(
                    "QPushButton { background: #FFF7ED; border: 2px solid #FDBA74; border-radius: 10px; }"
                    "QPushButton:hover { background: #FFEDD5; }"
                    "QLabel { color: #9A3412; font-size: 14px; font-weight: 900; background: transparent; border: none; }"
                )
        else:
            # ── 普通加价/饮料卡片 (深浅自适应) ──
            if self.is_dark_mode:
                if self.count > 0:
                    self.setStyleSheet(
                        "QPushButton { background: #1E293B; border: 2px solid #EA580C; border-radius: 10px; }"
                        "QPushButton:hover { background: #263352; }"
                        "QLabel { color: #F97316; font-size: 15px; font-weight: 900; background: transparent; border: none; }"
                    )
                else:
                    self.setStyleSheet(
                        "QPushButton { background: #172136; border: 1px solid #374151; border-radius: 10px; }"
                        "QPushButton:hover { background: #1E293B; }"
                        "QLabel { color: #F9FAFB; font-size: 15px; font-weight: bold; background: transparent; border: none; }"
                    )
            else:
                if self.count > 0:
                    self.setStyleSheet(
                        "QPushButton { background: #FFF7ED; border: 2px solid #EA580C; border-radius: 10px; }"
                        "QPushButton:hover { background: #FFEDD5; }"
                        "QLabel { color: #EA580C; font-size: 15px; font-weight: 900; background: transparent; border: none; }"
                    )
                else:
                    self.setStyleSheet(
                        "QPushButton { background: #FFFFFF; border: 2px solid #94A3B8; border-radius: 10px; }"
                        "QPushButton:hover { background: #F1F5F9; }"
                        "QLabel { color: #000000; font-size: 15px; font-weight: 900; background: transparent; border: none; }"
                    )


class SaleWidget(QWidget):
    """主销售界面 (双主题无缝适配)"""

    def __init__(self, config, db, call_mgr: CallNumberManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.db = db
        self.call_mgr = call_mgr
        self.printer = ReceiptPrinter(config)

        self.is_dark_mode = True
        self.current_weight = 0.0
        self._stable_weight = 0.0
        self._is_stable = False
        
        # 购物车项目列表
        self.cart_items = []
        self.menu_buttons = {}

        self.temp_order_no = self._gen_temp_order_no()
        self._detail_expanded = False

        self._build_ui()
        self._setup_scale()
        self.refresh_call_number_display()

    def update_theme(self, is_dark_mode: bool):
        """响应主题切换事件"""
        self.is_dark_mode = is_dark_mode
        for btn in self.menu_buttons.values():
            btn.update_theme(is_dark_mode)

        if hasattr(self, 'lbl_call_title'):
            c_text = "#9CA3AF" if is_dark_mode else "#111827"
            self.lbl_call_title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {c_text}; border: none; background: transparent;")
            self.lbl_item_count.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {c_text}; border: none; background: transparent;")
            self.lbl_mode_tip.setStyleSheet(f"color: {c_text}; font-size: 13px; border: none; background: transparent;")

            if is_dark_mode:
                self.btn_toggle_detail.setStyleSheet("background: #1E293B; color: #38BDF8; font-size: 13px; font-weight: bold; border-radius: 6px; padding: 4px 10px;")
            else:
                self.btn_toggle_detail.setStyleSheet("background: #E0F2FE; color: #0284C7; font-size: 13px; font-weight: bold; border-radius: 6px; padding: 4px 10px;")

        self._update_price_display()

    def _gen_temp_order_no(self):
        return "%05d" % random.randint(10000, 99999)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── 左侧：开单面板 ──
        left_card = QFrame()
        left_card.setObjectName("left_card_frame")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)

        # 1. 顶栏：本次打印叫号模块
        call_header = QHBoxLayout()
        
        self.lbl_call_title = QLabel(u"本次打印叫号：")
        self.lbl_call_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #9CA3AF; border: none;")
        call_header.addWidget(self.lbl_call_title)

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
        self.call_detail_box.setObjectName("call_detail_box")
        self.call_detail_box.setVisible(False)
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

        # 状态指示图标: ⏳ vs ✅
        self.lbl_scale_status_icon = QLabel(u"⏳")
        self.lbl_scale_status_icon.setToolTip(u"读数计算中...")
        self.lbl_scale_status_icon.setStyleSheet("font-size: 26px; border: none; background: transparent;")
        led_layout.addWidget(self.lbl_scale_status_icon)

        self.lbl_weight = QLabel("00.000 kg")
        self.lbl_weight.setStyleSheet(
            "font-size: 36px; font-weight: 900; color: #FFFFFF; border: none; background: transparent; "
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

        # ── 右侧：4x4 网格菜单 ──
        right = QVBoxLayout()
        right.setSpacing(12)

        menu_group = QGroupBox(u"请点选汤底与附加项目")
        mg_grid = QGridLayout(menu_group)
        mg_grid.setSpacing(8)

        unit_price = self.config.get("unit_price", 47.60)
        price_unit = self.config.get("price_unit", "per_jin")
        pu_lbl = price_unit_label(price_unit)

        # 菜单配置：三款汤底 + 打包盒 + 1-10元饮料
        menu_items_config = [
            (0, 0, "soup_1", u"经典草本骨汤", f"¥ {unit_price:.2f}/{pu_lbl}", unit_price, True),
            (0, 1, "soup_2", u"酸甜番茄汤", f"¥ {unit_price:.2f}/{pu_lbl}", unit_price, True),
            (0, 2, "soup_3", u"石磨醇香麻辣拌", f"¥ {unit_price:.2f}/{pu_lbl}", unit_price, True),
            (0, 3, "item_box", u"打包盒 (小)", "", 1.0, False),

            (1, 0, "item_1", u"1元饮料", "", 1.0, False),
            (1, 1, "item_2", u"2元饮料", "", 2.0, False),
            (1, 2, "item_3", u"3元饮料", "", 3.0, False),
            (1, 3, "item_4", u"4元饮料", "", 4.0, False),

            (2, 0, "item_5", u"5元饮料", "", 5.0, False),
            (2, 1, "item_6", u"6元饮料", "", 6.0, False),
            (2, 2, "item_7", u"7元饮料", "", 7.0, False),
            (2, 3, "item_8", u"8元饮料", "", 8.0, False),

            (3, 0, "item_9", u"9元饮料", "", 9.0, False),
            (3, 1, "item_10", u"10元饮料", "", 10.0, False),
        ]

        for r, c, key_id, title, sub, price, is_soup in menu_items_config:
            btn = MenuGridButton(key_id, title, sub, price, is_soup, self.is_dark_mode)
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
        unit_price = self.config.get("unit_price", 47.60)
        price_unit = self.config.get("price_unit", "per_jin")

        if btn.is_soup:
            # 弹出快捷口味选择框
            soup_clean_name = btn.title_str.replace("\n", " ")
            dlg = TasteSelectionDialog(soup_clean_name, is_dark_mode=self.is_dark_mode, parent=self)
            
            pos = btn.mapToGlobal(btn.rect().bottomLeft())
            dlg.move(pos.x(), pos.y() - dlg.height() - 10 if pos.y() + 200 > self.height() else pos.y())

            if dlg.exec_() == QDialog.Accepted:
                tag_str = dlg.get_tag_string()
                w = self.current_weight
                b_price = calculate_price(w, unit_price, price_unit)
                
                self.cart_items.append({
                    "type": "soup",
                    "key_id": btn.key_id,
                    "name": soup_clean_name,
                    "tag": tag_str,
                    "weight": w,
                    "price": b_price,
                    "unit_price": unit_price,
                    "price_unit": price_unit
                })
                btn.set_count(btn.count + 1)
        else:
            self.cart_items.append({
                "type": "item",
                "key_id": btn.key_id,
                "name": btn.title_str.replace("\n", " "),
                "tag": "",
                "price": btn.price_val
            })
            btn.set_count(btn.count + 1)

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

        pu_lbl = price_unit_label(self.config.get("price_unit", "per_jin"))
        total_price = 0.0
        total_items = len(self.cart_items)

        # 遍历渲染所有项目卡片
        for idx, item in enumerate(self.cart_items):
            is_last = (idx == len(self.cart_items) - 1)
            
            if item["type"] == "soup":
                w_str = f"{item['weight']:.3f}"
                sub_str = f"{w_str} kg   ¥{item['unit_price']:.2f}/{pu_lbl}   x{w_str}"
                card = OrderItemCard(item["name"], sub_str, price_val=item["price"], tag=item.get("tag", ""), is_dark=self.is_dark_mode, is_active=is_last)
                total_price += item["price"]
            else:
                sub_str = f"1   ¥{item['price']:.2f}   x1"
                card = OrderItemCard(item["name"], sub_str, price_val=item["price"], is_dark=self.is_dark_mode, is_active=is_last)
                total_price += item["price"]

            self.cart_layout.addWidget(card)

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
        unit_price = self.config.get("unit_price", 47.60)
        price_unit = self.config.get("price_unit", "per_jin")
        pu_lbl = price_unit_label(price_unit)
        sub_text = f"¥ {unit_price:.2f}/{pu_lbl}"

        for key_id in ["soup_1", "soup_2", "soup_3"]:
            btn = self.menu_buttons.get(key_id)
            if btn:
                btn.update_subtitle(sub_text)

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

        if abs(weight_kg - self._stable_weight) <= 0.005:
            self._is_stable = True
            self.lbl_scale_status_icon.setText(u"✅")
            self.lbl_scale_status_icon.setToolTip(u"读数稳定，可随时打印！")
        else:
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
        if not self.cart_items:
            QMessageBox.warning(self, u"提示", u"请先点选汤底或附加项目加入开单列表！")
            return

        unit_price = self.config.get("unit_price", 47.60)
        price_unit = self.config.get("price_unit", "per_jin")
        
        total_price = sum(item["price"] for item in self.cart_items)
        assigned_num = self.call_mgr.get_next_number()
        call_no_str = "%02d" % assigned_num

        items_summary = ", ".join(
            f"{item['name']}({item['tag']})" if item.get("tag") else item["name"]
            for item in self.cart_items
        )

        record = self.db.insert_sale(
            weight_kg=self.current_weight,
            unit_price=unit_price,
            price_unit=price_unit,
            total_price=total_price,
            remark=u"单号:%s 叫号:#%s 项目:%s" % (self.temp_order_no, call_no_str, items_summary)
        )

        sale_data = dict(record)
        sale_data["shop_name"] = self.config.get("shop_name", u"杨国福麻辣烫")
        sale_data["shop_subtitle"] = self.config.get("shop_subtitle", "")
        sale_data["receipt_footer"] = self.config.get("receipt_footer", u"谢谢惠顾！")
        sale_data["call_no"] = call_no_str
        sale_data["cart_items"] = self.cart_items

        success = self.printer.print_receipt(sale_data)

        if success:
            self._on_clear()
            self.refresh_call_number_display()
        else:
            QMessageBox.warning(self, u"打印失败", u"小票打印失败，请检查打印机连接！\n记录已保存。")

    def _on_clear(self):
        """清空购物车与所有按钮角标"""
        self.cart_items.clear()
        for b in self.menu_buttons.values():
            b.set_count(0)
        self.temp_order_no = self._gen_temp_order_no()
        self._update_price_display()

    def cleanup(self):
        if hasattr(self, 'scale'):
            self.scale.stop()
