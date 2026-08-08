"""
交班小结与营业报表界面 — 还原 POS 标准排版
PyQt5 + Python 3.8 兼容
"""
import json
import re
from datetime import datetime, date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCalendarWidget, QFrame, QScrollArea, QGridLayout, QMessageBox,
    QStackedWidget, QSizePolicy
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QFont, QTextCharFormat

from core.database import Database
from core.printer_relay_mode import validate_relay_config
from core.printer_relay_host import STATUS_PATH


class ReportWidget(QWidget):
    """营业报表"""

    def __init__(self, db: Database, printer=None, config=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.printer = printer
        self.config = config or {}
        self.start_date_str = date.today().strftime("%Y-%m-%d")
        self.end_date_str = self.start_date_str
        self._range_marked_dates = []
        self.report_section = "private"
        self._official_report_state = {"available": False, "reason": "尚未检查"}

        self._build_ui()
        self.reload_report()

    def reload_report(self):
        self._load_data()

    def _build_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ── 1. 顶部 Header 栏 ──
        header_bar = QHBoxLayout()

        self.lbl_header_title = QLabel(u"报表")
        self.lbl_header_title.setStyleSheet("font-size: 20px; font-weight: 900; color: #F9FAFB; border: none;")
        header_bar.addWidget(self.lbl_header_title)

        header_bar.addStretch()

        self.lbl_header_date = QLabel(self.start_date_str)
        self.lbl_header_date.setStyleSheet("font-size: 16px; font-weight: bold; color: #F9FAFB; border: none;")
        header_bar.addWidget(self.lbl_header_date)

        main_layout.addLayout(header_bar)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #374151; border: none;")
        main_layout.addWidget(line)

        # 报表二级目录采用与“分流规则”一致的左侧固定菜单，避免在
        # Win7 窄屏上占用报表正文的横向空间。官方金额只有在中继数据
        # 完成订单号/金额/付款状态校验后才会进入总营业额。
        section_sidebar = QFrame()
        section_sidebar.setObjectName("ReportSidebar")
        # Keep enough room for the longest tab on Win7 narrow screens.  The
        # button font is intentionally smaller than the page title so the
        # full ``官方 POS 营业额`` label never gets clipped.
        section_sidebar.setMinimumWidth(178)
        section_sidebar.setMaximumWidth(220)
        section_sidebar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        section_sidebar.setStyleSheet(
            "QFrame#ReportSidebar { background-color: #0F172A; border-right: 1px solid #1E293B; }"
            "QLabel { background: transparent; }"
        )
        sidebar_layout = QVBoxLayout(section_sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 18)
        sidebar_layout.setSpacing(8)
        sidebar_title = QLabel(u"▥ 报表")
        sidebar_title.setStyleSheet(
            "font-size: 22px; font-weight: 900; color: #F8FAFC; "
            "padding-left: 8px; margin-bottom: 8px; border: none;"
        )
        sidebar_layout.addWidget(sidebar_title)
        self.report_section_buttons = {}
        for key, title in (("total", u"总营业额"), ("official", u"官方 POS\n营业额"), ("private", u"私域 POS\n营业额")):
            button = QPushButton(title)
            button.setCheckable(True)
            button.setMinimumHeight(62 if "\n" in title else 56)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton { text-align: left; padding: 10px 9px; font-size: 14px; "
                "font-weight: 600; color: #94A3B8; background-color: transparent; "
                "border-radius: 10px; border: none; }"
                "QPushButton:hover { color: #F1F5F9; background-color: #1E293B; }"
                "QPushButton:checked { color: #38BDF8; background-color: #1E293B; "
                "font-weight: bold; border-left: 4px solid #38BDF8; }"
            )
            button.clicked.connect(lambda checked=False, section=key: self._select_report_section(section))
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            sidebar_layout.addWidget(button)
            self.report_section_buttons[key] = button
        sidebar_layout.addStretch()

        self.lbl_official_notice = QLabel()
        self.lbl_official_notice.setWordWrap(True)
        self.lbl_official_notice.setStyleSheet(
            "color: #FEF3C7; background: #78350F; border: 1px solid #D97706; "
            "border-radius: 8px; padding: 10px;"
        )
        # Keep the warning from consuming the fixed-height POS viewport.  A
        # full explanation remains on the official/total report cards.
        self.lbl_official_notice.setMaximumHeight(72)
        self.lbl_official_notice.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.btn_go_private_report = QPushButton(u"查看私域 POS 营业额")
        self.btn_go_private_report.setMinimumHeight(42)
        self.btn_go_private_report.clicked.connect(lambda: self._select_report_section("private"))
        notice_row = QHBoxLayout()
        notice_row.addWidget(self.lbl_official_notice, stretch=1)
        notice_row.addWidget(self.btn_go_private_report)
        main_layout.addLayout(notice_row)
        self.report_notice_row = notice_row

        # ── 2. 主体布局 (左:日历, 右:营业报表票据) ──
        body_layout = QHBoxLayout()
        body_layout.setSpacing(16)

        # ──────────────── Left Column (日历选择器) ────────────────
        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        # 日历控件
        from ui.styles import fix_calendar_header_style
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        # The calendar's legacy 280px minimum plus the quick buttons caused
        # the title to be painted into the last calendar row on short/narrow
        # POS windows.  Let the calendar shrink a little while keeping its
        # cells usable, and give the title a clear separation from it.
        self.calendar.setMinimumHeight(235)
        self.calendar.setMaximumHeight(310)
        self.calendar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        fix_calendar_header_style(self.calendar)
        self.calendar.selectionChanged.connect(self._on_date_changed)
        self.calendar.currentPageChanged.connect(lambda _year, _month: self._apply_calendar_range_marks())

        left_col.addWidget(self.calendar)
        
        # 快捷按钮布局
        quick_btn_style = """
            QPushButton { background: #374151; color: white; font-weight: bold; font-size: 13px; padding: 4px; border-radius: 4px; border: none; }
            QPushButton:hover { background: #4B5563; }
        """
        quick_grid = QGridLayout()
        quick_grid.setSpacing(4)
        
        point_btn_configs = [
            [(u"今天", "today"), (u"昨天", "yesterday"), (u"前天", "day_before")],
            [(u"本周", "this_week"), (u"上周", "last_week"), None],
            [(u"本月", "this_month"), (u"上月", "last_month"), None],
            [(u"本年", "this_year"), (u"去年", "last_year"), None],
        ]
        
        for row, row_items in enumerate(point_btn_configs):
            for col, item in enumerate(row_items):
                if item:
                    btn = QPushButton(item[0])
                    btn.setStyleSheet(quick_btn_style)
                    btn.clicked.connect(lambda checked, cmd=item[1]: self._set_date_range(cmd))
                    quick_grid.addWidget(btn, row, col)

        point_title = QLabel(u"时间点查看")
        point_title.setStyleSheet(
            "color: #38BDF8; font-size: 17px; font-weight: 900; "
            "padding: 8px 0 2px 2px; border: none;"
        )
        left_col.addWidget(point_title)
        left_col.addLayout(quick_grid)

        period_title = QLabel(u"时间段查看")
        period_title.setStyleSheet(
            "color: #38BDF8; font-size: 17px; font-weight: 900; "
            "padding: 12px 0 0 2px; border: none;"
        )
        left_col.addWidget(period_title)

        period_grid = QGridLayout()
        period_grid.setSpacing(4)
        for col, item in enumerate(((u"7天", "7_days"), (u"30天", "30_days"), (u"365天", "365_days"))):
            btn = QPushButton(item[0])
            btn.setStyleSheet(quick_btn_style)
            btn.clicked.connect(lambda checked, cmd=item[1]: self._set_date_range(cmd))
            period_grid.addWidget(btn, 0, col)
        left_col.addLayout(period_grid)
        left_col.addStretch()

        body_layout.addLayout(left_col, stretch=3)

        # ──────────────── Right Column (营业汇总票据) ────────────────
        mid_card = QFrame()
        mid_card.setStyleSheet(
            "QFrame { background: #FFFFFF; border-radius: 10px; border: none; }"
        )
        mid_layout = QVBoxLayout(mid_card)
        mid_layout.setContentsMargins(24, 20, 24, 20)
        mid_layout.setSpacing(10)

        # 票据标题
        self.lbl_ticket_title = QLabel(u"私域 POS 营业额")
        self.lbl_ticket_title.setAlignment(Qt.AlignCenter)
        self.lbl_ticket_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #111827; border: none;")
        mid_layout.addWidget(self.lbl_ticket_title)

        lbl_sep1 = QLabel("------------------------------------------")
        lbl_sep1.setAlignment(Qt.AlignCenter)
        lbl_sep1.setStyleSheet("color: #9CA3AF; border: none;")
        mid_layout.addWidget(lbl_sep1)

        # 头部门店元数据
        shop_name = self.config.get("shop_subtitle", u"未配置门店名称")
        self.lbl_shop_name = QLabel(u"门店名称：%s" % shop_name)
        self.lbl_shop_name.setStyleSheet("color: #374151; font-size: 13px; border: none;")
        self.lbl_start_time = QLabel(u"统计时间：%s" % self.start_date_str)
        self.lbl_start_time.setStyleSheet("color: #374151; font-size: 13px; border: none;")

        mid_layout.addWidget(self.lbl_shop_name)
        mid_layout.addWidget(self.lbl_start_time)

        lbl_sep2 = QLabel("------------------------------------------")
        lbl_sep2.setAlignment(Qt.AlignCenter)
        lbl_sep2.setStyleSheet("color: #9CA3AF; border: none;")
        mid_layout.addWidget(lbl_sep2)

        # 销售汇总
        lbl_sec_sales = QLabel(u"销售汇总")
        lbl_sec_sales.setStyleSheet("font-size: 15px; font-weight: bold; color: #111827; border: none;")
        mid_layout.addWidget(lbl_sec_sales)

        lbl_eq1 = QLabel("==========================================")
        lbl_eq1.setAlignment(Qt.AlignCenter)
        lbl_eq1.setStyleSheet("color: #9CA3AF; border: none;")
        mid_layout.addWidget(lbl_eq1)

        # 收入、订单量、客单价
        self.lbl_rev = self._add_receipt_row(mid_layout, u"营业收入：", u"¥ 0.00", is_bold=True)
        self.lbl_cnt = self._add_receipt_row(mid_layout, u"订单数量：", u"0")
        self.lbl_avg = self._add_receipt_row(mid_layout, u"客单价：", u"¥ 0.00")
        self.lbl_ref_amt = self._add_receipt_row(mid_layout, u"退单金额：", u"¥ 0.00")
        self.lbl_ref_cnt = self._add_receipt_row(mid_layout, u"退单数量：", u"0")

        # 收入明细 (总结)
        lbl_sec_pay = QLabel(u"结账方式明细")
        lbl_sec_pay.setStyleSheet("font-size: 15px; font-weight: bold; color: #111827; margin-top: 8px; border: none;")
        mid_layout.addWidget(lbl_sec_pay)

        lbl_eq2 = QLabel("==========================================")
        lbl_eq2.setAlignment(Qt.AlignCenter)
        lbl_eq2.setStyleSheet("color: #9CA3AF; border: none;")
        mid_layout.addWidget(lbl_eq2)

        self.lbl_pay_sqb = self._add_receipt_row(mid_layout, u"收钱吧：", u"¥ 0.00 (0笔)")
        self.lbl_pay_scan = self._add_receipt_row(mid_layout, u"手持：", u"¥ 0.00 (0笔)")
        self.lbl_pay_cash = self._add_receipt_row(mid_layout, u"现金：", u"¥ 0.00 (0笔)")
        self.lbl_pay_qr = self._add_receipt_row(mid_layout, u"被扫：", u"¥ 0.00 (0笔)")
        self.lbl_pay_total = self._add_receipt_row(mid_layout, u"合计", u"¥ 0.00", is_bold=True)

        mid_layout.addStretch()

        btn_print = QPushButton(u"打印")
        btn_print.setStyleSheet(
            "background: #EA580C; color: white; font-weight: 900; font-size: 16px; "
            "padding: 12px; border-radius: 6px; border: none;"
        )
        btn_print.clicked.connect(self._on_print_click)
        mid_layout.addWidget(btn_print)

        self.private_report_card = mid_card
        self.report_stack = QStackedWidget()
        self.total_report_card = self._build_channel_report_card("total", u"总营业额")
        self.official_report_card = self._build_channel_report_card("official", u"官方 POS 营业额")
        self.report_stack.addWidget(self.total_report_card)
        self.report_stack.addWidget(self.official_report_card)
        self.report_stack.addWidget(self.private_report_card)
        body_layout.addWidget(self.report_stack, stretch=5)

        body_page = QWidget()
        body_page.setLayout(body_layout)
        self.report_content_stack = QStackedWidget()
        self.report_content_stack.addWidget(body_page)

        self.report_fallback_page = QWidget()
        fallback_layout = QVBoxLayout(self.report_fallback_page)
        fallback_layout.setContentsMargins(36, 36, 36, 36)
        fallback_layout.setSpacing(20)
        fallback_layout.addStretch()
        fallback_title = QLabel(u"官方 POS 营业额暂不可用")
        fallback_title.setAlignment(Qt.AlignCenter)
        fallback_title.setStyleSheet(
            "font-size: 32px; font-weight: 900; color: #FDE68A; "
            "background: #78350F; border: 2px solid #D97706; "
            "border-radius: 14px; padding: 26px;"
        )
        fallback_layout.addWidget(fallback_title)
        self.lbl_report_fallback_reason = QLabel()
        self.lbl_report_fallback_reason.setAlignment(Qt.AlignCenter)
        self.lbl_report_fallback_reason.setWordWrap(True)
        self.lbl_report_fallback_reason.setStyleSheet(
            "font-size: 20px; color: #E2E8F0; background: #1E293B; "
            "border: 1px solid #475569; border-radius: 12px; padding: 22px;"
        )
        fallback_layout.addWidget(self.lbl_report_fallback_reason)
        btn_fallback_private = QPushButton(u"前往私域 POS 营业额")
        btn_fallback_private.setMinimumHeight(74)
        btn_fallback_private.setCursor(Qt.PointingHandCursor)
        btn_fallback_private.setStyleSheet(
            "QPushButton { background: #0284C7; color: white; font-size: 22px; "
            "font-weight: 900; border-radius: 12px; padding: 14px 26px; }"
            "QPushButton:hover { background: #0369A1; }"
        )
        btn_fallback_private.clicked.connect(lambda: self._select_report_section("private"))
        fallback_layout.addWidget(btn_fallback_private)
        fallback_layout.addStretch()
        self.report_content_stack.addWidget(self.report_fallback_page)
        # The calendar and receipt have a deliberately dense layout.  When a
        # reliability notice is visible, let the report body scroll instead
        # of squeezing the calendar until its rows overlap the quick buttons.
        report_scroll = QScrollArea()
        report_scroll.setWidgetResizable(True)
        report_scroll.setFrameShape(QFrame.NoFrame)
        report_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        report_scroll.setWidget(self.report_content_stack)
        self.report_scroll = report_scroll
        main_layout.addWidget(report_scroll, stretch=1)

        root_layout.addWidget(section_sidebar)
        root_layout.addLayout(main_layout, stretch=1)
        self._select_report_section("private")

    def _build_channel_report_card(self, key, title):
        card = QFrame()
        card.setStyleSheet("QFrame { background: #FFFFFF; border-radius: 10px; border: none; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        heading = QLabel(title)
        heading.setAlignment(Qt.AlignCenter)
        heading.setStyleSheet("font-size: 21px; font-weight: 900; color: #111827; border: none;")
        layout.addWidget(heading)
        sep = QLabel("==========================================")
        sep.setAlignment(Qt.AlignCenter)
        sep.setStyleSheet("color: #9CA3AF; border: none;")
        layout.addWidget(sep)

        status = QLabel(u"数据状态：检查中")
        status.setWordWrap(True)
        status.setStyleSheet("color: #374151; font-size: 15px; border: none;")
        amount = QLabel(u"¥ 0.00")
        amount.setAlignment(Qt.AlignCenter)
        amount.setStyleSheet("color: #111827; font-size: 32px; font-weight: 900; border: none;")
        count = QLabel(u"订单数量：0")
        count.setAlignment(Qt.AlignCenter)
        count.setStyleSheet("color: #374151; font-size: 15px; border: none;")
        hint = QLabel()
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6B7280; font-size: 14px; border: none;")
        layout.addWidget(status)
        layout.addWidget(amount)
        layout.addWidget(count)
        layout.addWidget(hint)
        layout.addStretch()
        card._report_status = status
        card._report_amount = amount
        card._report_count = count
        card._report_hint = hint
        card._report_key = key
        return card

    def _select_report_section(self, section):
        section = section if section in ("total", "official", "private") else "private"
        if section == "private" and hasattr(self, "lbl_official_notice"):
            self.lbl_official_notice.setVisible(False)
            self.btn_go_private_report.setVisible(False)
            if hasattr(self, "report_content_stack"):
                self.report_content_stack.setCurrentIndex(0)
        elif section != "private" and hasattr(self, "lbl_official_notice"):
            # Re-show the completeness warning when the operator deliberately
            # opens the official or total view after having inspected private
            # POS figures.
            mode_warning = (getattr(self, "_official_report_state", {}) or {}).get("mode_warning") or ""
            self.lbl_official_notice.setVisible(bool(mode_warning))
            self.btn_go_private_report.setVisible(False)
        # When the official source is unavailable, both official and total
        # views intentionally fall back to the private-POS view.  A deliberate
        # click on either unavailable entry must still show the reason instead
        # of appearing to do nothing.
        if section != "private" and hasattr(self, "_official_report_state") and not self._official_report_state.get("available"):
            reason = self._official_report_state.get("reason") or u"未获取到官方 POS 数据"
            self.report_section = section
            if hasattr(self, "lbl_report_fallback_reason"):
                self.lbl_report_fallback_reason.setText(
                    u"系统不会用打印任务猜测营业额。\n\n原因：%s" % reason
                )
            if hasattr(self, "report_content_stack"):
                self.report_content_stack.setCurrentIndex(1)
            if hasattr(self, "report_notice_row"):
                for index in range(self.report_notice_row.count()):
                    item = self.report_notice_row.itemAt(index)
                    if item.widget():
                        item.widget().setVisible(False)
            for key, button in getattr(self, "report_section_buttons", {}).items():
                button.setChecked(key == section)
            return
        self.report_section = section
        index = {"total": 0, "official": 1, "private": 2}[section]
        if hasattr(self, "report_stack"):
            self.report_stack.setCurrentIndex(index)
        for key, button in getattr(self, "report_section_buttons", {}).items():
            active = key == section
            button.setChecked(active)
            button.setStyleSheet(
                "QPushButton { text-align: left; padding: 12px 14px; font-size: 17px; "
                "background-color: %s; color: %s; font-weight: %s; border-radius: 10px; "
                "border: none; border-left: %s; }"
                "QPushButton:hover { color: #F1F5F9; background-color: #1E293B; }" % (
                    "#1E293B" if active else "transparent",
                    "#38BDF8" if active else "#94A3B8",
                    "bold" if active else "600",
                    "4px solid #38BDF8" if active else "4px solid transparent",
                )
            )

    def _official_report_summary(self):
        """Return official totals only when relay setup and source are usable."""
        mode_warning = self._mode_reliability_warning()
        report = validate_relay_config(self.config, check_windows=False)
        if report.get("errors"):
            return {"available": False, "reason": "打印中继未配置成功：%s" % "；".join(report["errors"]), "mode_warning": mode_warning}
        if not bool(self.config.get("printer_relay_enabled")):
            return {"available": False, "reason": "打印中继未启用，暂时没有可核验的官方 POS 数据。", "mode_warning": mode_warning}

        state = {}
        try:
            with open(STATUS_PATH, "r", encoding="utf-8") as stream:
                state = json.load(stream) or {}
        except (OSError, ValueError, TypeError):
            state = {}
        if state.get("last_error"):
            return {"available": False, "reason": "官方数据获取失败：%s" % state.get("last_error"), "mode_warning": mode_warning}
        if not state.get("running"):
            return {"available": False, "reason": "打印中继未运行，暂时没有可核验的官方 POS 数据。", "mode_warning": mode_warning}

        summary = self.db.get_official_stats_by_date(self.start_date_str, self.end_date_str)
        if not summary.get("count"):
            return {"available": False, "reason": "当前时间段没有获取到已验证的官方 POS 营业数据。", "mode_warning": mode_warning}
        return {"available": True, "reason": "金额和付款状态均已验证", "summary": summary, "mode_warning": mode_warning}

    def _mode_reliability_warning(self):
        """Return a notice when the selected period ever fell back to compatibility.

        The warning is deliberately separate from availability: verified rows
        remain visible, but a compatibility interval means some official
        payments may never have reached the relay and totals are incomplete.
        """
        getter = getattr(self.db, "get_relay_mode_events", None)
        if not callable(getter):
            return ""
        try:
            events = getter(self.start_date_str, self.end_date_str, limit=500) or []
        except Exception:
            return ""
        fallback_events = []
        for event in events:
            new_mode = str(event.get("new_mode", "") or "").strip().lower()
            previous_mode = str(event.get("previous_mode", "") or "").strip().lower()
            if new_mode in ("compatibility", "degraded") or (
                previous_mode == "enhanced" and new_mode != "enhanced"
            ):
                fallback_events.append(event)
        if not fallback_events:
            return ""
        first = sorted(
            fallback_events,
            key=lambda row: str(row.get("created_at", "") or "")
        )[0]
        stamp = str(first.get("created_at", "") or "")
        reason = str(first.get("reason", "") or "").strip()
        detail = (u"首次发生：%s" % stamp) if stamp else u"统计期间曾发生"
        if reason:
            detail += u"；原因：%s" % reason
        return (
            u"可信度提示：本统计期间曾切换到兼容模式（%s）。"
            u"期间可能有官方 POS 支付未经过中继，因此官方营业额和总营业额可能不完整；"
            u"当前已入账的可验证数据仍保留并展示。" % detail
        )

    @staticmethod
    def _set_channel_card(card, status, amount_text, count_text, hint):
        card._report_status.setText(status)
        card._report_amount.setText(amount_text)
        card._report_count.setText(count_text)
        card._report_hint.setText(hint)

    def _add_receipt_row(self, layout, key_text, val_text, is_bold=False):
        row = QHBoxLayout()
        lbl_k = QLabel(key_text)
        lbl_v = QLabel(val_text)

        font_style = "font-weight: bold;" if is_bold else ""
        lbl_k.setStyleSheet("color: #111827; font-size: 14px; border: none; %s" % font_style)
        lbl_v.setStyleSheet("color: #111827; font-size: 14px; border: none; %s" % font_style)

        row.addWidget(lbl_k)
        row.addStretch()
        row.addWidget(lbl_v)
        layout.addLayout(row)
        return lbl_v

    def _set_date_range(self, cmd):
        from datetime import date, timedelta
        import calendar
        today = date.today()
        
        if cmd == "today":
            start_d = today
            end_d = today
        elif cmd == "yesterday":
            start_d = today - timedelta(days=1)
            end_d = start_d
        elif cmd == "day_before":
            start_d = today - timedelta(days=2)
            end_d = start_d
        elif cmd == "this_week":
            start_d = today - timedelta(days=today.weekday())
            end_d = start_d + timedelta(days=6)
        elif cmd == "last_week":
            end_d = today - timedelta(days=today.weekday() + 1)
            start_d = end_d - timedelta(days=6)
        elif cmd == "this_month":
            start_d = today.replace(day=1)
            last_day = calendar.monthrange(today.year, today.month)[1]
            end_d = today.replace(day=last_day)
        elif cmd == "last_month":
            first_day = today.replace(day=1)
            end_d = first_day - timedelta(days=1)
            start_d = end_d.replace(day=1)
        elif cmd == "this_year":
            start_d = today.replace(month=1, day=1)
            end_d = today.replace(month=12, day=31)
        elif cmd == "last_year":
            start_d = today.replace(year=today.year-1, month=1, day=1)
            end_d = today.replace(year=today.year-1, month=12, day=31)
        elif cmd == "7_days":
            end_d = today
            start_d = today - timedelta(days=6)
        elif cmd == "30_days":
            end_d = today
            start_d = today - timedelta(days=29)
        elif cmd == "365_days":
            end_d = today
            start_d = today - timedelta(days=364)
        else:
            return
            
        self.start_date_str = start_d.strftime("%Y-%m-%d")
        self.end_date_str = end_d.strftime("%Y-%m-%d")
        
        self.calendar.blockSignals(True)
        from PyQt5.QtCore import QDate
        self.calendar.setSelectedDate(QDate(start_d.year, start_d.month, start_d.day))
        self.calendar.blockSignals(False)
        self._apply_calendar_range_marks()
        
        if self.start_date_str == self.end_date_str:
            self.lbl_header_date.setText(self.start_date_str)
            self.lbl_start_time.setText(u"统计时间：%s" % self.start_date_str)
        else:
            self.lbl_header_date.setText(f"{self.start_date_str} ~ {self.end_date_str}")
            self.lbl_start_time.setText(u"统计时间：%s ~ %s" % (self.start_date_str, self.end_date_str))
            
        self._load_data()

    def _on_date_changed(self):
        qd = self.calendar.selectedDate()
        self.start_date_str = qd.toString("yyyy-MM-dd")
        self.end_date_str = self.start_date_str
        self._apply_calendar_range_marks()
        self.lbl_header_date.setText(self.start_date_str)
        self.lbl_start_time.setText(u"统计时间：%s" % self.start_date_str)
        self._load_data()

    def _apply_calendar_range_marks(self):
        """Highlight every day in a selected report range, not only its start."""
        # Clear formats left by the previous range first.  Keeping this list
        # avoids resetting the calendar's normal weekend/adjacent-day style.
        empty_format = QTextCharFormat()
        for marked_date in self._range_marked_dates:
            self.calendar.setDateTextFormat(marked_date, empty_format)
        self._range_marked_dates = []

        try:
            start = QDate.fromString(self.start_date_str, "yyyy-MM-dd")
            end = QDate.fromString(self.end_date_str, "yyyy-MM-dd")
            if not start.isValid() or not end.isValid() or start > end:
                return
        except Exception:
            return

        # A single selected date is already highlighted by QCalendarWidget's
        # native selection; date text formats are needed for multi-day ranges.
        if start == end:
            return
        range_format = QTextCharFormat()
        range_format.setBackground(QColor("#0EA5E9"))
        range_format.setForeground(QColor("#FFFFFF"))
        range_format.setFontWeight(QFont.Bold)
        cursor = start
        while cursor <= end:
            self.calendar.setDateTextFormat(cursor, range_format)
            self._range_marked_dates.append(QDate(cursor))
            cursor = cursor.addDays(1)

    def _load_data(self):
        stats = self.db.get_stats_by_date(self.start_date_str, self.end_date_str)
        refunds = self.db.get_refund_stats_by_date(self.start_date_str, self.end_date_str)
        count = stats.get("count", 0)
        a_sum = stats.get("amount_sum", 0.0)
        avg = a_sum / count if count > 0 else 0.0

        self.lbl_rev.setText("¥ %.2f" % a_sum)
        self.lbl_cnt.setText("%d" % count)
        self.lbl_avg.setText("¥ %.2f" % avg)
        self.lbl_ref_amt.setText("¥ %.2f" % refunds.get("amount_sum", 0.0))
        self.lbl_ref_cnt.setText("%d" % refunds.get("count", 0))
        self.lbl_pay_total.setText("¥ %.2f" % a_sum)

        # 结账方式明细
        pay_stats = self.db.get_payment_stats_by_date(self.start_date_str, self.end_date_str)
        pm_data = {}
        for row in pay_stats:
            pm_data[row.get("pm", "")] = {"cnt": row.get("cnt", 0), "amt": row.get("amt", 0.0)}

        sqb_d = pm_data.get("shouqianba", {"cnt": 0, "amt": 0.0})
        scan_d = pm_data.get("scan", {"cnt": 0, "amt": 0.0})
        cash_d = pm_data.get("cash", {"cnt": 0, "amt": 0.0})
        qr_d = pm_data.get("qr", {"cnt": 0, "amt": 0.0})

        self.lbl_pay_sqb.setText("¥ %.2f (%d笔)" % (sqb_d["amt"], sqb_d["cnt"]))
        self.lbl_pay_scan.setText("¥ %.2f (%d笔)" % (scan_d["amt"], scan_d["cnt"]))
        self.lbl_pay_cash.setText("¥ %.2f (%d笔)" % (cash_d["amt"], cash_d["cnt"]))
        self.lbl_pay_qr.setText("¥ %.2f (%d笔)" % (qr_d["amt"], qr_d["cnt"]))

        official = self._official_report_summary()
        self._official_report_state = official
        if official.get("available"):
            official_summary = official.get("summary") or {}
            official_amount = float(official_summary.get("amount_sum", 0.0) or 0.0)
            official_count = int(official_summary.get("count", 0) or 0)
            total_amount = float(a_sum or 0.0) + official_amount
            total_count = int(count or 0) + official_count
            mode_warning = official.get("mode_warning") or ""
            official_status = u"已验证；统计期间曾降级" if mode_warning else u"已验证"
            total_status = u"不完整风险；统计期间曾降级" if mode_warning else u"完整"
            official_hint = u"来源：打印中继；只统计订单号、金额和付款状态均已校验的官方 POS 订单。"
            total_hint = u"总营业额 = 私域 POS 已支付流水 + 已验证官方 POS 营业额。"
            if mode_warning:
                official_hint += u"\n\n" + mode_warning
                total_hint += u"\n\n" + mode_warning
            self._set_channel_card(
                self.official_report_card,
                u"数据状态：%s" % official_status,
                u"¥ %.2f" % official_amount,
                u"订单数量：%d" % official_count,
                official_hint,
            )
            self._set_channel_card(
                self.total_report_card,
                u"数据状态：%s" % total_status,
                u"¥ %.2f" % total_amount,
                u"订单数量：%d" % total_count,
                total_hint,
            )
            self.lbl_official_notice.setText(mode_warning)
            # This is a warning about the completeness of official/total
            # figures.  The private-POS report is independent of that source
            # and must stay clean even when the selected period had a relay
            # fallback event.
            self.lbl_official_notice.setVisible(bool(mode_warning) and self.report_section != "private")
            self.btn_go_private_report.setVisible(False)
        else:
            reason = official.get("reason") or u"未获取到官方 POS 数据"
            mode_warning = official.get("mode_warning") or ""
            unavailable_detail = u"提示：%s\n请先完成打印中继配置并通过真实测试单，再查看官方 POS 营业额。" % reason
            total_detail = u"提示：总营业额需要官方 POS 数据；当前已自动转到私域 POS 营业额。\n原因：%s" % reason
            if mode_warning:
                unavailable_detail += u"\n\n" + mode_warning
                total_detail += u"\n\n" + mode_warning
            self._set_channel_card(
                self.official_report_card,
                u"数据状态：不可用",
                u"暂不可统计",
                u"订单数量：暂不可统计",
                unavailable_detail,
            )
            self._set_channel_card(
                self.total_report_card,
                u"数据状态：不完整",
                u"暂不可统计",
                u"订单数量：暂不可统计",
                total_detail,
            )
            if self.report_section != "private":
                self._select_report_section("private")
            # 已经展示私域 POS 营业额时，不再重复显示“跳转到私域”的
            # 提示和按钮；只有用户停留在官方/总营业额入口时才需要引导。
            show_fallback_notice = self.report_section != "private"
            self.lbl_official_notice.setText(
                u"官方 POS 营业额暂不可用，系统不会用打印任务猜测营业额。\n原因：%s%s" % (
                    reason,
                    (u"\n\n" + mode_warning) if mode_warning else "",
                )
            )
            self.lbl_official_notice.setVisible(show_fallback_notice)
            self.btn_go_private_report.setVisible(show_fallback_notice)

    def _on_print_click(self):
        stats = self.db.get_stats_by_date(self.start_date_str, self.end_date_str)
        refunds = self.db.get_refund_stats_by_date(self.start_date_str, self.end_date_str)
        stats["refund_amount_sum"] = refunds.get("amount_sum", 0.0)
        stats["refund_count"] = refunds.get("count", 0)
        stats["date_str"] = self.start_date_str if self.start_date_str == self.end_date_str else f"{self.start_date_str} to {self.end_date_str}"
        if self.printer:
            if hasattr(self.printer, "print_shift_report"):
                self.printer.print_shift_report(stats)
            else:
                rev_amt = float(self.lbl_rev.text().replace("¥", "").strip())
                ticket_data = {
                    "shop_name": self.config.get("shop_name", u"杨国福麻辣烫"),
                    "call_no": "REPORT",
                    "weight_kg": 0.0,
                    "unit_price": 0.0,
                    "total_price": rev_amt,
                    "temp_order_no": "REP-" + datetime.now().strftime("%Y%m%d%H%M"),
                    "cart_items": [{"name": u"营业汇总报表", "price": rev_amt}],
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                self.printer.print_receipt(ticket_data)

        from ui.custom_dialog import show_info
        show_info(self, u"打印成功", u"营业汇总报表已成功发送至打印机！")
