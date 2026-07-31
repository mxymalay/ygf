"""
历史订单查询界面 — 还原 POS 标准排版
PyQt5 + Python 3.8 兼容
"""
import re
from datetime import date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QLineEdit, QComboBox, QFrame, QScrollArea,
    QGridLayout, QMessageBox, QDialog
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QFont

from core.database import Database


class OrderCard(QFrame):
    """左侧订单列表卡片"""

    def __init__(self, record, is_selected=False, parent=None):
        super().__init__(parent)
        self.record = record
        self.is_selected = is_selected
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(64)
        self._setup_ui()

    def _setup_ui(self):
        r = self.record
        remark = r.get("remark", "")
        created_at = str(r.get("created_at", ""))

        # 提取叫号
        call_match = re.search(r"叫号:#?(\w+)", remark)
        call_no = call_match.group(1) if call_match else r.get("sale_no", "")[-3:]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # 第一行：POS点餐：050 堂食         已支付
        row1 = QHBoxLayout()
        lbl_title = QLabel(u"📋 POS点餐：%s 堂食" % call_no)
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #F9FAFB;")

        lbl_status = QLabel(u"已支付")
        lbl_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #EA580C;")

        row1.addWidget(lbl_title)
        row1.addStretch()
        row1.addWidget(lbl_status)
        layout.addLayout(row1)

        # 第二行：2026-07-31 21:12:05     实收：¥ 38.83
        row2 = QHBoxLayout()
        lbl_time = QLabel(created_at)
        lbl_time.setStyleSheet("font-size: 12px; color: #9CA3AF;")

        lbl_amount = QLabel(u"实收：¥ %.2f" % r.get("total_price", 0.0))
        lbl_amount.setStyleSheet("font-size: 13px; font-weight: bold; color: #D1D5DB;")

        row2.addWidget(lbl_time)
        row2.addStretch()
        row2.addWidget(lbl_amount)
        layout.addLayout(row2)

        self._update_style()

    def set_selected(self, val: bool):
        self.is_selected = val
        self._update_style()

    def _update_style(self):
        if self.is_selected:
            self.setStyleSheet(
                "QFrame { background: #1E293B; border: 2px solid #EA580C; border-radius: 8px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background: #111827; border: 1px solid #374151; border-radius: 8px; }"
                "QFrame:hover { background: #1F2937; }"
            )


