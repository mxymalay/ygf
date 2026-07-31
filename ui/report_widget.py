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
    """交班小结 & 营业报表"""

    def __init__(self, db: Database, printer=None, config=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.printer = printer
        self.config = config or {}
        self.selected_date_str = date.today().strftime("%Y-%m-%d")
        self.current_sub_tab = u"交班小结"

        self._build_ui()
        self.reload_report()

    def reload_report(self):
        self._load_data()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ── 1. 顶部 Header 栏 ──
        header_bar = QHBoxLayout()

        self.lbl_header_title = QLabel(u"交班小结")
        self.lbl_header_title.setStyleSheet("font-size: 20px; font-weight: 900; color: #F9FAFB;")
        header_bar.addWidget(self.lbl_header_title)

        header_bar.addStretch()

        self.lbl_header_date = QLabel(self.selected_date_str)
        self.lbl_header_date.setStyleSheet("font-size: 16px; font-weight: bold; color: #F9FAFB;")
        header_bar.addWidget(self.lbl_header_date)

        main_layout.addLayout(header_bar)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #374151;")
        main_layout.addWidget(line)

        # ── 2. 主体三栏布局 (左:日历+菜单, 中:交班小结票据, 右:小结状态+历史) ──
        body_layout = QHBoxLayout()
        body_layout.setSpacing(12)

        # ──────────────── Left Column (日历 + 报表子导航) ────────────────
        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        # 日历控件
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setStyleSheet(
            "QCalendarWidget { background: #1E293B; color: #F9FAFB; border: 1px solid #374151; border-radius: 8px; }"
            "QCalendarWidget QWidget#qt_calendar_navigationbar { background: #111827; }"
            "QCalendarWidget QAbstractItemView { selection-background-color: #EA580C; selection-color: white; }"
        )
        self.calendar.selectionChanged.connect(self._on_date_changed)
        left_col.addWidget(self.calendar)

        # 子导航菜单列表
        self.sub_tabs_container = QVBoxLayout()
        self.sub_tabs_container.setSpacing(4)

        self.sub_tab_btns = {}
        sub_tab_names = [
            u"交班小结", u"数据日结", u"营业数据汇总",
            u"商品售卖量", u"时段营业额", u"操作日志"
        ]

        for name in sub_tab_names:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, n=name: self._switch_sub_tab(n))
            self.sub_tabs_container.addWidget(btn)
            self.sub_tab_btns[name] = btn

        left_col.addLayout(self.sub_tabs_container)
        left_col.addStretch()

        body_layout.addLayout(left_col, stretch=3)

        # ──────────────── Middle Column (交班小结白板票据) ────────────────
        mid_card = QFrame()
        mid_card.setStyleSheet(
            "QFrame { background: #FFFFFF; border-radius: 10px; border: 1px solid #E5E7EB; }"
        )
        mid_layout = QVBoxLayout(mid_card)
        mid_layout.setContentsMargins(20, 20, 20, 20)
        mid_layout.setSpacing(8)

        # 票据标题
        lbl_ticket_title = QLabel(u"交班小结")
        lbl_ticket_title.setAlignment(Qt.AlignCenter)
        lbl_ticket_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #111827;")
        mid_layout.addWidget(lbl_ticket_title)

        lbl_sep1 = QLabel("------------------------------------------")
        lbl_sep1.setAlignment(Qt.AlignCenter)
        lbl_sep1.setStyleSheet("color: #9CA3AF;")
        mid_layout.addWidget(lbl_sep1)

        # 头部门店元数据
        self.lbl_shop_name = QLabel(u"门店名称：杨国福(肥西水晶城店)")
        self.lbl_shop_name.setStyleSheet("color: #374151; font-size: 13px;")
        self.lbl_start_time = QLabel(u"开始时间：%s" % self.selected_date_str)
        self.lbl_start_time.setStyleSheet("color: #374151; font-size: 13px;")
        self.lbl_pending_count = QLabel(u"挂单数量：0")
        self.lbl_pending_count.setStyleSheet("color: #374151; font-size: 13px;")

        mid_layout.addWidget(self.lbl_shop_name)
        mid_layout.addWidget(self.lbl_start_time)
        mid_layout.addWidget(self.lbl_pending_count)

        lbl_sep2 = QLabel("------------------------------------------")
        lbl_sep2.setAlignment(Qt.AlignCenter)
        lbl_sep2.setStyleSheet("color: #9CA3AF;")
        mid_layout.addWidget(lbl_sep2)

        # 销售汇总
        lbl_sec_sales = QLabel(u"销售汇总")
        lbl_sec_sales.setStyleSheet("font-size: 15px; font-weight: bold; color: #111827;")
        mid_layout.addWidget(lbl_sec_sales)

        lbl_eq1 = QLabel("==========================================")
        lbl_eq1.setAlignment(Qt.AlignCenter)
        lbl_eq1.setStyleSheet("color: #9CA3AF;")
        mid_layout.addWidget(lbl_eq1)

        # 收入、订单量、客单价
        self.lbl_rev = self._add_receipt_row(mid_layout, u"营业收入：", u"¥ 0.00", is_bold=True)
        self.lbl_cnt = self._add_receipt_row(mid_layout, u"订单数量：", u"0")
        self.lbl_avg = self._add_receipt_row(mid_layout, u"客单价：", u"¥ 0.00")
        self.lbl_ref_amt = self._add_receipt_row(mid_layout, u"退单金额：", u"¥ 0.00")
        self.lbl_ref_cnt = self._add_receipt_row(mid_layout, u"退单数量：", u"0")

        # 收入明细
        lbl_sec_pay = QLabel(u"收入明细")
        lbl_sec_pay.setStyleSheet("font-size: 15px; font-weight: bold; color: #111827; margin-top: 8px;")
        mid_layout.addWidget(lbl_sec_pay)

        lbl_eq2 = QLabel("==========================================")
        lbl_eq2.setAlignment(Qt.AlignCenter)
        lbl_eq2.setStyleSheet("color: #9CA3AF;")
        mid_layout.addWidget(lbl_eq2)

        self.lbl_pay_rmb = self._add_receipt_row(mid_layout, u"人民币", u"¥ 0.00")
        self.lbl_pay_wx = self._add_receipt_row(mid_layout, u"微信-主扫", u"¥ 0.00")

        mid_layout.addStretch()

        # 票据内翻页 & 打印按钮
        ticket_page_row = QHBoxLayout()
        btn_t_prev = QPushButton(u"上一页")
        btn_t_prev.setStyleSheet("background: #E5E7EB; color: #374151; padding: 4px 12px; border-radius: 4px; border: none;")
        btn_t_next = QPushButton(u"下一页")
        btn_t_next.setStyleSheet("background: #E5E7EB; color: #374151; padding: 4px 12px; border-radius: 4px; border: none;")
        ticket_page_row.addWidget(btn_t_prev)
        ticket_page_row.addWidget(btn_t_next)
        mid_layout.addLayout(ticket_page_row)

        btn_print = QPushButton(u"打印")
        btn_print.setStyleSheet(
            "background: #EA580C; color: white; font-weight: 900; font-size: 16px; "
            "padding: 10px; border-radius: 6px; border: none;"
        )
        btn_print.clicked.connect(self._on_print_click)
        mid_layout.addWidget(btn_print)

        body_layout.addWidget(mid_card, stretch=4)

        # ──────────────── Right Column (小结状态卡片 + 历史操作) ────────────────
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        # 顶部收银员小结卡片
        summary_card = QFrame()
        summary_card.setStyleSheet(
            "QFrame { background: #1E293B; border: 1px solid #374151; border-radius: 10px; padding: 14px; }"
        )
        sc_layout = QVBoxLayout(summary_card)
        sc_layout.setSpacing(10)

        user_row = QHBoxLayout()
        lbl_avatar = QLabel(u"👤")
        lbl_avatar.setStyleSheet("font-size: 32px; background: #374151; border-radius: 20px; padding: 4px;")
        user_info = QVBoxLayout()
        lbl_cashier_name = QLabel(u"杨国福(肥西水晶城店)")
        lbl_cashier_name.setStyleSheet("color: #F9FAFB; font-weight: bold; font-size: 14px;")
        self.lbl_shift_time = QLabel("%s 06:44:13" % self.selected_date_str)
        self.lbl_shift_time.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        self.lbl_shift_total = QLabel(u"¥ 0.00")
        self.lbl_shift_total.setStyleSheet("color: #F9FAFB; font-size: 18px; font-weight: 900;")

        user_info.addWidget(lbl_cashier_name)
        user_info.addWidget(self.lbl_shift_time)
        user_info.addWidget(self.lbl_shift_total)

        user_row.addWidget(lbl_avatar)
        user_row.addLayout(user_info)
        sc_layout.addLayout(user_row)

        btn_settle_now = QPushButton(u"现在小结")
        btn_settle_now.setStyleSheet(
            "background: #EA580C; color: white; font-weight: bold; font-size: 15px; "
            "padding: 10px; border-radius: 6px; border: none;"
        )
        btn_settle_now.clicked.connect(self._on_settle_now)
        sc_layout.addWidget(btn_settle_now)

        right_col.addWidget(summary_card)
        right_col.addStretch()

        # 右侧底部翻页控制
        right_page_row = QHBoxLayout()
        btn_r_prev = QPushButton(u"上一页")
        btn_r_prev.setStyleSheet("background: #EA580C; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; border: none;")
        btn_r_next = QPushButton(u"下一页")
        btn_r_next.setStyleSheet("background: #EA580C; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; border: none;")

        right_page_row.addWidget(btn_r_prev)
        right_page_row.addWidget(btn_r_next)
        right_col.addLayout(right_page_row)

        body_layout.addLayout(right_col, stretch=3)

        main_layout.addLayout(body_layout, stretch=1)

        self._switch_sub_tab(u"交班小结")

    def _add_receipt_row(self, layout, key_text, val_text, is_bold=False):
        row = QHBoxLayout()
        lbl_k = QLabel(key_text)
        lbl_v = QLabel(val_text)

        font_style = "font-weight: bold;" if is_bold else ""
        lbl_k.setStyleSheet("color: #111827; font-size: 14px; %s" % font_style)
        lbl_v.setStyleSheet("color: #111827; font-size: 14px; %s" % font_style)

        row.addWidget(lbl_k)
        row.addStretch()
        row.addWidget(lbl_v)
        layout.addLayout(row)
        return lbl_v

    def _switch_sub_tab(self, name):
        self.current_sub_tab = name
        self.lbl_header_title.setText(name)
        for tab_name, btn in self.sub_tab_btns.items():
            if tab_name == name:
                btn.setStyleSheet(
                    "background: #EA580C; color: white; font-weight: bold; "
                    "border-radius: 6px; padding: 10px; border: none;"
                )
            else:
                btn.setStyleSheet(
                    "background: #1E293B; color: #9CA3AF; font-weight: bold; "
                    "border-radius: 6px; padding: 10px; border: 1px solid #374151;"
                )
        self._load_data()

    def _on_date_changed(self):
        qd = self.calendar.selectedDate()
        self.selected_date_str = qd.toString("yyyy-MM-dd")
        self.lbl_header_date.setText(self.selected_date_str)
        self.lbl_start_time.setText(u"开始时间：%s" % self.selected_date_str)
        self.lbl_shift_time.setText("%s %s" % (self.selected_date_str, datetime.now().strftime("%H:%M:%S")))
        self._load_data()

    def _load_data(self):
        stats = self.db.get_stats_by_date(self.selected_date_str, self.selected_date_str)
        count = stats.get("count", 0)
        a_sum = stats.get("amount_sum", 0.0)
        avg = a_sum / count if count > 0 else 0.0

        self.lbl_rev.setText("¥ %.2f" % a_sum)
        self.lbl_cnt.setText("%d" % count)
        self.lbl_avg.setText("¥ %.2f" % avg)
        self.lbl_pay_wx.setText("¥ %.2f" % a_sum)
        self.lbl_shift_total.setText("¥ %.2f" % a_sum)

    def _on_print_click(self):
        if self.printer:
            ticket_data = {
                "shop_name": self.config.get("shop_name", u"杨国福麻辣烫"),
                "call_no": "SHIFT",
                "weight_kg": 0.0,
                "unit_price": 0.0,
                "total_price": float(self.lbl_shift_total.text().replace("¥", "").strip()),
                "temp_order_no": "SHIFT-" + datetime.now().strftime("%Y%m%d%H%M"),
                "cart_items": [{"name": u"交班小结报表", "price": float(self.lbl_shift_total.text().replace("¥", "").strip())}],
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.printer.print_receipt(ticket_data)

        from ui.custom_dialog import show_info
        show_info(self, u"打印成功", u"交班小结报表已发送至打印机！")

    def _on_settle_now(self):
        from ui.custom_dialog import show_info
        show_info(self, u"交班成功", u"当前班次小结完成！营业额累计：￥%.2f" % float(self.lbl_shift_total.text().replace("¥", "").strip()))
