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
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal

from core.calculator import calculate_price, weight_display, price_unit_label
from core.database import Database
from core.printer import ReceiptPrinter
from core.scale_reader import ScaleReader
from core.call_number_manager import CallNumberManager
from ui.custom_dialog import show_warning, show_info, show_question, get_int_input, ReceiptPreviewDialog


class TasteSelectionDialog(QDialog):
    """
    点击汤底时弹出的口味偏好对话框 (漫画对话框气泡尖尖箭头样式，即选即显无缝加购)
    """
    flavor_changed = pyqtSignal(str)

    def __init__(self, soup_name, is_dark_mode=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"选择口味 - {soup_name}")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.is_dark_mode = is_dark_mode
        self.arrow_direction = "up"
        self.arrow_x_offset = 60

        btn_bg = "#1F2937" if is_dark_mode else "#F3F4F6"
        btn_fg = "#D1D5DB" if is_dark_mode else "#374151"
        btn_border = "#374151" if is_dark_mode else "#D1D5DB"

        self.setStyleSheet("QDialog { background: transparent; }")

        # 草本骨汤不提供“不辣”
        if "草本骨汤" in soup_name:
            self.spicy_options = [u"微辣", u"中辣", u"重辣"]
            self.selected_spice = "微辣"
        else:
            self.spicy_options = [u"不辣", u"微辣", u"中辣", u"重辣"]
            self.selected_spice = "微辣"

        self.selected_prefs = set()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(18, 26, 18, 18)

        # 辣度选择 (单选)
        lbl_spicy = QLabel(u"辣度偏好：")
        lbl_spicy.setStyleSheet(f"font-size: 13px; color: {'#9CA3AF' if is_dark_mode else '#4B5563'}; border: none; background: transparent;")
        self.main_layout.addWidget(lbl_spicy)

        spicy_box = QHBoxLayout()
        spicy_box.setSpacing(8)
        self.spicy_btns = {}
        for s in self.spicy_options:
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
        self.main_layout.addLayout(spicy_box)

        # 忌口偏好 (多选)
        lbl_pref = QLabel(u"附加避忌：")
        lbl_pref.setStyleSheet(f"font-size: 13px; color: {'#9CA3AF' if is_dark_mode else '#4B5563'}; border: none; background: transparent;")
        self.main_layout.addWidget(lbl_pref)

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
        self.main_layout.addLayout(pref_box)

    def _select_spice(self, val):
        self.selected_spice = val
        for s, btn in self.spicy_btns.items():
            btn.setChecked(s == val)
        self.flavor_changed.emit(self.get_tag_string())

    def _toggle_pref(self, val):
        if val in self.selected_prefs:
            self.selected_prefs.remove(val)
        else:
            self.selected_prefs.add(val)
        self.flavor_changed.emit(self.get_tag_string())

    def update_layout_margins(self):
        if self.arrow_direction == "up":
            self.main_layout.setContentsMargins(18, 28, 18, 18)
        else:
            self.main_layout.setContentsMargins(18, 18, 18, 28)

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_col = QColor("#111827" if self.is_dark_mode else "#FFFFFF")
        border_col = QColor("#EA580C")

        w = float(self.width())
        h = float(self.height())
        arrow_h = 12.0
        arrow_w = 16.0
        radius = 12.0
        arrow_x = max(radius + arrow_w, min(w - radius - arrow_w, float(self.arrow_x_offset)))

        path = QPainterPath()

        if self.arrow_direction == "up":
            top = arrow_h + 2.0
            bottom = h - 2.0
            left = 2.0
            right = w - 2.0

            path.moveTo(left + radius, top)
            path.lineTo(arrow_x - arrow_w / 2.0, top)
            path.lineTo(arrow_x, 2.0)
            path.lineTo(arrow_x + arrow_w / 2.0, top)
            path.lineTo(right - radius, top)
            path.arcTo(right - radius * 2.0, top, radius * 2.0, radius * 2.0, 90, -90)
            path.lineTo(right, bottom - radius)
            path.arcTo(right - radius * 2.0, bottom - radius * 2.0, radius * 2.0, radius * 2.0, 0, -90)
            path.lineTo(left + radius, bottom)
            path.arcTo(left, bottom - radius * 2.0, radius * 2.0, radius * 2.0, 270, -90)
            path.lineTo(left, top + radius)
            path.arcTo(left, top, radius * 2.0, radius * 2.0, 180, -90)
            path.closeSubpath()
        else:
            top = 2.0
            bottom = h - arrow_h - 2.0
            left = 2.0
            right = w - 2.0

            path.moveTo(left + radius, top)
            path.lineTo(right - radius, top)
            path.arcTo(right - radius * 2.0, top, radius * 2.0, radius * 2.0, 90, -90)
            path.lineTo(right, bottom - radius)
            path.arcTo(right - radius * 2.0, bottom - radius * 2.0, radius * 2.0, radius * 2.0, 0, -90)
            path.lineTo(arrow_x + arrow_w / 2.0, bottom)
            path.lineTo(arrow_x, h - 2.0)
            path.lineTo(arrow_x - arrow_w / 2.0, bottom)
            path.lineTo(left + radius, bottom)
            path.arcTo(left, bottom - radius * 2.0, radius * 2.0, radius * 2.0, 270, -90)
            path.lineTo(left, top + radius)
            path.arcTo(left, top, radius * 2.0, radius * 2.0, 180, -90)
            path.closeSubpath()

        painter.setBrush(QBrush(bg_col))
        painter.setPen(QPen(border_col, 2))
        painter.drawPath(path)

    def _select_spice(self, val):
        self.selected_spice = val
        for s, btn in self.spicy_btns.items():
            btn.setChecked(s == val)
        self.flavor_changed.emit(self.get_tag_string())

    def _toggle_pref(self, val):
        if val in self.selected_prefs:
            self.selected_prefs.remove(val)
        else:
            self.selected_prefs.add(val)
        self.flavor_changed.emit(self.get_tag_string())

    def get_tag_string(self):
        tags = [self.selected_spice] + sorted(list(self.selected_prefs))
        return " / ".join(tags)


