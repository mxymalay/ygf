"""
结账模态框 — 左侧小票预览 + 右侧付款方式选择 + 小票飞出动画
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QGraphicsOpacityEffect
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QEasingCurve, QPoint
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
    结账模态框：左侧小票预览 + 右侧三大付款按钮
    用户点击任意按钮后播放小票飞出动画，3秒后自动 accept。
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
            "#CheckoutOuter { background: #0F172A; border-radius: 16px; border: 2px solid #334155; }"
        )

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.outer)

        root = QHBoxLayout(self.outer)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ──────── 左侧：小票预览区域 ────────
        self.receipt_container = QFrame()
        self.receipt_container.setStyleSheet(
            "QFrame { background: #111827; border-top-left-radius: 16px; "
            "border-bottom-left-radius: 16px; border: none; }"
        )
        left_layout = QVBoxLayout(self.receipt_container)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(8)

        lbl_receipt_title = QLabel(u"📄 小票预览")
        lbl_receipt_title.setAlignment(Qt.AlignCenter)
        lbl_receipt_title.setStyleSheet(
            "font-size: 15px; font-weight: 900; color: #94A3B8; border: none; background: transparent;"
        )
        left_layout.addWidget(lbl_receipt_title)

        # 滚动小票内容
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
        sw_layout.setContentsMargins(8, 8, 8, 8)
        sw_layout.setSpacing(6)

        self._build_receipt_content(sw_layout)

        scroll.setWidget(scroll_widget)
        left_layout.addWidget(scroll, stretch=1)

        root.addWidget(self.receipt_container, stretch=5)

        # ──────── 右侧：付款方式按钮区域 ────────
        right_panel = QFrame()
        right_panel.setStyleSheet(
            "QFrame { background: #1E293B; border-top-right-radius: 16px; "
            "border-bottom-right-radius: 16px; border: none; }"
        )
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 20, 16, 20)
        right_layout.setSpacing(14)

        lbl_pay_title = QLabel(u"选择结账方式")
        lbl_pay_title.setAlignment(Qt.AlignCenter)
        lbl_pay_title.setStyleSheet(
            "font-size: 16px; font-weight: 900; color: #F8FAFC; border: none; background: transparent;"
        )
        right_layout.addWidget(lbl_pay_title)

        total_p = sum(i.get("price", 0.0) for i in sale_data.get("cart_items", []))
        lbl_amount = QLabel(f"应收：¥ {total_p:.2f}")
        lbl_amount.setAlignment(Qt.AlignCenter)
        lbl_amount.setStyleSheet(
            "font-size: 22px; font-weight: 900; color: #F97316; border: none; background: transparent;"
        )
        right_layout.addWidget(lbl_amount)

        right_layout.addSpacing(6)

        # 三个竖排大按钮
        btn_configs = [
            (PAYMENT_SCAN, u"💳\n\n已扫码机器付款", "#059669", "#10B981"),
            (PAYMENT_CASH, u"💵\n\n已现金付款", "#2563EB", "#3B82F6"),
            (PAYMENT_QR,   u"📱\n\n已收钱吧/二维码\n/转账付款", "#7C3AED", "#8B5CF6"),
        ]

        self.pay_buttons = []
        for method, text, bg_color, hover_color in btn_configs:
            btn = QPushButton(text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {bg_color}; color: white; font-weight: 900; font-size: 16px;
                    border-radius: 12px; border: none; padding: 14px 8px;
                    min-height: 90px;
                }}
                QPushButton:hover {{ background: {hover_color}; }}
                QPushButton:pressed {{ background: {bg_color}; }}
            """)
            btn.clicked.connect(lambda checked, m=method: self._on_payment_selected(m))
            right_layout.addWidget(btn, stretch=1)
            self.pay_buttons.append(btn)

        right_layout.addSpacing(6)

        # 取消按钮
        btn_cancel = QPushButton(u"✕ 取消结账")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet(
            "QPushButton { background: #374151; color: #F87171; font-weight: bold; font-size: 14px; "
            "border-radius: 8px; padding: 10px 16px; border: 1px solid #7F1D1D; }"
            "QPushButton:hover { background: #7F1D1D; color: #FFFFFF; }"
        )
        btn_cancel.clicked.connect(self._on_cancel)
        right_layout.addWidget(btn_cancel)

        root.addWidget(right_panel, stretch=3)

        # 动画相关
        self._anim_timer = None

    def _build_receipt_content(self, layout):
        """生成小票票面内容"""
        sd = self.sale_data

        def add_center_label(text, size=13, bold=False, color="#94A3B8"):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignCenter)
            weight = "900" if bold else "normal"
            lbl.setStyleSheet(f"font-size: {size}px; font-weight: {weight}; color: {color}; border: none; background: transparent;")
            layout.addWidget(lbl)

        def add_line():
            lbl = QLabel("- - - - - - - - - - - - - - - - - - - -")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #475569; font-family: monospace; font-size: 11px; border: none;")
            layout.addWidget(lbl)

        add_center_label("POS点餐  堂食", 12, False, "#64748B")
        add_center_label(sd.get("shop_name", "杨国福麻辣烫"), 18, True, "#F8FAFC")

        sub = sd.get("shop_subtitle", "")
        if sub:
            add_center_label(f"门店名称：{sub}", 11, False, "#94A3B8")

        # 取餐号
        call_frame = QFrame()
        call_frame.setStyleSheet("background: rgba(249, 115, 22, 0.15); border-radius: 8px; padding: 4px;")
        cf_layout = QVBoxLayout(call_frame)
        cf_layout.setContentsMargins(4, 4, 4, 4)
        lbl_call = QLabel(f"取餐号: {sd.get('call_no', '050')}")
        lbl_call.setAlignment(Qt.AlignCenter)
        lbl_call.setStyleSheet("font-size: 22px; font-weight: 900; color: #F97316; border: none;")
        cf_layout.addWidget(lbl_call)
        layout.addWidget(call_frame)

        add_line()

        # 商品明细
        cart_items = sd.get("cart_items", [])
        for item in cart_items:
            name = item.get("name", "")
            price = item.get("price", 0.0)
            qty = item.get("qty", 1)
            tag = item.get("tag", "")

            row_w = QWidget()
            row_w.setStyleSheet("background: transparent; border: none;")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)

            lbl_n = QLabel(name)
            lbl_n.setStyleSheet("font-size: 13px; color: #E2E8F0; font-weight: bold; border: none;")
            row_l.addWidget(lbl_n, stretch=1)

            if qty > 1:
                lbl_q = QLabel(f"x{qty}")
                lbl_q.setStyleSheet("font-size: 12px; color: #94A3B8; border: none;")
                row_l.addWidget(lbl_q)

            lbl_p = QLabel(f"¥{price:.2f}")
            lbl_p.setAlignment(Qt.AlignRight)
            lbl_p.setStyleSheet("font-size: 13px; color: #F59E0B; font-weight: bold; font-family: monospace; border: none;")
            row_l.addWidget(lbl_p)

            layout.addWidget(row_w)

            if tag:
                lbl_tag = QLabel(f"  {tag}")
                lbl_tag.setStyleSheet("font-size: 11px; color: #34D399; border: none; background: transparent;")
                layout.addWidget(lbl_tag)

        add_line()

        # 合计
        total_p = sum(i.get("price", 0.0) for i in cart_items)
        lbl_total = QLabel(f"应收金额：￥{total_p:.2f}")
        lbl_total.setAlignment(Qt.AlignRight)
        lbl_total.setStyleSheet("font-size: 18px; font-weight: 900; color: #34D399; border: none;")
        layout.addWidget(lbl_total)

    def _on_payment_selected(self, method):
        """用户点击付款方式后：禁用按钮、启动小票飞出动画"""
        self.selected_payment_method = method

        # 禁用所有按钮防止重复点击
        for btn in self.pay_buttons:
            btn.setEnabled(False)
            btn.setStyleSheet(
                "QPushButton { background: #374151; color: #6B7280; font-weight: 900; font-size: 16px; "
                "border-radius: 12px; border: none; padding: 14px 8px; min-height: 90px; }"
            )

        # 在小票区域上方显示支付成功标志
        success_lbl = QLabel(f"✅ {PAYMENT_LABELS.get(method, '')} 成功！")
        success_lbl.setAlignment(Qt.AlignCenter)
        success_lbl.setStyleSheet(
            "font-size: 18px; font-weight: 900; color: #10B981; border: none; background: transparent;"
        )
        self.receipt_container.layout().addWidget(success_lbl)

        # 启动飞出动画
        QTimer.singleShot(500, self._start_fly_animation)

    def _start_fly_animation(self):
        """小票容器向上飞出并逐渐透明"""
        self.opacity_effect = QGraphicsOpacityEffect(self.receipt_container)
        self.receipt_container.setGraphicsEffect(self.opacity_effect)

        # 位移动画：向上移动
        self.pos_anim = QPropertyAnimation(self.receipt_container, b"pos")
        self.pos_anim.setDuration(2000)
        start_pos = self.receipt_container.pos()
        end_pos = QPoint(start_pos.x(), start_pos.y() - 300)
        self.pos_anim.setStartValue(start_pos)
        self.pos_anim.setEndValue(end_pos)
        self.pos_anim.setEasingCurve(QEasingCurve.InQuad)

        # 透明度动画
        self.opa_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opa_anim.setDuration(2000)
        self.opa_anim.setStartValue(1.0)
        self.opa_anim.setEndValue(0.0)
        self.opa_anim.setEasingCurve(QEasingCurve.InQuad)

        self.pos_anim.start()
        self.opa_anim.start()

        # 3秒后自动关闭（动画2秒 + 缓冲1秒）
        QTimer.singleShot(3000, self._finish)

    def _finish(self):
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
                from PyQt5.QtWidgets import QGraphicsBlurEffect
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
