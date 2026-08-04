"""
销售/称重界面 — 全面支持【曜石黑 / 极简光亮】双主题动态自适应
PyQt5 + Python 3.8 兼容
"""
import random
import time
import uuid
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QSpinBox, QCheckBox, QGridLayout, QGroupBox,
    QScrollArea, QDialog, QLineEdit, QComboBox, QListView
)
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal, QTimer, QPoint
from PyQt5.QtGui import QPainter, QPolygon, QFontMetrics

from core.calculator import calculate_price, weight_display, price_unit_label
from core.database import Database
from core.printer import ReceiptPrinter
from core.scale_reader import ScaleReader
from core.call_number_manager import CallNumberManager
from core.order_draft import clear_draft, load_draft, save_draft
from ui.custom_dialog import show_warning, show_info, show_question, get_int_input, ReceiptPreviewDialog
from core.app_logger import log_event, CAT_USER, CAT_PRINT, CAT_ORDER, CAT_SYSTEM


class MockWeightModeComboBox(QComboBox):
    """Compact touch selector with its arrow immediately after the text."""

    def paintEvent(self, event):
        super().paintEvent(event)
        text = self.currentText()
        if not text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        metrics = QFontMetrics(self.font())
        # Keep the indicator beside the final character instead of reserving
        # a wide right-hand drop-down column that squeezes the kg display.
        x = min(12 + metrics.horizontalAdvance(text) + 6, self.width() - 14)
        y = self.height() // 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.palette().text().color())
        painter.drawPolygon(QPolygon([QPoint(x, y - 3), QPoint(x + 8, y - 3), QPoint(x + 4, y + 4)]))
        painter.end()


