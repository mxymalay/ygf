"""
历史记录查询界面
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
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── 顶部：查询栏 ──
        query_bar = QHBoxLayout()

        query_bar.addWidget(QLabel(u"日期："))

        self.date_start = QDateEdit()
        self.date_start.setDate(QDate.currentDate())
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        query_bar.addWidget(self.date_start)

        query_bar.addWidget(QLabel(u" 至 "))

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

        query_bar.addSpacing(16)

        btn_query = QPushButton(u"查询")
        btn_query.setStyleSheet(
            "background: #00b4d8; color: white; font-weight: bold;"
            "padding: 10px 24px; border-radius: 6px; border: none;"
        )
        btn_query.clicked.connect(self._on_query)
        query_bar.addWidget(btn_query)

        query_bar.addStretch()

        layout.addLayout(query_bar)

        # ── 中部：统计卡片 ──
        cards = QHBoxLayout()
        cards.setSpacing(12)

        self.card_count = self._make_stat_card(u"笔数", "0", "#00b4d8")
        self.card_weight = self._make_stat_card(u"总重量", "0.00 kg", "#48cae4")
        self.card_amount = self._make_stat_card(u"总营收", u"￥0.00", "#e94560")
        self.card_avg = self._make_stat_card(u"均单价", u"￥0.00", "#f39c12")

        cards.addWidget(self.card_count)
        cards.addWidget(self.card_weight)
        cards.addWidget(self.card_amount)
        cards.addWidget(self.card_avg)

        layout.addLayout(cards)

        # ── 下部：明细表格 ──
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [u"单号", u"时间", u"重量", u"单价", u"金额", u"操作"]
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
            "QFrame { background: #16213e; border: 1px solid #2a2a4a;"
            "border-radius: 12px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignCenter)

        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("color: #a0a0b8; font-size: 13px;")
        card_layout.addWidget(lbl_title)

        lbl_value = QLabel(value)
        lbl_value.setAlignment(Qt.AlignCenter)
        lbl_value.setStyleSheet(
            "color: %s; font-size: 28px; font-weight: bold;" % color
        )
        card_layout.addWidget(lbl_value)

        card._value_label = lbl_value
        return card

    # ─── 快捷日期 ──────────────────────────────────
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

    # ─── 查询 ──────────────────────────────────────
    def _on_query(self):
        start = self.date_start.date().toPyDate()
        end = self.date_end.date().toPyDate()

        if start == end:
            records = self.db.get_sales_by_date(start)
        else:
            records = []
            d = start
            while d <= end:
                records.extend(self.db.get_sales_by_date(d))
                d += timedelta(days=1)

        # 填充统计卡片
        count = len(records)
        total_weight = sum(r["weight_kg"] for r in records)
        total_amount = sum(r["total_price"] for r in records)
        avg_price = total_amount / count if count > 0 else 0

        self.card_count._value_label.setText(str(count))
        self.card_weight._value_label.setText("%.2f kg" % total_weight)
        self.card_amount._value_label.setText(u"￥%.2f" % total_amount)
        self.card_avg._value_label.setText(u"￥%.2f" % avg_price)

        # 填充表格
        self.table.setRowCount(len(records))
        for i, r in enumerate(records):
            pu = r.get("price_unit", "per_jin")
            if pu == "per_jin":
                w_str = "%.2f 斤" % (r["weight_kg"] * 2)
                u_str = "%.2f 元/斤" % r["unit_price"]
            else:
                w_str = "%.3f kg" % r["weight_kg"]
                u_str = "%.2f 元/kg" % r["unit_price"]

            self.table.setItem(i, 0, QTableWidgetItem(r["sale_no"]))
            self.table.setItem(i, 1, QTableWidgetItem(r["created_at"]))
            self.table.setItem(i, 2, QTableWidgetItem(w_str))
            self.table.setItem(i, 3, QTableWidgetItem(u_str))

            amount_item = QTableWidgetItem(u"￥%.2f" % r["total_price"])
            amount_item.setForeground(QColor("#e94560"))
            self.table.setItem(i, 4, amount_item)

            btn_del = QPushButton(u"删除")
            btn_del.setStyleSheet(
                "background: transparent; color: #e74c3c;"
                "border: 1px solid #e74c3c; border-radius: 4px;"
                "padding: 4px 12px; font-size: 12px;"
            )
            sale_id = r["id"]
            btn_del.clicked.connect(lambda checked, rid=sale_id: self._delete_record(rid))
            self.table.setCellWidget(i, 5, btn_del)

    def _delete_record(self, sale_id):
        reply = QMessageBox.question(
            self, u"确认删除", u"确定要删除这条记录吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.db.delete_sale(sale_id)
            self._on_query()
