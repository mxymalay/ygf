"""
结账模态框 — 左侧经典小票预览 + 右侧精致付款方式按钮 + 出票动画
点击付款按钮后立即 accept() 发送打印指令，随后展示出票动画。
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QGraphicsBlurEffect, QGraphicsOpacityEffect
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve
from PyQt5.QtGui import QColor, QFont


# 结账方式常量
PAYMENT_SCAN = "scan"       # 扫码机器付款
PAYMENT_CASH = "cash"       # 现金付款
PAYMENT_QR   = "qr"         # 收钱吧/二维码/转账

PAYMENT_LABELS = {
    PAYMENT_SCAN: "扫码机器付款",
    PAYMENT_CASH: "现金付款",
    PAYMENT_QR:   "收钱吧/二维码/转账",
}


class CheckoutDialog(QDialog):
    """
    结账模态框：左侧经典小票预览 + 右侧三大付款按钮
    点击付款按钮后**立即** accept()，不等待动画。
    """

    def __init__(self, sale_data, parent=None):
        super().__init__(parent)
        self.sale_data = sale_data
        self.selected_payment_method = ""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        # 外层容器
        self.outer = QFrame(self)
        self.outer.setObjectName("CheckoutOuter")
        self.outer.setStyleSheet(
            "#CheckoutOuter { background: #0F172A; border-radius: 18px; "
            "border: 2px solid #1E293B; }"
        )

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.outer)

        root = QHBoxLayout(self.outer)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ════════════════════════════════════════════════════════════
        # 左侧：经典小票预览区域（复用原 ReceiptPreviewDialog 风格）
        # ════════════════════════════════════════════════════════════
        left_frame = QFrame()
        left_frame.setObjectName("ReceiptLeft")
        left_frame.setStyleSheet(
            "#ReceiptLeft { background: #111827; "
            "border-top-left-radius: 18px; border-bottom-left-radius: 18px; "
            "border-right: 1px solid #1E293B; }"
        )
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        # 小票卡片（虚线边框）
        ticket_card = QFrame()
        ticket_card.setObjectName("TicketCard")
        ticket_card.setStyleSheet(
            "#TicketCard { background: #0F172A; border-radius: 12px; "
            "border: 2px dashed #334155; }"
        )
        tc_layout = QVBoxLayout(ticket_card)
        tc_layout.setContentsMargins(12, 12, 12, 12)
        tc_layout.setSpacing(8)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 5px; background: #1E293B; border-radius: 2px; }"
            "QScrollBar::handle:vertical { background: #475569; border-radius: 2px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        sw_layout = QVBoxLayout(scroll_widget)
        sw_layout.setContentsMargins(4, 4, 4, 4)
        sw_layout.setSpacing(8)

        self._build_receipt_content(sw_layout)

        scroll.setWidget(scroll_widget)
        tc_layout.addWidget(scroll, stretch=1)

        left_layout.addWidget(ticket_card, stretch=1)

        # 底部打印数量提示
        m_count = sum(1 for item in sale_data.get("cart_items", [])
                      if item.get("type") == "soup" or "weight" in item)
        slip_info = f"[打印] 1张顾客单 + {m_count}张后厨制作单"
        lbl_slip = QLabel(slip_info)
        lbl_slip.setAlignment(Qt.AlignCenter)
        lbl_slip.setStyleSheet(
            "background: rgba(52, 211, 153, 0.12); color: #34D399; font-size: 12px; "
            "font-weight: bold; padding: 6px; border-radius: 6px; border: none;"
        )
        left_layout.addWidget(lbl_slip)

        root.addWidget(left_frame, stretch=5)

        # ════════════════════════════════════════════════════════════
        # 右侧：付款方式选择面板
        # ════════════════════════════════════════════════════════════
        right_frame = QFrame()
        right_frame.setObjectName("PaymentRight")
        right_frame.setStyleSheet(
            "#PaymentRight { background: #1E293B; "
            "border-top-right-radius: 18px; border-bottom-right-radius: 18px; }"
        )
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(20, 24, 20, 20)
        right_layout.setSpacing(12)

        # 标题
        lbl_title = QLabel(u"请选择结账方式")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet(
            "font-size: 17px; font-weight: 900; color: #F8FAFC; "
            "border: none; background: transparent; letter-spacing: 2px;"
        )
        right_layout.addWidget(lbl_title)

        # 应收金额
        total_p = sum(i.get("price", 0.0) for i in sale_data.get("cart_items", []))
        lbl_amount = QLabel(f"¥ {total_p:.2f}")
        lbl_amount.setAlignment(Qt.AlignCenter)
        lbl_amount.setStyleSheet(
            "font-size: 32px; font-weight: 900; color: #F97316; "
            "border: none; background: transparent; font-family: 'Segoe UI', monospace;"
        )
        right_layout.addWidget(lbl_amount)

        lbl_amount_sub = QLabel(u"应收金额")
        lbl_amount_sub.setAlignment(Qt.AlignCenter)
        lbl_amount_sub.setStyleSheet(
            "font-size: 12px; color: #64748B; border: none; background: transparent;"
        )
        right_layout.addWidget(lbl_amount_sub)

        right_layout.addSpacing(8)

        # ── 三个竖排精致付款按钮 ──
        btn_configs = [
            (PAYMENT_SCAN, u"💳", u"扫码机器付款", u"已通过POS刷卡/扫码终端付款",
             "#064E3B", "#059669", "#10B981", "#A7F3D0"),
            (PAYMENT_CASH, u"💵", u"现金付款", u"已收到顾客现金",
             "#1E3A5F", "#2563EB", "#3B82F6", "#93C5FD"),
            (PAYMENT_QR,   u"📱", u"收钱吧/二维码/转账", u"已通过微信/支付宝/转账收款",
             "#4C1D95", "#7C3AED", "#8B5CF6", "#DDD6FE"),
        ]

        self.pay_buttons = []
        for method, icon, title, desc, bg_dark, bg_main, bg_hover, fg_accent in btn_configs:
            btn_frame = QFrame()
            btn_frame.setStyleSheet(f"""
                QFrame {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {bg_dark}, stop:1 {bg_main});
                    border-radius: 14px; border: 1px solid {bg_hover};
                }}
            """)
            btn_layout = QHBoxLayout(btn_frame)
            btn_layout.setContentsMargins(16, 14, 16, 14)
            btn_layout.setSpacing(12)

            lbl_icon = QLabel(icon)
            lbl_icon.setStyleSheet("font-size: 30px; border: none; background: transparent;")
            lbl_icon.setFixedWidth(40)
            btn_layout.addWidget(lbl_icon)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            lbl_btn_title = QLabel(title)
            lbl_btn_title.setStyleSheet(
                f"font-size: 16px; font-weight: 900; color: {fg_accent}; "
                "border: none; background: transparent;"
            )
            text_col.addWidget(lbl_btn_title)
            lbl_btn_desc = QLabel(desc)
            lbl_btn_desc.setStyleSheet(
                "font-size: 11px; color: rgba(255,255,255,0.5); "
                "border: none; background: transparent;"
            )
            text_col.addWidget(lbl_btn_desc)
            btn_layout.addLayout(text_col, stretch=1)

            # 覆盖的透明按钮 (全区域可点击)
            overlay_btn = QPushButton("", btn_frame)
            overlay_btn.setCursor(Qt.PointingHandCursor)
            overlay_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                }}
                QPushButton:hover {{
                    background: rgba(255, 255, 255, 0.08);
                    border-radius: 14px;
                }}
                QPushButton:pressed {{
                    background: rgba(255, 255, 255, 0.15);
                    border-radius: 14px;
                }}
            """)
            overlay_btn.clicked.connect(lambda checked, m=method: self._on_payment_selected(m))

            # 让覆盖按钮跟随 frame 大小
            btn_frame.resizeEvent = lambda event, ob=overlay_btn, bf=btn_frame: ob.setGeometry(0, 0, bf.width(), bf.height())

            right_layout.addWidget(btn_frame, stretch=1)
            self.pay_buttons.append(overlay_btn)

        right_layout.addSpacing(4)

        # 取消按钮
        btn_cancel = QPushButton(u"取消结账")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet(
            "QPushButton { background: transparent; color: #64748B; font-weight: bold; "
            "font-size: 13px; border-radius: 8px; padding: 8px 16px; border: 1px solid #334155; }"
            "QPushButton:hover { background: #374151; color: #F87171; border-color: #7F1D1D; }"
        )
        btn_cancel.clicked.connect(self._on_cancel)
        right_layout.addWidget(btn_cancel)

        root.addWidget(right_frame, stretch=3)

    def _build_receipt_content(self, layout):
        """生成经典风格小票票面内容（复用 ReceiptPreviewDialog 原有设计）"""
        sd = self.sale_data

        # Header
        lbl_top = QLabel("POS点餐  堂食")
        lbl_top.setAlignment(Qt.AlignCenter)
        lbl_top.setStyleSheet("font-size: 13px; font-weight: bold; color: #94A3B8; border: none;")
        layout.addWidget(lbl_top)

        lbl_shop = QLabel(sd.get("shop_name", u"杨国福麻辣烫"))
        lbl_shop.setAlignment(Qt.AlignCenter)
        lbl_shop.setStyleSheet("font-size: 19px; font-weight: 900; color: #F9FAFB; border: none;")
        layout.addWidget(lbl_shop)

        sub_title = sd.get("shop_subtitle", "")
        if sub_title:
            if not sub_title.startswith(u"门店名称："):
                sub_title = u"门店名称：" + sub_title
            lbl_sub = QLabel(sub_title)
            lbl_sub.setAlignment(Qt.AlignCenter)
            lbl_sub.setStyleSheet("font-size: 12px; color: #9CA3AF; border: none;")
            layout.addWidget(lbl_sub)

        # 叫号大牌
        call_no_box = QFrame()
        call_no_box.setStyleSheet("background: rgba(249, 115, 22, 0.15); border-radius: 10px; padding: 4px;")
        cn_layout = QVBoxLayout(call_no_box)
        lbl_call = QLabel(f"取餐号: {sd.get('call_no', '050')}")
        lbl_call.setAlignment(Qt.AlignCenter)
        lbl_call.setStyleSheet("font-size: 24px; font-weight: 900; color: #F97316; border: none;")
        cn_layout.addWidget(lbl_call)
        layout.addWidget(call_no_box)

        # 虚线分隔
        self._add_sep(layout)

        # 细项表头
        hdr_w = QWidget()
        hdr_w.setStyleSheet("background: transparent; border: none;")
        hdr_l = QHBoxLayout(hdr_w)
        hdr_l.setContentsMargins(0, 0, 0, 0)
        l_name = QLabel("菜品名")
        l_name.setStyleSheet("font-size: 12px; font-weight: bold; color: #64748B;")
        hdr_l.addWidget(l_name, stretch=1)
        for t in ["规格", "单价", "数量", "小计"]:
            l = QLabel(t)
            l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            l.setStyleSheet("font-size: 12px; font-weight: bold; color: #64748B;")
            l.setFixedWidth(45)
            hdr_l.addWidget(l)
        layout.addWidget(hdr_w)

        # 商品明细
        cart_items = sd.get("cart_items", [])
        m_count = 0
        for item in cart_items:
            is_soup = (item.get("type") == "soup" or "weight" in item)
            name_str = item.get("name", "")
            tag_str = item.get("tag", "")

            item_box = QVBoxLayout()
            item_box.setSpacing(2)

            if is_soup:
                m_count += 1
                title_lbl = QLabel(f"【制{m_count}】{name_str}")
                title_lbl.setStyleSheet("font-size: 14px; font-weight: 900; color: #F8FAFC; border: none;")
                item_box.addWidget(title_lbl)

                w_val = item.get("weight", sd.get("weight_kg", 0.0))
                p_val = item.get("unit_price", sd.get("unit_price", 47.60))
                sub_total = item.get("price", 0.0)

                det_w = QWidget()
                det_l = QHBoxLayout(det_w)
                det_l.setContentsMargins(0, 0, 0, 0)
                det_l.addStretch(1)
                for t in ["KG", f"{p_val:.2f}", f"{w_val:.3f}", f"{sub_total:.2f}"]:
                    l = QLabel(t)
                    l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    l.setStyleSheet("font-size: 13px; color: #F59E0B; font-family: monospace; border: none;")
                    l.setFixedWidth(45)
                    det_l.addWidget(l)
                item_box.addWidget(det_w)
            else:
                title_lbl = QLabel(name_str)
                title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #E2E8F0; border: none;")
                item_box.addWidget(title_lbl)

                qty = item.get("qty", 1)
                unit_label = item.get("unit", "份")
                base_p = item.get("base_price", item.get("price", 0.0) / max(1, qty))
                sub_total = item.get("price", 0.0)

                det_w = QWidget()
                det_l = QHBoxLayout(det_w)
                det_l.setContentsMargins(0, 0, 0, 0)
                det_l.addStretch(1)
                for t in [unit_label, f"{base_p:.2f}", f"{qty}", f"{sub_total:.2f}"]:
                    l = QLabel(t)
                    l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    l.setStyleSheet("font-size: 13px; color: #F59E0B; font-family: monospace; border: none;")
                    l.setFixedWidth(45)
                    det_l.addWidget(l)
                item_box.addWidget(det_w)

            if tag_str:
                lbl_tag = QLabel(f"  {tag_str}")
                lbl_tag.setStyleSheet("font-size: 12px; color: #34D399; font-weight: bold; border: none;")
                item_box.addWidget(lbl_tag)

            layout.addLayout(item_box)

        self._add_sep(layout)

        # 合计金额
        total_p = sum(i.get("price", 0.0) for i in cart_items)
        lbl_total = QLabel(f"应收金额：￥{total_p:.2f}")
        lbl_total.setAlignment(Qt.AlignRight)
        lbl_total.setStyleSheet("font-size: 20px; font-weight: 900; color: #34D399; border: none;")
        layout.addWidget(lbl_total)

    def _add_sep(self, layout):
        lbl = QLabel("----------------------------------------")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #475569; font-family: monospace; border: none;")
        layout.addWidget(lbl)

    def _on_payment_selected(self, method):
        """用户点击付款方式 → 立即 accept 发送打印指令"""
        self.selected_payment_method = method
        self.accept()

    def _on_cancel(self):
        self.reject()

    def exec_(self):
        parent_w = self.parent()
        if parent_w and hasattr(parent_w, 'window'):
            parent_w = parent_w.window()

        screen_h = 768
        screen_w = 1024
        if parent_w:
            screen_h = parent_w.height()
            screen_w = parent_w.width()
            try:
                blur = QGraphicsBlurEffect(parent_w)
                blur.setBlurRadius(42)
                parent_w.setGraphicsEffect(blur)
            except Exception:
                pass

        dlg_h = min(600, max(440, screen_h - 60))
        dlg_w = min(780, max(600, screen_w - 200))
        self.setFixedSize(dlg_w, dlg_h)

        try:
            return super().exec_()
        finally:
            if parent_w:
                try:
                    parent_w.setGraphicsEffect(None)
                except Exception:
                    pass