class ClickableWeightLabel(QLabel):
    """Touch-friendly weight display that can act as the mock input target."""

    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ManualWeightDialog(QDialog):
    """Large on-screen keypad for entering simulated scale weight in kg."""

    def __init__(self, initial_kg=0.0, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.weight_kg = 0.0
        self._digits = ""

        card = QFrame(self)
        card.setObjectName("ManualWeightCard")
        card.setStyleSheet(
            "QFrame#ManualWeightCard { background: #1E293B; border: 2px solid #8B5CF6; border-radius: 18px; }"
            "QLabel { border: none; background: transparent; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.addWidget(card)

        body = QVBoxLayout(card)
        body.setContentsMargins(24, 22, 24, 22)
        body.setSpacing(12)

        title = QLabel(u"输入模拟称重")
        title.setStyleSheet("color: #F8FAFC; font-size: 22px; font-weight: 900;")
        title.setAlignment(Qt.AlignCenter)
        body.addWidget(title)

        hint = QLabel(u"单位：千克（kg），按数字从右向左累加，例如 5-0-0 = 0.500")
        hint.setStyleSheet("color: #CBD5E1; font-size: 14px;")
        hint.setAlignment(Qt.AlignCenter)
        body.addWidget(hint)

        self.display = QLineEdit()
        self.display.setReadOnly(True)
        self.display.setText("0.000")
        self.display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.display.setMinimumHeight(66)
        self.display.setStyleSheet(
            "QLineEdit { background: #0F172A; color: #DDD6FE; border: 2px solid #8B5CF6; "
            "border-radius: 10px; padding: 6px 14px; font-size: 32px; font-weight: 900; "
            "font-family: 'Consolas', monospace; }"
        )
        body.addWidget(self.display)

        grid = QGridLayout()
        grid.setSpacing(8)
        keys = (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9"), ("清空", "0", "⌫"))
        for row, values in enumerate(keys):
            for col, key in enumerate(values):
                button = QPushButton(key)
                button.setMinimumHeight(58)
                button.setFocusPolicy(Qt.NoFocus)
                button.setStyleSheet(
                    "QPushButton { background: #334155; color: #F8FAFC; border: 1px solid #475569; "
                    "border-radius: 10px; font-size: 22px; font-weight: 900; }"
                    "QPushButton:pressed { background: #7C3AED; }"
                )
                button.clicked.connect(lambda _checked=False, value=key: self._press(value))
                grid.addWidget(button, row, col)
        body.addLayout(grid)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        cancel = QPushButton(u"取消")
        confirm = QPushButton(u"确认使用")
        for button in (cancel, confirm):
            button.setMinimumHeight(58)
            button.setFocusPolicy(Qt.NoFocus)
        cancel.setStyleSheet(
            "QPushButton { background: #475569; color: #F8FAFC; border-radius: 10px; font-size: 17px; font-weight: bold; }"
        )
        confirm.setStyleSheet(
            "QPushButton { background: #059669; color: #FFFFFF; border-radius: 10px; font-size: 17px; font-weight: bold; }"
        )
        cancel.clicked.connect(self.reject)
        confirm.clicked.connect(self._confirm)
        actions.addWidget(cancel)
        actions.addWidget(confirm)
        body.addLayout(actions)
        self.resize(430, 610)

        # Weight entry follows a scale keypad: digits are appended from the
        # right in grams.  1 -> 0.001 kg, then 1 -> 0.011 kg, etc.

    def _press(self, key):
        text = self.display.text()
        if key == "清空":
            self._digits = ""
            self.display.setText("0.000")
            return
        if key == "⌫":
            self._digits = self._digits[:-1]
            self._refresh_display()
            return
        if not key.isdigit() or len(self._digits) >= 4:
            return
        self._digits += key
        self._refresh_display()

    def _refresh_display(self):
        grams = int(self._digits or "0")
        self.display.setText("%.3f" % (grams / 1000.0))

    def _confirm(self):
        try:
            value = int(self._digits or "0") / 1000.0
        except (TypeError, ValueError):
            value = 0.0
        if value <= 0 or value > 9.999:
            return
        self.weight_kg = round(value, 3)
        self.accept()


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
            self.spicy_options = [u"微辣", u"原汤", u"中辣", u"重辣"]
        else:
            self.spicy_options = [u"不辣", u"微辣", u"原汤", u"中辣", u"重辣"]

        self.selected_spice = ""
        self.selected_prefs = set()
        self.extra_tags = set()
        
        from PyQt5.QtCore import QTimer
        self.auto_close_timer = QTimer(self)
        self.auto_close_timer.setSingleShot(True)
        self.auto_close_timer.timeout.connect(self.accept)

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

        self.pref_btns = {}
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
            self.pref_btns[p] = btn
        self.main_layout.addLayout(pref_box)

    def set_initial_tag(self, tag_str):
        """解析已有 tag 字符串 (如 '微辣 / 免蒜') 并恢复勾选状态"""
        self.selected_spice = ""
        self.selected_prefs.clear()
        self.extra_tags.clear()
        for b in self.spicy_btns.values():
            b.setChecked(False)
        for b in self.pref_btns.values():
            b.setChecked(False)

        if not tag_str:
            return
        parts = [p.strip() for p in tag_str.split("/") if p.strip()]
        for p in parts:
            if p in self.spicy_options:
                self.selected_spice = p
                for s, b in self.spicy_btns.items():
                    b.setChecked(s == p)
            elif p in self.pref_btns:
                self.selected_prefs.add(p)
                self.pref_btns[p].setChecked(True)
            else:
                self.extra_tags.add(p)

    def _select_spice(self, val):
        if self.selected_spice == val:
            self.selected_spice = ""
        else:
            self.selected_spice = val
        for s, btn in self.spicy_btns.items():
            btn.setChecked(s == self.selected_spice)
        self.flavor_changed.emit(self.get_tag_string())
        self._reset_auto_close_timer()

    def _toggle_pref(self, val):
        if val in self.selected_prefs:
            self.selected_prefs.remove(val)
        else:
            self.selected_prefs.add(val)
        self.flavor_changed.emit(self.get_tag_string())
        self._reset_auto_close_timer()
        
    def _reset_auto_close_timer(self):
        self.auto_close_timer.start(1500)

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


    def get_tag_string(self):
        tags = []
        if self.selected_spice:
            tags.append(self.selected_spice)
        tags.extend(sorted(list(self.selected_prefs)))
        if hasattr(self, 'extra_tags') and self.extra_tags:
            tags.extend(sorted(list(self.extra_tags)))
        return " / ".join(tags)


class TakeoutLabel(QLabel):
    clicked = pyqtSignal()
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAlignment(Qt.AlignCenter)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()

class OrderItemCard(QFrame):
    """无边框极简 POS 风格订单细项卡片 (深浅主题自适应，支持选中高亮与点击选择)"""
    clicked = pyqtSignal(int)
    takeout_clicked = pyqtSignal(int)

    def __init__(self, index, title, subline, price_val, tag="", discount_rate=1.0, is_dark=True, is_active=False, is_soup=False, parent=None):
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
            f"QFrame#OrderItemCard {{ {bg_style} padding: 4px 6px; margin-bottom: 1px; }}"
            "QFrame#OrderItemCard:hover { background: rgba(255, 255, 255, 0.06); }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(6)

        # 1. 最左侧：清晰不易混淆的第几项序号徽章 (如 #1, #2, #3...)
        lbl_badge = QLabel(f"#{index + 1}")
        lbl_badge.setAlignment(Qt.AlignCenter)
        badge_bg = "#EA580C" if is_active else "#334155"
        lbl_badge.setStyleSheet(
            f"font-size: 12px; font-weight: 900; color: #FFFFFF; "
            f"background: {badge_bg}; border-radius: 5px; padding: 2px 5px; min-width: 22px;"
        )
        layout.addWidget(lbl_badge, alignment=Qt.AlignVCenter)

        left_vbox = QVBoxLayout()
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.setSpacing(2)

        title_col = "#F9FAFB" if is_dark else "#111827"
        sub_col = "#9CA3AF" if is_dark else "#4B5563"

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {title_col}; border: none; background: transparent;")
        title_row.addWidget(lbl_title)

        if is_soup:
            is_takeout = "打包" in [p.strip() for p in tag.split("/") if p.strip()]
            btn_text = "打包 ∨" if is_takeout else "堂食 ∨"
            
            btn_takeout = TakeoutLabel(btn_text)
            if is_takeout:
                btn_takeout.setStyleSheet(
                    "color: #F59E0B; font-weight: bold; font-size: 11px; border-radius: 3px; padding: 1px 4px; margin: 0px; border: 1px dashed #F59E0B; background: transparent;"
                )
            else:
                btn_takeout.setStyleSheet(
                    "color: #9CA3AF; font-weight: bold; font-size: 11px; border-radius: 3px; padding: 1px 4px; margin: 0px; border: 1px dashed #475569; background: transparent;"
                )
            btn_takeout.clicked.connect(self._on_takeout_click)
            title_row.addWidget(btn_takeout, alignment=Qt.AlignVCenter)

        title_row.addStretch()
        left_vbox.addLayout(title_row)

        if subline:
            lbl_sub = QLabel(subline)
            lbl_sub.setStyleSheet(f"font-size: 12px; color: {sub_col}; font-family: 'Consolas', monospace; border: none; background: transparent;")
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

    def _on_takeout_click(self):
        self.clicked.emit(self.index)
        self.takeout_clicked.emit(self.index)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)


class MenuGridButton(QPushButton):
    """
    右侧菜单卡片按钮 — 深浅主题自适应 (分类支持汤底、打包盒、精品串与饮料)
    """

    def __init__(self, key_id, title, subtitle, price, is_soup=False, is_box=False, is_skewer=False, is_dark_mode=True, parent=None):
        super().__init__(parent)
        self.key_id = key_id
        self.title_str = title
        self.subtitle_str = subtitle
        self.price_val = price
        self.price = price
        self.is_soup = is_soup
        self.is_box = is_box
        self.is_skewer = is_skewer
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

        if subtitle:
            self.lbl_sub = QLabel(subtitle)
            self.lbl_sub.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.lbl_sub)
        else:
            self.lbl_sub = None

        self.lbl_badge = QLabel("", self)
        self.lbl_badge.setAlignment(Qt.AlignCenter)
        self.lbl_badge.setStyleSheet(
            "background: #EF4444; color: white; font-size: 11px; font-weight: 900; "
            "border-radius: 9px; min-width: 18px; max-height: 18px; padding: 1px 4px;"
        )
        self.lbl_badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lbl_badge.hide()

        self._update_style()

    def set_dark_mode(self, is_dark):
        self.is_dark_mode = is_dark
        self._update_style()

    def set_count(self, cnt):
        self.count = cnt
        if self.count > 0:
            self.lbl_badge.setText(str(self.count))
            self.lbl_badge.adjustSize()
            self.lbl_badge.show()
            self.lbl_badge.move(max(0, self.width() - self.lbl_badge.width() - 4), 4)
        else:
            self.lbl_badge.hide()
        self._update_style()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.count > 0:
            self.lbl_badge.adjustSize()
            self.lbl_badge.move(max(0, self.width() - self.lbl_badge.width() - 4), 4)

    def update_subtitle(self, sub_text):
        self.subtitle_str = sub_text
        if self.lbl_sub:
            self.lbl_sub.setText(sub_text)

    def _update_style(self):
        if self.is_soup:
            # ── 1. 汤底专属橙暖色样式 ──
            if self.is_dark_mode:
                if self.count > 0:
                    self.setStyleSheet(
                        "QPushButton { background: #EA580C; border: 2px solid #F97316; border-radius: 10px; }"
                        "QPushButton:hover { background: #C2410C; }"
                        "QLabel { color: #FFFFFF; font-size: 14px; font-weight: 900; background: transparent; border: none; }"
                    )
                else:
                    self.setStyleSheet(
                        "QPushButton { background: #431407; border: 1.5px solid #EA580C; border-radius: 10px; }"
                        "QPushButton:hover { background: #7C2D12; }"
                        "QLabel { color: #FFEDD5; font-size: 14px; font-weight: bold; background: transparent; border: none; }"
                    )
            else:
                if self.count > 0:
                    self.setStyleSheet(
                        "QPushButton { background: #FFEDD5; border: 2px solid #F97316; border-radius: 10px; }"
                        "QPushButton:hover { background: #FDBA74; }"
                        "QLabel { color: #9A3412; font-size: 14px; font-weight: 900; background: transparent; border: none; }"
                    )
                else:
                    self.setStyleSheet(
                        "QPushButton { background: #FFF7ED; border: 1.5px solid #EA580C; border-radius: 10px; }"
                        "QPushButton:hover { background: #FFEDD5; }"
                        "QLabel { color: #C2410C; font-size: 14px; font-weight: bold; background: transparent; border: none; }"
                    )
        elif self.is_box:
            # ── 2. 打包盒专属翡翠绿样式 ──
            if self.is_dark_mode:
                if self.count > 0:
                    self.setStyleSheet(
                        "QPushButton { background: #059669; border: 2px solid #34D399; border-radius: 10px; }"
                        "QPushButton:hover { background: #047857; }"
                        "QLabel { color: #FFFFFF; font-size: 14px; font-weight: 900; background: transparent; border: none; }"
                    )
                else:
                    self.setStyleSheet(
                        "QPushButton { background: #064E3B; border: 1.5px solid #10B981; border-radius: 10px; }"
                        "QPushButton:hover { background: #022C22; }"
                        "QLabel { color: #A7F3D0; font-size: 14px; font-weight: bold; background: transparent; border: none; }"
                    )
            else:
                if self.count > 0:
                    self.setStyleSheet(
                        "QPushButton { background: #D1FAE5; border: 2px solid #059669; border-radius: 10px; }"
                        "QPushButton:hover { background: #A7F3D0; }"
                        "QLabel { color: #047857; font-size: 14px; font-weight: 900; background: transparent; border: none; }"
                    )
                else:
                    self.setStyleSheet(
                        "QPushButton { background: #ECFDF5; border: 1.5px solid #10B981; border-radius: 10px; }"
                        "QPushButton:hover { background: #D1FAE5; }"
                        "QLabel { color: #065F46; font-size: 14px; font-weight: bold; background: transparent; border: none; }"
                    )
        elif self.is_skewer:
            # ── 3. 精品串专属紫罗兰样式 ──
            if self.is_dark_mode:
                if self.count > 0:
                    self.setStyleSheet(
                        "QPushButton { background: #6D28D9; border: 2px solid #A78BFA; border-radius: 10px; }"
                        "QPushButton:hover { background: #5B21B6; }"
                        "QLabel { color: #FFFFFF; font-size: 14px; font-weight: 900; background: transparent; border: none; }"
                    )
                else:
                    self.setStyleSheet(
                        "QPushButton { background: #2E1065; border: 1.5px solid #8B5CF6; border-radius: 10px; }"
                        "QPushButton:hover { background: #3B0764; }"
                        "QLabel { color: #DDD6FE; font-size: 14px; font-weight: bold; background: transparent; border: none; }"
                    )
            else:
                if self.count > 0:
                    self.setStyleSheet(
                        "QPushButton { background: #DDD6FE; border: 2px solid #7C3AED; border-radius: 10px; }"
                        "QPushButton:hover { background: #C4B5FD; }"
                        "QLabel { color: #4C1D95; font-size: 14px; font-weight: 900; background: transparent; border: none; }"
                    )
                else:
                    self.setStyleSheet(
                        "QPushButton { background: #F5F3FF; border: 1.5px solid #8B5CF6; border-radius: 10px; }"
                        "QPushButton:hover { background: #EDE9FE; }"
                        "QLabel { color: #5B21B6; font-size: 14px; font-weight: bold; background: transparent; border: none; }"
                    )
        else:
            # ── 4. 普通饮料卡片 (深浅自适应) ──
            if self.is_dark_mode:
                if self.count > 0:
                    self.setStyleSheet(
                        "QPushButton { background: #1E293B; border: 2px solid #EA580C; border-radius: 10px; }"
                        "QPushButton:hover { background: #263352; }"
                        "QLabel { color: #F97316; font-size: 14px; font-weight: 900; background: transparent; border: none; }"
                    )
                else:
                    self.setStyleSheet(
                        "QPushButton { background: #172136; border: 1px solid #374151; border-radius: 10px; }"
                        "QPushButton:hover { background: #1E293B; }"
                        "QLabel { color: #F9FAFB; font-size: 14px; font-weight: bold; background: transparent; border: none; }"
                    )
            else:
                if self.count > 0:
                    self.setStyleSheet(
                        "QPushButton { background: #FFF7ED; border: 2px solid #EA580C; border-radius: 10px; }"
                        "QPushButton:hover { background: #FFEDD5; }"
                        "QLabel { color: #EA580C; font-size: 14px; font-weight: 900; background: transparent; border: none; }"
                    )
                else:
                    self.setStyleSheet(
                        "QPushButton { background: #FFFFFF; border: 2px solid #94A3B8; border-radius: 10px; }"
                        "QPushButton:hover { background: #F1F5F9; }"
                        "QLabel { color: #000000; font-size: 14px; font-weight: 900; background: transparent; border: none; }"
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
        self._low_price_warning_shown = False
        self._scale_connected = False
        self._last_weight_monotonic = 0.0
        self._checkout_active = False
        # Simulation starts in the safer/manual mode.  It is intentionally a
        # session setting: real hardware configuration is never changed by
        # the mock controls.
        self._is_mock_mode = bool(config.get("is_mock_mode", False))
        self.mock_weight_mode = "manual"
        
        # 购物车项目列表与选中项目索引与分页状态
        self.cart_items = []
        self.selected_item_index = -1
        self.cart_page = 0
        self.menu_buttons = {}

        self.temp_order_no = self._gen_temp_order_no()
        self.current_order_id = uuid.uuid4().hex
        self._detail_expanded = False
        self._resize_timer = None
        self._cart_dirty = True
        self._draft_signature = ""
        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.timeout.connect(self._save_draft_now)

        self._build_ui()
        self._restore_draft()
        self._setup_scale()
        self.refresh_call_number_display()

    def _restore_draft(self):
        """Restore an unfinished basket after an abnormal POS exit."""
        draft = load_draft()
        if not draft or not draft.get("cart_items"):
            return
        self.cart_items = draft["cart_items"]
        self.temp_order_no = draft.get("temp_order_no") or self._gen_temp_order_no()
        self.current_order_id = draft.get("order_id") or uuid.uuid4().hex
        self.selected_item_index = len(self.cart_items) - 1
        for item in self.cart_items:
            btn = self.menu_buttons.get(item.get("key_id"))
            if btn:
                btn.set_count(btn.count + max(1, int(item.get("qty", 1))))
        self._auto_focus_requested = True
        self._update_price_display()
        QTimer.singleShot(350, lambda: self._show_toast(u"已恢复上次未结账订单，请核对后再收款"))

    def _schedule_draft_save(self):
        """Coalesce frequent touch edits into one atomic draft write."""
        self._draft_timer.start(250)

    def _save_draft_now(self):
        try:
            import json
            signature = json.dumps(self.cart_items, ensure_ascii=False, sort_keys=True)
            if signature == self._draft_signature:
                return
            self._draft_signature = signature
            save_draft(self.current_order_id, self.temp_order_no, self.cart_items)
        except Exception as exc:
            log_event(CAT_SYSTEM, "订单草稿保存失败", str(exc))

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

        # 重量 LED 横幅：只有模拟模式使用紫色，正常称重恢复橙色业务样式。
        led_banner = QFrame()
        self.led_banner = led_banner
        self._update_weight_banner_style()
        led_layout = QHBoxLayout(led_banner)
        led_layout.setContentsMargins(12, 4, 12, 4)

        # 状态指示图标: ⏳ vs ✅
        self.lbl_scale_status_icon = QLabel(u"⏳")
        self.lbl_scale_status_icon.setToolTip(u"读数计算中...")
        self.lbl_scale_status_icon.setStyleSheet("font-size: 24px; font-weight: bold; color: #FEF08A; border: none; background: transparent;")
        led_layout.addWidget(self.lbl_scale_status_icon)

        # 模拟调试模式下显示重量模式列表；重量数字本身就是操作入口。
        mode_box = QVBoxLayout()
        mode_box.setSpacing(0)
        mode_selector_row = QHBoxLayout()
        mode_selector_row.setSpacing(6)
        self.cmb_mock_weight_mode = MockWeightModeComboBox()
        self.cmb_mock_weight_mode.addItem(u"手动输入重量", "manual")
        self.cmb_mock_weight_mode.addItem(u"随机生成重量", "random")
        self.cmb_mock_weight_mode.addItem(u"切换到正常模式（检测设备）", "normal")
        self.cmb_mock_weight_mode.setMinimumHeight(56)
        # Leave enough horizontal room for the complete ``00.000 kg`` readout
        # on the narrower Win7 touch layout.
        self.cmb_mock_weight_mode.setMinimumWidth(140)
        self.cmb_mock_weight_mode.setMaximumWidth(165)
        self.cmb_mock_weight_mode.setFocusPolicy(Qt.NoFocus)
        self.cmb_mock_weight_mode.setStyleSheet(
            "QComboBox { background: #2E1065; color: #F5F3FF; border: 2px solid #8B5CF6; "
            "border-radius: 9px; padding: 7px 12px; font-size: 14px; font-weight: 900; }"
            "QComboBox:focus { border: 2px solid #C4B5FD; background: #4C1D95; }"
            "QComboBox::drop-down { width: 0px; border: none; }"
            "QComboBox::down-arrow { image: none; width: 0px; height: 0px; }"
            "QComboBox QAbstractItemView { background: #1E1B4B; color: #F5F3FF; "
            "border: 2px solid #8B5CF6; border-radius: 10px; padding: 6px; outline: none; }"
            "QListView::item { min-height: 56px; padding: 14px 16px; margin: 2px 4px; "
            "border-radius: 8px; font-size: 16px; }"
            "QListView::item:selected, QListView::item:hover { background: #7C3AED; color: #FFFFFF; }"
        )
        mode_view = QListView()
        mode_view.setStyleSheet(
            "QListView { background: #1E1B4B; color: #F5F3FF; border: 2px solid #8B5CF6; "
            "border-radius: 10px; padding: 6px; outline: none; }"
            "QListView::item { min-height: 56px; padding: 14px 16px; margin: 2px 4px; "
            "border-radius: 8px; font-size: 16px; }"
            "QListView::item:selected, QListView::item:hover { background: #7C3AED; color: #FFFFFF; }"
        )
        self.cmb_mock_weight_mode.setView(mode_view)
        self.cmb_mock_weight_mode.setMaxVisibleItems(3)
        self.cmb_mock_weight_mode.currentIndexChanged.connect(self._on_mock_weight_mode_changed)
        mode_selector_row.addWidget(self.cmb_mock_weight_mode)
        mode_box.addLayout(mode_selector_row)
        led_layout.addLayout(mode_box)
        self.mock_mode_box = mode_box
        self._mock_mode_index = 0

        if self._is_mock_mode:
            self.lbl_scale_status_icon.hide()
            self.cmb_mock_weight_mode.show()
            self.cmb_mock_weight_mode.setCurrentIndex(0)
            self._on_mock_weight_mode_changed(0)
        else:
            self.cmb_mock_weight_mode.hide()

        self.lbl_weight = ClickableWeightLabel("00.000 kg")
        self.lbl_weight.clicked.connect(self._on_weight_display_click)
        self.lbl_weight.setCursor(Qt.PointingHandCursor)
        self.lbl_weight.setMinimumWidth(215)
        self.lbl_weight.setToolTip(u"模拟模式：点击重量数字输入或生成重量")
        self.lbl_weight.setStyleSheet(
            "font-size: 32px; font-weight: 900; color: #FFFFFF; border: none; background: transparent; "
            "font-family: 'Segoe UI', 'Consolas', sans-serif; letter-spacing: 1px;"
        )
        led_layout.addWidget(self.lbl_weight, stretch=1, alignment=Qt.AlignRight)

        left_layout.addWidget(led_banner)

        # 2. 订单消费卡片列表 (ScrollArea 禁用下滑条，采用精准分页)
        self.cart_scroll = QScrollArea()
        self.cart_scroll.setWidgetResizable(True)
        self.cart_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cart_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cart_container = QWidget()
        self.cart_layout = QVBoxLayout(self.cart_container)
        self.cart_layout.setContentsMargins(0, 0, 0, 0)
        self.cart_layout.setSpacing(6)
        self.cart_layout.setAlignment(Qt.AlignTop)

        self.cart_scroll.setWidget(self.cart_container)
        left_layout.addWidget(self.cart_scroll, stretch=1)

        # 3. 分页控制栏 (◀ 上一页 | 第 X / Y 页 | 下一页 ▶)
        self.page_bar = QHBoxLayout()
        self.page_bar.setContentsMargins(0, 4, 0, 4)

        self.btn_prev_page = QPushButton(u"◀ 上一页")
        self.btn_prev_page.setCursor(Qt.PointingHandCursor)
        self.btn_prev_page.setStyleSheet(
            "QPushButton { background: #334155; color: #E2E8F0; font-weight: bold; font-size: 13px; "
            "border-radius: 6px; padding: 6px 12px; border: 1px solid #475569; }"
            "QPushButton:hover { background: #475569; color: #FFFFFF; }"
            "QPushButton:disabled { background: #1E293B; color: #475569; border: 1px solid #334155; }"
        )
        self.btn_prev_page.clicked.connect(self._prev_cart_page)
        self.page_bar.addWidget(self.btn_prev_page)

        self.lbl_cart_page = QLabel(u"第 1 / 1 页")
        self.lbl_cart_page.setAlignment(Qt.AlignCenter)
        self.lbl_cart_page.setStyleSheet("font-size: 13px; font-weight: bold; color: #F59E0B; border: none; background: transparent;")
        self.page_bar.addWidget(self.lbl_cart_page, stretch=1)

        self.btn_next_page = QPushButton(u"下一页 ▶")
        self.btn_next_page.setCursor(Qt.PointingHandCursor)
        self.btn_next_page.setStyleSheet(
            "QPushButton { background: #334155; color: #E2E8F0; font-weight: bold; font-size: 13px; "
            "border-radius: 6px; padding: 6px 12px; border: 1px solid #475569; }"
            "QPushButton:hover { background: #475569; color: #FFFFFF; }"
            "QPushButton:disabled { background: #1E293B; color: #475569; border: 1px solid #334155; }"
        )
        self.btn_next_page.clicked.connect(self._next_cart_page)
        self.page_bar.addWidget(self.btn_next_page)

        left_layout.addLayout(self.page_bar)

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

        # 折扣按钮: 9.5折, 9折, 8.8折, 8折 (点击二次可反选恢复原价)
        self.discount_btns = {}
        discounts = [(0.95, "9.5折"), (0.90, "9折"), (0.88, "8.8折"), (0.80, "8折")]
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

        mid_layout.addSpacing(20) # Category separator

        # 改口味按钮
        btn_flavor = QPushButton("改口味")
        btn_flavor.setCursor(Qt.PointingHandCursor)
        btn_flavor.setToolTip(u"修改选中汤底的辣度与避忌偏好")
        btn_flavor.setStyleSheet(
            "QPushButton { background: #0284C7; color: white; font-weight: bold; font-size: 13px; border-radius: 6px; padding: 8px 4px; min-width: 50px; border: 1px solid #0369A1; }"
            "QPushButton:hover { background: #0369A1; }"
        )
        btn_flavor.clicked.connect(self._change_selected_flavor)
        mid_layout.addWidget(btn_flavor)
        
        mid_layout.addSpacing(6)
        
        # 打包按钮
        btn_takeout = QPushButton("打包")
        btn_takeout.setCursor(Qt.PointingHandCursor)
        btn_takeout.setToolTip(u"切换选中汤底的堂食/打包状态")
        btn_takeout.setStyleSheet(
            "QPushButton { background: #D97706; color: white; font-weight: bold; font-size: 13px; border-radius: 6px; padding: 8px 4px; min-width: 50px; border: 1px solid #B45309; }"
            "QPushButton:hover { background: #B45309; }"
        )
        btn_takeout.clicked.connect(lambda: self._on_cart_item_takeout_click(self.selected_item_index))
        mid_layout.addWidget(btn_takeout)

        mid_layout.addSpacing(20) # Category separator

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

        special_soup_price = self.config.get("special_soup_price", self.config.get("soup_price_4", 25.00 if price_unit == "per_jin" else 50.00))

        # 菜单配置：
        # 第 0 行：标准汤底类 (骨汤, 番茄汤, 麻辣拌)
        # 第 1 行：精品汤底类 (菌汤, 金汤)
        # 第 2 行：打包盒
        # 第 3-4 行：精品串类 (1元, 2元, 3元, 4元, 5元, 6元)
        # 第 5-7 行：1-10元饮料
        menu_items_config = [
            # 第 0 行：标准汤底类 (橙暖色)
            (0, 0, "soup_1", u"经典草本骨汤", f"¥ {unit_price:.2f}/{pu_lbl}", unit_price, True, False, False),
            (0, 1, "soup_2", u"酸甜番茄汤", f"¥ {unit_price:.2f}/{pu_lbl}", unit_price, True, False, False),
            (0, 2, "soup_3", u"石磨醇香麻辣拌", f"¥ {unit_price:.2f}/{pu_lbl}", unit_price, True, False, False),

            # 第 1 行：精品汤底类 (菌汤/金汤)
            (1, 0, "soup_4", u"草本穹顶菌汤", f"¥ {special_soup_price:.2f}/{pu_lbl}", special_soup_price, True, False, False),
            (1, 1, "soup_5", u"草本酸辣金汤", f"¥ {special_soup_price:.2f}/{pu_lbl}", special_soup_price, True, False, False),

            # 第 2 行：打包盒
            (2, 0, "item_box", u"打包盒", "¥ 1.00", 1.0, False, True, False),

            # 第 3 行：精品串类 (1-4元，典雅紫罗兰色)
            (3, 0, "item_skewer_1", u"精品串 1元", "", 1.0, False, False, True),
            (3, 1, "item_skewer_2", u"精品串 2元", "", 2.0, False, False, True),
            (3, 2, "item_skewer_3", u"精品串 3元", "", 3.0, False, False, True),
            (3, 3, "item_skewer_4", u"精品串 4元", "", 4.0, False, False, True),

            # 第 4 行：精品串类 (5-6元，典雅紫罗兰色)
            (4, 0, "item_skewer_5", u"精品串 5元", "", 5.0, False, False, True),
            (4, 1, "item_skewer_6", u"精品串 6元", "", 6.0, False, False, True),

            # 第 5 行：1-4元饮料
            (5, 0, "item_1", u"1元饮料", "", 1.0, False, False, False),
            (5, 1, "item_2", u"2元饮料", "", 2.0, False, False, False),
            (5, 2, "item_3", u"3元饮料", "", 3.0, False, False, False),
            (5, 3, "item_4", u"4元饮料", "", 4.0, False, False, False),

            # 第 6 行：5-8元饮料
            (6, 0, "item_5", u"5元饮料", "", 5.0, False, False, False),
            (6, 1, "item_6", u"6元饮料", "", 6.0, False, False, False),
            (6, 2, "item_7", u"7元饮料", "", 7.0, False, False, False),
            (6, 3, "item_8", u"8元饮料", "", 8.0, False, False, False),

            # 第 7 行：9-10元饮料
            (7, 0, "item_9", u"9元饮料", "", 9.0, False, False, False),
            (7, 1, "item_10", u"10元饮料", "", 10.0, False, False, False),
        ]

        for r, c, key_id, title, sub, price, is_soup, is_box, is_skewer in menu_items_config:
            btn = MenuGridButton(key_id, title, sub, price, is_soup, is_box, is_skewer, self.is_dark_mode)
            btn.clicked.connect(lambda checked, b=btn: self._on_menu_click(b))
            mg_grid.addWidget(btn, r, c)
            self.menu_buttons[key_id] = btn

        right.addWidget(menu_group)

        # 底部核心按键
        btn_box = QHBoxLayout()
        
        clear_box = QHBoxLayout()
        clear_box.setSpacing(10)
        
        self.btn_clear = QPushButton(u"清空重置")
        self.btn_clear.setObjectName("btn_clear")
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.clicked.connect(self._on_clear)
        clear_box.addWidget(self.btn_clear, stretch=1)
        
        self.btn_open_drawer = QPushButton(u"开钱箱")
        self.btn_open_drawer.setObjectName("btn_open_drawer")
        self.btn_open_drawer.setCursor(Qt.PointingHandCursor)
        self.btn_open_drawer.clicked.connect(lambda: self.printer.open_cash_drawer() if self.printer else None)
        clear_box.addWidget(self.btn_open_drawer, stretch=1)
        
        btn_box.addLayout(clear_box, stretch=1)

        self.btn_other = QPushButton(u"去其他")
        self.btn_other.setObjectName("btn_other")
        self.btn_other.setCursor(Qt.PointingHandCursor)
        self.btn_other.setFixedWidth(78)
        self.btn_other.clicked.connect(self._on_other_checkout)
        btn_box.addWidget(self.btn_other)

        self.btn_cash = QPushButton(u"去现金")
        self.btn_cash.setObjectName("btn_cash")
        self.btn_cash.setCursor(Qt.PointingHandCursor)
        self.btn_cash.clicked.connect(self._on_cash_checkout)
        btn_box.addWidget(self.btn_cash, stretch=1)

        self.btn_print = QPushButton(u"去扫码")
        self.btn_print.setObjectName("btn_print")
        self.btn_print.setCursor(Qt.PointingHandCursor)
        self.btn_print.clicked.connect(self._on_print)
        btn_box.addWidget(self.btn_print, stretch=1)

        right.addLayout(btn_box)

        layout.addLayout(right, stretch=7)

        self._update_price_display()

    def _update_weight_banner_style(self):
        """Keep simulation styling separate from the live scale screen."""
        banner = getattr(self, "led_banner", None)
        if banner is None:
            return
        if self._is_mock_mode:
            start, end = "#6D28D9", "#4C1D95"
        else:
            start, end = "#EA580C", "#C2410C"
        banner.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 %s, stop:1 %s); border-radius: 8px; padding: 8px 14px; border: none; }"
            % (start, end)
        )

    def _show_toast(self, msg_text):
        """显示一个自动消失的提示框（使用系统级 WindowOpacity 保证丝滑动画）"""
        from PyQt5.QtWidgets import QLabel, QWidget, QVBoxLayout
        from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
        
        toast = QWidget(self.window())  # 必须挂在主窗口上，且设为 top-level
        toast.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        toast.setAttribute(Qt.WA_TranslucentBackground)
        
        layout = QVBoxLayout(toast)
        layout.setContentsMargins(0, 0, 0, 0)
        
        lbl = QLabel(msg_text)
        is_low_price = u"低于" in str(msg_text) and u"元" in str(msg_text)
        toast_color = "#FDE68A" if is_low_price else "#34D399"
        toast_border = "#F59E0B" if is_low_price else "#059669"
        lbl.setStyleSheet("""
            QLabel {
                background-color: rgba(30, 41, 59, 0.95);
                color: %s;
                font-size: 28px;
                font-weight: bold;
                padding: 20px 40px;
                border-radius: 16px;
                border: 2px solid %s;
            }
        """ % (toast_color, toast_border))
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        
        toast.adjustSize()
        
        # 居中显示在主窗口中心偏上
        main_win = self.window()
        main_rect = main_win.geometry()
        x = main_rect.x() + (main_rect.width() - toast.width()) // 2
        y = main_rect.y() + (main_rect.height() - toast.height()) // 2 - 80
        toast.move(x, y)
        
        # 初始透明度
        toast.setWindowOpacity(0.0)
        toast.show()

        # 淡入动画
        anim_in = QPropertyAnimation(toast, b"windowOpacity")
        anim_in.setDuration(300)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)
        anim_in.setEasingCurve(QEasingCurve.OutCubic)
        
        # 淡出动画
        anim_out = QPropertyAnimation(toast, b"windowOpacity")
        anim_out.setDuration(500)
        anim_out.setStartValue(1.0)
        anim_out.setEndValue(0.0)
        anim_out.setEasingCurve(QEasingCurve.InCubic)

        # 保留引用
        toast._anim_in = anim_in
        toast._anim_out = anim_out
        
        anim_in.start()

        # 0.8秒后开始淡出
        QTimer.singleShot(800, anim_out.start)
        anim_out.finished.connect(toast.deleteLater)

    def _on_menu_click(self, btn: MenuGridButton):
        """点击右侧菜单按钮"""
        unit_price = self.config.get("unit_price", 47.60)
        price_unit = self.config.get("price_unit", "per_jin")

        if btn.is_soup:
            # Snapshot the launch mode.  A settings save must not be able to
            # turn a running simulation into a real-scale checkout.
            is_mock = self._is_mock_mode
            if is_mock and self.mock_weight_mode == "manual":
                # Manual mode deliberately asks for the weight on every soup
                # selection, so a previous bowl's value cannot be reused by
                # accident.
                if not self._prompt_manual_weight():
                    return
            elif self.current_weight <= 0.0005:
                if is_mock and self.mock_weight_mode == "random":
                    show_warning(self, u"请先生成模拟重量", u"当前为随机重量模式，请先点击上方“随机重量”，再选择麻辣烫。")
                else:
                    show_warning(self, u"请先称重", u"当前电子秤读数为 0.000 kg，请先将麻辣烫放置在电子秤上！")
                return
            if not is_mock:
                if not self._scale_connected or time.monotonic() - self._last_weight_monotonic > 2.0:
                    show_warning(self, u"称重读数不可用", u"电子秤读数已断开或超过 2 秒未更新。请确认电子秤连接正常后重新称重。")
                    return
                if not self._is_stable:
                    show_warning(self, u"请等待稳定", u"电子秤读数正在变化，请等待绿色稳定标记出现后再加入汤底。")
                    return

            soup_clean_name = btn.title_str.replace("\n", " ")
            dlg = TasteSelectionDialog(soup_clean_name, is_dark_mode=self.is_dark_mode, parent=self)
            
            skip_flavor_popup = ("骨汤" not in soup_clean_name)
            
            w = self.current_weight
            soup_unit_price = btn.price if (btn.price > 0) else unit_price
            b_price = calculate_price(w, soup_unit_price, price_unit)
            
            # 1. 点击汤底卡片，无需二次确认，即刻加入订单列表
            item_entry = {
                "type": "soup",
                "key_id": btn.key_id,
                "name": soup_clean_name,
                "tag": "" if skip_flavor_popup else dlg.get_tag_string(),
                "weight": w,
                "weight_captured_at": datetime.now().isoformat(timespec="seconds"),
                "base_price": b_price,
                "price": b_price,
                "unit_price": soup_unit_price,
                "price_unit": price_unit,
                "qty": 1,
                "discount_rate": 1.0
            }
            self.cart_items.append(item_entry)
            self.selected_item_index = len(self.cart_items) - 1
            pages = self._compute_cart_pages()
            self.cart_page = len(pages) - 1
            btn.set_count(btn.count + 1)
            self._update_price_display()
            log_event(CAT_USER, f"点选汤底: {soup_clean_name}", f"重量 {w:.3f}kg | 单价 {soup_unit_price} | 金额 ¥{b_price:.2f}")

            # 2. 实时响应辣度/避忌按钮，点击即刻刷新卡片标签
            def update_flavor(new_tag):
                item_entry["tag"] = new_tag
                self._auto_focus_requested = True
                self._update_price_display()

            dlg.flavor_changed.connect(update_flavor)

            # 3. 智能精准定位气泡弹窗在当前按键旁边/下方，且严格防越界 (特定汤底免打扰)
            if not skip_flavor_popup:
                self._position_popup_at_widget(dlg, btn)
                dlg.exec_()
                
            reminders = []
            if self.config.get("skewer_reminder_enabled", True):
                reminders.append(u"是否有精品串？")
            if self.config.get("packing_reminder_enabled", True):
                reminders.append(u"是否需要打包？")
            if reminders:
                self._show_toast(u"温馨提示：" + " ".join(reminders))
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
            pages = self._compute_cart_pages()
            self.cart_page = len(pages) - 1
            btn.set_count(btn.count + 1)
            self._update_price_display()
            log_event(CAT_USER, f"点选附加项: {btn.title_str.replace(chr(10), ' ')}", f"单价 ¥{btn.price_val:.2f}")

    def _select_cart_item(self, index):
        """选择指定的订单卡片"""
        if 0 <= index < len(self.cart_items):
            self.selected_item_index = index
            self._update_price_display()

    def _on_cart_item_takeout_click(self, index):
        """在已选汤底卡片上点击了打包/堂食按钮"""
        if 0 <= index < len(self.cart_items):
            item = self.cart_items[index]
            if item["type"] != "soup": return
            
            tag = item.get("tag", "")
            tags = [p.strip() for p in tag.split("/") if p.strip()]
            
            if "打包" not in tags:
                tags.append("打包")
                item["tag"] = " / ".join(tags)
                
                # 自动增加一个打包盒
                box_btn = self.menu_buttons.get("item_box")
                if box_btn:
                    self._on_menu_click(box_btn)
                else:
                    self._update_price_display()
            else:
                tags.remove("打包")
                item["tag"] = " / ".join(tags)
                
                # 自动删减一个打包盒 (从后往前找最近添加的)
                for i in range(len(self.cart_items)-1, -1, -1):
                    box_item = self.cart_items[i]
                    if box_item.get("key_id") == "item_box":
                        qty = box_item.get("qty", 1)
                        if qty > 1:
                            box_item["qty"] = qty - 1
                            box_item["price"] = box_item["base_price"] * box_item["qty"] * box_item.get("discount_rate", 1.0)
                        else:
                            self.cart_items.pop(i)
                            if "item_box" in self.menu_buttons:
                                btn = self.menu_buttons["item_box"]
                                btn.set_count(max(0, btn.count - 1))
                            
                            # 调整当前选中的索引，防止越界或错位
                            if self.selected_item_index == i:
                                self.selected_item_index = min(self.selected_item_index, max(0, len(self.cart_items)-1)) if self.cart_items else -1
                            elif self.selected_item_index > i:
                                self.selected_item_index -= 1
                        break
                
                self._update_price_display()

    def _position_popup_at_widget(self, dlg, target_widget):
        """将 气泡弹窗 精准安放在 target_widget 旁边/上方/下方，并严格防止超出屏幕边界"""
        dlg.adjustSize()
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QPoint
        
        # 获取当前显示屏的可用地理几何尺寸 (排除任务栏)
        screen_geo = QApplication.primaryScreen().availableGeometry()
        if self.window() and self.window().windowHandle() and self.window().windowHandle().screen():
            screen_geo = self.window().windowHandle().screen().availableGeometry()

        widget_global = target_widget.mapToGlobal(QPoint(0, 0))
        widget_w = target_widget.width()
        widget_h = target_widget.height()
        
        dlg_w = dlg.width()
        dlg_h = dlg.height()
        
        # 默认在 target_widget 下方 (气泡尖尖向上)
        target_x = widget_global.x() + (widget_w - dlg_w) // 2
        target_y = widget_global.y() + widget_h + 6
        arrow_dir = "up"

        # 若下方会超出屏幕底部，反向置于目标上方 (气泡尖尖向下)
        if target_y + dlg_h > screen_geo.bottom() - 10:
            target_y = widget_global.y() - dlg_h - 6
            arrow_dir = "down"
            
        # 若上方又超出了屏幕顶部，强行贴齐顶部视口
        if target_y < screen_geo.top() + 10:
            target_y = screen_geo.top() + 10

        # 严控 X 轴不超过屏幕左右边界
        min_x = screen_geo.left() + 10
        max_x = screen_geo.right() - dlg_w - 10
        clamped_x = max(min_x, min(max_x, target_x))

        # 动态计算指针尖尖 Arrow 的相对 X 偏移量，使其精准指向目标组件的中心
        widget_center_x = widget_global.x() + widget_w // 2
        arrow_offset = widget_center_x - clamped_x
        arrow_offset = max(24, min(dlg_w - 24, arrow_offset))

        dlg.arrow_direction = arrow_dir
        dlg.arrow_x_offset = int(arrow_offset)
        dlg.update_layout_margins()
        dlg.adjustSize()
        dlg.move(int(clamped_x), int(target_y))

    def _change_selected_flavor(self):
        """快捷按键：在选中的已点卡片旁边重新弹开口味选择框"""
        if 0 <= self.selected_item_index < len(self.cart_items):
            item = self.cart_items[self.selected_item_index]
            if item.get("type") != "soup":
                show_warning(self, u"提示", u"只有麻辣烫汤底项目支持修改辣度及避忌偏好！")
                return

            soup_name = item.get("name", u"麻辣烫")
            dlg = TasteSelectionDialog(soup_name, is_dark_mode=self.is_dark_mode, parent=self)
            
            # 设置初始勾选已有的口味标签 (如 '微辣 / 免蒜')
            if item.get("tag"):
                dlg.set_initial_tag(item["tag"])

            def update_flavor(new_tag):
                item["tag"] = new_tag
                self._auto_focus_requested = True
                self._update_price_display()

            dlg.flavor_changed.connect(update_flavor)

            # 获取左侧正在被修改的卡片组件对象
            target_card = None
            if 0 <= self.selected_item_index < self.cart_layout.count():
                item_layout = self.cart_layout.itemAt(self.selected_item_index)
                if item_layout and item_layout.widget():
                    target_card = item_layout.widget()

            if target_card:
                self._position_popup_at_widget(dlg, target_card)
            else:
                self._position_popup_at_widget(dlg, getattr(self, 'btn_flavor', self))

            dlg.exec_()
        else:
            show_warning(self, u"提示", u"请先在已点项目列表中选择要修改口味的麻辣烫！")

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
            log_event(CAT_USER, f"设置折扣: {item.get('name','')}", f"折扣率: {new_rate:.0%} | 折后价: ¥{item['price']:.2f}")

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
            log_event(CAT_USER, f"删除订单项: {removed.get('name','')}", f"单价 ¥{removed.get('base_price', 0):.2f}")

    def _toggle_call_detail(self):
        self._detail_expanded = not self._detail_expanded
        self.call_detail_box.setVisible(self._detail_expanded)
        if self._detail_expanded:
            self.btn_toggle_detail.setText(u"详细信息 ∧")
        else:
            self.btn_toggle_detail.setText(u"详细信息 ∨")
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(20, self._update_price_display)

    def _compute_cart_pages(self):
        """根据每张卡片真实渲染总像素高度 (含外间距：带口味约 76px，无口味约 56px) 毫厘不差切页"""
        usable_h = 300
        if hasattr(self, 'cart_scroll') and self.cart_scroll.viewport():
            vh = self.cart_scroll.viewport().height()
            if vh > 50:
                usable_h = max(50, vh - 2)

        if not self.cart_items:
            return [(0, 0)]

        pages = []
        curr_start = 0
        curr_h = 0

        for i, item in enumerate(self.cart_items):
            # 真实像素测量：带口味卡片(67px)+间距(6px)≈74~76px；无口味卡片(50px)+间距(6px)≈56px
            item_h = 76 if item.get("tag") else 56
            if curr_h + item_h > usable_h and i > curr_start:
                pages.append((curr_start, i))
                curr_start = i
                curr_h = item_h
            else:
                curr_h += item_h

        pages.append((curr_start, len(self.cart_items)))
        return pages

    def showEvent(self, event):
        super().showEvent(event)
        self._cart_dirty = True
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(50, self._update_price_display)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._resize_timer is not None:
            self.killTimer(self._resize_timer)
        self._resize_timer = self.startTimer(80)

    def timerEvent(self, event):
        if event.timerId() == self._resize_timer:
            self.killTimer(self._resize_timer)
            self._resize_timer = None
            self._cart_dirty = True
            self._update_price_display()
        else:
            super().timerEvent(event)

    def _prev_cart_page(self):
        if self.cart_page > 0:
            self.cart_page -= 1
            self._update_price_display()

    def _next_cart_page(self):
        pages = self._compute_cart_pages()
        if self.cart_page < len(pages) - 1:
            self.cart_page += 1
            self._update_price_display()

    def _update_price_display(self):
        """刷新购物明细卡片列表与金额 (根据口味动态切页与无混淆序号徽章)"""
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

        # 1. 汇总所有商品的总件数与总金额
        for item in self.cart_items:
            total_price += item["price"]
            total_items += item.get("qty", 1)

        # 2. 动态精准切页计算 (兼顾有/无口味标签的不同卡片高度)
        total_items_count = len(self.cart_items)
        pages = self._compute_cart_pages()
        total_pages = len(pages)

        # 自动定位：确保当前选中的卡片始终在当前可视页面内 (仅当请求了自动追焦时执行，防止锁死翻页)
        if getattr(self, '_auto_focus_requested', False) and 0 <= self.selected_item_index < total_items_count:
            for p_idx, (s_idx, e_idx) in enumerate(pages):
                if s_idx <= self.selected_item_index < e_idx:
                    self.cart_page = p_idx
                    break
            self._auto_focus_requested = False

        self.cart_page = min(max(0, self.cart_page), total_pages - 1)

        if hasattr(self, 'lbl_cart_page'):
            self.lbl_cart_page.setText(u"第 %d / %d 页 (共 %d 项)" % (self.cart_page + 1, total_pages, total_items_count))
            self.btn_prev_page.setEnabled(self.cart_page > 0)
            self.btn_next_page.setEnabled(self.cart_page < total_pages - 1)

        start_idx, end_idx = pages[self.cart_page]

        # 3. 仅在数据变化时重建卡片，避免无意义的 destroy+recreate 开销
        self._rebuild_cart_cards(start_idx, end_idx)

        self.lbl_item_count.setText(u"共 %d 件，需付款：" % total_items)
        self.lbl_price.setText(u"￥%.2f" % total_price)
        self._schedule_draft_save()

    def _rebuild_cart_cards(self, start_idx, end_idx):
        """高效重建当前页购物车卡片"""
        # 清除旧卡片
        while self.cart_layout.count() > 0:
            child = self.cart_layout.takeAt(0)
            w = child.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        # 渲染当前页的商品卡片
        for idx in range(start_idx, end_idx):
            item = self.cart_items[idx]
            is_selected = (idx == self.selected_item_index)
            qty = item.get("qty", 1)
            disc_rate = item.get("discount_rate", 1.0)

            if item["type"] == "soup":
                sub_str = f"{item['weight']:.3f} kg"
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
                is_active=is_selected,
                is_soup=(item["type"] == "soup")
            )
            card.clicked.connect(self._select_cart_item)
            card.takeout_clicked.connect(self._on_cart_item_takeout_click)
            self.cart_layout.addWidget(card)

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

        special_soup_price = self.config.get("special_soup_price", self.config.get("soup_price_4", 25.00 if price_unit == "per_jin" else 50.00))

        for key_id in ["soup_1", "soup_2", "soup_3"]:
            btn = self.menu_buttons.get(key_id)
            if btn:
                btn.update_subtitle(f"¥ {unit_price:.2f}/{pu_lbl}")
                btn.price = unit_price

        for key_id in ["soup_4", "soup_5"]:
            btn = self.menu_buttons.get(key_id)
            if btn:
                btn.update_subtitle(f"¥ {special_soup_price:.2f}/{pu_lbl}")
                btn.price = special_soup_price

        self._update_price_display()
        self.refresh_call_number_display()

    def restart_scale(self):
        self.refresh_unit_price_info()
        if getattr(self, 'scale', None) is not None:
            self.scale.restart()

    def _setup_scale(self):
        # Simulation is a complete session mode.  Do not start the real
        # reader in the background: its disconnected/error signal used to
        # paint a red X beside the mock selector and made the page look as if
        # it had switched back to hardware mode.
        if self._is_mock_mode:
            self.scale = None
            return
        self.scale = ScaleReader(self.config)
        self.scale.weight_updated.connect(self._on_weight_update)
        self.scale.status_changed.connect(self._on_status_change)
        self.scale.weight_stable.connect(self._on_weight_stable)
        self.scale.error_occurred.connect(self._on_error)
        self.scale.start()

    @pyqtSlot(float)
    def _on_weight_update(self, weight_kg):
        self.current_weight = weight_kg
        self._last_weight_monotonic = time.monotonic()
        self.lbl_weight.setText("%06.3f kg" % weight_kg)
        # A new bowl is allowed to receive the low-price hint only after the
        # previous weighing has returned to zero.
        if weight_kg <= 0.005:
            self._low_price_warning_shown = False

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
        self._scale_connected = connected
        is_mock = self._is_mock_mode
        if is_mock:
            self.lbl_scale_status_icon.hide()
            return

        self.lbl_scale_status_icon.show()

        if connected:
            if not hasattr(self, '_is_stable') or not self._is_stable:
                self.lbl_scale_status_icon.setText(u"✔")
                self.lbl_scale_status_icon.setStyleSheet("font-size: 28px; font-weight: 900; color: #10B981; border: none; background: transparent;")
            self.lbl_scale_status_icon.setToolTip(u"电子秤串口正常连通: %s" % msg)
        else:
            self._is_stable = False
            self.lbl_scale_status_icon.setText(u"✕")
            self.lbl_scale_status_icon.setStyleSheet("font-size: 26px; font-weight: bold; color: #EF4444; border: none; background: transparent;")
            self.lbl_scale_status_icon.setToolTip(u"电子秤连接提示: %s" % msg)

    @pyqtSlot(float)
    def _on_weight_stable(self, weight_kg):
        self._is_stable = True
        self._stable_weight = weight_kg
        self.lbl_scale_status_icon.setText(u"✔")
        self.lbl_scale_status_icon.setStyleSheet("font-size: 28px; font-weight: 900; color: #10B981; border: none; background: transparent;")
        self.lbl_scale_status_icon.setToolTip(u"重量已稳定，可随时打印！")
        
        # 称重稳定且预计价格低于配置阈值时，弹出一次黄色提醒
        if weight_kg > 0.005:
            if not self.config.get("low_price_warning_enabled", True):
                self._low_price_warning_shown = False
                return
            unit_price = self.config.get("unit_price", 47.60)
            price_unit = self.config.get("price_unit", "per_jin")
            from core.calculator import calculate_price
            expected_price = calculate_price(weight_kg, unit_price, price_unit)
            threshold = float(self.config.get("low_price_warning_threshold", 15.00) or 15.00)
            if expected_price < threshold and not self._low_price_warning_shown:
                self._show_toast(u"温馨提示：此麻辣烫预计称重低于 %.2f 元。" % threshold)
                self._low_price_warning_shown = True
            elif expected_price >= 15.0:
                self._low_price_warning_shown = False

    @pyqtSlot(str)
    def _on_error(self, msg):
        if self._is_mock_mode:
            self.lbl_scale_status_icon.hide()
            return
        self.lbl_scale_status_icon.setText(u"✕")
        self.lbl_scale_status_icon.setStyleSheet("font-size: 26px; font-weight: bold; color: #EF4444; border: none; background: transparent;")
        self.lbl_scale_status_icon.setToolTip(u"错误: %s" % msg)

    def _on_random_weight_click(self):
        if self._is_mock_mode and self.mock_weight_mode == "manual":
            self._prompt_manual_weight()
            return
        weights = [0.120, 0.150, 0.320, 0.450, 0.580, 0.640, 0.760, 0.850, 0.980, 1.150]
        w = random.choice(weights)
        w = round(w + random.uniform(-0.02, 0.02), 3)
        w = max(0.100, w)
        self._apply_mock_weight(w)

    def _on_weight_display_click(self):
        """Use the large weight number as the only mock-weight action target."""
        if self._is_mock_mode:
            self._on_random_weight_click()

    def _on_mock_weight_mode_changed(self, index):
        """Switch mock input, or verify and leave simulation for real mode."""
        index = int(index)
        if self.cmb_mock_weight_mode.itemData(index) == "normal":
            previous_index = getattr(self, "_mock_mode_index", 0)
            self.cmb_mock_weight_mode.setEnabled(False)
            try:
                ready, reason = self._check_normal_scale_ready()
            finally:
                self.cmb_mock_weight_mode.setEnabled(True)
            if not ready:
                # A failed check must never leave the selector on an item
                # that is not actually active.
                self.cmb_mock_weight_mode.blockSignals(True)
                self.cmb_mock_weight_mode.setCurrentIndex(previous_index)
                self.cmb_mock_weight_mode.blockSignals(False)
                show_warning(self, u"暂时不能切换到正常模式", reason)
                return
            self._leave_mock_mode()
            return

        self._mock_mode_index = index
        self.mock_weight_mode = "random" if index == 1 else "manual"
        if not hasattr(self, "lbl_weight"):
            return
        if self.mock_weight_mode == "manual":
            self.lbl_weight.setToolTip(u"手动模式：点击重量数字打开触屏键盘输入 kg")
        else:
            self.lbl_weight.setToolTip(u"随机模式：点击重量数字生成一组模拟重量")

    def _check_normal_scale_ready(self):
        """Return whether the configured real scale can be used right now."""
        source = self.config.get("scale_source", "official")
        if source == "official":
            from utils.window_utils import is_official_window_configured, find_official_window_info
            from core.official_pos import find_active_official_log

            if not is_official_window_configured(self.config):
                return False, u"尚未配置官方 POS 窗口识别词。请到“系统设置 → 官方 POS 窗口识别”先检测并选择窗口。"
            info = find_official_window_info(self.config)
            if not info:
                return False, u"当前没有找到官方 POS 窗口。请先打开官方 POS，或重新选择正确的窗口识别词。"
            log_file = find_active_official_log(self.config)
            if not log_file:
                return False, u"已找到官方 POS 窗口，但没有正在刷新的称重日志。请让官方 POS 读取一次重量后再切换。"
            return True, u""

        port = str(self.config.get("scale_port", "") or "").strip()
        if not port:
            return False, u"尚未配置电子秤 COM 端口，请先在称设置中选择并保存端口。"
        if self.config.get("scale_connection_mode") == "bridge":
            try:
                from scale_bridge.lifecycle import ScaleBridgeServiceController
                state = ScaleBridgeServiceController().query()
                if not (state.installed and state.state_code == 4):
                    return False, u"POS 称桥接服务未运行。请先到“POS 称桥接”启动服务，再切换正常模式。"
            except Exception as exc:
                return False, u"无法确认 POS 称桥接服务状态：%s" % exc
        from ui.login_window import check_dibal_scale_connection
        if not check_dibal_scale_connection(self.config):
            return False, u"%s 没有返回有效重量。请确认电子秤、波特率和端口未被其它软件占用。" % port
        return True, u""

    def _leave_mock_mode(self):
        """Switch this running window from simulation to the configured scale."""
        self._is_mock_mode = False
        self._update_weight_banner_style()
        # This is transient and is intentionally omitted from disk by
        # save_config; retaining the in-memory value keeps all widgets in the
        # same session consistent until the next startup.
        self.config["is_mock_mode"] = False
        self.current_weight = 0.0
        self._stable_weight = 0.0
        self._is_stable = False
        self._low_price_warning_shown = False
        self._scale_connected = False
        self._last_weight_monotonic = 0.0
        self.lbl_weight.setText("00.000 kg")
        self.lbl_scale_status_icon.show()
        self.cmb_mock_weight_mode.hide()
        self._setup_scale()
        self._show_toast(u"已切换到正常称重模式，正在读取电子秤")

    def _apply_mock_weight(self, weight_kg):
        """Apply a mock reading through the same UI path as a real scale."""
        self._on_weight_update(round(float(weight_kg), 3))
        self._on_weight_stable(round(float(weight_kg), 3))

    def _prompt_manual_weight(self):
        """Open the large touch keypad and apply the entered kg value."""
        dlg = ManualWeightDialog(parent=self)
        if dlg.exec_() != QDialog.Accepted or dlg.weight_kg <= 0:
            return False
        self._apply_mock_weight(dlg.weight_kg)
        return True

    def _on_other_checkout(self):
        """点击 '去其他' 按钮：调起去除收钱吧和现金的备选支付模态框"""
        self._open_checkout_dialog(mode="OTHER")

    def _on_cash_checkout(self):
        """点击 '去现金' 按钮：调起现金结算框"""
        self._open_checkout_dialog(mode="CASH")

    def _on_print(self, auto_method=None):
        """点击 '去扫码' 或快捷键结账：调起扫码专属等待/感知模态框"""
        if isinstance(auto_method, bool):
            auto_method = None
        if auto_method == "cash":
            self._open_checkout_dialog(mode="CASH")
        else:
            self._open_checkout_dialog(mode="SCAN_CODE", auto_method=auto_method)

    def _open_checkout_dialog(self, mode="OTHER", auto_method=None):
        """统一结账弹窗控制核心逻辑"""
        if self._checkout_active:
            self._show_toast(u"正在处理本笔订单，请勿重复结账")
            return
        if not self.cart_items:
            show_warning(self, u"提示", u"没有加入任何东西，<span style='font-size: 22px; font-weight: 900; color: #EF4444;'>0元</span> 无法结账")
            return

        unit_price = self.config.get("unit_price", 47.60)
        price_unit = self.config.get("price_unit", "per_jin")
        total_price = sum(item["price"] for item in self.cart_items)

        # 模式三：传统手动模式 -> 弹出确认/输入餐牌号弹窗
        if self.call_mgr.get_mode() == CallNumberManager.MODE_MANUAL:
            curr = self.call_mgr.peek_next_number()
            val, ok = get_int_input(
                self,
                u"手动指定叫号牌",
                u"【模式三：传统手动模式】\n请输入或确认本次结账的餐牌号码：",
                curr,
                1,
                9999
            )
            if not ok:
                return
            self.call_mgr.set_manual_number(val)

        peek_num = self.call_mgr.peek_next_number()
        call_no_str = "%02d" % peek_num

        items_summary = ", ".join(
            f"{item['name']}({item['tag']})" if item.get("tag") else item["name"]
            for item in self.cart_items
        )

        order_weight = round(sum(float(item.get("weight", 0.0)) for item in self.cart_items if item.get("type") == "soup"), 3)
        sale_data = {
            "shop_name": self.config.get("shop_name", u"杨国福麻辣烫"),
            "shop_subtitle": self.config.get("shop_subtitle", ""),
            "call_no": call_no_str,
            "cart_items": list(self.cart_items),
            "weight_kg": order_weight,
            "unit_price": unit_price,
            "price_unit": price_unit,
            "total_price": total_price,
            "temp_order_no": self.temp_order_no,
            "config": self.config,
            "remark": u"单号:%s 叫号:#%s 项目:%s" % (self.temp_order_no, call_no_str, items_summary)
        }

        from ui.checkout_dialog import CheckoutDialog

        def handle_payment(payment_method):
            import json
            existing = self.db.get_sale_by_order_id(self.current_order_id)
            if existing:
                log_event(CAT_ORDER, "拦截重复结账", "订单标识: %s" % self.current_order_id)
                self._on_clear()
                return True

            actual_num = self.call_mgr.get_next_number()
            sale_data["call_no"] = "%02d" % actual_num
            cart_items_json = json.dumps(sale_data["cart_items"], ensure_ascii=False)
            try:
                record, created = self.db.insert_sale(
                    weight_kg=order_weight,
                    unit_price=unit_price,
                    price_unit=price_unit,
                    total_price=total_price,
                    remark=u"单号:%s 叫号:#%s 项目:%s" % (self.temp_order_no, sale_data["call_no"], items_summary),
                    cart_items_json=cart_items_json,
                    payment_method=payment_method,
                    order_id=self.current_order_id,
                )
            except Exception as exc:
                log_event(CAT_ORDER, "订单入库失败", str(exc))
                show_warning(self, u"订单未完成", u"本地账本写入失败，订单未清空。请检查磁盘和数据库后重试。\n%s" % exc)
                return False
            if not created:
                self._on_clear()
                return True
            log_event(CAT_ORDER, f"订单成交入库: 叫号#{sale_data['call_no']}", f"支付方式: {payment_method} | 实付: ¥{total_price:.2f} | 明细: {items_summary}")

            full_sale = dict(record)
            full_sale.update(sale_data)

            log_event(CAT_USER, f"点击付款结算", f"选择方式: {payment_method} | 应付: ¥{total_price:.2f}")

            try:
                success = self.printer.print_receipt(full_sale)
            except Exception as e:
                success = False
                self.printer.last_error = str(e)

            self.db.mark_print_result(record["id"], success, getattr(self.printer, "last_error", ""))
            self._on_clear()
            self.refresh_call_number_display()

            if success:
                log_event(CAT_PRINT, f"小票驱动出票成功: 叫号#{sale_data['call_no']}", f"出票完成，启动 3 秒全自动退场倒计时")
                parent_mw = self.window()
                if hasattr(parent_mw, 'switch_controller') and parent_mw.switch_controller:
                    parent_mw.switch_controller.on_receipt_printed()
            else:
                err_detail = getattr(self.printer, 'last_error', '') or u"打印机名无效或硬件未连接"
                log_event(CAT_PRINT, f"打印失败", f"错误: {err_detail}")
                show_warning(
                    self,
                    u"打印故障提示",
                    u"小票硬件发送失败，错误详情：\n"
                    f"{err_detail}\n\n"
                    u"请检查打印机驱动名称与物理硬件连接！\n"
                    u"（注：本次消费记录已安全存入本地数据库，不会丢单）"
                )
            return True

        if mode == "SCAN_CODE":
            try:
                from core.shouqianba_sender import send_shouqianba_amount
                send_shouqianba_amount(total_price, self.config)
            except Exception as e:
                print(f"[SaleWidget] 唤起收钱吧金额失败: {e}")

        self._checkout_active = True
        try:
            dlg = CheckoutDialog(sale_data, on_payment_callback=handle_payment, parent=self, mode=mode)
            dlg.exec_()
        finally:
            self._checkout_active = False

    def _on_cash_checkout(self):
        """去现金结账"""
        self._open_checkout_dialog(mode="CASH")

    def _on_clear(self):
        """清空购物车与所有按钮角标"""
        self.cart_items.clear()
        self.selected_item_index = -1
        for b in self.menu_buttons.values():
            b.set_count(0)
        self.temp_order_no = self._gen_temp_order_no()
        self.current_order_id = uuid.uuid4().hex
        self._draft_signature = ""
        clear_draft()
        self._update_price_display()
        
        # 清空购物车时，重置所有自动切换锁，允许即刻重新评估下一碗
        parent_mw = self.window()
        if hasattr(parent_mw, 'switch_controller') and parent_mw.switch_controller:
            parent_mw.switch_controller._last_official_time = 0.0
            parent_mw.switch_controller._has_auto_popped = False
            parent_mw.switch_controller._current_is_private = False

    def cleanup(self):
        if getattr(self, 'scale', None) is not None:
            self.scale.stop()
