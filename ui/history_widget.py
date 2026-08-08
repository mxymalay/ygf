"""
历史订单查询界面 — 还原 POS 标准排版
PyQt5 + Python 3.8 兼容
"""
import re
from datetime import date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QLineEdit, QComboBox, QFrame, QScrollArea,
    QGridLayout, QMessageBox, QDialog, QSizePolicy
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QFont

from core.database import Database, REFUNDED
from core.payment_utils import payment_display_label


class OrderCard(QFrame):
    """左侧订单列表卡片"""

    def __init__(self, record, is_selected=False, parent=None):
        super().__init__(parent)
        self.setObjectName("OrderCard")
        self.record = record
        self.is_selected = is_selected
        self.setCursor(Qt.PointingHandCursor)
        # Win7 的 Qt 字体度量比 Win11 更容易把两行内容撑高；固定卡片
        # 高度，避免下一张卡片压住当前卡片的底边。
        self.setFixedHeight(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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
            tag_text, tag_color = u"⛔ 已退款", "#EF4444"
        lbl_status = QLabel(tag_text)
        lbl_status.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {tag_color}; border: 1px solid {tag_color}; border-radius: 4px; padding: 2px 6px; background: transparent;")

        source = str(r.get("source", "private") or "private").lower()
        source_text = u"官方" if source in ("official", "official_pos", "official_pos_relay") else u"私域"
        source_color = "#0EA5E9" if source_text == u"官方" else "#10B981"
        lbl_source = QLabel(source_text)
        lbl_source.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #FFFFFF; background: %s; "
            "border-radius: 4px; padding: 2px 6px;" % source_color
        )

        # 结账方式标签
        pm = r.get("payment_method", "")
        pm_colors = {"shouqianba": "#F97316", "scan": "#059669", "cash": "#2563EB", "qr": "#7C3AED", "mixed": "#D97706"}
        breakdown = r.get("payment_breakdown_json", "")
        pm_text = payment_display_label(pm, breakdown)
        if not pm_text and breakdown:
            pm_text = payment_display_label("mixed", breakdown)
        if pm == "mixed":
            pm_text = "混合支付"
        pm_color = pm_colors.get(pm, "#6B7280")

        row1.addWidget(lbl_title)
        row1.addWidget(lbl_source)
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
        self.order_source_filter = "all"
        self.order_source_buttons = {}

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

    def open_order(self, order_id=None, record=None):
        """Show one order directly, bypassing the current date filter.

        ``record`` is preferred because the cashier summary already has the
        exact ledger row.  ``order_id`` remains as a compatibility fallback
        for callers that only know the identifier.
        """
        if record is None:
            if not order_id:
                return False
            record = self.db.get_sale_by_order_id(str(order_id))
        if not record:
            return False

        # When the cashier page is opened with a different date selected,
        # move the history filter to this order's date first.  This makes the
        # left-hand list and the detail pane point at the same order instead
        # of showing a detail record that is invisible in the list.
        created_at = str(record.get("created_at", "") or "")
        target_date = created_at[:10]
        current_date = ""
        try:
            current_date = "%04d-%02d-%02d" % (
                int(self.cbo_year.currentData()),
                int(self.cbo_month.currentData()),
                int(self.cbo_day.currentData()),
            )
        except (AttributeError, TypeError, ValueError):
            pass
        if target_date and target_date != current_date:
            try:
                year, month, day = [int(part) for part in target_date.split("-")]
                self.cbo_year.blockSignals(True)
                self.cbo_month.blockSignals(True)
                self.cbo_day.blockSignals(True)
                self.cbo_year.setCurrentText("%d年" % year)
                self.cbo_month.setCurrentText("%02d月" % month)
                self._update_days()
                self.cbo_day.setCurrentText("%02d日" % day)
                self.cbo_year.blockSignals(False)
                self.cbo_month.blockSignals(False)
                self.cbo_day.blockSignals(False)
                self._on_query()
            except (AttributeError, TypeError, ValueError):
                # Older/invalid timestamps should still open in the detail
                # pane even when the date controls cannot be adjusted.
                for combo in (self.cbo_year, self.cbo_month, self.cbo_day):
                    combo.blockSignals(False)

        record_key = record.get("id")
        if record_key is None:
            record_key = record.get("order_id") or order_id
        match_index = None
        for index, candidate in enumerate(self.records):
            candidate_key = candidate.get("id")
            if candidate_key is None:
                candidate_key = candidate.get("order_id")
            if record_key is not None and str(candidate_key) == str(record_key):
                match_index = index
                break
        if match_index is not None:
            self.current_page = match_index // max(1, self.items_per_page)
            self._render_order_list()
            # _render_order_list creates the visible card for this page; use
            # the in-list row so its highlight and detail pane stay linked.
            self._select_order(self.records[match_index])
            if hasattr(self, "order_list_scroll"):
                self.order_list_scroll.verticalScrollBar().setValue(0)
        else:
            # Keep the direct-detail fallback for rows filtered out by a
            # keyword/time filter or legacy records outside the date range.
            self._select_order(record)
        return True

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ── 1. 顶部 Header 栏 ──
        header_bar = QHBoxLayout()
        header_bar.setSpacing(12)

        # 日期选择 (触屏优化的独立年月日下拉框)
        date_layout = QHBoxLayout()
        date_layout.setSpacing(8)
        date_layout.setContentsMargins(0, 0, 0, 0)

        lbl_date = QLabel(u"日期")
        lbl_date.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #CBD5E1; "
            "border: none; background: transparent; padding-right: 2px;"
        )
        date_layout.addWidget(lbl_date)
        
        cbo_style = """
            QComboBox { background: #1F2937; color: #F9FAFB; font-size: 15px; font-weight: bold; 
                        padding: 6px 5px; border: none; border-radius: 6px; min-width: 58px; }
            QComboBox::drop-down { width: 18px; border: none; }
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

        for cbo, combo_width, popup_width in (
            (self.cbo_year, 142, 250),
            (self.cbo_month, 108, 190),
            (self.cbo_day, 108, 190),
        ):
            cbo.setStyleSheet(cbo_style)
            # 为了触屏体验，注入强制高度委托
            from ui.styles import apply_touch_combo_style
            apply_touch_combo_style(cbo, item_height=48)
            # Fixed widths keep the whole filter row stable on Win7, where
            # the native arrow can otherwise consume the text area after DPI
            # scaling and make values look clipped or partially blank.
            cbo.setFixedWidth(combo_width)
            cbo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            # Win7 原生样式会把过窄的列表项自动省略成“0…”。日期只有
            # 3~5 个字符，不应出现省略号；同时给触屏弹出层留足宽度。
            popup = cbo.view()
            popup.setTextElideMode(Qt.ElideNone)
            popup.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            popup.setMinimumWidth(popup_width)

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

        # ── 添加时间筛选 (从时分到时分) ──
        lbl_time = QLabel(u"时间")
        lbl_time.setStyleSheet("font-size: 15px; font-weight: bold; color: #9CA3AF; border: none;")
        date_layout.addSpacing(10)
        date_layout.addWidget(lbl_time)

        lbl_from = QLabel(u"从")
        lbl_from.setStyleSheet("font-size: 15px; font-weight: bold; color: #9CA3AF; border: none;")
        date_layout.addWidget(lbl_from)

        self.cbo_start_hour = QComboBox()
        self.cbo_start_minute = QComboBox()
        self.cbo_end_hour = QComboBox()
        self.cbo_end_minute = QComboBox()

        for cbo, suffix in (
            (self.cbo_start_hour, u"时"),
            (self.cbo_start_minute, u"分"),
            (self.cbo_end_hour, u"时"),
            (self.cbo_end_minute, u"分"),
        ):
            cbo.setStyleSheet(cbo_style)
            from ui.styles import apply_touch_combo_style
            apply_touch_combo_style(cbo, item_height=48)
            cbo.setFixedWidth(82)
            cbo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            popup = cbo.view()
            popup.setTextElideMode(Qt.ElideNone)
            popup.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            popup.setMinimumWidth(112)
            maximum = 24 if suffix == u"时" else 60
            for value in range(maximum):
                cbo.addItem(f"{value:02d}{suffix}", value)

        self.cbo_start_hour.setCurrentIndex(0)  # 00时
        self.cbo_start_minute.setCurrentIndex(0)  # 00分
        self.cbo_end_hour.setCurrentIndex(23)   # 23时
        self.cbo_end_minute.setCurrentIndex(59)  # 59分

        self.cbo_start_hour.currentIndexChanged.connect(self._on_query)
        self.cbo_start_minute.currentIndexChanged.connect(self._on_query)
        self.cbo_end_hour.currentIndexChanged.connect(self._on_query)
        self.cbo_end_minute.currentIndexChanged.connect(self._on_query)

        date_layout.addWidget(self.cbo_start_hour)
        date_layout.addWidget(self.cbo_start_minute)
        
        lbl_to = QLabel(u"至")
        lbl_to.setStyleSheet("font-size: 15px; font-weight: bold; color: #9CA3AF; border: none;")
        date_layout.addWidget(lbl_to)
        
        date_layout.addWidget(self.cbo_end_hour)
        date_layout.addWidget(self.cbo_end_minute)

        # 快捷操作按钮
        quick_date_layout = QHBoxLayout()
        quick_date_layout.setSpacing(8)
        quick_date_layout.setContentsMargins(0, 0, 0, 0)
        
        quick_btn_style = """
            QPushButton { background: #374151; color: white; font-weight: bold; font-size: 14px; padding: 8px 12px; border-radius: 6px; border: none; }
        """
        
        self.btn_today = QPushButton(u"今天")
        self.btn_today.setFixedSize(118, 42)
        self.btn_today.setStyleSheet(quick_btn_style)
        self.btn_today.clicked.connect(lambda: self._set_quick_date(0))
        
        self.btn_yesterday = QPushButton(u"昨天")
        self.btn_yesterday.setFixedSize(118, 42)
        self.btn_yesterday.setStyleSheet(quick_btn_style)
        self.btn_yesterday.clicked.connect(lambda: self._set_quick_date(-1))
        
        self.btn_day_before = QPushButton(u"前天")
        self.btn_day_before.setFixedSize(118, 42)
        self.btn_day_before.setStyleSheet(quick_btn_style)
        self.btn_day_before.clicked.connect(lambda: self._set_quick_date(-2))
        
        quick_date_layout.addWidget(self.btn_today)
        quick_date_layout.addWidget(self.btn_yesterday)
        quick_date_layout.addWidget(self.btn_day_before)
        quick_date_layout.addStretch()

        # The date/time controls and the quick day buttons no longer compete
        # for one horizontal line on a 1024px Win7 POS display.
        header_controls = QVBoxLayout()
        header_controls.setSpacing(6)
        header_controls.addLayout(date_layout)
        header_controls.addLayout(quick_date_layout)
        header_controls.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        header_bar.addLayout(header_controls)

        # 订单来源筛选紧跟“今天/昨天/前天”快捷按钮，默认显示官方和私域全部流水。
        source_filter = QHBoxLayout()
        source_filter.setSpacing(6)
        source_title = QLabel(u"订单来源")
        source_title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #CBD5E1; border: none;"
        )
        source_filter.addWidget(source_title)
        source_style = (
            "QPushButton { background: #1F2937; color: #CBD5E1; border: 1px solid #374151; "
            "border-radius: 6px; padding: 8px 14px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #374151; color: #FFFFFF; }"
            "QPushButton:checked { background: #0369A1; color: #FFFFFF; border-color: #38BDF8; }"
        )
        for source_key, source_label in (("all", u"全部"), ("official", u"官方"), ("private", u"私域")):
            source_button = QPushButton(source_label)
            source_button.setCheckable(True)
            source_button.setMinimumHeight(42)
            source_button.setStyleSheet(source_style)
            source_button.clicked.connect(
                lambda checked=False, key=source_key: self._set_order_source_filter(key)
            )
            source_filter.addWidget(source_button)
            self.order_source_buttons[source_key] = source_button
        self.order_source_buttons["all"].setChecked(True)
        quick_date_layout.addSpacing(16)
        quick_date_layout.addLayout(source_filter)
        
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

        # (3) 订单列表：卡片总高度可能超过 Win7 可用窗口高度，必须放进
        # 独立滚动区域。否则布局会把卡片挤到一起，选中边框被下一张覆盖。
        self.order_list_container = QWidget()
        self.order_list_layout = QVBoxLayout(self.order_list_container)
        self.order_list_layout.setContentsMargins(0, 0, 0, 0)
        self.order_list_layout.setSpacing(10)
        self.order_list_layout.setAlignment(Qt.AlignTop)

        self.order_list_scroll = QScrollArea()
        self.order_list_scroll.setWidgetResizable(True)
        self.order_list_scroll.setFrameShape(QFrame.NoFrame)
        self.order_list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.order_list_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.order_list_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 10px; background: #111827; margin: 0; }"
            "QScrollBar::handle:vertical { background: #475569; border-radius: 5px; min-height: 32px; }"
        )
        self.order_list_scroll.setWidget(self.order_list_container)
        left_col.addWidget(self.order_list_scroll, stretch=1)

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

        self.lbl_header_source = QLabel(u"官方系统")
        self.lbl_header_source.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #DBEAFE; "
            "background: #2563EB; border: none; border-radius: 14px; padding: 6px 12px;"
        )
        meta_row.addWidget(self.lbl_header_source)
        
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

        self.btn_refund = QPushButton(u"退单")
        self.btn_refund.setMinimumHeight(48)
        self.btn_refund.setMinimumWidth(96)
        self.btn_refund.setStyleSheet(
            "QPushButton { background: #B91C1C; color: #FFFFFF; font-weight: 900; "
            "font-size: 15px; padding: 10px 20px; border-radius: 6px; border: 1px solid #EF4444; }"
            "QPushButton:hover { background: #DC2626; }"
            "QPushButton:disabled { background: #374151; color: #9CA3AF; border: 1px solid #4B5563; }"
        )
        self.btn_refund.setToolTip(u"先在实际支付渠道完成退款，再在此登记退单")
        self.btn_refund.setEnabled(False)
        self.btn_refund.clicked.connect(self._on_refund_click)
        right_action_row.addWidget(self.btn_refund)

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

    def _set_order_source_filter(self, source):
        source = source if source in ("all", "official", "private") else "all"
        self.order_source_filter = source
        for key, button in self.order_source_buttons.items():
            button.setChecked(key == source)
        self._on_query()

    @staticmethod
    def _record_source(record):
        source = str(record.get("source", "") or "").strip().lower()
        return "official" if source in ("official", "official_pos", "official_pos_relay") else "private"

    @staticmethod
    def _official_record(row):
        """Adapt the verified official-POS ledger to the order-card shape."""
        import json

        order_id = str(row.get("order_id", "") or row.get("order_key", "") or "")
        platform = str(row.get("platform", "") or "官方 POS")
        amount = float(row.get("amount", 0.0) or 0.0)
        item_names = []
        try:
            value = json.loads(row.get("item_names_json", "[]") or "[]")
            if isinstance(value, list):
                item_names = [str(item).strip() for item in value if str(item).strip()]
        except (TypeError, ValueError):
            item_names = []
        item_details = []
        try:
            value = json.loads(row.get("item_details_json", "[]") or "[]")
            if isinstance(value, list):
                item_details = [item for item in value if isinstance(item, dict) and str(item.get("name", "")).strip()]
        except (TypeError, ValueError):
            item_details = []
        if item_details:
            cart_items = []
            for detail in item_details:
                name = str(detail.get("name", "")).strip()
                try:
                    unit_price = float(detail.get("unit_price")) if detail.get("unit_price") is not None else 0.0
                except (TypeError, ValueError):
                    unit_price = 0.0
                try:
                    qty = float(detail.get("quantity")) if detail.get("quantity") is not None else 1.0
                except (TypeError, ValueError):
                    qty = 1.0
                try:
                    subtotal = float(detail.get("subtotal")) if detail.get("subtotal") is not None else unit_price * qty
                except (TypeError, ValueError):
                    subtotal = unit_price * qty
                cart_items.append({
                    "name": name,
                    "tag": str(detail.get("flavor", "") or ""),
                    "type": "official",
                    "qty": qty,
                    "price": unit_price,
                    "base_price": unit_price,
                    "subtotal": subtotal,
                    "spec": str(detail.get("spec", "") or ""),
                })
        else:
            cart_items = [
                {
                    "name": name,
                    "tag": "官方小票商品",
                    "type": "official",
                    "qty": 1,
                    "price": 0.0,
                    "base_price": 0.0,
                }
                for name in item_names
            ]
        return {
            "id": "official:%s" % str(row.get("id", row.get("order_key", ""))),
            "source": "official_pos",
            "platform": platform,
            "order_id": order_id,
            "order_key": row.get("order_key", ""),
            "sale_no": order_id,
            "remark": u"官方 POS｜%s" % platform,
            "created_at": str(row.get("created_at", "") or ""),
            "payment_status": str(row.get("payment_status", "PAID") or "PAID"),
            "payment_method": str(row.get("payment_method", "") or ""),
            "payment_breakdown_json": str(row.get("payment_breakdown_json", "") or ""),
            "total_price": amount,
            "weight_kg": 0.0,
            "item_count": int(row.get("item_count", 0) or 0),
            "cart_items_json": json.dumps(cart_items, ensure_ascii=False),
            "print_status": "PRINTED",
        }

    def _on_query(self):
        y = self.cbo_year.currentData()
        m = self.cbo_month.currentData()
        d = self.cbo_day.currentData()
        if not y or not m or not d:
            return
        target_date = f"{y}-{m:02d}-{d:02d}"
        raw_records = list(self.db.get_sales_by_date(target_date, target_date) or [])
        # 官方营业额只来自已验证、已去重的官方 POS 流水；未知付款状态的
        # 票据不会伪装成订单，也不会进入默认订单列表。
        get_official = getattr(self.db, "get_official_revenue_by_date", None)
        if callable(get_official):
            try:
                raw_records.extend(
                    self._official_record(row)
                    for row in (get_official(target_date, target_date) or [])
                )
            except Exception:
                pass

        # 如果有关键字搜索或时间筛选
        kw = self.txt_search.text().strip()
        stype = self.cbo_search_type.currentText()
        start_h = self.cbo_start_hour.currentData()
        start_minute = self.cbo_start_minute.currentData()
        end_h = self.cbo_end_hour.currentData()
        end_minute = self.cbo_end_minute.currentData()
        start_time = int(start_h or 0) * 60 + int(start_minute or 0)
        end_time = int(end_h or 0) * 60 + int(end_minute or 0)
        
        filtered = []
        for r in raw_records:
            source = self._record_source(r)
            if self.order_source_filter != "all" and source != self.order_source_filter:
                continue
            # 1. 时间筛选逻辑 (精确到分钟)
            created_at = r.get("created_at", "")
            if len(created_at) >= 16:
                try:
                    hour_int = int(created_at[11:13])
                    minute_int = int(created_at[14:16])
                    created_time = hour_int * 60 + minute_int
                    if not (start_time <= created_time <= end_time):
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
                    if (
                        kw not in r.get("sale_no", "")
                        and kw not in remark
                        and kw not in str(r.get("order_id", "") or "")
                    ):
                        continue
                        
            filtered.append(r)
            
        self.records = filtered

        # 应用排序逻辑
        is_asc = getattr(self, "btn_sort", None) and self.btn_sort.isChecked()
        self.records.sort(
            key=lambda x: (str(x.get("created_at", "") or ""), str(x.get("id", "") or "")),
            reverse=not is_asc,
        )

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

        # 退单只允许对已支付订单执行一次；空列表或已退订单保持禁用。
        if hasattr(self, "btn_refund"):
            is_official = self._record_source(record or {}) == "official"
            self.btn_refund.setEnabled(
                bool(record) and not is_official and record.get("payment_status", "PAID") != REFUNDED
            )
            # 官方 POS 的退款必须由官方 POS 打印退款单并由中继关联，
            # 本地订单页不提供容易误操作的“退单”入口。
            self.btn_refund.setVisible(bool(record) and not is_official)

        # 高亮选中的卡片
        for i in range(self.order_list_layout.count()):
            w = self.order_list_layout.itemAt(i).widget()
            if isinstance(w, OrderCard):
                w.set_selected(w.record == record)

        if not record:
            self.lbl_header_title.setText(u"📋 取餐号：---")
            self.lbl_header_source.setText(u"---")
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
        # New sales store the receipt-compatible 25-digit identifier in
        # ``order_id``.  Keep the legacy remark/sale number as a fallback for
        # historical rows created before that field existed.
        display_order_no = record.get("order_id") or temp_order_no

        self.lbl_header_title.setText(u"取餐号：%s" % call_no)
        self.lbl_order_no.setText(u"订单编号：%s" % display_order_no)
        self.lbl_create_time.setText(u"创建时间：%s" % str(record.get("created_at", "")))
        is_official_record = self._record_source(record) == "official"
        self.lbl_header_source.setText(u"官方系统" if is_official_record else u"私域 POS")
        self.lbl_header_source.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #DBEAFE; "
            "background: #2563EB; border: none; border-radius: 14px; padding: 6px 12px;"
            if is_official_record else
            "font-size: 13px; font-weight: bold; color: #D1FAE5; "
            "background: #059669; border: none; border-radius: 14px; padding: 6px 12px;"
        )
        
        # 结账方式
        pm = record.get("payment_method", "")
        payment_state = record.get("payment_status", "PAID")
        breakdown = record.get("payment_breakdown_json", "")
        payment_label = payment_display_label(pm, breakdown)
        if not payment_label and breakdown:
            payment_label = payment_display_label("mixed", breakdown)
        if not payment_label and self._record_source(record) == "official" and payment_state == "PAID":
            payment_label = u"官方 POS 已结账（票面未提供方式）"
        self.lbl_payment_method.setText(
            u"结账方式：%s" % (payment_label or u"未记录")
        )
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
                    tag_text = u"🍲 含汤底"
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
                elif item_type == "official" and "subtotal" in item and item.get("subtotal") is not None:
                    qty_value = float(item.get("qty", 1.0) or 1.0)
                    qty_text = ("%.3f" % qty_value).rstrip("0").rstrip(".")
                    unit = str(item.get("spec", "") or "")
                    lbl_qty = QLabel("x%s%s" % (qty_text, (" " + unit) if unit else ""))
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
                elif item_type == "official":
                    subtotal = item.get("subtotal")
                    unit_price = item.get("price", 0.0)
                    qty_value = item.get("qty", 1.0)
                    if subtotal is not None and unit_price:
                        lbl_price = QLabel(u"¥ %.2f" % float(subtotal))
                        lbl_price.setToolTip(u"单价：¥ %.2f × 数量：%s" % (
                            float(unit_price),
                            ("%.3f" % float(qty_value)).rstrip("0").rstrip("."),
                        ))
                    else:
                        lbl_price = QLabel(u"官方小票")
                    lbl_price.setStyleSheet("font-size: 13px; color: #9CA3AF; border: none;")
                    row_main.addSpacing(30)
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
            
            if any(item.get("type") == "official" for item in cart_items):
                # Official POS receipts provide the product names separately
                # from the final paid amount; do not replace the real amount
                # with zero just because the ticket has no per-item prices.
                self.lbl_item_total.setText(u"商品金额：¥ %.2f" % tot)
                self.lbl_discount_total.setText(u"折扣金额：¥ 0.00")
            else:
                self.lbl_item_total.setText(u"商品金额：¥ %.2f" % original_total)
                self.lbl_discount_total.setText(u"折扣金额：¥ %.2f" % (original_total - tot))
        else:
            official_item_count = int(record.get("item_count", 0) or 0)
            if self._record_source(record) == "official" and official_item_count:
                item_row = QVBoxLayout()
                item_label = QLabel(u"官方小票未解析出商品名称（共 %d 项）" % official_item_count)
                item_label.setStyleSheet("font-size: 14px; color: #F59E0B; border: none;")
                item_row.addWidget(item_label)
                self.items_layout.addLayout(item_row)
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
                "order_id": r.get("order_id") or temp_order_no,
                "cart_items": cart_items,
                "created_at": str(r.get("created_at", ""))
            }

            # “重打”是明确的人工操作，允许补打曾被自动打印开关关闭的
            # 单据；正常结账流程仍由打印设置控制。
            success = self.printer.print_receipt(
                sale_data, print_type=ptype, respect_settings=False
            )
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
