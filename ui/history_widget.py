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

from core.database import Database, REFUNDED


class OrderCard(QFrame):
    """左侧订单列表卡片"""

    def __init__(self, record, is_selected=False, parent=None):
        super().__init__(parent)
        self.setObjectName("OrderCard")
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

        # 第一行：取餐号：050         已支付
        row1 = QHBoxLayout()
        lbl_title = QLabel(u"取餐号：%s" % call_no)
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #F9FAFB; border: none; background: transparent;")

        import json
        tag_text = u"已支付"
        tag_color = "#6B7280"
        try:
            items = json.loads(r.get("cart_items_json", "[]"))
            if items:
                has_soup = False
                has_drink = False
                has_skewer = False
                has_box = False
                for item in items:
                    name = item.get("name", "")
                    itype = item.get("type", "")
                    if itype == "soup" or "汤" in name or "拌" in name:
                        has_soup = True
                    elif "饮料" in name or "水" in name or "茶" in name:
                        has_drink = True
                    elif "串" in name:
                        has_skewer = True
                    elif "盒" in name:
                        has_box = True
                        
                if has_soup:
                    tag_text = u"含汤底"
                    tag_color = "#F59E0B" # Orange
                else:
                    tag_text = u"不含汤底"
                    tag_color = "#6B7280" # Gray
        except Exception:
            pass

        is_refunded = r.get("payment_status") == REFUNDED
        if is_refunded:
            tag_text, tag_color = u"已退款", "#EF4444"
        lbl_status = QLabel(tag_text)
        lbl_status.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {tag_color}; border: 1px solid {tag_color}; border-radius: 4px; padding: 2px 6px; background: transparent;")

        # 结账方式标签
        pm = r.get("payment_method", "")
        pm_labels = {"shouqianba": "收钱吧", "scan": "手持机器", "cash": "现金", "qr": "被扫"}
        pm_colors = {"shouqianba": "#F97316", "scan": "#059669", "cash": "#2563EB", "qr": "#7C3AED"}
        pm_text = pm_labels.get(pm, "")
        pm_color = pm_colors.get(pm, "#6B7280")

        row1.addWidget(lbl_title)
        row1.addWidget(lbl_status)
        row1.addStretch()
        if pm_text:
            lbl_pm = QLabel(pm_text)
            lbl_pm.setStyleSheet(f"font-size: 10px; font-weight: bold; color: white; background: {pm_color}; border-radius: 4px; padding: 2px 5px;")
            row1.addWidget(lbl_pm)
        layout.addLayout(row1)

        # 第二行：2026-07-31 21:12:05     实收：¥ 38.83
        row2 = QHBoxLayout()
        lbl_time = QLabel(created_at)
        lbl_time.setStyleSheet("font-size: 12px; color: #9CA3AF; border: none; background: transparent;")

        amount_prefix = u"已退：" if is_refunded else u"实收："
        amount_color = "#FCA5A5" if is_refunded else "#D1D5DB"
        lbl_amount = QLabel(u"%s¥ %.2f" % (amount_prefix, r.get("total_price", 0.0)))
        lbl_amount.setStyleSheet("font-size: 13px; font-weight: bold; color: %s; border: none; background: transparent;" % amount_color)

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
                "#OrderCard { background: #1E293B; border: 2px solid #EA580C; border-radius: 8px; }\n"
                "#OrderCard QLabel { background: transparent; border: none; }"
            )
        else:
            self.setStyleSheet(
                "#OrderCard { background: #111827; border: 1px solid transparent; border-radius: 8px; }\n"
                "#OrderCard:hover { background: #1F2937; }\n"
                "#OrderCard QLabel { background: transparent; border: none; }"
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

        self.current_page = 0
        self.items_per_page = 8

        self._build_ui()
        self.reload_orders()

    def _clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self._clear_layout(item.layout())

    def reload_orders(self):
        self._on_query()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ── 1. 顶部 Header 栏 ──
        header_bar = QHBoxLayout()
        header_bar.setSpacing(12)

        # 日期选择 (触屏优化的独立年月日下拉框)
        date_layout = QHBoxLayout()
        date_layout.setSpacing(6)
        
        cbo_style = """
            QComboBox { background: #1F2937; color: #F9FAFB; font-size: 16px; font-weight: bold; 
                        padding: 8px 12px; border: none; border-radius: 6px; min-width: 80px; }
            QComboBox QAbstractItemView {
                background-color: #1F2937;
                color: #F9FAFB;
                selection-background-color: #EA580C;
                font-size: 18px;
            }
            QComboBox QAbstractItemView::item {
                min-height: 44px;
            }
        """

        self.cbo_year = QComboBox()
        self.cbo_month = QComboBox()
        self.cbo_day = QComboBox()

        for cbo in (self.cbo_year, self.cbo_month, self.cbo_day):
            cbo.setStyleSheet(cbo_style)
            # 为了触屏体验，注入强制高度委托
            from ui.styles import apply_touch_combo_style
            apply_touch_combo_style(cbo, item_height=48)

        curr_year = QDate.currentDate().year()
        for y in range(2020, curr_year + 5):
            self.cbo_year.addItem(f"{y}年", y)
        self.cbo_year.setCurrentText(f"{curr_year}年")

        for m in range(1, 13):
            self.cbo_month.addItem(f"{m:02d}月", m)
        self.cbo_month.setCurrentText(f"{QDate.currentDate().month():02d}月")

        self._update_days()
        self.cbo_day.setCurrentText(f"{QDate.currentDate().day():02d}日")

        self.cbo_year.currentIndexChanged.connect(self._on_year_month_changed)
        self.cbo_month.currentIndexChanged.connect(self._on_year_month_changed)
        self.cbo_day.currentIndexChanged.connect(self._on_query)

        date_layout.addWidget(self.cbo_year)
        date_layout.addWidget(self.cbo_month)
        date_layout.addWidget(self.cbo_day)

        # ── 添加时间筛选 (从 X 时 到 X 时) ──
        lbl_from = QLabel(u" 从 ")
        lbl_from.setStyleSheet("font-size: 15px; font-weight: bold; color: #9CA3AF; border: none;")
        date_layout.addWidget(lbl_from)

        self.cbo_start_hour = QComboBox()
        self.cbo_end_hour = QComboBox()

        for cbo in (self.cbo_start_hour, self.cbo_end_hour):
            cbo.setStyleSheet(cbo_style)
            from ui.styles import apply_touch_combo_style
            apply_touch_combo_style(cbo, item_height=48)
            for h in range(0, 24):
                cbo.addItem(f"{h:02d}时", h)

        self.cbo_start_hour.setCurrentIndex(0)  # 00时
        self.cbo_end_hour.setCurrentIndex(23)   # 23时

        self.cbo_start_hour.currentIndexChanged.connect(self._on_query)
        self.cbo_end_hour.currentIndexChanged.connect(self._on_query)

        date_layout.addWidget(self.cbo_start_hour)
        
        lbl_to = QLabel(u" 到 ")
        lbl_to.setStyleSheet("font-size: 15px; font-weight: bold; color: #9CA3AF; border: none;")
        date_layout.addWidget(lbl_to)
        
        date_layout.addWidget(self.cbo_end_hour)

        header_bar.addLayout(date_layout)

        # 快捷操作按钮
        quick_date_layout = QHBoxLayout()
        quick_date_layout.setSpacing(8)
        
        quick_btn_style = """
            QPushButton { background: #374151; color: white; font-weight: bold; font-size: 14px; padding: 8px 12px; border-radius: 6px; border: none; }
        """
        
        self.btn_today = QPushButton(u"今天")
        self.btn_today.setStyleSheet(quick_btn_style)
        self.btn_today.clicked.connect(lambda: self._set_quick_date(0))
        
        self.btn_yesterday = QPushButton(u"昨天")
        self.btn_yesterday.setStyleSheet(quick_btn_style)
        self.btn_yesterday.clicked.connect(lambda: self._set_quick_date(-1))
        
        self.btn_day_before = QPushButton(u"前天")
        self.btn_day_before.setStyleSheet(quick_btn_style)
        self.btn_day_before.clicked.connect(lambda: self._set_quick_date(-2))
        
        quick_date_layout.addWidget(self.btn_today)
        quick_date_layout.addWidget(self.btn_yesterday)
        quick_date_layout.addWidget(self.btn_day_before)

        header_bar.addLayout(quick_date_layout)

        header_bar.addSpacing(16)

        header_bar.addStretch()
        
        main_layout.addLayout(header_bar)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #374151; border: none;")
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
        cbo_search_style = """
            QComboBox { background: #1F2937; color: white; padding: 6px 12px; border: none; border-radius: 6px; outline: none; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox QAbstractItemView {
                background-color: #1F2937;
                color: #F9FAFB;
                selection-background-color: #EA580C;
                outline: none;
                border: 1px solid #374151;
            }
            QComboBox QAbstractItemView::item {
                min-height: 36px;
            }
        """
        self.cbo_search_type.setStyleSheet(cbo_search_style)
        from ui.styles import apply_touch_combo_style
        apply_touch_combo_style(self.cbo_search_type, item_height=48)
        search_row.addWidget(self.cbo_search_type)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(u"输入查询内容...")
        self.txt_search.setStyleSheet(
            "QLineEdit { background: #1F2937; color: white; padding: 6px 12px; border: none; border-radius: 6px; }"
        )
        self.txt_search.returnPressed.connect(self._on_query)
        search_row.addWidget(self.txt_search)

        btn_search = QPushButton(u"查询")
        btn_search.setStyleSheet(
            "background: #EA580C; color: white; font-weight: bold; padding: 6px 14px; border-radius: 6px; border: none;"
        )
        btn_search.clicked.connect(self._on_query)
        search_row.addWidget(btn_search)

        self.btn_sort = QPushButton(u"1↓")
        self.btn_sort.setStyleSheet(
            "background: #EA580C; color: white; font-weight: bold; padding: 6px 10px; border-radius: 6px; border: none;"
        )
        self.btn_sort.setCheckable(True)
        self.btn_sort.clicked.connect(self._on_sort_clicked)
        search_row.addWidget(self.btn_sort)

        left_col.addLayout(search_row)

        # (3) 订单列表容器 (取消滑动，纯分页展示)
        self.order_list_container = QWidget()
        self.order_list_layout = QVBoxLayout(self.order_list_container)
        self.order_list_layout.setContentsMargins(0, 0, 0, 0)
        self.order_list_layout.setSpacing(6)
        self.order_list_layout.setAlignment(Qt.AlignTop)

        left_col.addWidget(self.order_list_container, stretch=1)

        # 底部翻页控制
        left_page_row = QHBoxLayout()
        self.btn_prev_l = QPushButton(u"上一页")
        self.btn_prev_l.setStyleSheet("background: #374151; color: white; padding: 6px 12px; border-radius: 6px; border: none;")
        self.btn_prev_l.clicked.connect(self._on_prev_page)

        self.lbl_page = QLabel("1/1")
        self.lbl_page.setAlignment(Qt.AlignCenter)
        self.lbl_page.setStyleSheet("color: white; font-weight: bold;")

        self.btn_next_l = QPushButton(u"下一页")
        self.btn_next_l.setStyleSheet("background: #EA580C; color: white; font-weight: bold; padding: 6px 12px; border-radius: 6px; border: none;")
        self.btn_next_l.clicked.connect(self._on_next_page)

        left_page_row.addWidget(self.btn_prev_l)
        left_page_row.addWidget(self.lbl_page)
        left_page_row.addWidget(self.btn_next_l)
        left_col.addLayout(left_page_row)

        body_layout.addLayout(left_col, stretch=3)

        # ──────────────── Right Panel (订单详情) ────────────────
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        # (1) 基础信息 Header
        meta_row = QHBoxLayout()
        
        self.lbl_header_title = QLabel(u"取餐号：---")
        self.lbl_header_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #F9FAFB; border: none;")
        meta_row.addWidget(self.lbl_header_title)
        
        meta_row.addStretch()
        
        self.lbl_header_status = QLabel(u"已支付")
        self.lbl_header_status.setStyleSheet("font-size: 16px; font-weight: bold; color: #EA580C; border: none;")
        meta_row.addWidget(self.lbl_header_status)
        
        right_col.addLayout(meta_row)

        # (2) 购买商品明细滚动区域
        self.items_scroll = QScrollArea()
        self.items_scroll.setWidgetResizable(True)
        self.items_scroll.setStyleSheet(
            "QScrollArea { border: none; background: #1E293B; border-radius: 10px; }"
            "QScrollBar:vertical { width: 8px; background: #1E293B; }"
            "QScrollBar::handle:vertical { background: #4B5563; border-radius: 4px; }"
        )
        
        self.items_card = QWidget()
        self.items_card.setStyleSheet("background: transparent;")
        self.items_layout = QVBoxLayout(self.items_card)
        self.items_layout.setContentsMargins(16, 14, 16, 14)
        self.items_layout.setSpacing(10)
        self.items_layout.setAlignment(Qt.AlignTop)

        self.items_scroll.setWidget(self.items_card)
        right_col.addWidget(self.items_scroll, stretch=2)



        # (4) 底部并排信息框 (订单信息 + 金额明细)
        bottom_cards_row = QHBoxLayout()
        bottom_cards_row.setSpacing(10)

        # 订单信息卡片
        card_order_info = QFrame()
        card_order_info.setStyleSheet("QFrame { background: #1E293B; border: none; border-radius: 10px; }")
        layout_oi = QVBoxLayout(card_order_info)
        layout_oi.setContentsMargins(14, 12, 14, 12)
        layout_oi.setSpacing(6)

        lbl_oi_title = QLabel(u"订单信息")
        lbl_oi_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB; border: none;")
        layout_oi.addWidget(lbl_oi_title)

        self.lbl_order_no = QLabel(u"订单编号：---")
        self.lbl_order_no.setStyleSheet("color: #9CA3AF; font-size: 13px; border: none;")
        self.lbl_create_time = QLabel(u"创建时间：---")
        self.lbl_create_time.setStyleSheet("color: #9CA3AF; font-size: 13px; border: none;")
        self.lbl_payment_method = QLabel(u"结账方式：---")
        self.lbl_payment_method.setStyleSheet("color: #9CA3AF; font-size: 13px; border: none;")
        self.lbl_remark_info = QLabel(u"备注信息：")
        self.lbl_remark_info.setStyleSheet("color: #9CA3AF; font-size: 13px; border: none;")

        layout_oi.addWidget(self.lbl_order_no)
        layout_oi.addWidget(self.lbl_create_time)
        layout_oi.addWidget(self.lbl_payment_method)
        layout_oi.addWidget(self.lbl_remark_info)
        bottom_cards_row.addWidget(card_order_info, stretch=1)

        # 金额明细卡片
        card_amount_info = QFrame()
        card_amount_info.setStyleSheet("QFrame { background: #1E293B; border: none; border-radius: 10px; }")
        layout_ai = QVBoxLayout(card_amount_info)
        layout_ai.setContentsMargins(14, 12, 14, 12)
        layout_ai.setSpacing(6)

        lbl_ai_title = QLabel(u"金额明细")
        lbl_ai_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB; border: none;")
        layout_ai.addWidget(lbl_ai_title)

        self.lbl_item_total = QLabel(u"商品金额：¥ 0.00")
        self.lbl_item_total.setStyleSheet("color: #9CA3AF; font-size: 13px; border: none;")
        self.lbl_discount_total = QLabel(u"折扣金额：¥ 0.00")
        self.lbl_discount_total.setStyleSheet("color: #9CA3AF; font-size: 13px; border: none;")
        self.lbl_final_total = QLabel(u"实收金额：¥ 0.00")
        self.lbl_final_total.setStyleSheet("color: #EA580C; font-size: 15px; font-weight: 900; border: none;")

        layout_ai.addWidget(self.lbl_item_total)
        layout_ai.addWidget(self.lbl_discount_total)
        layout_ai.addWidget(self.lbl_final_total)
        bottom_cards_row.addWidget(card_amount_info, stretch=1)

        right_col.addLayout(bottom_cards_row)

        # (5) 底部操作栏
        right_action_row = QHBoxLayout()
        right_action_row.setSpacing(8)

        right_action_row.addStretch()

        btn_reprint_customer = QPushButton(u"重打顾客单")
        btn_reprint_customer.setStyleSheet("background: #374151; color: white; font-weight: bold; font-size: 14px; padding: 10px 20px; border-radius: 6px; border: none;")
        btn_reprint_customer.clicked.connect(lambda checked=False: self._on_reprint_click("customer"))

        btn_reprint_kitchen = QPushButton(u"重打制作单")
        btn_reprint_kitchen.setStyleSheet("background: #374151; color: white; font-weight: bold; font-size: 14px; padding: 10px 20px; border-radius: 6px; border: none;")
        btn_reprint_kitchen.clicked.connect(lambda checked=False: self._on_reprint_click("kitchen"))

        btn_reprint_all = QPushButton(u"全部重打")
        btn_reprint_all.setStyleSheet("background: #EA580C; color: white; font-weight: 900; font-size: 15px; padding: 10px 24px; border-radius: 6px; border: none;")
        btn_reprint_all.clicked.connect(lambda checked=False: self._on_reprint_click("all"))

        right_action_row.addWidget(btn_reprint_customer)
        right_action_row.addWidget(btn_reprint_kitchen)
        right_action_row.addWidget(btn_reprint_all)

        right_col.addLayout(right_action_row)

        body_layout.addLayout(right_col, stretch=5)

        main_layout.addLayout(body_layout, stretch=1)

    # ─── 数据查询与加载 ───
    def _set_quick_date(self, days_offset):
        target = QDate.currentDate().addDays(days_offset)
        
        self.cbo_year.blockSignals(True)
        self.cbo_month.blockSignals(True)
        self.cbo_day.blockSignals(True)
        
        self.cbo_year.setCurrentText(f"{target.year()}年")
        self.cbo_month.setCurrentText(f"{target.month():02d}月")
        self._update_days()
        self.cbo_day.setCurrentText(f"{target.day():02d}日")
        
        self.cbo_year.blockSignals(False)
        self.cbo_month.blockSignals(False)
        self.cbo_day.blockSignals(False)
        
        self._on_query()

    def _update_days(self):
        y = self.cbo_year.currentData()
        m = self.cbo_month.currentData()
        if not y or not m: return
        
        curr_day_text = self.cbo_day.currentText()
        curr_day = int(curr_day_text.replace("日", "")) if curr_day_text else 1
        
        days_in_month = QDate(y, m, 1).daysInMonth()
        
        self.cbo_day.blockSignals(True)
        self.cbo_day.clear()
        for d in range(1, days_in_month + 1):
            self.cbo_day.addItem(f"{d:02d}日", d)
            
        if curr_day <= days_in_month:
            self.cbo_day.setCurrentText(f"{curr_day:02d}日")
        else:
            self.cbo_day.setCurrentText(f"{days_in_month:02d}日")
        self.cbo_day.blockSignals(False)

    def _on_year_month_changed(self):
        self._update_days()
        self._on_query()

    def _on_query(self):
        y = self.cbo_year.currentData()
        m = self.cbo_month.currentData()
        d = self.cbo_day.currentData()
        if not y or not m or not d:
            return
        target_date = f"{y}-{m:02d}-{d:02d}"
        raw_records = self.db.get_sales_by_date(target_date, target_date)

        # 如果有关键字搜索或时间筛选
        kw = self.txt_search.text().strip()
        stype = self.cbo_search_type.currentText()
        start_h = self.cbo_start_hour.currentData()
        end_h = self.cbo_end_hour.currentData()
        
        filtered = []
        for r in raw_records:
            # 1. 时间筛选逻辑 (解析 created_at 字段的小时)
            created_at = r.get("created_at", "")
            if len(created_at) >= 13:
                try:
                    hour_int = int(created_at[11:13])
                    if not (start_h <= hour_int <= end_h):
                        continue
                except ValueError:
                    pass
            
            # 2. 关键字筛选逻辑
            if kw:
                remark = r.get("remark", "")
                if stype == u"取餐号":
                    if kw not in remark and kw not in r.get("sale_no", ""):
                        continue
                else:
                    if kw not in r.get("sale_no", "") and kw not in remark:
                        continue
                        
            filtered.append(r)
            
        self.records = filtered

        # 应用排序逻辑
        is_asc = getattr(self, "btn_sort", None) and self.btn_sort.isChecked()
        self.records.sort(key=lambda x: x.get("id", 0), reverse=not is_asc)

        self.current_page = 0
        self._render_order_list()

    def _on_sort_clicked(self):
        is_asc = getattr(self, "btn_sort", None) and self.btn_sort.isChecked()
        if is_asc:
            self.btn_sort.setText(u"1↑")
        else:
            self.btn_sort.setText(u"1↓")
        self._on_query()

    def _on_prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render_order_list()

    def _on_next_page(self):
        total_pages = max(1, (len(self.records) + self.items_per_page - 1) // self.items_per_page)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._render_order_list()

    def _render_order_list(self):
        # 清空已有卡片
        while self.order_list_layout.count():
            item = self.order_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total_pages = max(1, (len(self.records) + self.items_per_page - 1) // self.items_per_page)
        self.lbl_page.setText(f"{self.current_page + 1}/{total_pages}")

        if not self.records:
            lbl_empty = QLabel(u"暂无订单记录")
            lbl_empty.setAlignment(Qt.AlignCenter)
            lbl_empty.setStyleSheet("color: #9CA3AF; font-size: 14px; margin-top: 20px;")
            self.order_list_layout.addWidget(lbl_empty)
            self._select_order(None)
            return

        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_records = self.records[start_idx:end_idx]

        for idx, rec in enumerate(page_records):
            card = OrderCard(rec, is_selected=(idx == 0))
            card.mousePressEvent = lambda event, r=rec: self._select_order(r)
            self.order_list_layout.addWidget(card)

        # 默认选中第一个
        if page_records:
            self._select_order(page_records[0])

    def _select_order(self, record):
        self.selected_record = record

        # 高亮选中的卡片
        for i in range(self.order_list_layout.count()):
            w = self.order_list_layout.itemAt(i).widget()
            if isinstance(w, OrderCard):
                w.set_selected(w.record == record)

        if not record:
            self.lbl_header_title.setText(u"表 取餐号：---")
            self.lbl_order_no.setText(u"订单编号：---")
            self.lbl_create_time.setText(u"创建时间：---")
            self.lbl_item_total.setText(u"商品金额：¥ 0.00")
            self.lbl_final_total.setText(u"实收金额：¥ 0.00")
            self.lbl_remark_info.setText(u"备注信息：")

            # 清空商品卡片
            self._clear_layout(self.items_layout)
            return

        remark = record.get("remark", "")
        call_match = re.search(r"叫号:#?(\w+)", remark)
        call_no = call_match.group(1) if call_match else record.get("sale_no", "")[-3:]
        temp_order_match = re.search(r"单号:(\w+)", remark)
        temp_order_no = temp_order_match.group(1) if temp_order_match else record.get("sale_no", "")

        self.lbl_header_title.setText(u"取餐号：%s" % call_no)
        self.lbl_order_no.setText(u"订单编号：%s" % temp_order_no)
        self.lbl_create_time.setText(u"创建时间：%s" % str(record.get("created_at", "")))
        
        # 结账方式
        pm = record.get("payment_method", "")
        pm_display = {"shouqianba": "收钱吧", "scan": "手持机器", "cash": "现金", "qr": "被扫"}
        payment_state = record.get("payment_status", "PAID")
        self.lbl_payment_method.setText(u"结账方式：%s" % pm_display.get(pm, "未记录"))
        if payment_state == REFUNDED:
            self.lbl_remark_info.setText(
                u"退款：%s；原因：%s" % (
                    record.get("refunded_at") or u"已退款",
                    record.get("refund_reason") or u"门店退单",
                )
            )
        else:
            print_state = record.get("print_status", "")
            self.lbl_remark_info.setText(u"打印状态：%s" % ({"PRINTED": u"已打印", "FAILED": u"打印失败，可补打", "PENDING": u"待打印"}.get(print_state, u"未记录")))
        
        import json
        tag_text = u"已支付"
        tag_color = "#6B7280"
        try:
            items = json.loads(record.get("cart_items_json", "[]"))
            if items:
                has_soup = False
                has_drink = False
                has_skewer = False
                has_box = False
                for item in items:
                    name = item.get("name", "")
                    itype = item.get("type", "")
                    if itype == "soup" or "汤" in name or "拌" in name:
                        has_soup = True
                    elif "饮料" in name or "水" in name or "茶" in name:
                        has_drink = True
                    elif "串" in name:
                        has_skewer = True
                    elif "盒" in name:
                        has_box = True
                        
                if has_soup:
                    tag_text = u"汤 含汤底"
                    tag_color = "#F59E0B" # Orange
                else:
                    tag_text = u"不含汤底"
                    tag_color = "#6B7280" # Gray
        except Exception:
            pass

        if payment_state == REFUNDED:
            tag_text, tag_color = u"已退款", "#EF4444"
        self.lbl_header_status.setText(tag_text)
        self.lbl_header_status.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {tag_color}; border: 1px solid {tag_color}; border-radius: 4px; padding: 2px 8px; background: transparent;")
        tot = record.get("total_price", 0.0)
        self.lbl_item_total.setText(u"商品金额：¥ %.2f" % tot)
        self.lbl_discount_total.setText(u"折扣金额：¥ 0.00")
        self.lbl_final_total.setText((u"退款金额：¥ %.2f" if payment_state == REFUNDED else u"实收金额：¥ %.2f") % tot)

        # 渲染右侧商品列表
        self._clear_layout(self.items_layout)

        import json
        cart_items_json = record.get("cart_items_json")
        cart_items = []
        if cart_items_json:
            try:
                cart_items = json.loads(cart_items_json)
            except Exception:
                pass

        if cart_items:
            original_total = 0.0
            for idx, item in enumerate(cart_items):
                name = item.get("name", "")
                tag = item.get("tag", "")
                qty = item.get("qty", 1)
                price = item.get("price", 0.0)
                base_price = item.get("base_price", 0.0)
                item_type = item.get("type", "")
                disc_rate = item.get("discount_rate", 1.0)
                
                original_total += base_price * qty
                
                item_row = QVBoxLayout()
                item_row.setSpacing(2)

                row_main = QHBoxLayout()
                lbl_name = QLabel(name)
                lbl_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB; border: none;")

                if item_type == "soup":
                    w = item.get("weight", record.get("weight_kg", 0.0))
                    lbl_qty = QLabel("x%.3f kg" % w)
                else:
                    lbl_qty = QLabel("x%d" % qty)

                lbl_qty.setStyleSheet("font-size: 14px; color: #D1D5DB; border: none;")
                
                row_main.addWidget(lbl_name)
                row_main.addStretch()
                row_main.addWidget(lbl_qty)
                
                if abs(disc_rate - 1.0) > 0.001:
                    rate_str = f"{disc_rate * 10:g}折"
                    lbl_disc_rate = QLabel(f"({rate_str})")
                    lbl_disc_rate.setStyleSheet("color: #F59E0B; border: none; font-size: 13px;")
                    
                    lbl_orig_price = QLabel(f"¥ {base_price * qty:.2f}")
                    font = lbl_orig_price.font()
                    font.setStrikeOut(True)
                    lbl_orig_price.setFont(font)
                    lbl_orig_price.setStyleSheet("color: #9CA3AF; border: none;")
                    
                    lbl_price = QLabel(f"¥ {price:.2f}")
                    lbl_price.setStyleSheet("font-size: 15px; font-weight: bold; color: #F59E0B; border: none;")

                    row_main.addSpacing(10)
                    row_main.addWidget(lbl_disc_rate)
                    row_main.addSpacing(10)
                    row_main.addWidget(lbl_orig_price)
                    row_main.addSpacing(10)
                    row_main.addWidget(lbl_price)
                else:
                    lbl_price = QLabel("¥ %.2f" % price)
                    lbl_price.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB; border: none;")
                    row_main.addSpacing(30)
                    row_main.addWidget(lbl_price)

                item_row.addLayout(row_main)

                if tag and tag != "无":
                    lbl_tag = QLabel(tag)
                    lbl_tag.setStyleSheet("font-size: 12px; color: #EA580C; border: none; font-weight: bold;")
                    item_row.addWidget(lbl_tag)

                self.items_layout.addLayout(item_row)
            
            self.lbl_item_total.setText(u"商品金额：¥ %.2f" % original_total)
            self.lbl_discount_total.setText(u"折扣金额：¥ %.2f" % (original_total - tot))
        else:
            # 兼容旧版本记录
            proj_match = re.search(r"项目:(.*)", remark)
            proj_str = proj_match.group(1).strip() if proj_match else ""

            w_kg = record.get("weight_kg", 0.0)

            if proj_str:
                items_list = [p.strip() for p in proj_str.split(",") if p.strip()]
                for idx, p in enumerate(items_list):
                    tag_match = re.search(r"^([^(]+)(?:\(([^)]+)\))?", p)
                    if tag_match:
                        name_part = tag_match.group(1).strip()
                        tag_part = tag_match.group(2)
                    else:
                        name_part = p
                        tag_part = None

                    item_row = QVBoxLayout()
                    item_row.setSpacing(2)

                    row_main = QHBoxLayout()
                    lbl_name = QLabel(name_part)
                    lbl_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB; border: none;")

                    if idx == 0 and w_kg > 0:
                        lbl_qty = QLabel("x%.3f kg" % w_kg)
                        item_price_str = "¥ %.2f" % tot
                    else:
                        lbl_qty = QLabel("x1")
                        item_price_str = "¥ 1.00" if (idx > 0 and w_kg > 0) else ("¥ %.2f" % tot)

                    lbl_qty.setStyleSheet("font-size: 14px; color: #D1D5DB; border: none;")
                    lbl_price = QLabel(item_price_str)
                    lbl_price.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB; border: none;")

                    row_main.addWidget(lbl_name)
                    row_main.addStretch()
                    row_main.addWidget(lbl_qty)
                    row_main.addSpacing(30)
                    row_main.addWidget(lbl_price)
                    item_row.addLayout(row_main)

                    if tag_part and tag_part != "无":
                        lbl_tag = QLabel(tag_part)
                        lbl_tag.setStyleSheet("font-size: 12px; color: #EA580C; border: none; font-weight: bold;")
                        item_row.addWidget(lbl_tag)

                    self.items_layout.addLayout(item_row)

            elif w_kg > 0:
                item_row = QVBoxLayout()
                row_main = QHBoxLayout()
                lbl_name = QLabel(u"称重菜品")
                lbl_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB; border: none;")
                lbl_qty = QLabel("x%.3f kg" % w_kg)
                lbl_qty.setStyleSheet("font-size: 14px; color: #D1D5DB; border: none;")
                lbl_price = QLabel("¥ %.2f" % tot)
                lbl_price.setStyleSheet("font-size: 15px; font-weight: bold; color: #F9FAFB; border: none;")

                row_main.addWidget(lbl_name)
                row_main.addStretch()
                row_main.addWidget(lbl_qty)
                row_main.addSpacing(30)
                row_main.addWidget(lbl_price)
                item_row.addLayout(row_main)
                self.items_layout.addLayout(item_row)

        self.items_layout.addStretch()

    # ─── 操作按钮 ───
    def _on_reprint_click(self, ptype="all"):
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

            # 提取真实的订单列表数据以供打印
            import json
            cart_items = []
            cart_items_json = r.get("cart_items_json")
            if cart_items_json:
                try:
                    cart_items = json.loads(cart_items_json)
                except Exception:
                    pass
            if not cart_items:
                # 兼容旧版本记录
                proj_match = re.search(r"项目:(.*)", remark)
                proj_str = proj_match.group(1).strip() if proj_match else ""
                w_kg = r.get("weight_kg", 0.0)
                tot = r.get("total_price", 0.0)

                if proj_str:
                    items_list = [p.strip() for p in proj_str.split(",") if p.strip()]
                    for idx, p in enumerate(items_list):
                        tag_match = re.search(r"^([^(]+)(?:\(([^)]+)\))?", p)
                        name_part = tag_match.group(1).strip() if tag_match else p
                        tag_part = tag_match.group(2) if tag_match else ""
                        
                        item_entry = {
                            "name": name_part,
                            "tag": tag_part if tag_part and tag_part != "无" else ""
                        }
                        if idx == 0 and w_kg > 0:
                            item_entry["type"] = "soup"
                            item_entry["weight"] = w_kg
                            item_entry["price"] = tot
                            item_entry["base_price"] = tot
                            item_entry["qty"] = 1
                        else:
                            item_entry["type"] = "item"
                            item_entry["price"] = 1.00
                            item_entry["base_price"] = 1.00
                            item_entry["qty"] = 1
                        cart_items.append(item_entry)
                elif w_kg > 0:
                    cart_items.append({
                        "name": u"称重菜品",
                        "type": "soup",
                        "weight": w_kg,
                        "price": tot,
                        "base_price": tot,
                        "qty": 1,
                        "tag": ""
                    })
                else:
                    # 兜底：如果找不到任何信息
                    cart_items = [{"name": u"重打印历史订单", "price": tot, "type": "soup", "weight": 0.0}]

            sale_data = {
                "shop_name": self.config.get("shop_name", u"杨国福麻辣烫"),
                "shop_subtitle": self.config.get("shop_subtitle", ""),
                "call_no": call_no,
                "weight_kg": r.get("weight_kg", 0.0),
                "unit_price": r.get("unit_price", 47.60),
                "price_unit": r.get("price_unit", "per_jin"),
                "total_price": r.get("total_price", 0.0),
                "temp_order_no": temp_order_no,
                "cart_items": cart_items,
                "created_at": str(r.get("created_at", ""))
            }

            success = self.printer.print_receipt(sale_data, print_type=ptype)
            self.db.mark_print_result(r["id"], success, getattr(self.printer, "last_error", ""))
            if success:
                from ui.custom_dialog import show_info
                show_info(self, u"打印成功", u"订单小票已成功重发至打印机！")
            else:
                from ui.custom_dialog import show_warning
                show_warning(self, u"打印失败", u"无法连接硬件打印机，请检查串口与电缆！")

    def _on_refund_click(self):
        if not self.selected_record:
            from ui.custom_dialog import show_warning
            show_warning(self, u"提示", u"请先选择要处理的订单！")
            return

        if self.selected_record.get("payment_status") == REFUNDED:
            from ui.custom_dialog import show_warning
            show_warning(self, u"无需重复退款", u"该笔订单已经标记为退款，交易记录会永久保留以便对账。")
            return

        from ui.custom_dialog import show_question, show_info, show_warning
        if show_question(self, u"确认退款", u"确认将本订单标记为已退款吗？\n\n退款不会删除订单、小票和操作记录。请先在实际支付渠道完成退款。"):
            if self.db.refund_sale(self.selected_record["id"], reason=u"前台退单"):
                show_info(self, u"已标记退款", u"订单已保留并显示为“已退款”，报表会自动从实收中扣除。")
                self._on_query()
            else:
                show_warning(self, u"退款未完成", u"订单状态已变化，请刷新后确认。")