class HistoryWidget(QWidget):
    """历史订单查询"""

    def __init__(self, db: Database, printer=None, config=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.printer = printer
        self.config = config or {}
        self.records = []
        self.selected_record = None

        self._build_ui()
        self.reload_orders()

    def reload_orders(self):
        self._on_query()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ── 1. 顶部 Header 栏 ──
        header_bar = QHBoxLayout()
        header_bar.setSpacing(12)

        # 日期选择
        self.date_picker = QDateEdit()
        self.date_picker.setDate(QDate.currentDate())
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setDisplayFormat("yyyy-MM-dd")
        self.date_picker.setStyleSheet(
            "QDateEdit { background: #1F2937; color: #F9FAFB; font-size: 14px; font-weight: bold; "
            "padding: 6px 12px; border: 1px solid #374151; border-radius: 6px; }"
        )
        self.date_picker.dateChanged.connect(self._on_query)
        header_bar.addWidget(self.date_picker)

        header_bar.addSpacing(16)

        # 选中的订单标题
        self.lbl_header_title = QLabel(u"📋 POS点餐：--- 堂食")
        self.lbl_header_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #F9FAFB;")
        header_bar.addWidget(self.lbl_header_title)

        header_bar.addStretch()

        # 右侧状态标识
        self.lbl_header_status = QLabel(u"已支付")
        self.lbl_header_status.setStyleSheet("font-size: 16px; font-weight: bold; color: #EA580C;")
        header_bar.addWidget(self.lbl_header_status)

        main_layout.addLayout(header_bar)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #374151;")
        main_layout.addWidget(line)

        # ── 2. 主体：左右双栏结构 ──
        body_layout = QHBoxLayout()
        body_layout.setSpacing(12)

        # ──────────────── Left Column (订单列表) ────────────────
        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        # (1) 搜索控制行
        search_row = QHBoxLayout()
        search_row.setSpacing(6)

        self.cbo_search_type = QComboBox()
        self.cbo_search_type.addItems([u"取餐号", u"订单号"])
        self.cbo_search_type.setStyleSheet(
            "QComboBox { background: #1F2937; color: white; padding: 6px; border: 1px solid #374151; border-radius: 6px; }"
        )
        search_row.addWidget(self.cbo_search_type)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(u"输入查询内容...")
        self.txt_search.setStyleSheet(
            "QLineEdit { background: #1F2937; color: white; padding: 6px; border: 1px solid #374151; border-radius: 6px; }"
        )
        self.txt_search.returnPressed.connect(self._on_query)
        search_row.addWidget(self.txt_search)

        btn_search = QPushButton(u"查询")
        btn_search.setStyleSheet(
            "background: #EA580C; color: white; font-weight: bold; padding: 6px 14px; border-radius: 6px; border: none;"
        )
        btn_search.clicked.connect(self._on_query)
        search_row.addWidget(btn_search)

        btn_sort = QPushButton(u"1↓")
        btn_sort.setStyleSheet(
            "background: #EA580C; color: white; font-weight: bold; padding: 6px 10px; border-radius: 6px; border: none;"
        )
        search_row.addWidget(btn_sort)

        left_col.addLayout(search_row)

        # (2) 渠道与状态 Filter 标签页
        chan_row = QHBoxLayout()
        chan_row.setSpacing(4)
        for name in [u"全部", u"POS", u"小程序", u"饿了么", u"美团", u"其它"]:
            b = QPushButton(name)
            if name == u"全部":
                b.setStyleSheet("background: #EA580C; color: white; font-weight: bold; border-radius: 4px; padding: 4px 8px; border: none;")
            else:
                b.setStyleSheet("background: #1F2937; color: #9CA3AF; font-weight: bold; border-radius: 4px; padding: 4px 8px; border: 1px solid #374151;")
            chan_row.addWidget(b)
        left_col.addLayout(chan_row)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        b_paid = QPushButton(u"已支付")
        b_paid.setStyleSheet("background: #1F2937; color: #EA580C; font-weight: bold; border: 1px solid #EA580C; border-radius: 4px; padding: 4px 12px;")
        status_row.addWidget(b_paid)

        b_refunded = QPushButton(u"已退单")
        b_refunded.setStyleSheet("background: #1F2937; color: #9CA3AF; font-weight: bold; border: 1px solid #374151; border-radius: 4px; padding: 4px 12px;")
        status_row.addWidget(b_refunded)
        status_row.addStretch()
        left_col.addLayout(status_row)

        # (3) 订单滚动列表
        self.scroll_orders = QScrollArea()
        self.scroll_orders.setWidgetResizable(True)
        self.scroll_orders.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.order_list_container = QWidget()
        self.order_list_layout = QVBoxLayout(self.order_list_container)
        self.order_list_layout.setContentsMargins(0, 0, 0, 0)
        self.order_list_layout.setSpacing(6)
        self.order_list_layout.setAlignment(Qt.AlignTop)

        self.scroll_orders.setWidget(self.order_list_container)
        left_col.addWidget(self.scroll_orders, stretch=1)

        # (4) 底部翻页控制
        left_page_row = QHBoxLayout()
        btn_batch = QPushButton(u"批量操作")
        btn_batch.setStyleSheet("background: #374151; color: white; padding: 6px 12px; border-radius: 6px; border: none;")
        btn_prev_l = QPushButton(u"上一页")
        btn_prev_l.setStyleSheet("background: #374151; color: white; padding: 6px 12px; border-radius: 6px; border: none;")
        btn_next_l = QPushButton(u"下一页")
        btn_next_l.setStyleSheet("background: #EA580C; color: white; font-weight: bold; padding: 6px 12px; border-radius: 6px; border: none;")

        left_page_row.addWidget(btn_batch)
        left_page_row.addWidget(btn_prev_l)
        left_page_row.addWidget(btn_next_l)
        left_col.addLayout(left_page_row)

        body_layout.addLayout(left_col, stretch=3)

        # ──────────────── Right Panel (订单详情) ────────────────
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        # (1) 基础信息 Header
        meta_row = QHBoxLayout()
        lbl_meta = QLabel(u"POS机号：1    就餐人数：1    收银员：杨国福(肥西水晶城店)门店经理")
        lbl_meta.setStyleSheet("color: #9CA3AF; font-size: 13px; font-weight: bold;")
        meta_row.addWidget(lbl_meta)
        meta_row.addStretch()
        right_col.addLayout(meta_row)

        # (2) 购买商品明细卡片
        self.items_card = QFrame()
        self.items_card.setStyleSheet("QFrame { background: #1E293B; border: 1px solid #374151; border-radius: 10px; }")
        self.items_layout = QVBoxLayout(self.items_card)
        self.items_layout.setContentsMargins(16, 14, 16, 14)
        self.items_layout.setSpacing(10)

        right_col.addWidget(self.items_card, stretch=2)

        # (3) 支付信息卡片
        self.pay_card = QFrame()
        self.pay_card.setStyleSheet("QFrame { background: #1E293B; border: 1px solid #374151; border-radius: 10px; }")
        pay_layout = QVBoxLayout(self.pay_card)
        pay_layout.setContentsMargins(16, 12, 16, 12)
        pay_layout.setSpacing(6)

        lbl_pay_title = QLabel(u"支付信息")
        lbl_pay_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB;")
        pay_layout.addWidget(lbl_pay_title)

        self.pay_info_row = QHBoxLayout()
        self.lbl_pay_type = QLabel(u"微信:")
        self.lbl_pay_type.setStyleSheet("color: #9CA3AF; font-size: 14px;")
        self.lbl_pay_val = QLabel(u"¥ 0.00")
        self.lbl_pay_val.setStyleSheet("color: #F9FAFB; font-size: 14px; font-weight: bold;")
        self.pay_info_row.addWidget(self.lbl_pay_type)
        self.pay_info_row.addStretch()
        self.pay_info_row.addWidget(self.lbl_pay_val)
        pay_layout.addLayout(self.pay_info_row)

        right_col.addWidget(self.pay_card)

        # (4) 底部并排信息框 (订单信息 + 金额明细)
        bottom_cards_row = QHBoxLayout()
        bottom_cards_row.setSpacing(10)

        # 订单信息卡片
        card_order_info = QFrame()
        card_order_info.setStyleSheet("QFrame { background: #1E293B; border: 1px solid #374151; border-radius: 10px; }")
        layout_oi = QVBoxLayout(card_order_info)
        layout_oi.setContentsMargins(14, 12, 14, 12)
        layout_oi.setSpacing(6)

        lbl_oi_title = QLabel(u"订单信息")
        lbl_oi_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB;")
        layout_oi.addWidget(lbl_oi_title)

        self.lbl_order_no = QLabel(u"订单编号：---")
        self.lbl_order_no.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        self.lbl_create_time = QLabel(u"创建时间：---")
        self.lbl_create_time.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        self.lbl_remark_info = QLabel(u"备注信息：")
        self.lbl_remark_info.setStyleSheet("color: #9CA3AF; font-size: 13px;")

        layout_oi.addWidget(self.lbl_order_no)
        layout_oi.addWidget(self.lbl_create_time)
        layout_oi.addWidget(self.lbl_remark_info)
        bottom_cards_row.addWidget(card_order_info, stretch=1)

        # 金额明细卡片
        card_amount_info = QFrame()
        card_amount_info.setStyleSheet("QFrame { background: #1E293B; border: 1px solid #374151; border-radius: 10px; }")
        layout_ai = QVBoxLayout(card_amount_info)
        layout_ai.setContentsMargins(14, 12, 14, 12)
        layout_ai.setSpacing(6)

        lbl_ai_title = QLabel(u"金额明细")
        lbl_ai_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB;")
        layout_ai.addWidget(lbl_ai_title)

        self.lbl_item_total = QLabel(u"商品金额：¥ 0.00")
        self.lbl_item_total.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        self.lbl_discount_total = QLabel(u"折扣金额：¥ 0.00")
        self.lbl_discount_total.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        self.lbl_final_total = QLabel(u"实收金额：¥ 0.00")
        self.lbl_final_total.setStyleSheet("color: #EA580C; font-size: 15px; font-weight: 900;")

        layout_ai.addWidget(self.lbl_item_total)
        layout_ai.addWidget(self.lbl_discount_total)
        layout_ai.addWidget(self.lbl_final_total)
        bottom_cards_row.addWidget(card_amount_info, stretch=1)

        right_col.addLayout(bottom_cards_row)

        # (5) 底部操作栏
        right_action_row = QHBoxLayout()
        right_action_row.setSpacing(8)

        btn_r_prev = QPushButton(u"上一页")
        btn_r_prev.setStyleSheet("background: #EA580C; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; border: none;")
        btn_r_next = QPushButton(u"下一页")
        btn_r_next.setStyleSheet("background: #EA580C; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; border: none;")

        right_action_row.addWidget(btn_r_prev)
        right_action_row.addWidget(btn_r_next)
        right_action_row.addStretch()

        btn_part_refund = QPushButton(u"部分退")
        btn_part_refund.setStyleSheet("background: #374151; color: white; padding: 8px 18px; border-radius: 6px; border: none;")
        btn_refund = QPushButton(u"退单")
        btn_refund.setStyleSheet("background: #374151; color: white; padding: 8px 18px; border-radius: 6px; border: none;")
        btn_refund.clicked.connect(self._on_refund_click)

        btn_reprint = QPushButton(u"重打印")
        btn_reprint.setStyleSheet("background: #EA580C; color: white; font-weight: 900; font-size: 15px; padding: 8px 24px; border-radius: 6px; border: none;")
        btn_reprint.clicked.connect(self._on_reprint_click)

        right_action_row.addWidget(btn_part_refund)
        right_action_row.addWidget(btn_refund)
        right_action_row.addWidget(btn_reprint)

        right_col.addLayout(right_action_row)

        body_layout.addLayout(right_col, stretch=5)

        main_layout.addLayout(body_layout, stretch=1)

    # ─── 数据查询与加载 ───
    def _on_query(self):
        target_date = self.date_picker.date().toString("yyyy-MM-dd")
        raw_records = self.db.get_sales_by_date(target_date, target_date)

        # 如果有关键字搜索
        kw = self.txt_search.text().strip()
        if kw:
            stype = self.cbo_search_type.currentText()
            filtered = []
            for r in raw_records:
                remark = r.get("remark", "")
                if stype == u"取餐号":
                    if kw in remark or kw in r.get("sale_no", ""):
                        filtered.append(r)
                else:
                    if kw in r.get("sale_no", "") or kw in remark:
                        filtered.append(r)
            self.records = filtered
        else:
            self.records = raw_records

        self._render_order_list()

    def _render_order_list(self):
        # 清空已有卡片
        while self.order_list_layout.count():
            item = self.order_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.records:
            lbl_empty = QLabel(u"暂无订单记录")
            lbl_empty.setAlignment(Qt.AlignCenter)
            lbl_empty.setStyleSheet("color: #9CA3AF; font-size: 14px; margin-top: 20px;")
            self.order_list_layout.addWidget(lbl_empty)
            self._select_order(None)
            return

        for idx, rec in enumerate(self.records):
            card = OrderCard(rec, is_selected=(idx == 0))
            card.mousePressEvent = lambda event, r=rec: self._select_order(r)
            self.order_list_layout.addWidget(card)

        # 默认选中第一个
        self._select_order(self.records[0])

    def _select_order(self, record):
        self.selected_record = record

        # 高亮选中的卡片
        for i in range(self.order_list_layout.count()):
            w = self.order_list_layout.itemAt(i).widget()
            if isinstance(w, OrderCard):
                w.set_selected(w.record == record)

        if not record:
            self.lbl_header_title.setText(u"📋 POS点餐：--- 堂食")
            self.lbl_order_no.setText(u"订单编号：---")
            self.lbl_create_time.setText(u"创建时间：---")
            self.lbl_item_total.setText(u"商品金额：¥ 0.00")
            self.lbl_final_total.setText(u"实收金额：¥ 0.00")
            self.lbl_pay_val.setText(u"¥ 0.00")

            # 清空商品卡片
            while self.items_layout.count():
                item = self.items_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            return

        remark = record.get("remark", "")
        call_match = re.search(r"叫号:#?(\w+)", remark)
        call_no = call_match.group(1) if call_match else record.get("sale_no", "")[-3:]
        temp_order_match = re.search(r"单号:(\w+)", remark)
        temp_order_no = temp_order_match.group(1) if temp_order_match else record.get("sale_no", "")

        self.lbl_header_title.setText(u"📋 POS点餐：%s 堂食" % call_no)
        self.lbl_order_no.setText(u"订单编号：%s" % temp_order_no)
        self.lbl_create_time.setText(u"创建时间：%s" % str(record.get("created_at", "")))
        tot = record.get("total_price", 0.0)
        self.lbl_item_total.setText(u"商品金额：¥ %.2f" % tot)
        self.lbl_final_total.setText(u"实收金额：¥ %.2f" % tot)
        self.lbl_pay_val.setText(u"¥ %.2f" % tot)

        # 渲染右侧商品列表
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 解析项目
        proj_match = re.search(r"项目:(.*)", remark)
        proj_str = proj_match.group(1) if proj_match else ""

        w_kg = record.get("weight_kg", 0.0)

        if w_kg > 0:
            item_row = QVBoxLayout()
            row_main = QHBoxLayout()
            lbl_name = QLabel(u"经典草本骨汤 ( KG )")
            lbl_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB;")
            lbl_qty = QLabel("x%.3f" % w_kg)
            lbl_qty.setStyleSheet("font-size: 14px; color: #D1D5DB;")
            lbl_price = QLabel("¥ %.2f" % tot)
            lbl_price.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB;")

            row_main.addWidget(lbl_name)
            row_main.addStretch()
            row_main.addWidget(lbl_qty)
            row_main.addSpacing(30)
            row_main.addWidget(lbl_price)
            item_row.addLayout(row_main)

            # 叫号或口味
            lbl_tag = QLabel(u"微辣/")
            lbl_tag.setStyleSheet("font-size: 12px; color: #9CA3AF;")
            item_row.addWidget(lbl_tag)
            self.items_layout.addLayout(item_row)

        elif proj_str:
            for p in proj_str.split(", "):
                p = p.strip()
                if not p:
                    continue
                item_row = QHBoxLayout()
                lbl_name = QLabel(p)
                lbl_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB;")
                lbl_qty = QLabel("x1")
                lbl_qty.setStyleSheet("font-size: 14px; color: #D1D5DB;")
                lbl_price = QLabel("¥ 1.00")
                lbl_price.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB;")

                item_row.addWidget(lbl_name)
                item_row.addStretch()
                item_row.addWidget(lbl_qty)
                item_row.addSpacing(30)
                item_row.addWidget(lbl_price)
                self.items_layout.addLayout(item_row)

        self.items_layout.addStretch()

    # ─── 操作按钮 ───
    def _on_reprint_click(self):
        if not self.selected_record:
            from ui.custom_dialog import show_warning
            show_warning(self, u"提示", u"请先选择要补打小票的订单！")
            return

        if self.printer:
            r = self.selected_record
            remark = r.get("remark", "")
            call_match = re.search(r"叫号:#?(\w+)", remark)
            call_no = call_match.group(1) if call_match else r.get("sale_no", "")[-3:]
            temp_order_match = re.search(r"单号:(\w+)", remark)
            temp_order_no = temp_order_match.group(1) if temp_order_match else r.get("sale_no", "")

            sale_data = {
                "shop_name": self.config.get("shop_name", u"杨国福麻辣烫"),
                "shop_subtitle": self.config.get("shop_subtitle", ""),
                "receipt_footer": self.config.get("receipt_footer", u"谢谢惠顾！"),
                "call_no": call_no,
                "weight_kg": r.get("weight_kg", 0.0),
                "unit_price": r.get("unit_price", 47.60),
                "price_unit": r.get("price_unit", "per_jin"),
                "total_price": r.get("total_price", 0.0),
                "temp_order_no": temp_order_no,
                "cart_items": [{"name": u"重打印订单", "price": r.get("total_price", 0.0)}],
                "created_at": str(r.get("created_at", ""))
            }

            success = self.printer.print_receipt(sale_data)
            if success:
                from ui.custom_dialog import show_info
                show_info(self, u"打印成功", u"订单小票已成功重打印！")
            else:
                from ui.custom_dialog import show_warning
                show_warning(self, u"打印失败", u"无法连接硬件打印机，请检查串口与电缆！")

    def _on_refund_click(self):
        if not self.selected_record:
            from ui.custom_dialog import show_warning
            show_warning(self, u"提示", u"请先选择要处理的订单！")
            return

        from ui.custom_dialog import show_question
        if show_question(self, u"确认退单", u"确定要撤销并退单该笔交易吗？"):
            self.db.delete_sale(self.selected_record["id"])
            self._on_query()
