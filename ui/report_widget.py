"""
交班小结与营业报表界面 — 还原 POS 标准排版
PyQt5 + Python 3.8 兼容
"""
import re
from datetime import datetime, date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCalendarWidget, QFrame, QScrollArea, QGridLayout, QMessageBox
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QFont

from core.database import Database


class ReportWidget(QWidget):
    """营业报表"""

    def __init__(self, db: Database, printer=None, config=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.printer = printer
        self.config = config or {}
        self.selected_date_str = date.today().strftime("%Y-%m-%d")

        self._build_ui()
        self.reload_report()

    def reload_report(self):
        self._load_data()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ── 1. 顶部 Header 栏 ──
        header_bar = QHBoxLayout()

        self.lbl_header_title = QLabel(u"报表")
        self.lbl_header_title.setStyleSheet("font-size: 20px; font-weight: 900; color: #F9FAFB; border: none;")
        header_bar.addWidget(self.lbl_header_title)

        header_bar.addStretch()

        self.lbl_header_date = QLabel(self.selected_date_str)
        self.lbl_header_date.setStyleSheet("font-size: 16px; font-weight: bold; color: #F9FAFB; border: none;")
        header_bar.addWidget(self.lbl_header_date)

        main_layout.addLayout(header_bar)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #374151; border: none;")
        main_layout.addWidget(line)

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
        fix_calendar_header_style(self.calendar)
        self.calendar.selectionChanged.connect(self._on_date_changed)
        left_col.addWidget(self.calendar)
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
        lbl_ticket_title = QLabel(u"营业汇总报表")
        lbl_ticket_title.setAlignment(Qt.AlignCenter)
        lbl_ticket_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #111827; border: none;")
        mid_layout.addWidget(lbl_ticket_title)

        lbl_sep1 = QLabel("------------------------------------------")
        lbl_sep1.setAlignment(Qt.AlignCenter)
        lbl_sep1.setStyleSheet("color: #9CA3AF; border: none;")
        mid_layout.addWidget(lbl_sep1)

        # 头部门店元数据
        self.lbl_shop_name = QLabel(u"门店名称：杨国福(肥西水晶城店)")
        self.lbl_shop_name.setStyleSheet("color: #374151; font-size: 13px; border: none;")
        self.lbl_start_time = QLabel(u"开始时间：%s" % self.selected_date_str)
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
        lbl_sec_pay = QLabel(u"收入明细")
        lbl_sec_pay.setStyleSheet("font-size: 15px; font-weight: bold; color: #111827; margin-top: 8px; border: none;")
        mid_layout.addWidget(lbl_sec_pay)

        lbl_eq2 = QLabel("==========================================")
        lbl_eq2.setAlignment(Qt.AlignCenter)
        lbl_eq2.setStyleSheet("color: #9CA3AF; border: none;")
        mid_layout.addWidget(lbl_eq2)

        self.lbl_pay_total = self._add_receipt_row(mid_layout, u"总结", u"¥ 0.00", is_bold=True)

        mid_layout.addStretch()

        btn_print = QPushButton(u"打印")
        btn_print.setStyleSheet(
            "background: #EA580C; color: white; font-weight: 900; font-size: 16px; "
            "padding: 12px; border-radius: 6px; border: none;"
        )
        btn_print.clicked.connect(self._on_print_click)
        mid_layout.addWidget(btn_print)

        body_layout.addWidget(mid_card, stretch=5)

        main_layout.addLayout(body_layout, stretch=1)

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

    def _on_date_changed(self):
        qd = self.calendar.selectedDate()
        self.selected_date_str = qd.toString("yyyy-MM-dd")
        self.lbl_header_date.setText(self.selected_date_str)
        self.lbl_start_time.setText(u"开始时间：%s" % self.selected_date_str)
        self._load_data()

    def _load_data(self):
        stats = self.db.get_stats_by_date(self.selected_date_str, self.selected_date_str)
        count = stats.get("count", 0)
        a_sum = stats.get("amount_sum", 0.0)
        avg = a_sum / count if count > 0 else 0.0

        self.lbl_rev.setText("¥ %.2f" % a_sum)
        self.lbl_cnt.setText("%d" % count)
        self.lbl_avg.setText("¥ %.2f" % avg)
        self.lbl_pay_total.setText("¥ %.2f" % a_sum)

    def _on_print_click(self):
        stats = self.db.get_stats_by_date(self.selected_date_str, self.selected_date_str)
        stats["date_str"] = self.selected_date_str
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
