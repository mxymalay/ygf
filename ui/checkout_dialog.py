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
    PAYMENT_SCAN: "主扫",
    PAYMENT_CASH: "现金",
    PAYMENT_QR:   "被扫",
}


class CheckoutDialog(QDialog):
    """
    结账模态框：左侧经典小票预览 + 右侧三大付款按钮
    点击付款按钮后**立即** accept()，不等待动画。
    """

    def __init__(self, sale_data, parent=None, on_payment_callback=None):
        super().__init__(parent)
        self.sale_data = sale_data
        self.on_payment_callback = on_payment_callback
        self.selected_payment_method = ""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        # 外层容器：使用极低透明度(alpha=1)替代完全透明，以确保系统能捕获到鼠标点击事件
        self.outer = QFrame(self)
        self.outer.setObjectName("CheckoutOuter")
        self.outer.setStyleSheet(
            "#CheckoutOuter { background: rgba(0, 0, 0, 0.01); border: none; }"
        )

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.outer)

        wrapper_layout = QHBoxLayout(self.outer)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        
        self.inner_container = QWidget()
        self.inner_container.setStyleSheet("background: transparent;")
        wrapper_layout.addWidget(self.inner_container, alignment=Qt.AlignCenter)

        root = QHBoxLayout(self.inner_container)
        root.setContentsMargins(30, 20, 30, 20)
        root.setSpacing(40)

        # ════════════════════════════════════════════════════════════
        # 左侧：经典小票预览区域（复用原 ReceiptPreviewDialog 风格）
        # ════════════════════════════════════════════════════════════
        left_frame = QFrame()
        left_frame.setObjectName("ReceiptLeft")
        left_frame.setStyleSheet(
            "#ReceiptLeft { background: #FFFFFF; "
            "border-radius: 18px; border: 1px solid #E2E8F0; }"
        )
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        # 小票卡片（虚线边框）
        ticket_card = QFrame()
        ticket_card.setObjectName("TicketCard")
        ticket_card.setStyleSheet(
            "#TicketCard { background: #F8FAFC; border-radius: 12px; "
            "border: 2px dashed #CBD5E1; }"
        )
        tc_layout = QVBoxLayout(ticket_card)
        tc_layout.setContentsMargins(12, 12, 12, 12)
        tc_layout.setSpacing(8)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 5px; background: #F1F5F9; border-radius: 2px; }"
            "QScrollBar::handle:vertical { background: #CBD5E1; border-radius: 2px; }"
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

        # 固定的底部合计（不随滚动条滚动）
        self._add_sep(tc_layout)
        
        cart_items = sale_data.get("cart_items", [])
        total_p = sum(i.get("price", 0.0) for i in cart_items)
        lbl_total = QLabel(f"应收金额：￥{total_p:.2f}")
        lbl_total.setAlignment(Qt.AlignRight)
        lbl_total.setStyleSheet("font-size: 26px; font-weight: bold; color: #059669; border: none;")
        tc_layout.addWidget(lbl_total)

        left_layout.addWidget(ticket_card, stretch=1)

        # 底部打印数量提示
        m_count = sum(1 for item in sale_data.get("cart_items", [])
                      if item.get("type") == "soup" or "weight" in item)
        slip_info = f"[打印] 1张顾客单 + {m_count}张后厨制作单"
        lbl_slip = QLabel(slip_info)
        lbl_slip.setAlignment(Qt.AlignCenter)
        lbl_slip.setStyleSheet(
            "background: rgba(16, 185, 129, 0.1); color: #059669; font-size: 12px; "
            "font-weight: bold; padding: 6px; border-radius: 6px; border: none;"
        )
        left_layout.addWidget(lbl_slip)

        self.receipt_container = left_frame
        root.addWidget(self.receipt_container, stretch=5)

        # ════════════════════════════════════════════════════════════
        # 右侧：付款方式选择面板（仅按钮悬浮）
        # ════════════════════════════════════════════════════════════
        right_frame = QFrame()
        right_frame.setObjectName("PaymentRight")
        right_frame.setStyleSheet(
            "#PaymentRight { background: transparent; border: none; }"
        )
        self.right_panel = right_frame
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(16)
        right_layout.setAlignment(Qt.AlignCenter)

        # ── 三个竖排精致付款按钮 ──
        btn_configs = [
            (PAYMENT_SCAN, u"💳", u"主扫", u"已通过POS/扫码终端主动扫码",
             "#064E3B", "#059669", "#10B981", "#A7F3D0"),
            (PAYMENT_CASH, u"💵", u"现金", u"已收到顾客现金",
             "#1E3A5F", "#2563EB", "#3B82F6", "#93C5FD"),
            (PAYMENT_QR,   u"📱", u"被扫", u"顾客已扫描收钱吧/微信/支付宝二维码",
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
            lbl_icon.setStyleSheet("font-size: 46px; border: none; background: transparent;")
            lbl_icon.setFixedWidth(56)
            btn_layout.addWidget(lbl_icon)

            text_col = QVBoxLayout()
            text_col.setSpacing(6)
            text_col.addStretch()

            lbl_btn_title = QLabel(title)
            lbl_btn_title.setStyleSheet(
                f"font-size: 24px; font-weight: 900; color: {fg_accent}; "
                "border: none; background: transparent;"
            )
            text_col.addWidget(lbl_btn_title)

            lbl_btn_desc = QLabel(desc)
            lbl_btn_desc.setStyleSheet(
                "font-size: 13px; color: rgba(255,255,255,0.65); "
                "border: none; background: transparent;"
            )
            text_col.addWidget(lbl_btn_desc)

            text_col.addStretch()
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

        root.addWidget(right_frame, stretch=3)

    def _build_receipt_content(self, layout):
        """生成经典风格小票票面内容（复用 ReceiptPreviewDialog 原有设计）"""
        sd = self.sale_data

        # Header
        lbl_top = QLabel("POS点餐  堂食")
        lbl_top.setAlignment(Qt.AlignCenter)
        lbl_top.setStyleSheet("font-size: 13px; font-weight: bold; color: #64748B; border: none;")
        layout.addWidget(lbl_top)

        lbl_shop = QLabel(sd.get("shop_name", u"杨国福麻辣烫"))
        lbl_shop.setAlignment(Qt.AlignCenter)
        lbl_shop.setStyleSheet("font-size: 19px; font-weight: 900; color: #0F172A; border: none;")
        layout.addWidget(lbl_shop)

        sub_title = sd.get("shop_subtitle", "")
        if sub_title:
            if not sub_title.startswith(u"门店名称："):
                sub_title = u"门店名称：" + sub_title
            lbl_sub = QLabel(sub_title)
            lbl_sub.setAlignment(Qt.AlignCenter)
            lbl_sub.setStyleSheet("font-size: 12px; color: #64748B; border: none;")
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

            item_row = QHBoxLayout()
            item_row.setContentsMargins(0, 0, 0, 0)
            item_row.setSpacing(4)

            if is_soup:
                m_count += 1
                title_lbl = QLabel(f"【制{m_count}】{name_str}")
                title_lbl.setStyleSheet("font-size: 14px; font-weight: 900; color: #0F172A; border: none;")
                item_row.addWidget(title_lbl, stretch=1)

                w_val = item.get("weight", sd.get("weight_kg", 0.0))
                p_val = item.get("unit_price", sd.get("unit_price", 47.60))
                sub_total = item.get("price", 0.0)

                for t in ["KG", f"{p_val:.2f}", f"{w_val:.3f}", f"{sub_total:.2f}"]:
                    l = QLabel(t)
                    l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    l.setStyleSheet("font-size: 13px; color: #D97706; font-family: monospace; border: none;")
                    l.setFixedWidth(45)
                    item_row.addWidget(l)
            else:
                title_lbl = QLabel(name_str)
                title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #1E293B; border: none;")
                item_row.addWidget(title_lbl, stretch=1)

                qty = item.get("qty", 1)
                unit_label = item.get("unit", "份")
                base_p = item.get("base_price", item.get("price", 0.0) / max(1, qty))
                sub_total = item.get("price", 0.0)

                for t in [unit_label, f"{base_p:.2f}", f"{qty}", f"{sub_total:.2f}"]:
                    l = QLabel(t)
                    l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    l.setStyleSheet("font-size: 13px; color: #D97706; font-family: monospace; border: none;")
                    l.setFixedWidth(45)
                    item_row.addWidget(l)

            item_box.addLayout(item_row)

            if tag_str:
                lbl_tag = QLabel(f"  {tag_str}")
                lbl_tag.setStyleSheet("font-size: 12px; color: #059669; font-weight: bold; border: none;")
                item_box.addWidget(lbl_tag)

            layout.addLayout(item_box)


    def _add_sep(self, layout):
        lbl = QLabel("----------------------------------------")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #CBD5E1; font-family: monospace; border: none;")
        layout.addWidget(lbl)

    def _on_payment_selected(self, method):
        """用户点击付款方式 → 立即发送打印指令，同时触发飞出动画"""
        self.selected_payment_method = method
        
        # 禁用所有按钮，防止重复点击
        for btn in self.pay_buttons:
            btn.setEnabled(False)
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; }"
            )

        # 立即回调发送打印指令
        if self.on_payment_callback:
            self.on_payment_callback(method)

        # 启动飞出动画
        QTimer.singleShot(100, self._start_fly_animation)

    def _start_fly_animation(self):
        """小票飞出动画，同时右侧面板淡出，2秒后自动 accept"""
        self.opacity_effect = QGraphicsOpacityEffect(self.receipt_container)
        self.receipt_container.setGraphicsEffect(self.opacity_effect)

        # 向上飞出位移
        self.pos_anim = QPropertyAnimation(self.receipt_container, b"pos")
        self.pos_anim.setDuration(2000)
        start_pos = self.receipt_container.pos()
        end_pos = QPoint(start_pos.x(), start_pos.y() - 350)
        self.pos_anim.setStartValue(start_pos)
        self.pos_anim.setEndValue(end_pos)
        self.pos_anim.setEasingCurve(QEasingCurve.InBack)

        # 渐隐透明度 (左侧小票)
        self.opa_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opa_anim.setDuration(2000)
        self.opa_anim.setStartValue(1.0)
        self.opa_anim.setEndValue(0.0)
        self.opa_anim.setEasingCurve(QEasingCurve.InCubic)

        # 右侧面板快速淡出
        self.right_opacity = QGraphicsOpacityEffect(self.right_panel)
        self.right_panel.setGraphicsEffect(self.right_opacity)
        self.right_opa_anim = QPropertyAnimation(self.right_opacity, b"opacity")
        self.right_opa_anim.setDuration(800)
        self.right_opa_anim.setStartValue(1.0)
        self.right_opa_anim.setEndValue(0.0)

        self.pos_anim.start()
        self.opa_anim.start()
        self.right_opa_anim.start()

        # 动画结束后自动关闭模态框
        QTimer.singleShot(2100, self.accept)

    def mousePressEvent(self, event):
        # 如果点击了空白处（没有点到小票或按钮），则取消结账
        child = self.childAt(event.pos())
        if not child or child == self.outer or child == self.inner_container or child == self.right_panel:
            self.reject()
        else:
            super().mousePressEvent(event)

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
                blur.setBlurRadius(65)
                parent_w.setGraphicsEffect(blur)
            except Exception:
                pass

        dlg_h = min(600, max(440, screen_h - 60))
        dlg_w = min(880, max(600, screen_w - 120))
        self.inner_container.setFixedSize(dlg_w, dlg_h)
        self.setFixedSize(screen_w, screen_h)

        try:
            return super().exec_()
        finally:
            if parent_w:
                try:
                    parent_w.setGraphicsEffect(None)
                except Exception:
                    pass