class OrderItemCard(QFrame):
    """无边框极简 POS 风格订单细项卡片 (深浅主题自适应，支持选中高亮与点击选择)"""
    clicked = pyqtSignal(int)

    def __init__(self, index, title, subline, price_val, tag="", discount_rate=1.0, is_dark=True, is_active=False, parent=None):
        super().__init__(parent)
        self.index = index
        self.setObjectName("OrderItemCard")
        self.setCursor(Qt.PointingHandCursor)

        # 选中高亮状态样式
        if is_active:
            bg_style = "background: rgba(249, 115, 22, 0.18); border: 1.5px solid #F97316; border-radius: 8px;"
        else:
            bg_style = "background: transparent; border: 1px solid transparent; border-radius: 8px;"

        self.setStyleSheet(
            f"QFrame#OrderItemCard {{ {bg_style} padding: 6px 8px; margin-bottom: 2px; }}"
            "QFrame#OrderItemCard:hover { background: rgba(255, 255, 255, 0.06); }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
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

        # 组合口味标签与折扣标签
        tag_parts = []
        if tag:
            tag_parts.append(tag)
        if discount_rate < 0.999:
            disc_num = discount_rate * 10.0
            disc_str = f"[{disc_num:.1f}折]".replace(".0折", "折")
            tag_parts.append(disc_str)

        full_tag_str = "   ".join(tag_parts)

        if full_tag_str:
            lbl_tag = QLabel(full_tag_str)
            lbl_tag.setStyleSheet("font-size: 13px; font-weight: bold; color: #F59E0B; border: none; background: transparent;")
            left_vbox.addWidget(lbl_tag)

        layout.addLayout(left_vbox, stretch=1)

        # 右侧：高亮价格
        lbl_price = QLabel(f"￥{price_val:.2f}")
        lbl_price.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl_price.setStyleSheet("font-size: 18px; font-weight: 900; color: #EA580C; border: none; background: transparent;")
        layout.addWidget(lbl_price)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)


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
        
        # 购物车项目列表与选中项目索引
        self.cart_items = []
        self.selected_item_index = -1
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
        self.lbl_call_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #9CA3AF; border: none; background: transparent; padding: 0px;")
        call_header.addWidget(self.lbl_call_title)

        self.lbl_next_call_no = QLabel("# 50")
        self.lbl_next_call_no.setStyleSheet("font-size: 26px; font-weight: 900; color: #F97316; border: none; background: transparent; padding: 0px;")
        call_header.addWidget(self.lbl_next_call_no)

        self.btn_toggle_detail = QPushButton(u"详细信息 ∨")
        self.btn_toggle_detail.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_detail.setStyleSheet(
            "background: transparent; color: #38BDF8; font-size: 13px; font-weight: bold; border: none; padding: 0px 6px;"
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
        self.lbl_scale_status_icon.setStyleSheet("font-size: 24px; font-weight: bold; color: #FEF08A; border: none; background: transparent;")
        led_layout.addWidget(self.lbl_scale_status_icon)

        self.lbl_weight = QLabel("00.000 kg")
        self.lbl_weight.setStyleSheet(
            "font-size: 36px; font-weight: 900; color: #FFFFFF; border: none; background: transparent; "
            "font-family: 'Segoe UI', 'Consolas', sans-serif; letter-spacing: 1px;"
        )
        led_layout.addWidget(self.lbl_weight, stretch=1, alignment=Qt.AlignRight)

        left_layout.addWidget(led_banner)

        # 2. 订单消费卡片列表 (ScrollArea)
        self.cart_scroll = QScrollArea()
        self.cart_scroll.setWidgetResizable(True)
        self.cart_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cart_container = QWidget()
        self.cart_layout = QVBoxLayout(self.cart_container)
        self.cart_layout.setContentsMargins(0, 0, 0, 0)
        self.cart_layout.setSpacing(6)
        self.cart_layout.setAlignment(Qt.AlignTop)

        self.cart_scroll.setWidget(self.cart_container)
        left_layout.addWidget(self.cart_scroll, stretch=1)

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

        # ── 中间：快捷操作工具栏 (折扣、增减数量、删除) ──
        mid_bar = QFrame()
        mid_bar.setObjectName("QuickOpBar")
        mid_bar.setStyleSheet(
            "QFrame#QuickOpBar { background: #1E293B; border-radius: 10px; padding: 4px; border: 1px solid #334155; }"
        )
        mid_layout = QVBoxLayout(mid_bar)
        mid_layout.setContentsMargins(6, 12, 6, 12)
        mid_layout.setSpacing(10)
        mid_layout.setAlignment(Qt.AlignCenter)

        lbl_ops_title = QLabel(u"快捷\n操作")
        lbl_ops_title.setAlignment(Qt.AlignCenter)
        lbl_ops_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #9CA3AF; border: none; background: transparent; margin-bottom: 4px;")
        mid_layout.addWidget(lbl_ops_title)

        # 折扣按钮: 9.5折, 8.8折, 8折 (点击二次可反选恢复原价)
        self.discount_btns = {}
        discounts = [(0.95, "9.5折"), (0.88, "8.8折"), (0.80, "8折")]
        for rate, label_text in discounts:
            btn_d = QPushButton(label_text)
            btn_d.setCursor(Qt.PointingHandCursor)
            btn_d.setStyleSheet(
                "QPushButton { background: #334155; color: #F59E0B; font-weight: bold; font-size: 13px; border-radius: 6px; padding: 8px 4px; min-width: 50px; border: 1px solid #475569; }"
                "QPushButton:hover { background: #F59E0B; color: #1E293B; border: 1px solid #F59E0B; }"
            )
            btn_d.clicked.connect(lambda checked, r=rate: self._apply_discount_to_selected(r))
            mid_layout.addWidget(btn_d)
            self.discount_btns[rate] = btn_d

        mid_layout.addSpacing(6)

        # 数量加减与删除按钮: +, -, 删
        btn_plus = QPushButton("＋")
        btn_plus.setCursor(Qt.PointingHandCursor)
        btn_plus.setToolTip(u"增加数量 (+1)")
        btn_plus.setStyleSheet(
            "QPushButton { background: #064E3B; color: #34D399; font-weight: 900; font-size: 18px; border-radius: 6px; padding: 8px 4px; min-width: 50px; border: 1px solid #059669; }"
            "QPushButton:hover { background: #059669; color: #FFFFFF; }"
        )
        btn_plus.clicked.connect(self._increase_selected_qty)
        mid_layout.addWidget(btn_plus)

        btn_minus = QPushButton("－")
        btn_minus.setCursor(Qt.PointingHandCursor)
        btn_minus.setToolTip(u"减少数量 (-1)")
        btn_minus.setStyleSheet(
            "QPushButton { background: #78350F; color: #FBBF24; font-weight: 900; font-size: 18px; border-radius: 6px; padding: 8px 4px; min-width: 50px; border: 1px solid #D97706; }"
            "QPushButton:hover { background: #D97706; color: #FFFFFF; }"
        )
        btn_minus.clicked.connect(self._decrease_selected_qty)
        mid_layout.addWidget(btn_minus)

        mid_layout.addSpacing(6)

        btn_delete = QPushButton("删")
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.setToolTip(u"删除选中项目")
        btn_delete.setStyleSheet(
            "QPushButton { background: #7F1D1D; color: #F87171; font-weight: bold; font-size: 14px; border-radius: 6px; padding: 10px 4px; min-width: 50px; border: 1px solid #DC2626; }"
            "QPushButton:hover { background: #DC2626; color: #FFFFFF; }"
        )
        btn_delete.clicked.connect(self._delete_selected_item)
        mid_layout.addWidget(btn_delete)

        mid_layout.addStretch()

        layout.addWidget(left_card, stretch=5)
        layout.addWidget(mid_bar, stretch=0)

        # ── 右侧：4x4 网格菜单 ──
        right = QVBoxLayout()
        right.setSpacing(12)

        menu_group = QGroupBox("")
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

        self.btn_print = QPushButton(u"确认收款")
        self.btn_print.setObjectName("btn_print")
        self.btn_print.setCursor(Qt.PointingHandCursor)
        self.btn_print.clicked.connect(self._on_print)
        btn_box.addWidget(self.btn_print, stretch=2)

        right.addLayout(btn_box)

        layout.addLayout(right, stretch=7)

        self._update_price_display()

    def _on_menu_click(self, btn: MenuGridButton):
        """点击右侧菜单按钮"""
        unit_price = self.config.get("unit_price", 47.60)
        price_unit = self.config.get("price_unit", "per_jin")

        if btn.is_soup:
            if self.current_weight <= 0.0005:
                show_warning(self, u"请先称重", u"当前电子秤读数为 0.000 kg，请先将麻辣烫放置在电子秤上！")
                return

            soup_clean_name = btn.title_str.replace("\n", " ")
            dlg = TasteSelectionDialog(soup_clean_name, is_dark_mode=self.is_dark_mode, parent=self)
            
            w = self.current_weight
            b_price = calculate_price(w, unit_price, price_unit)
            
            # 1. 点击汤底卡片，无需二次确认，即刻加入订单列表
            item_entry = {
                "type": "soup",
                "key_id": btn.key_id,
                "name": soup_clean_name,
                "tag": dlg.get_tag_string(),
                "weight": w,
                "base_price": b_price,
                "price": b_price,
                "unit_price": unit_price,
                "price_unit": price_unit,
                "qty": 1,
                "discount_rate": 1.0
            }
            self.cart_items.append(item_entry)
            self.selected_item_index = len(self.cart_items) - 1
            btn.set_count(btn.count + 1)
            self._update_price_display()

            # 2. 实时响应辣度/避忌按钮，点击即刻刷新卡片标签
            def update_flavor(new_tag):
                item_entry["tag"] = new_tag
                self._update_price_display()

            dlg.flavor_changed.connect(update_flavor)

            # 3. 智能精准定位气泡弹窗
            dlg.adjustSize()
            dlg_w = dlg.width()
            dlg_h = dlg.height()

            btn_rect = btn.rect()
            top_left = btn.mapToGlobal(btn_rect.topLeft())
            bottom_right = btn.mapToGlobal(btn_rect.bottomRight())
            btn_center_x = top_left.x() + btn_rect.width() / 2

            win = self.window()
            win_rect = win.geometry()
            win_right = win_rect.x() + win_rect.width()
            win_bottom = win_rect.y() + win_rect.height()

            target_x = top_left.x()
            if target_x + dlg_w > win_right - 12:
                target_x = bottom_right.x() - dlg_w
            if target_x < win_rect.x() + 12:
                target_x = win_rect.x() + 12

            if bottom_right.y() + 6 + dlg_h <= win_bottom - 12:
                target_y = bottom_right.y() + 4
                dlg.arrow_direction = "up"
            else:
                target_y = top_left.y() - dlg_h - 4
                dlg.arrow_direction = "down"

            dlg.arrow_x_offset = int(btn_center_x - target_x)
            dlg.update_layout_margins()
            dlg.adjustSize()
            dlg.move(target_x, target_y)

            dlg.exec_()
        else:
            item_entry = {
                "type": "item",
                "key_id": btn.key_id,
                "name": btn.title_str.replace("\n", " "),
                "tag": "",
                "base_price": btn.price_val,
                "price": btn.price_val,
                "qty": 1,
                "discount_rate": 1.0
            }
            self.cart_items.append(item_entry)
            self.selected_item_index = len(self.cart_items) - 1
            btn.set_count(btn.count + 1)
            self._update_price_display()

    def _select_cart_item(self, index):
        """选择指定的订单卡片"""
        if 0 <= index < len(self.cart_items):
            self.selected_item_index = index
            self._update_price_display()

    def _apply_discount_to_selected(self, rate):
        """对选中的订单项应用或反选折扣 (如再点一次同折扣则恢复原价 1.0)"""
        if 0 <= self.selected_item_index < len(self.cart_items):
            item = self.cart_items[self.selected_item_index]
            cur_rate = item.get("discount_rate", 1.0)
            
            # 如果当前已经应用了该折扣，再次点击则反选恢复原价 (1.0)
            if abs(cur_rate - rate) < 0.001:
                new_rate = 1.0
            else:
                new_rate = rate

            item["discount_rate"] = new_rate
            item["price"] = item["base_price"] * item.get("qty", 1) * new_rate
            self._update_price_display()

    def _increase_selected_qty(self):
        """增加选中项数量 (+1，汤底不可加减量)"""
        if 0 <= self.selected_item_index < len(self.cart_items):
            item = self.cart_items[self.selected_item_index]
            if item.get("type") == "soup":
                return
            item["qty"] = item.get("qty", 1) + 1
            item["price"] = item["base_price"] * item["qty"] * item.get("discount_rate", 1.0)
            self._update_price_display()

    def _decrease_selected_qty(self):
        """减少选中项数量 (-1，汤底不可加减量)"""
        if 0 <= self.selected_item_index < len(self.cart_items):
            item = self.cart_items[self.selected_item_index]
            if item.get("type") == "soup":
                return
            cur_qty = item.get("qty", 1)
            if cur_qty > 1:
                item["qty"] = cur_qty - 1
                item["price"] = item["base_price"] * item["qty"] * item.get("discount_rate", 1.0)
            else:
                self._delete_selected_item()
                return
            self._update_price_display()

    def _delete_selected_item(self):
        """删除选中的订单项 (支持删除任意选中项，包括汤底)"""
        if 0 <= self.selected_item_index < len(self.cart_items):
            removed = self.cart_items.pop(self.selected_item_index)
            
            # 更新右侧菜单按钮角标计数
            key_id = removed.get("key_id")
            if key_id and key_id in self.menu_buttons:
                btn = self.menu_buttons[key_id]
                btn.set_count(max(0, btn.count - 1))

            if self.cart_items:
                self.selected_item_index = min(self.selected_item_index, len(self.cart_items) - 1)
            else:
                self.selected_item_index = -1

            self._update_price_display()

    def _toggle_call_detail(self):
        self._detail_expanded = not self._detail_expanded
        self.call_detail_box.setVisible(self._detail_expanded)
        if self._detail_expanded:
            self.btn_toggle_detail.setText(u"详细信息 ∧")
        else:
            self.btn_toggle_detail.setText(u"详细信息 ∨")

    def _update_price_display(self):
        """刷新购物明细卡片列表与金额 (即刻清理旧组件并强刷新UI)"""
        from PyQt5.QtCore import QCoreApplication

        while self.cart_layout.count() > 0:
            child = self.cart_layout.takeAt(0)
            if child.widget():
                w = child.widget()
                w.setParent(None)
                w.deleteLater()

        pu_lbl = price_unit_label(self.config.get("price_unit", "per_jin"))
        total_price = 0.0
        total_items = 0

        # 获取当前选中项的折扣状态，更新折扣按钮高亮
        cur_selected_rate = 1.0
        if 0 <= self.selected_item_index < len(self.cart_items):
            cur_selected_rate = self.cart_items[self.selected_item_index].get("discount_rate", 1.0)

        for rate, btn in getattr(self, 'discount_btns', {}).items():
            if abs(cur_selected_rate - rate) < 0.001:
                btn.setStyleSheet(
                    "QPushButton { background: #EA580C; color: #FFFFFF; font-weight: bold; font-size: 13px; border-radius: 6px; padding: 8px 4px; min-width: 50px; border: 1px solid #F97316; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { background: #334155; color: #F59E0B; font-weight: bold; font-size: 13px; border-radius: 6px; padding: 8px 4px; min-width: 50px; border: 1px solid #475569; }"
                    "QPushButton:hover { background: #F59E0B; color: #1E293B; border: 1px solid #F59E0B; }"
                )

        # 遍历渲染所有项目卡片
        for idx, item in enumerate(self.cart_items):
            is_selected = (idx == self.selected_item_index)
            qty = item.get("qty", 1)
            disc_rate = item.get("discount_rate", 1.0)
            total_items += qty

            if item["type"] == "soup":
                w_str = f"{item['weight']:.3f}"
                sub_str = f"{w_str} kg   ¥{item['unit_price']:.2f}/{pu_lbl}   x{qty}"
            else:
                sub_str = f"¥{item['base_price']:.2f}   x{qty}"

            card = OrderItemCard(
                index=idx,
                title=item["name"],
                subline=sub_str,
                price_val=item["price"],
                tag=item.get("tag", ""),
                discount_rate=disc_rate,
                is_dark=self.is_dark_mode,
                is_active=is_selected
            )
            card.clicked.connect(self._select_cart_item)
            total_price += item["price"]
            self.cart_layout.addWidget(card)

        self.lbl_item_count.setText(u"共 %d 件，需付款：" % total_items)
        self.lbl_price.setText(u"￥%.2f" % total_price)
        QCoreApplication.processEvents()
        if hasattr(self, 'cart_scroll'):
            self.cart_scroll.verticalScrollBar().setValue(self.cart_scroll.verticalScrollBar().maximum())

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
        curr = self.call_mgr.peek_next_number()
        val, ok = get_int_input(self, u"微调叫号", u"请输入本次叫号牌号码：", curr, 1, 9999)
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
            self.lbl_scale_status_icon.setText(u"✔")
            self.lbl_scale_status_icon.setStyleSheet("font-size: 28px; font-weight: 900; color: #10B981; border: none; background: transparent;")
            self.lbl_scale_status_icon.setToolTip(u"读数稳定，可随时打印！")
        else:
            self._is_stable = False
            self._stable_weight = weight_kg
            self.lbl_scale_status_icon.setText(u"⏳")
            self.lbl_scale_status_icon.setStyleSheet("font-size: 24px; font-weight: bold; color: #FEF08A; border: none; background: transparent;")
            self.lbl_scale_status_icon.setToolTip(u"读数计算/变动中...")

    @pyqtSlot(bool, str)
    def _on_status_change(self, connected, msg):
        if not connected:
            self.lbl_scale_status_icon.setText(u"✕")
            self.lbl_scale_status_icon.setStyleSheet("font-size: 26px; font-weight: bold; color: #EF4444; border: none; background: transparent;")
            self.lbl_scale_status_icon.setToolTip(u"官方秤未连接: %s" % msg)

    @pyqtSlot(float)
    def _on_weight_stable(self, weight_kg):
        self._is_stable = True
        self._stable_weight = weight_kg
        self.lbl_scale_status_icon.setText(u"✔")
        self.lbl_scale_status_icon.setStyleSheet("font-size: 28px; font-weight: 900; color: #10B981; border: none; background: transparent;")
        self.lbl_scale_status_icon.setToolTip(u"重量已稳定，可随时打印！")

    @pyqtSlot(str)
    def _on_error(self, msg):
        self.lbl_scale_status_icon.setText(u"✕")
        self.lbl_scale_status_icon.setStyleSheet("font-size: 26px; font-weight: bold; color: #EF4444; border: none; background: transparent;")
        self.lbl_scale_status_icon.setToolTip(u"错误: %s" % msg)

    def _on_print(self):
        """确认收款 -> 弹出模拟小票预览与 10s 倒计时 -> 确认/到期打票"""
        if not self.cart_items:
            show_warning(self, u"提示", u"请先点选汤底或附加项目加入开单列表！")
            return

        unit_price = self.config.get("unit_price", 47.60)
        price_unit = self.config.get("price_unit", "per_jin")
        
        total_price = sum(item["price"] for item in self.cart_items)
        peek_num = self.call_mgr.peek_next_number()
        call_no_str = "%02d" % peek_num

        items_summary = ", ".join(
            f"{item['name']}({item['tag']})" if item.get("tag") else item["name"]
            for item in self.cart_items
        )

        sale_data = {
            "shop_name": self.config.get("shop_name", u"杨国福麻辣烫"),
            "shop_subtitle": self.config.get("shop_subtitle", ""),
            "receipt_footer": self.config.get("receipt_footer", u"谢谢惠顾！"),
            "call_no": call_no_str,
            "cart_items": self.cart_items,
            "weight_kg": self.current_weight,
            "unit_price": unit_price,
            "price_unit": price_unit,
            "total_price": total_price,
            "temp_order_no": self.temp_order_no,
            "remark": u"单号:%s 叫号:#%s 项目:%s" % (self.temp_order_no, call_no_str, items_summary)
        }

        # 1. 弹出模拟小票框框 (含取消打票 / 立即打票 / 10s 倒计时)
        dlg = ReceiptPreviewDialog(sale_data, countdown_sec=10, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            # 2. 确认打票：正式消费叫号、记录数据库与驱动硬件打票
            actual_num = self.call_mgr.get_next_number()
            sale_data["call_no"] = "%02d" % actual_num

            record = self.db.insert_sale(
                weight_kg=self.current_weight,
                unit_price=unit_price,
                price_unit=price_unit,
                total_price=total_price,
                remark=u"单号:%s 叫号:#%s 项目:%s" % (self.temp_order_no, sale_data["call_no"], items_summary)
            )

            full_sale = dict(record)
            full_sale.update(sale_data)

            success = self.printer.print_receipt(full_sale)

            if success:
                self._on_clear()
                self.refresh_call_number_display()
            else:
                show_warning(self, u"打印失败", u"小票打印失败，请检查打印机连接！\n记录已保存。")

    def _on_clear(self):
        """清空购物车与所有按钮角标"""
        self.cart_items.clear()
        self.selected_item_index = -1
        for b in self.menu_buttons.values():
            b.set_count(0)
        self.temp_order_no = self._gen_temp_order_no()
        self._update_price_display()

    def cleanup(self):
        if hasattr(self, 'scale'):
            self.scale.stop()
