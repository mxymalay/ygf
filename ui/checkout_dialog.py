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
PAYMENT_SQB  = "shouqianba"  # 收钱吧 PC 客户端自动调起
PAYMENT_SCAN = "scan"        # 主扫
PAYMENT_CASH = "cash"        # 现金
PAYMENT_QR   = "qr"          # 被扫/静态码

PAYMENT_LABELS = {
    PAYMENT_SQB:  "收钱吧",
    PAYMENT_SCAN: "手持机器",
    PAYMENT_CASH: "现金",
    PAYMENT_QR:   "被扫",
}


class PaymentStatusWidget(QFrame):
    """
    极客风动态支付状态卡片：
    - WAITING 状态：360° 高帧率平滑旋转双色渐变光环 (QPainter 60FPS) + 极客脉冲 "⚡"
    - SUCCESS 状态：平滑过渡为柔光绿底圈与加粗弹跳对号 "✓"
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "WAITING"
        self.angle = 0
        self.scale_factor = 0.8
        self.setMinimumSize(220, 220)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")

        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(16) # ~60 FPS
        self.anim_timer.timeout.connect(self._on_anim_tick)
        self.anim_timer.start()

    def _on_anim_tick(self):
        if self.state == "WAITING":
            self.angle = (self.angle + 4) % 360
            self.update()
        elif self.state == "SUCCESS":
            if self.scale_factor < 1.1:
                self.scale_factor += 0.03
                self.update()

    def set_state(self, new_state):
        if self.state != new_state:
            self.state = new_state
            self.scale_factor = 0.7
            self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QConicalGradient, QFont
        from PyQt5.QtCore import QPointF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0 - 15.0
        radius = 65.0

        if self.state == "WAITING":
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(self.angle)

            grad = QConicalGradient(0, 0, 0)
            grad.setColorAt(0.0, QColor("#EA580C"))
            grad.setColorAt(0.5, QColor("#F97316"))
            grad.setColorAt(0.85, QColor(249, 115, 22, 50))
            grad.setColorAt(1.0, QColor(249, 115, 22, 0))

            pen = QPen(QBrush(grad), 9)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(int(-radius), int(-radius), int(radius * 2), int(radius * 2), 0, 360 * 16)
            painter.restore()

            font = QFont("Microsoft YaHei", 32, QFont.Bold)
            painter.setFont(font)
            painter.setPen(QColor("#FFEDD5"))
            painter.drawText(int(cx - 40), int(cy - 40), 80, 80, Qt.AlignCenter, "⚡")

        elif self.state == "SUCCESS":
            painter.save()
            painter.translate(cx, cy)
            painter.scale(self.scale_factor, self.scale_factor)

            pen_bg = QPen(QColor("#10B981"), 8)
            painter.setPen(pen_bg)
            painter.setBrush(QBrush(QColor(16, 185, 129, 35)))
            painter.drawEllipse(int(-radius), int(-radius), int(radius * 2), int(radius * 2))

            pen_check = QPen(QColor("#10B981"), 10, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen_check)
            path_points = [
                QPointF(-24, 2),
                QPointF(-7, 20),
                QPointF(26, -18)
            ]
            painter.drawPolyline(path_points)
            painter.restore()


class CheckoutDialog(QDialog):
    """
    结账模态框：左侧发票小票预览 + 右侧动态支付通道 (支持 mode="OTHER" / mode="SCAN_CODE")
    """

    def __init__(self, sale_data, parent=None, on_payment_callback=None, config=None, mode="OTHER"):
        super().__init__(parent)
        self.sale_data = sale_data
        self.on_payment_callback = on_payment_callback
        self.config = config or (parent.config if parent and hasattr(parent, 'config') else {})
        self.mode = mode  # "OTHER" | "SCAN_CODE"
        self.selected_payment_method = ""
        self._checkout_finalizing = False
        self._checkout_completed = False
        self._cancelled = False
        self._payment_monitors = []
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

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
        # 左侧：经典小票预览与发票明细区域
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

        ticket_card = QFrame()
        ticket_card.setObjectName("TicketCard")
        ticket_card.setStyleSheet(
            "#TicketCard { background: #F8FAFC; border-radius: 12px; "
            "border: 2px dashed #CBD5E1; }"
        )
        tc_layout = QVBoxLayout(ticket_card)
        tc_layout.setContentsMargins(12, 12, 12, 12)
        tc_layout.setSpacing(8)

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

        self._add_sep(tc_layout)
        
        cart_items = sale_data.get("cart_items", [])
        total_p = sum(i.get("price", 0.0) for i in cart_items)
        lbl_total = QLabel(f"应收金额：￥{total_p:.2f}")
        lbl_total.setAlignment(Qt.AlignRight)
        lbl_total.setStyleSheet("font-size: 26px; font-weight: bold; color: #059669; border: none;")
        tc_layout.addWidget(lbl_total)

        left_layout.addWidget(ticket_card, stretch=1)

        m_count = sum(1 for item in sale_data.get("cart_items", [])
                      if item.get("type") == "soup" or "weight" in item)
        if m_count > 0:
            slip_info = f"[打印] 1张顾客单 + {m_count}张后厨制作单"
            lbl_slip = QLabel(slip_info)
            lbl_slip.setAlignment(Qt.AlignCenter)
            lbl_slip.setStyleSheet(
                "background: rgba(16, 185, 129, 0.1); color: #059669; font-size: 12px; "
                "font-weight: bold; padding: 6px; border-radius: 6px; border: none;"
            )
        else:
            slip_info = u"[免出票] 无汤底订单，无需打印顾客单与制作单"
            lbl_slip = QLabel(slip_info)
            lbl_slip.setAlignment(Qt.AlignCenter)
            lbl_slip.setStyleSheet(
                "background: rgba(245, 158, 11, 0.12); color: #D97706; font-size: 12px; "
                "font-weight: bold; padding: 6px; border-radius: 6px; border: none;"
            )
        left_layout.addWidget(lbl_slip)

        self.receipt_container = left_frame
        root.addWidget(self.receipt_container, stretch=5)

        # ════════════════════════════════════════════════════════════
        # 右侧：根据 mode 构建面板 ("OTHER" 保留另外两个付款，"SCAN_CODE" 显示转圈圈对号)
        # ════════════════════════════════════════════════════════════
        right_frame = QFrame()
        right_frame.setObjectName("PaymentRight")
        right_frame.setStyleSheet(
            "#PaymentRight { background: #111827; border-radius: 18px; border: 1px solid #374151; }"
        )
        self.right_panel = right_frame
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(16)
        right_layout.setAlignment(Qt.AlignCenter)

        self.pay_buttons = []

        if self.mode == "SCAN_CODE":
            # ── 去扫码模式：显示 60FPS 旋转光环/对号 ──
            lbl_title = QLabel(u"收钱吧 自动扫码扣款")
            lbl_title.setAlignment(Qt.AlignCenter)
            lbl_title.setStyleSheet("font-size: 22px; font-weight: 900; color: #FFFFFF; border: none;")
            right_layout.addWidget(lbl_title)

            self.lbl_sqb_desc = QLabel(u"⚡ 已调起收钱吧，等待扣款中...")
            self.lbl_sqb_desc.setAlignment(Qt.AlignCenter)
            self.lbl_sqb_desc.setStyleSheet("font-size: 14px; font-weight: bold; color: #F97316; border: none;")
            right_layout.addWidget(self.lbl_sqb_desc)

            self.status_widget = PaymentStatusWidget(right_frame)
            right_layout.addWidget(self.status_widget, alignment=Qt.AlignCenter)

            # 开启收钱吧后台监视
            QTimer.singleShot(100, lambda: self._start_sqb_smart_monitoring(total_p, PAYMENT_SQB))

        elif self.mode == "CASH":
            # ── 去现金模式：无额外付款按钮，展示现金状态与 60FPS 绿对号动画 ──
            lbl_title = QLabel(u"现金收款")
            lbl_title.setAlignment(Qt.AlignCenter)
            lbl_title.setStyleSheet("font-size: 22px; font-weight: 900; color: #FFFFFF; border: none;")
            right_layout.addWidget(lbl_title)

            self.lbl_sqb_desc = QLabel(u"￥ 请在计算器中确认实收金额...")
            self.lbl_sqb_desc.setAlignment(Qt.AlignCenter)
            self.lbl_sqb_desc.setStyleSheet("font-size: 14px; font-weight: bold; color: #34D399; border: none;")
            right_layout.addWidget(self.lbl_sqb_desc)

            self.status_widget = PaymentStatusWidget(right_frame)
            right_layout.addWidget(self.status_widget, alignment=Qt.AlignCenter)

            # 50ms 后弹出现金计算器
            QTimer.singleShot(50, self._trigger_cash_calc)

        else:
            # ── 其他模式：去除收钱吧和现金，保留剩下两个 (手持POS/被扫/静态码) ──
            lbl_title = QLabel(u"其它渠道 记账结算")
            lbl_title.setAlignment(Qt.AlignCenter)
            lbl_title.setStyleSheet("font-size: 22px; font-weight: 900; color: #FFFFFF; border: none;")
            right_layout.addWidget(lbl_title)

            lbl_sub = QLabel(u"! 点击下方按钮，即刻出票")
            lbl_sub.setAlignment(Qt.AlignCenter)
            lbl_sub.setStyleSheet(
                "background: rgba(245, 158, 11, 0.15); color: #F59E0B; "
                "font-size: 15px; font-weight: 900; padding: 8px 16px; "
                "border-radius: 8px; border: 1px solid #D97706;"
            )
            right_layout.addWidget(lbl_sub)

            grid_layout = QVBoxLayout()
            grid_layout.setSpacing(14)

            sub_configs = [
                (PAYMENT_SCAN, u"码", u"手持机器", u"手持 POS 刷卡/离线记账",
                 "#064E3B", "#059669", "#10B981", "#A7F3D0"),
                (PAYMENT_QR,   u"码", u"被扫 / 静态码", u"顾客出示付款码或扫描静态码",
                 "#4C1D95", "#7C3AED", "#8B5CF6", "#DDD6FE"),
            ]

            for method, icon, title, desc, bg_dark, bg_main, bg_hover, fg_accent in sub_configs:
                sub_frame = QFrame()
                sub_frame.setFixedHeight(110)
                sub_frame.setStyleSheet(f"""
                    QFrame {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 {bg_dark}, stop:1 {bg_main});
                        border-radius: 14px; border: 1px solid {bg_hover};
                    }}
                """)
                sub_box = QHBoxLayout(sub_frame)
                sub_box.setContentsMargins(18, 12, 18, 12)
                sub_box.setSpacing(16)

                lbl_sub_icon = QLabel(icon)
                lbl_sub_icon.setStyleSheet("font-size: 32px; border: none; background: transparent;")
                lbl_sub_icon.setAlignment(Qt.AlignCenter)
                sub_box.addWidget(lbl_sub_icon)

                t_col = QVBoxLayout()
                t_col.setSpacing(2)
                t_col.addStretch()

                lbl_sub_title = QLabel(title)
                lbl_sub_title.setStyleSheet(f"font-size: 18px; font-weight: 900; color: {fg_accent}; border: none; background: transparent;")
                t_col.addWidget(lbl_sub_title)

                lbl_sub_desc = QLabel(desc)
                lbl_sub_desc.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.7); border: none; background: transparent;")
                t_col.addWidget(lbl_sub_desc)

                t_col.addStretch()
                sub_box.addLayout(t_col, stretch=1)

                sub_overlay = QPushButton("", sub_frame)
                sub_overlay.setCursor(Qt.PointingHandCursor)
                sub_overlay.setStyleSheet("""
                    QPushButton { background: transparent; border: none; }
                    QPushButton:hover { background: rgba(255, 255, 255, 0.1); border-radius: 14px; }
                    QPushButton:pressed { background: rgba(255, 255, 255, 0.2); border-radius: 14px; }
                """)
                sub_overlay.clicked.connect(lambda checked, m=method: self._on_payment_selected(m))
                sub_frame.resizeEvent = lambda event, ob=sub_overlay, bf=sub_frame: ob.setGeometry(0, 0, bf.width(), bf.height())

                grid_layout.addWidget(sub_frame)
                self.pay_buttons.append(sub_overlay)

            right_layout.addLayout(grid_layout)

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
        """用户点击付款方式"""
        self.selected_payment_method = method

        # 如果点击的是【收钱吧】，先唤起收钱吧并推送金额，启动后台无感侦测
        if method == PAYMENT_SQB:
            try:
                from core.shouqianba_sender import send_shouqianba_amount
                total_amt = self.sale_data.get("total_price", 0.0)
                cfg = self.sale_data.get("config", {})
                parent_w = self.parent()
                if parent_w and hasattr(parent_w, 'window'):
                    parent_w = parent_w.window()
                if not cfg and parent_w and hasattr(parent_w, 'config'):
                    cfg = parent_w.config
                send_shouqianba_amount(total_amt, cfg)
            except Exception as e:
                print(f"[CheckoutDialog] 调起收钱吧金额异常: {e}")

            # 启动智能无感监测：收钱吧窗口打开时静默等待；成功则直接打票结账；若窗口被关闭/超时未扣款，才弹窗确认
            self._start_sqb_smart_monitoring(total_amt, method)
            return

        elif method == PAYMENT_CASH:
            from ui.cash_dialog import CashCalculatorDialog
            parent_w = self.parent()
            printer = None
            if parent_w and hasattr(parent_w, 'printer'):
                printer = parent_w.printer
            
            # 开启底层高斯模糊
            blur = QGraphicsBlurEffect(self.inner_container)
            blur.setBlurRadius(18)
            self.inner_container.setGraphicsEffect(blur)
            
            # 弹出现金计算器
            def on_cash_confirm(pm):
                self._complete_checkout(pm)
                
            calc = CashCalculatorDialog(self.sale_data, parent=self, on_confirm=on_cash_confirm, printer=printer)
            calc.exec_()
            
            # 还原底层高斯模糊
            self.inner_container.setGraphicsEffect(None)
            
            # 如果计算器被取消（未确认），则重置选择状态，允许重新选择
            if calc.result() != QDialog.Accepted:
                self.selected_payment_method = ""
            return

        # 其他付款方式（主扫/被扫）直接完成
        self._complete_checkout(method)

    def _trigger_cash_calc(self):
        """去现金模式下的现金计算器唤起与确认动画流程"""
        from ui.cash_dialog import CashCalculatorDialog
        parent_w = self.parent()
        printer = getattr(parent_w, 'printer', None) if parent_w else None

        blur = QGraphicsBlurEffect(self.inner_container)
        blur.setBlurRadius(18)
        self.inner_container.setGraphicsEffect(blur)

        cash_confirmed = [False]
        def on_cash_confirm(pm):
            cash_confirmed[0] = True

        calc = CashCalculatorDialog(self.sale_data, parent=self, on_confirm=on_cash_confirm, printer=printer)
        calc.exec_()

        self.inner_container.setGraphicsEffect(None)

        if cash_confirmed[0]:
            if hasattr(self, 'lbl_sqb_desc') and self.lbl_sqb_desc:
                self.lbl_sqb_desc.setText(u"✓ 现金已确认收讫！已自动完成出票")
            if hasattr(self, 'status_widget') and self.status_widget:
                self.status_widget.set_state("SUCCESS")
            QTimer.singleShot(600, lambda: self._complete_checkout(PAYMENT_CASH))
        else:
            self.reject()

    def _start_sqb_smart_monitoring(self, amount, method):
        """
        智能无感感知模式：
        1. 唤起收钱吧后，通过 RapidOCR/色彩采样，只要【收钱吧付款窗口】在屏幕上显示，POS 保持后台静默等待；
        2. 若扫码成功，0 弹窗直接自动完成结账并打印小票！
        3. 若【收钱吧付款窗口已被关闭/消失】且未到账，才弹出确认卡片供收银员操作。
        """
        if hasattr(self, 'lbl_sqb_desc') and self.lbl_sqb_desc:
            self.lbl_sqb_desc.setText(u"⚡ 已调起收钱吧，等待扣款中...")

        from core.shouqianba_sender import get_sqb_overall_status

        monitoring_timer = QTimer(self)
        self._payment_monitors.append(monitoring_timer)
        monitoring_timer.setInterval(250)
        elapsed_ms = [0]
        window_ever_seen = [False]
        closed_count = [0]
        success_hits = [0]

        def _check_status():
            if self._cancelled or self._checkout_completed:
                monitoring_timer.stop()
                return
            elapsed_ms[0] += 250
            
            sqb_status = get_sqb_overall_status()

            # 1. 优先检测【支付成功】
            if sqb_status == "SUCCESS":
                # 收钱吧无回调，颜色信号至少连续命中两次才作为自动入账依据。
                success_hits[0] += 1
                if success_hits[0] < 2:
                    return
                monitoring_timer.stop()
                print("[CheckoutDialog] [AUTO] 智能无感感知：检测到收钱吧【支付成功】！零弹窗直接自动出票完成结账！")
                if hasattr(self, 'status_widget') and self.status_widget:
                    self.status_widget.set_state("SUCCESS")
                if hasattr(self, 'lbl_sqb_desc') and self.lbl_sqb_desc:
                    self.lbl_sqb_desc.setText(u"✓ 支付成功！已自动完成出票")
                QTimer.singleShot(600, lambda: self._complete_checkout(method))
                return
            success_hits[0] = 0

            # 2. 识别到正处于【付款界面】 (宝蓝顶栏 / 付款码 OCR)
            if sqb_status == "WAITING":
                window_ever_seen[0] = True
                closed_count[0] = 0
                if elapsed_ms[0] >= 90000: # 90 秒长超时
                    monitoring_timer.stop()
                    self._restore_pay_buttons()
                    self._show_sqb_confirm_overlay(amount, method)
                return

            # 3. 前 500ms 为窗口唤起留缓冲
            if elapsed_ms[0] < 750:
                return

            # 4. 如果窗口出现过且被关闭，300ms 极速响应弹出确认卡片
            closed_count[0] += 1
            if (window_ever_seen[0] and closed_count[0] >= 3) or elapsed_ms[0] >= 2500:
                monitoring_timer.stop()
                print("[CheckoutDialog] [INFO] 检测到收钱吧付款窗口已关闭（且未到账），展现确认卡片。")
                self._restore_pay_buttons()
                self._show_sqb_confirm_overlay(amount, method)

        monitoring_timer.timeout.connect(_check_status)
        monitoring_timer.start()

    def _restore_pay_buttons(self):
        """恢复付款按钮可用状态与描述信息"""
        for btn in self.pay_buttons:
            btn.setEnabled(True)
        if hasattr(self, 'lbl_sqb_desc') and self.lbl_sqb_desc:
            self.lbl_sqb_desc.setText(u"电脑扫码")

    def _complete_checkout(self, method):
        """执行最终结账、发送打印指令与飞出出票动画"""
        if self._checkout_completed or self._checkout_finalizing or self._cancelled:
            return False
        self._checkout_finalizing = True
        # 禁用所有按钮，防止重复点击
        for btn in self.pay_buttons:
            btn.setEnabled(False)
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; }"
            )

        # 立即回调发送打印指令与保存数据库
        try:
            completed = self.on_payment_callback(method) if self.on_payment_callback else True
        except Exception:
            completed = False
        if completed is False:
            self._checkout_finalizing = False
            self._restore_pay_buttons()
            return False
        self._checkout_completed = True
        self._stop_payment_monitors()

        # 启动飞出动画
        QTimer.singleShot(100, self._start_fly_animation)
        return True

    def _stop_payment_monitors(self):
        for timer in self._payment_monitors:
            timer.stop()
        self._payment_monitors = []

    def reject(self):
        """Cancel never records a sale; a scan payment also clears the plugin amount."""
        if self._checkout_completed:
            return
        self._cancelled = True
        self._stop_payment_monitors()
        if self.mode == "SCAN_CODE":
            try:
                from core.shouqianba_sender import clear_shouqianba_amount
                clear_shouqianba_amount(self.config)
            except Exception:
                pass
        super().reject()

    def _show_sqb_confirm_overlay(self, amount, method):
        """精致嵌入式等待/确认框：放大卡片尺寸 (580x420) + 展示金额 + 无盖遮罩嵌入付款界面中"""
        confirm_dialog = QDialog(self)
        confirm_dialog.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        confirm_dialog.setAttribute(Qt.WA_TranslucentBackground)
        confirm_dialog.setModal(True)
        confirm_dialog.resize(self.size())

        # 全透明自然无盖遮罩 (不阻挡底层付款界面)
        mask_frame = QFrame(confirm_dialog)
        mask_frame.setObjectName("ConfirmMask")
        mask_frame.setStyleSheet(
            "#ConfirmMask { background: rgba(15, 23, 42, 0.35); border: none; }"
        )
        mask_layout = QVBoxLayout(confirm_dialog)
        mask_layout.setContentsMargins(0, 0, 0, 0)
        mask_layout.addWidget(mask_frame)

        dialog_layout = QHBoxLayout(mask_frame)
        dialog_layout.setContentsMargins(0, 0, 0, 0)

        # 放大版确认卡片 (580px 宽 x 420px 高，与官方收钱吧弹窗比例大小保持一致)
        cd_outer = QFrame()
        cd_outer.setFixedSize(580, 420)
        cd_outer.setStyleSheet("""
            QFrame {
                background: #1E293B;
                border-radius: 20px;
                border: 2px solid #F97316;
            }
        """)
        dialog_layout.addWidget(cd_outer, alignment=Qt.AlignCenter)

        box = QVBoxLayout(cd_outer)
        box.setContentsMargins(28, 28, 28, 28)
        box.setSpacing(18)

        lbl_icon = QLabel(u"⚡ 请确认收钱吧收款状态")
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet("font-size: 24px; font-weight: 900; color: #F97316; border: none; background: transparent;")
        box.addWidget(lbl_icon)

        # 中间金额与状态显示卡片
        amt_box = QFrame()
        amt_box.setStyleSheet("""
            QFrame {
                background: #0F172A;
                border-radius: 14px;
                border: 1px solid #334155;
            }
        """)
        amt_layout = QVBoxLayout(amt_box)
        amt_layout.setContentsMargins(20, 16, 20, 16)
        amt_layout.setSpacing(6)
        amt_layout.setAlignment(Qt.AlignCenter)

        lbl_amt_title = QLabel(u"待确认支付金额")
        lbl_amt_title.setAlignment(Qt.AlignCenter)
        lbl_amt_title.setStyleSheet("font-size: 15px; color: #94A3B8; border: none; background: transparent;")
        amt_layout.addWidget(lbl_amt_title)

        int_val, dec_val = f"{amount:.2f}".split('.')
        lbl_amt_val = QLabel(f"￥<span style='font-size:42px; font-weight:900;'>{int_val}</span>.<span style='font-size:28px;'>{dec_val}</span>")
        lbl_amt_val.setAlignment(Qt.AlignCenter)
        lbl_amt_val.setStyleSheet("font-size: 32px; color: #10B981; font-weight: bold; font-family: 'Microsoft YaHei', sans-serif; border: none; background: transparent;")
        amt_layout.addWidget(lbl_amt_val)

        lbl_tip = QLabel(u"提示：请等待收钱吧客户端扣款成功或手动确认")
        lbl_tip.setAlignment(Qt.AlignCenter)
        lbl_tip.setStyleSheet("font-size: 13px; color: #64748B; border: none; background: transparent;")
        amt_layout.addWidget(lbl_tip)

        box.addWidget(amt_box, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)

        btn_cancel = QPushButton(u"❌ 未到账 / 退回")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setFocusPolicy(Qt.NoFocus)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #DC2626, stop:1 #EF4444);
                color: #FFFFFF; font-size: 18px; font-weight: bold;
                border-radius: 12px; padding: 18px 10px; border: none; outline: none;
            }
            QPushButton:hover { background: #EF4444; }
        """)
        btn_cancel.clicked.connect(confirm_dialog.reject)
        btn_row.addWidget(btn_cancel, stretch=1)

        btn_ok = QPushButton(u"✓ 确认已到账")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setFocusPolicy(Qt.NoFocus)
        btn_ok.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10B981);
                color: #FFFFFF; font-size: 18px; font-weight: bold;
                border-radius: 12px; padding: 18px 10px; border: none; outline: none;
            }
            QPushButton:hover { background: #10B981; }
        """)
        btn_ok.clicked.connect(confirm_dialog.accept)
        btn_row.addWidget(btn_ok, stretch=1)

        box.addLayout(btn_row)

        # 启动后台高频侦测：自动侦测收钱吧【收款成功/支付成功】窗口
        auto_check_timer = QTimer(confirm_dialog)
        auto_check_timer.setInterval(300)

        def _on_auto_detect_sqb():
            from core.shouqianba_sender import check_shouqianba_payment_success
            if check_shouqianba_payment_success():
                auto_check_timer.stop()
                print("[CheckoutDialog] [AUTO] 成功自动侦测到【收钱吧】支付成功窗口！无痛自动完成结账并打印出票！")
                lbl_icon.setText(u"✓ 收钱吧到账成功！自动结账打票中...")
                lbl_icon.setStyleSheet("font-size: 24px; font-weight: 900; color: #10B981; border: none; background: transparent;")
                cd_outer.setStyleSheet("""
                    QFrame {
                        background: #1E293B;
                        border-radius: 20px;
                        border: 2px solid #10B981;
                    }
                """)
                QTimer.singleShot(150, confirm_dialog.accept)

        auto_check_timer.timeout.connect(_on_auto_detect_sqb)
        auto_check_timer.start()

        res = confirm_dialog.exec_()
        auto_check_timer.stop()

        # 还原底层高斯模糊
        self.inner_container.setGraphicsEffect(None)

        if res == QDialog.Accepted:
            # 确认付款成功 → 执行结账出票
            self._complete_checkout(method)
        else:
            # 支付失败/退回：取消结账并重置插件金额。
            print("[CheckoutDialog] 用户点击收钱吧支付失败/退回，已清空收钱吧金额并退出至点菜界面。")
            self.reject()

    def _start_fly_animation(self):
        """小票动画：需打票则向上飞出，免打票则向下下沉，右侧面板淡出后关闭"""
        self.opacity_effect = QGraphicsOpacityEffect(self.receipt_container)
        self.receipt_container.setGraphicsEffect(self.opacity_effect)

        cart_items = self.sale_data.get("cart_items", [])
        has_soup = any(item.get("type") == "soup" or "weight" in item for item in cart_items)

        # 位移动画
        self.pos_anim = QPropertyAnimation(self.receipt_container, b"pos")
        self.pos_anim.setDuration(800)
        start_pos = self.receipt_container.pos()
        
        if has_soup:
            # 有汤底（出票）：向上飞出
            end_pos = QPoint(start_pos.x(), start_pos.y() - 250)
        else:
            # 无汤底（免出票）：向下下沉，与出票方向相反
            end_pos = QPoint(start_pos.x(), start_pos.y() + 250)

        self.pos_anim.setStartValue(start_pos)
        self.pos_anim.setEndValue(end_pos)
        self.pos_anim.setEasingCurve(QEasingCurve.InBack)

        # 渐隐透明度 (左侧小票)
        self.opa_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opa_anim.setDuration(800)
        self.opa_anim.setStartValue(1.0)
        self.opa_anim.setEndValue(0.0)
        self.opa_anim.setEasingCurve(QEasingCurve.InCubic)

        # 右侧面板快速淡出
        self.right_opacity = QGraphicsOpacityEffect(self.right_panel)
        self.right_panel.setGraphicsEffect(self.right_opacity)
        self.right_opa_anim = QPropertyAnimation(self.right_opacity, b"opacity")
        self.right_opa_anim.setDuration(400)
        self.right_opa_anim.setStartValue(1.0)
        self.right_opa_anim.setEndValue(0.0)

        self.pos_anim.start()
        self.opa_anim.start()
        self.right_opa_anim.start()

        # 动画结束后自动关闭模态框
        QTimer.singleShot(900, self.accept)

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
                blur.setBlurRadius(20)
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
