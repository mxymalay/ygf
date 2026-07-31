# -*- coding: utf-8 -*-
"""
POS 现代极简风格统一弹窗组件 (去系统原生框、圆角、无缝高颜值对话框)
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSpinBox,
    QGraphicsBlurEffect
)

class ModernDialog(QDialog):
    """现代风通用提示与确认对话框"""

    TYPE_INFO = "info"
    TYPE_WARNING = "warning"
    TYPE_QUESTION = "question"

    def __init__(self, title, message, dialog_type=TYPE_INFO, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        self.result_choice = False

        # 主卡片容器
        card = QFrame(self)
        card.setObjectName("DialogCard")
        card.setStyleSheet(
            "QFrame#DialogCard { background: #1E293B; border-radius: 16px; "
            "border: 1px solid #334155; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(16)

        # 头部标题与图标
        head_box = QHBoxLayout()
        head_box.setSpacing(10)

        icon_lbl = QLabel()
        if dialog_type == self.TYPE_WARNING:
            icon_lbl.setText("⚠️")
            icon_lbl.setStyleSheet("font-size: 24px; border: none; background: transparent;")
        elif dialog_type == self.TYPE_QUESTION:
            icon_lbl.setText("❓")
            icon_lbl.setStyleSheet("font-size: 24px; border: none; background: transparent;")
        else:
            icon_lbl.setText("ℹ️")
            icon_lbl.setStyleSheet("font-size: 24px; border: none; background: transparent;")

        head_box.addWidget(icon_lbl)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 17px; font-weight: bold; color: #F9FAFB; border: none; background: transparent;")
        head_box.addWidget(lbl_title, stretch=1)

        card_layout.addLayout(head_box)

        # 内容消息文本
        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("font-size: 14px; color: #9CA3AF; border: none; background: transparent; line-height: 1.4;")
        card_layout.addWidget(lbl_msg)

        card_layout.addSpacing(4)

        # 底部按钮栏
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        if dialog_type == self.TYPE_QUESTION:
            btn_no = QPushButton("取消")
            btn_no.setCursor(Qt.PointingHandCursor)
            btn_no.setStyleSheet(
                "QPushButton { background: #334155; color: #9CA3AF; font-weight: bold; font-size: 14px; "
                "border-radius: 8px; padding: 8px 18px; border: 1px solid #475569; }"
                "QPushButton:hover { background: #475569; color: #FFFFFF; }"
            )
            btn_no.clicked.connect(self._on_cancel)
            btn_box.addWidget(btn_no)

            btn_yes = QPushButton("确定")
            btn_yes.setCursor(Qt.PointingHandCursor)
            btn_yes.setStyleSheet(
                "QPushButton { background: #EA580C; color: white; font-weight: bold; font-size: 14px; "
                "border-radius: 8px; padding: 8px 22px; border: 1px solid #F97316; }"
                "QPushButton:hover { background: #F97316; }"
            )
            btn_yes.clicked.connect(self._on_confirm)
            btn_box.addWidget(btn_yes)
        else:
            btn_ok = QPushButton("好的")
            btn_ok.setCursor(Qt.PointingHandCursor)
            btn_ok.setStyleSheet(
                "QPushButton { background: #EA580C; color: white; font-weight: bold; font-size: 14px; "
                "border-radius: 8px; padding: 8px 24px; border: 1px solid #F97316; }"
                "QPushButton:hover { background: #F97316; }"
            )
            btn_ok.clicked.connect(self.accept)
            btn_box.addWidget(btn_ok)

        card_layout.addLayout(btn_box)
        self.resize(360, 200)

    def _on_confirm(self):
        self.result_choice = True
        self.accept()

    def _on_cancel(self):
        self.result_choice = False
        self.reject()

    def exec_(self):
        parent_w = self.parent()
        if parent_w and hasattr(parent_w, 'window'):
            parent_w = parent_w.window()
        
        if parent_w:
            try:
                blur = QGraphicsBlurEffect(parent_w)
                blur.setBlurRadius(16)
                parent_w.setGraphicsEffect(blur)
            except Exception:
                pass

        try:
            return super().exec_()
        finally:
            if parent_w:
                try:
                    parent_w.setGraphicsEffect(None)
                except Exception:
                    pass


class ModernInputDialog(QDialog):
    """现代风数字与文本输入对话框 (代替原生 QInputDialog)"""

    def __init__(self, title, message, value=1, min_val=1, max_val=9999, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        self.input_value = value
        self.confirmed = False

        card = QFrame(self)
        card.setObjectName("DialogCard")
        card.setStyleSheet(
            "QFrame#DialogCard { background: #1E293B; border-radius: 16px; "
            "border: 1px solid #334155; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(16)

        # 标题
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 17px; font-weight: bold; color: #F9FAFB; border: none; background: transparent;")
        card_layout.addWidget(lbl_title)

        # 提示词
        lbl_msg = QLabel(message)
        lbl_msg.setStyleSheet("font-size: 14px; color: #9CA3AF; border: none; background: transparent;")
        card_layout.addWidget(lbl_msg)

        # 输入框
        self.spin = QSpinBox()
        self.spin.setRange(min_val, max_val)
        self.spin.setValue(value)
        self.spin.setStyleSheet(
            "QSpinBox { background: #0F172A; color: #F97316; font-size: 20px; font-weight: bold; "
            "border: 1.5px solid #EA580C; border-radius: 8px; padding: 6px 12px; font-family: 'Consolas', monospace; }"
        )
        card_layout.addWidget(self.spin)

        card_layout.addSpacing(6)

        # 按钮栏
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet(
            "QPushButton { background: #334155; color: #9CA3AF; font-weight: bold; font-size: 14px; "
            "border-radius: 8px; padding: 8px 18px; border: 1px solid #475569; }"
            "QPushButton:hover { background: #475569; color: #FFFFFF; }"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_ok = QPushButton("确认调整")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setStyleSheet(
            "QPushButton { background: #EA580C; color: white; font-weight: bold; font-size: 14px; "
            "border-radius: 8px; padding: 8px 22px; border: 1px solid #F97316; }"
            "QPushButton:hover { background: #F97316; }"
        )
        btn_ok.clicked.connect(self._on_ok)
        btn_box.addWidget(btn_ok)

        card_layout.addLayout(btn_box)
        self.resize(360, 220)

    def _on_ok(self):
        self.input_value = self.spin.value()
        self.confirmed = True
        self.accept()


# 便捷调用的封装函数
def show_info(parent, title, message):
    dlg = ModernDialog(title, message, ModernDialog.TYPE_INFO, parent)
    dlg.exec_()

def show_warning(parent, title, message):
    dlg = ModernDialog(title, message, ModernDialog.TYPE_WARNING, parent)
    dlg.exec_()

def show_question(parent, title, message) -> bool:
    dlg = ModernDialog(title, message, ModernDialog.TYPE_QUESTION, parent)
    dlg.exec_()
    return dlg.result_choice

def get_int_input(parent, title, message, value=1, min_val=1, max_val=9999):
    dlg = ModernInputDialog(title, message, value, min_val, max_val, parent)
    res = dlg.exec_()
    return dlg.input_value, (res == QDialog.Accepted)


class ReceiptPreviewDialog(QDialog):
    """小票模拟预览与确认打票对话框 (含闪烁收款提醒 & 10 秒倒计时)"""

    def __init__(self, sale_data, countdown_sec=10, parent=None):
        super().__init__(parent)
        self.sale_data = sale_data
        self.countdown = countdown_sec
        self._flash_flag = False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        card = QFrame(self)
        card.setObjectName("ReceiptCard")
        card.setStyleSheet(
            "QFrame#ReceiptCard { background: #0F172A; border-radius: 16px; "
            "border: 2px dashed #334155; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(10)

        # 0. 闪烁收款提醒 Banner
        self.notice_banner = QLabel(u"⚠️ 请确认已通过其他工具完成收款！")
        self.notice_banner.setAlignment(Qt.AlignCenter)
        self.notice_banner.setStyleSheet(
            "background: #DC2626; color: #FFFFFF; font-size: 15px; font-weight: 900; "
            "padding: 10px; border-radius: 8px; border: none;"
        )
        card_layout.addWidget(self.notice_banner)

        # 1. 模拟小票 Header
        lbl_shop = QLabel(sale_data.get("shop_name", u"杨国福麻辣烫"))
        lbl_shop.setAlignment(Qt.AlignCenter)
        lbl_shop.setStyleSheet("font-size: 20px; font-weight: 900; color: #F9FAFB; border: none;")
        card_layout.addWidget(lbl_shop)

        sub_title = sale_data.get("shop_subtitle", "")
        if sub_title:
            lbl_sub = QLabel(sub_title)
            lbl_sub.setAlignment(Qt.AlignCenter)
            lbl_sub.setStyleSheet("font-size: 13px; color: #9CA3AF; border: none;")
            card_layout.addWidget(lbl_sub)

        # 叫号大牌
        call_no_box = QFrame()
        call_no_box.setStyleSheet("background: rgba(249, 115, 22, 0.15); border-radius: 10px; padding: 6px;")
        cn_layout = QVBoxLayout(call_no_box)
        lbl_call = QLabel(f"取餐叫号: #{sale_data.get('call_no', '01')}")
        lbl_call.setAlignment(Qt.AlignCenter)
        lbl_call.setStyleSheet("font-size: 26px; font-weight: 900; color: #F97316; border: none;")
        cn_layout.addWidget(lbl_call)
        card_layout.addWidget(call_no_box)

        # 虚线分隔
        line1 = QLabel("----------------------------------------")
        line1.setAlignment(Qt.AlignCenter)
        line1.setStyleSheet("color: #475569; font-family: monospace; border: none;")
        card_layout.addWidget(line1)

        # 商品明细
        items_layout = QVBoxLayout()
        items_layout.setSpacing(4)
        for item in sale_data.get("cart_items", []):
            item_row = QHBoxLayout()
            name_str = item["name"]
            tag_str = item.get("tag", "")
            if tag_str:
                name_str += f" ({tag_str})"
            
            lbl_name = QLabel(name_str)
            lbl_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #E2E8F0; border: none;")
            
            qty = item.get("qty", 1)
            price_val = item.get("price", 0.0)
            lbl_price = QLabel(f"x{qty}  ￥{price_val:.2f}")
            lbl_price.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl_price.setStyleSheet("font-size: 14px; font-weight: bold; color: #F59E0B; border: none;")
            
            item_row.addWidget(lbl_name, stretch=1)
            item_row.addWidget(lbl_price)
            items_layout.addLayout(item_row)

        card_layout.addLayout(items_layout)

        line2 = QLabel("----------------------------------------")
        line2.setAlignment(Qt.AlignCenter)
        line2.setStyleSheet("color: #475569; font-family: monospace; border: none;")
        card_layout.addWidget(line2)

        # 金额与时间
        total_p = sum(i.get("price", 0.0) for i in sale_data.get("cart_items", []))
        lbl_total = QLabel(f"实收金额：￥{total_p:.2f}")
        lbl_total.setAlignment(Qt.AlignRight)
        lbl_total.setStyleSheet("font-size: 22px; font-weight: 900; color: #34D399; border: none;")
        card_layout.addWidget(lbl_total)

        card_layout.addSpacing(10)

        # 2. 底部操作按钮
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        self.btn_cancel = QPushButton("取消打票")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background: #334155; color: #F87171; font-weight: bold; font-size: 15px; "
            "border-radius: 10px; padding: 12px 20px; border: 1px solid #7F1D1D; }"
            "QPushButton:hover { background: #7F1D1D; color: #FFFFFF; }"
        )
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_box.addWidget(self.btn_cancel, stretch=1)

        self.btn_print = QPushButton(f"立即打票 ({self.countdown}s)")
        self.btn_print.setCursor(Qt.PointingHandCursor)
        self.btn_print.setStyleSheet(
            "QPushButton { background: #EA580C; color: white; font-weight: bold; font-size: 15px; "
            "border-radius: 10px; padding: 12px 24px; border: 1px solid #F97316; }"
            "QPushButton:hover { background: #F97316; }"
        )
        self.btn_print.clicked.connect(self._on_print_now)
        btn_box.addWidget(self.btn_print, stretch=2)

        card_layout.addLayout(btn_box)
        self.resize(420, 520)

        # 3. 定时器: 倒计时 Timer & 高亮闪烁 Timer
        from PyQt5.QtCore import QTimer
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        self.flash_timer = QTimer(self)
        self.flash_timer.setInterval(500)
        self.flash_timer.timeout.connect(self._flash_tick)
        self.flash_timer.start()

    def _flash_tick(self):
        self._flash_flag = not self._flash_flag
        if self._flash_flag:
            self.notice_banner.setStyleSheet(
                "background: #EF4444; color: #FFFFFF; font-size: 15px; font-weight: 900; "
                "padding: 10px; border-radius: 8px; border: none;"
            )
        else:
            self.notice_banner.setStyleSheet(
                "background: #7F1D1D; color: #FEF08A; font-size: 15px; font-weight: 900; "
                "padding: 10px; border-radius: 8px; border: none;"
            )

    def _stop_all_timers(self):
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
        if hasattr(self, 'flash_timer') and self.flash_timer.isActive():
            self.flash_timer.stop()

    def _tick(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.btn_print.setText(f"立即打票 ({self.countdown}s)")
        else:
            self._stop_all_timers()
            self._on_print_now()

    def _on_print_now(self):
        self._stop_all_timers()
        self.accept()

    def _on_cancel(self):
        self._stop_all_timers()
        self.reject()

    def exec_(self):
        parent_w = self.parent()
        if parent_w and hasattr(parent_w, 'window'):
            parent_w = parent_w.window()
        
        if parent_w:
            try:
                blur = QGraphicsBlurEffect(parent_w)
                blur.setBlurRadius(16)
                parent_w.setGraphicsEffect(blur)
            except Exception:
                pass

        try:
            return super().exec_()
        finally:
            if parent_w:
                try:
                    parent_w.setGraphicsEffect(None)
                except Exception:
                    pass