class ReceiptFlyToast(QDialog):
    """
    打印成功后的轻量级出票飞出动画 Toast（非阻塞，自动关闭）
    """

    def __init__(self, payment_label="", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(False)

        card = QFrame(self)
        card.setStyleSheet(
            "QFrame { background: #0F172A; border-radius: 16px; "
            "border: 2px solid #10B981; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(30, 24, 30, 24)
        inner.setSpacing(10)

        lbl_icon = QLabel(u"🖨️")
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet("font-size: 48px; border: none; background: transparent;")
        inner.addWidget(lbl_icon)

        lbl_msg = QLabel(u"出票成功！")
        lbl_msg.setAlignment(Qt.AlignCenter)
        lbl_msg.setStyleSheet(
            "font-size: 20px; font-weight: 900; color: #10B981; "
            "border: none; background: transparent;"
        )
        inner.addWidget(lbl_msg)

        if payment_label:
            lbl_pm = QLabel(payment_label)
            lbl_pm.setAlignment(Qt.AlignCenter)
            lbl_pm.setStyleSheet(
                "font-size: 14px; color: #94A3B8; border: none; background: transparent;"
            )
            inner.addWidget(lbl_pm)

        self.setFixedSize(260, 180)

        # 2.5秒后自动关闭
        QTimer.singleShot(2500, self.close)

    def showEvent(self, event):
        super().showEvent(event)
        # 居中在父窗口
        parent_w = self.parent()
        if parent_w and hasattr(parent_w, 'window'):
            parent_w = parent_w.window()
        if parent_w:
            geo = parent_w.geometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
