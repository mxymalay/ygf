"""
历史记录查询界面 — 旗舰级现代 POS 统计与数据报表
PyQt5 + Python 3.8 兼容
"""
from datetime import date, timedelta
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QDateEdit, QGroupBox,
    QGridLayout, QHeaderView, QAbstractItemView, QMessageBox,
    QFrame
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor

from core.database import Database


class HistoryWidget(QWidget):
    """历史记录查询"""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._build_ui()
        self._on_query()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── 顶部：查询控制栏 ──
        query_bar = QHBoxLayout()
        query_bar.setSpacing(12)

        lbl_dt = QLabel(u"日期筛选：")
        lbl_dt.setStyleSheet("font-size: 15px; font-weight: bold; color: #9CA3AF;")
        query_bar.addWidget(lbl_dt)

        self.date_start = QDateEdit()
        self.date_start.setDate(QDate.currentDate())
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        query_bar.addWidget(self.date_start)

        lbl_to = QLabel(u"至")
        lbl_to.setStyleSheet("font-size: 14px; color: #9CA3AF;")
        query_bar.addWidget(lbl_to)

        self.date_end = QDateEdit()
        self.date_end.setDate(QDate.currentDate())
        self.date_end.setCalendarPopup(True)
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        query_bar.addWidget(self.date_end)

        btn_today = QPushButton(u"今天")
        btn_today.clicked.connect(self._set_today)
        query_bar.addWidget(btn_today)

        btn_week = QPushButton(u"本周")
        btn_week.clicked.connect(self._set_week)
        query_bar.addWidget(btn_week)

        btn_month = QPushButton(u"本月")
        btn_month.clicked.connect(self._set_month)
        query_bar.addWidget(btn_month)

        query_bar.addSpacing(12)

        btn_query = QPushButton(u"执行查询")
        btn_query.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #06B6D4, stop:1 #3B82F6); "
            "color: white; font-weight: bold; font-size: 15px; "
            "padding: 8px 24px; border-radius: 8px; border: none; min-height: 40px;"
        )
        btn_query.clicked.connect(self._on_query)
        query_bar.addWidget(btn_query)

        query_bar.addStretch()

        layout.addLayout(query_bar)

        # ── 中部：四维数据统计卡片 ──
        cards = QHBoxLayout()
        cards.setSpacing(16)

        self.card_count = self._make_stat_card(u"总成交笔数", "0 笔", "#06B6D4")
        self.card_weight = self._make_stat_card(u"累计食材重量", "0.00 kg", "#10B981")
        self.card_amount = self._make_stat_card(u"累计营收金额", u"￥0.00", "#F59E0B")
        self.card_avg = self._make_stat_card(u"平均客单价", u"￥0.00", "#EF4444")

        cards.addWidget(self.card_count)
        cards.addWidget(self.card_weight)
        cards.addWidget(self.card_amount)
        cards.addWidget(self.card_avg)

        layout.addLayout(cards)

        # ── 下部：高对比数据表格 ──
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [u"订单编号", u"交易时间", u"称重重量", u"计价单价", u"实付金额", u"管理操作"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        layout.addWidget(self.table, stretch=1)

    def _make_stat_card(self, title, value, color):
        """创建统计卡片"""
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #172136; border: 1px solid #263352;"
            "border-radius: 14px; padding: 14px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignCenter)

        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("color: #9CA3AF; font-size: 14px; font-weight: bold;")
        card_layout.addWidget(lbl_title)

        lbl_value = QLabel(value)
        lbl_value.setAlignment(Qt.AlignCenter)
        lbl_value.setStyleSheet(
            "color: %s; font-size: 26px; font-weight: 900; margin-top: 4px;" % color
        )
        card_layout.addWidget(lbl_value)

        card._value_label = lbl_value
        return card

    # ─── 快捷日期筛选 ──────────────────────────────
    def _set_today(self):
        today = QDate.currentDate()
        self.date_start.setDate(today)
        self.date_end.setDate(today)
        self._on_query()

    def _set_week(self):
        today = QDate.currentDate()
        start = today.addDays(-today.dayOfWeek() + 1)
        self.date_start.setDate(start)
        self.date_end.setDate(today)
        self._on_query()

    def _set_month(self):
        today = QDate.currentDate()
        start = QDate(today.year(), today.month(), 1)
        self.date_start.setDate(start)
        self.date_end.setDate(today)
        self._on_query()

    # ─── 数据查询与充填 ──────────────────────────────
    def _on_query(self):
        ds = self.date_start.date().toString("yyyy-MM-dd")
        de = self.date_end.date().toString("yyyy-MM-dd")

        stats = self.db.get_stats_by_date(ds, de)
        count = stats["count"]
        w_sum = stats["weight_sum"]
        a_sum = stats["amount_sum"]
        avg = a_sum / count if count > 0 else 0.0

        self.card_count._value_label.setText("%d 笔" % count)
        self.card_weight._value_label.setText("%.2f kg" % w_sum)
        self.card_amount._value_label.setText(u"￥%.2f" % a_sum)
        self.card_avg._value_label.setText(u"￥%.2f" % avg)

        records = self.db.get_sales_by_date(ds, de)
        self.table.setRowCount(len(records))

        for row, r in enumerate(records):
            item_no = QTableWidgetItem(r["sale_no"])
            item_time = QTableWidgetItem(str(r["created_at"]))
            item_weight = QTableWidgetItem("%.3f kg" % r["weight_kg"])

            pu_str = u"元/斤" if r.get("price_unit") == "per_jin" else u"元/kg"
            item_unit = QTableWidgetItem("%.2f %s" % (r["unit_price"], pu_str))
            item_total = QTableWidgetItem(u"￥%.2f" % r["total_price"])

            item_weight.setTextAlignment(Qt.AlignCenter)
            item_unit.setTextAlignment(Qt.AlignCenter)
            item_total.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            item_total.setForeground(QColor("#F59E0B"))

            self.table.setItem(row, 0, item_no)
            self.table.setItem(row, 1, item_time)
            self.table.setItem(row, 2, item_weight)
            self.table.setItem(row, 3, item_unit)
            self.table.setItem(row, 4, item_total)

            btn_del = QPushButton(u"删除")
            btn_del.setStyleSheet(
                "background: #7F1D1D; color: #FCA5A5; border: 1px solid #DC2626;"
                "border-radius: 6px; padding: 2px 10px; font-weight: bold; min-height: 28px;"
            )
            sale_id = r["id"]
            btn_del.clicked.connect(
                lambda checked, sid=sale_id: self._on_delete(sid)
            )
            self.table.setCellWidget(row, 5, btn_del)

    def _on_delete(self, sale_id):
        from ui.custom_dialog import show_question
        if show_question(self, u"确认删除", u"确定要删除这条销售记录吗？"):
            self.db.delete_sale(sale_id)
            self._on_query()
