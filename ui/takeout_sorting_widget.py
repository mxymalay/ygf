# -*- coding: utf-8 -*-
"""
外卖小票排版预览与菜品排序配置页面
支持触摸屏垂直滚动 (QScrollArea)、下置大高度小票预览、自动【外卖打包】标识
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QComboBox, QSpinBox, QDoubleSpinBox, QTabWidget, QTextEdit, QScrollArea
)
from core.takeout_interceptor import DEFAULT_CATEGORIES, parse_and_sort_takeout_text, build_takeout_escpos_ticket
from core.takeout_jobs import TakeoutJobStore
from config import save_config
from ui.custom_dialog import show_info, show_warning, show_question


# 样例外卖小票文本
SAMPLE_RAW_TAKEOUT = """美团外卖  #18存根联
-- 堂食/外卖：外卖打包 --
下单时间：2026-08-03 02:45:10

[菜品明细]
1. 肥牛(份) x 2                           ￥30.00
2. 经典草本骨汤(微辣) x 1                   ￥0.00
3. 可乐(听) x 1                           ￥4.50
4. 娃娃菜(份) x 1                         ￥6.00
5. 避忌：不要葱花, 加麻                    ￥0.00
6. 土豆片(份) x 1                         ￥5.00

原价合计：￥45.50
实付：￥40.00
地址：肥西水晶城 2 栋 1802 单元
订单号：100088921831920"""


class TakeoutSortingWidget(QWidget):
    """外卖小票排序与排版预览面板 (支持触屏滚动)。"""

    def __init__(self, config=None, printer=None, interceptor=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.printer = printer
        self.interceptor = interceptor
        self.job_store = TakeoutJobStore()
        self.last_job = None

        saved_cats = self.config.get("takeout_categories")
        if saved_cats and isinstance(saved_cats, list) and len(saved_cats) > 0:
            self.categories = saved_cats
        else:
            self.categories = list(DEFAULT_CATEGORIES)

        self._build_ui()
        self._refresh_printer_info()
        self._load_table_data()
        self._update_live_preview()
        recent_jobs = self.job_store.get_recent(1)
        if recent_jobs:
            self.last_job = recent_jobs[0]
            self.lbl_last_job.setText(
                u"最近任务：%s %s（%s，已打印 %d 联）" % (
                    self.last_job.get("platform", u"外卖"), self.last_job.get("order_no", u"#---"),
                    self.last_job.get("last_result", u"待打印"), self.last_job.get("print_count", 0),
                )
            )
        self._check_official_pos_status()
        # The listener now lives in a detached per-user process.  Polling its
        # compact status file keeps this settings page truthful without making
        # the page itself responsible for keeping the channel alive.
        self._proxy_status_timer = QTimer(self)
        self._proxy_status_timer.timeout.connect(self._check_official_pos_status)
        self._proxy_status_timer.start(1000)

    def showEvent(self, event):
        super().showEvent(event)
        # 仅在进入本页面时触发一次官方 POS 检测，无需后台定时循环
        self._check_official_pos_status()

    def _build_ui(self):
        # 1. 采用外层 QScrollArea 容器，完美适配触屏滑动
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # ── 1. 顶部控制栏 ──
        header_card = QFrame()
        header_card.setStyleSheet(
            "QFrame { background: #1E293B; border-radius: 10px; border: 1px solid #334155; }"
        )
        hc_layout = QHBoxLayout(header_card)
        hc_layout.setContentsMargins(16, 10, 16, 10)

        lbl_title = QLabel(u"↔ 外卖打印中继与排序")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F8FAFC; border: none;")
        hc_layout.addWidget(lbl_title)

        hc_layout.addStretch()

        self.lbl_pos_status = QLabel(u"中继未启动")
        self.lbl_pos_status.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: none;")
        hc_layout.addWidget(self.lbl_pos_status)

        self.lbl_printer = QLabel(u"目标打印机：检测中...")
        self.lbl_printer.setStyleSheet("font-size: 13px; color: #38BDF8; font-weight: bold; border: none;")
        hc_layout.addWidget(self.lbl_printer)

        is_active = bool(
            self.config.get("takeout_interceptor_enabled", False)
            and str(self.config.get("takeout_proxy_queue_name", "")).strip()
        )
        self.btn_toggle = QPushButton(u"停止中继" if is_active else u"启动中继")
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setChecked(is_active)
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setStyleSheet(
            "QPushButton { background: #10B981; color: white; font-weight: bold; font-size: 13px; "
            "border-radius: 6px; padding: 7px 18px; border: 1px solid #059669; }"
            "QPushButton:checked { background: #10B981; }"
            "QPushButton:!checked { background: #64748B; border-color: #475569; }"
            "QPushButton:disabled { background: #334155; color: #64748B; border-color: #1E293B; }"
        )
        self.btn_toggle.clicked.connect(self._on_toggle)
        hc_layout.addWidget(self.btn_toggle)

        main_layout.addWidget(header_card)

        proxy_card = QFrame()
        proxy_card.setStyleSheet("QFrame { background: #0F172A; border-radius: 10px; border: 1px solid #0EA5E9; padding: 10px; }")
        proxy_layout = QVBoxLayout(proxy_card)
        proxy_layout.setSpacing(8)
        proxy_title = QLabel(u"先配置一次：让官方 POS 的外卖单先进入本中继")
        proxy_title.setStyleSheet("font-size: 16px; font-weight: 900; color: #38BDF8; border: none;")
        proxy_layout.addWidget(proxy_title)
        proxy_hint = QLabel(
            u"1. 启动中继；2. 在 Windows 新建一个“外卖中继”打印队列，端口为标准 TCP/IP：127.0.0.1；"
            u"端口填下方数值，并使用能保留 RAW/ESC-POS 数据的热敏打印驱动；3. 官方 POS 的外卖打印选择该队列；"
            u"4. 本 POS 的打印机设置仍选择真实物理打印机。启动后中继守护进程会独立运行；即使退出本 POS 界面，"
            u"官方 POS 的外卖通道仍保持可用。原始外卖单不会直达物理机，中继会重排后再打印。"
        )
        proxy_hint.setWordWrap(True)
        proxy_hint.setStyleSheet("font-size: 13px; color: #CBD5E1; border: none;")
        proxy_layout.addWidget(proxy_hint)
        proxy_row = QHBoxLayout()
        proxy_row.addWidget(QLabel(u"中继端口："))
        self.spn_proxy_port = QSpinBox()
        self.spn_proxy_port.setRange(1024, 65535)
        self.spn_proxy_port.setValue(int(self.config.get("takeout_proxy_port", 9101)))
        proxy_row.addWidget(self.spn_proxy_port)
        proxy_row.addWidget(QLabel(u"Windows 中继队列名："))
        self.txt_proxy_queue = QLineEdit(self.config.get("takeout_proxy_queue_name", ""))
        self.txt_proxy_queue.setPlaceholderText(u"例如：YGF 外卖中继（用于防止输出回环）")
        proxy_row.addWidget(self.txt_proxy_queue)
        self.chk_auto_print = QCheckBox(u"识别到外卖单后自动打印制作联/存根联")
        self.chk_auto_print.setChecked(self.config.get("takeout_auto_print", True))
        proxy_row.addWidget(self.chk_auto_print)
        proxy_row.addStretch()
        proxy_layout.addLayout(proxy_row)

        proxy_action_row = QHBoxLayout()
        proxy_action_row.addStretch()
        self.btn_test_proxy = QPushButton(u"🧪 测试中继识别")
        self.btn_test_proxy.clicked.connect(self._on_test_proxy)
        proxy_action_row.addWidget(self.btn_test_proxy)
        self.btn_reprint_last = QPushButton(u"重打最近外卖单")
        self.btn_reprint_last.clicked.connect(self._on_reprint_last)
        proxy_action_row.addWidget(self.btn_reprint_last)
        self.btn_check_proxy = QPushButton(u"检查 Windows 队列")
        self.btn_check_proxy.clicked.connect(self._check_proxy_setup)
        proxy_action_row.addWidget(self.btn_check_proxy)
        self.btn_reset_proxy = QPushButton(u"清除本页中继配置")
        self.btn_reset_proxy.clicked.connect(self._on_reset_proxy_config)
        proxy_action_row.addWidget(self.btn_reset_proxy)
        for button in (
            self.btn_toggle, self.btn_test_proxy, self.btn_reprint_last,
            self.btn_check_proxy, self.btn_reset_proxy,
        ):
            button.setMinimumHeight(52)
            button.setCursor(Qt.PointingHandCursor)
        self.spn_proxy_port.setMinimumHeight(52)
        self.txt_proxy_queue.setMinimumHeight(52)
        proxy_layout.addLayout(proxy_action_row)
        self.lbl_last_job = QLabel(u"最近任务：无")
        self.lbl_last_job.setStyleSheet("color: #94A3B8; font-size: 13px; border: none;")
        proxy_layout.addWidget(self.lbl_last_job)
        main_layout.addWidget(proxy_card)

        # ── 2. Tab 选项卡配置板块 ──
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #334155; background: #1E293B; border-radius: 8px; }
            QTabBar::tab { background: #0F172A; color: #94A3B8; font-weight: bold; font-size: 13px; padding: 8px 16px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: #1E293B; color: #38BDF8; border: 1px solid #334155; border-bottom: none; }
        """)

        # Tab A: 分类与关键字排序
        tab_categories = QWidget()
        tc_lay = QVBoxLayout(tab_categories)
        tc_lay.setContentsMargins(12, 12, 12, 12)
        tc_lay.setSpacing(10)

        tbl_hdr = QHBoxLayout()
        lbl_t_title = QLabel(u"≡ 分类排序与关键字")
        lbl_t_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #F8FAFC; border: none;")
        tbl_hdr.addWidget(lbl_t_title)

        tbl_hdr.addStretch()

        lbl_mm = QLabel(u"匹配算法:")
        lbl_mm.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        tbl_hdr.addWidget(lbl_mm)

        self.cmb_match_mode = QComboBox()
        self.cmb_match_mode.addItems([
            u"包含匹配 (推荐)",
            u"精准全字匹配"
        ])
        saved_mode = self.config.get("takeout_match_mode", "contains")
        self.cmb_match_mode.setCurrentIndex(0 if saved_mode == "contains" else 1)
        self.cmb_match_mode.setStyleSheet("QComboBox { background: #0F172A; color: #38BDF8; font-weight: bold; border: 1px solid #334155; padding: 5px; border-radius: 4px; }")
        self.cmb_match_mode.currentIndexChanged.connect(self._auto_save_categories)
        tbl_hdr.addWidget(self.cmb_match_mode)

        btn_add_cat = QPushButton(u"+ 添加新分类")
        btn_add_cat.setCursor(Qt.PointingHandCursor)
        btn_add_cat.setStyleSheet(
            "QPushButton { background: #0284C7; color: white; font-weight: bold; font-size: 12px; "
            "border-radius: 6px; padding: 5px 14px; border: none; }"
            "QPushButton:hover { background: #0369A1; }"
        )
        btn_add_cat.clicked.connect(self._on_add_category)
        tbl_hdr.addWidget(btn_add_cat)
        tc_lay.addLayout(tbl_hdr)

        lbl_hint = QLabel(u"💡 关键字用逗号分隔，系统已自动过滤空格与序号干扰。")
        lbl_hint.setStyleSheet("color: #64748B; font-size: 12px; border: none;")
        tc_lay.addWidget(lbl_hint)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        
        item_hdr0 = QTableWidgetItem(u"排序")
        item_hdr0.setTextAlignment(Qt.AlignCenter)
        self.table.setHorizontalHeaderItem(0, item_hdr0)

        item_hdr1 = QTableWidgetItem(u"分类名称")
        item_hdr1.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setHorizontalHeaderItem(1, item_hdr1)

        item_hdr2 = QTableWidgetItem(u"匹配关键字 (逗号分隔)")
        item_hdr2.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setHorizontalHeaderItem(2, item_hdr2)

        item_hdr3 = QTableWidgetItem(u"顺序调整与操作")
        item_hdr3.setTextAlignment(Qt.AlignCenter)
        self.table.setHorizontalHeaderItem(3, item_hdr3)

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setMinimumHeight(420)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 75)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 230)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 230)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 8px;
                color: #F8FAFC;
                gridline-color: #1E293B;
                font-size: 14px;
                outline: none;
            }
            QHeaderView::section {
                background-color: #1E293B;
                color: #94A3B8;
                font-weight: bold;
                border-bottom: 1px solid #334155;
                border-right: 1px solid #1E293B;
                padding: 8px 12px;
                font-size: 13px;
            }
        """)
        tc_lay.addWidget(self.table)
        self.tabs.addTab(tab_categories, u"≡ 菜品分类排序")

        # Tab B: 排版字号、多份⭐标记与联数
        tab_format = QWidget()
        tf_lay = QVBoxLayout(tab_format)
        tf_lay.setContentsMargins(16, 16, 16, 16)
        tf_lay.setSpacing(14)

        # 区域 1：字号大小设置
        f_card1 = QFrame()
        f_card1.setStyleSheet("QFrame { background: #0F172A; border-radius: 8px; border: 1px solid #334155; padding: 12px; }")
        fc1_lay = QVBoxLayout(f_card1)
        fc1_lay.setSpacing(10)
        lbl_fc1 = QLabel(u"🔤 票据字号控制")
        lbl_fc1.setStyleSheet("font-size: 14px; font-weight: bold; color: #38BDF8; border: none;")
        fc1_lay.addWidget(lbl_fc1)

        row_f1 = QHBoxLayout()
        lbl_f_hdr = QLabel(u"单号字号:")
        lbl_f_hdr.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        self.cmb_font_hdr = QComboBox()
        self.cmb_font_hdr.addItems([u"标准字号", u"双倍大字", u"特大四倍"])
        self.cmb_font_hdr.setCurrentIndex(1)
        self.cmb_font_hdr.setStyleSheet("QComboBox { background: #1E293B; color: #F8FAFC; border: 1px solid #334155; padding: 4px; border-radius: 4px; }")
        self.cmb_font_hdr.currentIndexChanged.connect(self._auto_save_format_settings)

        lbl_f_cat = QLabel(u"  分类字号:")
        lbl_f_cat.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        self.cmb_font_cat = QComboBox()
        self.cmb_font_cat.addItems([u"标准字号", u"加粗大字", u"双倍高度"])
        self.cmb_font_cat.setCurrentIndex(1)
        self.cmb_font_cat.setStyleSheet("QComboBox { background: #1E293B; color: #F8FAFC; border: 1px solid #334155; padding: 4px; border-radius: 4px; }")
        self.cmb_font_cat.currentIndexChanged.connect(self._auto_save_format_settings)

        lbl_f_item = QLabel(u"  菜品字号:")
        lbl_f_item.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        self.cmb_font_item = QComboBox()
        self.cmb_font_item.addItems([u"标准字号", u"双倍高度", u"双倍大字"])
        self.cmb_font_item.setCurrentIndex(1)
        self.cmb_font_item.setStyleSheet("QComboBox { background: #1E293B; color: #F8FAFC; border: 1px solid #334155; padding: 4px; border-radius: 4px; }")
        self.cmb_font_item.currentIndexChanged.connect(self._auto_save_format_settings)

        row_f1.addWidget(lbl_f_hdr)
        row_f1.addWidget(self.cmb_font_hdr)
        row_f1.addWidget(lbl_f_cat)
        row_f1.addWidget(self.cmb_font_cat)
        row_f1.addWidget(lbl_f_item)
        row_f1.addWidget(self.cmb_font_item)
        row_f1.addStretch()
        fc1_lay.addLayout(row_f1)
        tf_lay.addWidget(f_card1)

        # 区域 2：⭐多份醒目标记与联数
        f_card2 = QFrame()
        f_card2.setStyleSheet("QFrame { background: #0F172A; border-radius: 8px; border: 1px solid #334155; padding: 12px; } QLabel { border: none; background: transparent; }")
        fc2_lay = QVBoxLayout(f_card2)
        fc2_lay.setSpacing(10)
        lbl_fc2 = QLabel(u"⭐ 多份标记与打印联数")
        lbl_fc2.setStyleSheet("font-size: 14px; font-weight: bold; color: #10B981; border: none; background: transparent;")
        fc2_lay.addWidget(lbl_fc2)

        row_f2 = QHBoxLayout()
        self.chk_star = QCheckBox(u"多份菜品 (≥2) 自动加 ⭐ 标记")
        self.chk_star.setChecked(self.config.get("takeout_mark_star", True))
        self.chk_star.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: bold;")
        self.chk_star.stateChanged.connect(self._auto_save_format_settings)
        row_f2.addWidget(self.chk_star)

        self.chk_prices = QCheckBox(u"制作联显示价格")
        self.chk_prices.setChecked(self.config.get("takeout_show_prices", False))
        self.chk_prices.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        self.chk_prices.stateChanged.connect(self._auto_save_format_settings)
        row_f2.addWidget(self.chk_prices)
        row_f2.addStretch()
        fc2_lay.addLayout(row_f2)

        row_f3 = QHBoxLayout()
        lbl_k_cnt = QLabel(u"👨‍🍳 制作联份数:")
        lbl_k_cnt.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self.spn_kitchen_copies = QSpinBox()
        self.spn_kitchen_copies.setRange(0, 5)
        self.spn_kitchen_copies.setValue(self.config.get("takeout_kitchen_copies", 1))
        self.spn_kitchen_copies.setStyleSheet("QSpinBox { background: #1E293B; color: #10B981; font-weight: bold; padding: 4px; }")
        self.spn_kitchen_copies.valueChanged.connect(self._auto_save_format_settings)

        lbl_c_cnt = QLabel(u"  🧾 存根联份数:")
        lbl_c_cnt.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self.spn_cust_copies = QSpinBox()
        self.spn_cust_copies.setRange(0, 5)
        self.spn_cust_copies.setValue(self.config.get("takeout_cust_copies", 0))
        self.spn_cust_copies.setStyleSheet("QSpinBox { background: #1E293B; color: #38BDF8; font-weight: bold; padding: 4px; }")
        self.spn_cust_copies.valueChanged.connect(self._auto_save_format_settings)

        row_f3.addWidget(lbl_k_cnt)
        row_f3.addWidget(self.spn_kitchen_copies)
        row_f3.addWidget(lbl_c_cnt)
        row_f3.addWidget(self.spn_cust_copies)
        row_f3.addStretch()
        fc2_lay.addLayout(row_f3)

        tf_lay.addWidget(f_card2)
        tf_lay.addStretch()
        self.tabs.addTab(tab_format, u"♨ 字号与联数设置")

        # Tab C: 外卖地址、单号与预订单
        tab_header = QWidget()
        th_lay = QVBoxLayout(tab_header)
        th_lay.setContentsMargins(16, 16, 16, 16)
        th_lay.setSpacing(14)

        h_card = QFrame()
        h_card.setStyleSheet("QFrame { background: #0F172A; border-radius: 8px; border: 1px solid #334155; padding: 14px; }")
        hc_box = QVBoxLayout(h_card)
        hc_box.setSpacing(12)

        lbl_hc_title = QLabel(u"📌 基础信息提醒配置")
        lbl_hc_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #F59E0B; border: none;")
        hc_box.addWidget(lbl_hc_title)

        self.chk_address = QCheckBox(u"显示送餐地址")
        self.chk_address.setChecked(self.config.get("takeout_show_address", True))
        self.chk_address.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold;")
        self.chk_address.stateChanged.connect(self._auto_save_format_settings)
        hc_box.addWidget(self.chk_address)

        self.chk_time = QCheckBox(u"显示下单时间")
        self.chk_time.setChecked(self.config.get("takeout_show_time", True))
        self.chk_time.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold;")
        self.chk_time.stateChanged.connect(self._auto_save_format_settings)
        hc_box.addWidget(self.chk_time)

        self.chk_full_id = QCheckBox(u"显示平台完整订单号")
        self.chk_full_id.setChecked(self.config.get("takeout_show_full_id", False))
        self.chk_full_id.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold;")
        self.chk_full_id.stateChanged.connect(self._auto_save_format_settings)
        hc_box.addWidget(self.chk_full_id)

        self.chk_preorder = QCheckBox(u"⏰ 预订单醒目提醒")
        self.chk_preorder.setChecked(self.config.get("takeout_show_preorder", True))
        self.chk_preorder.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: bold;")
        self.chk_preorder.stateChanged.connect(self._auto_save_format_settings)
        hc_box.addWidget(self.chk_preorder)

        th_lay.addWidget(h_card)
        th_lay.addStretch()
        self.tabs.addTab(tab_header, u"📌 地址与单号配置")

        main_layout.addWidget(self.tabs)

        # ── 3. 独立下置大高度【实时小票效果预览】卡片 ──
        pv_card = QFrame()
        pv_card.setStyleSheet("QFrame { background: #1E293B; border-radius: 10px; border: 1px solid #334155; padding: 14px; }")
        pv_lay = QVBoxLayout(pv_card)
        pv_lay.setContentsMargins(14, 10, 14, 10)
        pv_lay.setSpacing(8)

        pv_hdr = QHBoxLayout()
        lbl_pv = QLabel(u"🧾 小票排版效果预览")
        lbl_pv.setStyleSheet("font-size: 15px; font-weight: bold; color: #38BDF8; border: none;")
        pv_hdr.addWidget(lbl_pv)

        pv_hdr.addStretch()

        btn_refresh = QPushButton(u"🔄 刷新排版预览")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.setStyleSheet("QPushButton { background: #0284C7; color: white; font-weight: bold; font-size: 13px; border-radius: 6px; padding: 6px 14px; border: 1px solid #0369A1; } QPushButton:hover { background: #0369A1; }")
        btn_refresh.clicked.connect(self._update_live_preview)
        pv_hdr.addWidget(btn_refresh)

        btn_test = QPushButton(u"🧪 物理打票测试")
        btn_test.setCursor(Qt.PointingHandCursor)
        btn_test.setStyleSheet("QPushButton { background: #10B981; color: white; font-weight: bold; font-size: 13px; border-radius: 6px; padding: 6px 16px; border: 1px solid #059669; } QPushButton:hover { background: #059669; }")
        btn_test.clicked.connect(self._on_test_print)
        pv_hdr.addWidget(btn_test)

        pv_lay.addLayout(pv_hdr)

        self.txt_preview = QTextEdit()
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setFixedHeight(240)  # 240px 大高度下置小票预览
        self.txt_preview.setStyleSheet(
            "QTextEdit { background: #0F172A; color: #34D399; font-family: 'Consolas', monospace; "
            "font-size: 13px; font-weight: bold; border: 1.5px solid #059669; border-radius: 8px; padding: 10px; }"
        )
        pv_lay.addWidget(self.txt_preview)

        main_layout.addWidget(pv_card)

        # 2. 设置布局外层为 scroll_area
        scroll_area.setWidget(scroll_content)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll_area)

        # 3. 全局触控下拉框、选择框与数字框统一美化 (借鉴系统设置，完美适配触屏与高亮盲操)
        from ui.styles import apply_touch_combo_style, apply_touch_checkbox_style, apply_touch_spinbox_style
        for combo in self.findChildren(QComboBox):
            apply_touch_combo_style(combo, item_height=48)
            combo.wheelEvent = lambda event, w=combo: event.ignore()
        for chk in self.findChildren(QCheckBox):
            apply_touch_checkbox_style(chk)
        for spin in self.findChildren((QSpinBox, QDoubleSpinBox)):
            apply_touch_spinbox_style(spin)
            spin.wheelEvent = lambda event, w=spin: event.ignore()

    def _check_official_pos_status(self):
        if not self.interceptor:
            self.on_interceptor_status(u"✕ 外卖中继守护进程未加载")
            return
        state = self.interceptor.get_status()
        if state.get("running"):
            self.btn_toggle.setChecked(True)
            self.btn_toggle.setText(u"停止中继")
            self.on_interceptor_status(u"● 守护中继运行中：127.0.0.1:%d" % self.interceptor.port)
            last_order = state.get("last_order", "")
            if last_order:
                self.lbl_last_job.setText(u"守护中继最新：%s" % last_order)
            return
        if state.get("last_error"):
            # A checked toggle would make the next touch stop an already-dead
            # host.  Present a clear retry action instead.
            self.btn_toggle.setChecked(False)
            self.btn_toggle.setText(u"重新启动中继")
            self.on_interceptor_status(u"✕ 中继异常：%s" % state.get("last_error"))
            return
        self.btn_toggle.setChecked(False)
        self.btn_toggle.setText(u"启动中继")
        self.on_interceptor_status(u"○ 中继未启动；官方 POS 外卖单不会被拦截")

    def _refresh_printer_info(self):
        printer_name = self.config.get("printer_name", "")
        try:
            import win32print
            default_p = win32print.GetDefaultPrinter()
            actual_name = printer_name if printer_name else default_p
            if hasattr(self, 'lbl_printer'):
                self.lbl_printer.setText(f"中继输出到真实打印机：{actual_name}")
        except Exception:
            try:
                if hasattr(self, 'lbl_printer'):
                    self.lbl_printer.setText(f"中继输出到真实打印机：{printer_name or '默认打印机'}")
            except Exception:
                pass

    def _load_table_data(self):
        self.table.setRowCount(0)
        for idx, cat in enumerate(self.categories):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setRowHeight(r, 48)

            item_seq = QTableWidgetItem(f"#{r + 1}")
            item_seq.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 0, item_seq)

            txt_name = QLineEdit(cat.get("name", ""))
            txt_name.setStyleSheet("""
                QLineEdit {
                    background: transparent;
                    color: #F8FAFC;
                    border: none;
                    padding: 0px 12px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QLineEdit:focus {
                    background: #1E293B;
                    border-bottom: 2px solid #38BDF8;
                    border-radius: 2px;
                }
            """)
            txt_name.editingFinished.connect(self._auto_save_categories)
            self.table.setCellWidget(r, 1, txt_name)

            kw_str = ", ".join(cat.get("keywords", []))
            txt_kw = QLineEdit(kw_str)
            txt_kw.setStyleSheet("""
                QLineEdit {
                    background: transparent;
                    color: #38BDF8;
                    border: none;
                    padding: 0px 12px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QLineEdit:focus {
                    background: #1E293B;
                    border-bottom: 2px solid #38BDF8;
                    border-radius: 2px;
                }
            """)
            txt_kw.editingFinished.connect(self._auto_save_categories)
            self.table.setCellWidget(r, 2, txt_kw)

            btn_w = QWidget()
            btn_l = QHBoxLayout(btn_w)
            btn_l.setContentsMargins(4, 4, 4, 4)
            btn_l.setSpacing(6)

            btn_up = QPushButton(u"▲ 上移")
            btn_up.setEnabled(r > 0)
            btn_up.setCursor(Qt.PointingHandCursor)
            btn_up.setStyleSheet("QPushButton { background: #334155; color: #F8FAFC; font-size: 12px; font-weight: bold; padding: 6px 10px; border-radius: 4px; border: 1px solid #475569; } QPushButton:hover { background: #475569; } QPushButton:disabled { background: #1E293B; color: #475569; border-color: #334155; }")
            btn_up.clicked.connect(lambda _, row=r: self._move_row(row, -1))
            btn_l.addWidget(btn_up)

            btn_down = QPushButton(u"▼ 下移")
            btn_down.setEnabled(r < len(self.categories) - 1)
            btn_down.setCursor(Qt.PointingHandCursor)
            btn_down.setStyleSheet("QPushButton { background: #334155; color: #F8FAFC; font-size: 12px; font-weight: bold; padding: 6px 10px; border-radius: 4px; border: 1px solid #475569; } QPushButton:hover { background: #475569; } QPushButton:disabled { background: #1E293B; color: #475569; border-color: #334155; }")
            btn_down.clicked.connect(lambda _, row=r: self._move_row(row, 1))
            btn_l.addWidget(btn_down)

            btn_del = QPushButton(u"🗑️ 删除")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet("QPushButton { background: #7F1D1D; color: #FCA5A5; font-size: 12px; font-weight: bold; padding: 6px 10px; border-radius: 4px; border: 1px solid #991B1B; } QPushButton:hover { background: #991B1B; }")
            btn_del.clicked.connect(lambda _, row=r: self._on_delete_category(row))
            btn_l.addWidget(btn_del)

            self.table.setCellWidget(r, 3, btn_w)

    def _move_row(self, row, direction):
        target = row + direction
        if 0 <= target < len(self.categories):
            self.categories[row], self.categories[target] = self.categories[target], self.categories[row]
            self._load_table_data()
            self._auto_save_categories()

    def _on_delete_category(self, row):
        if len(self.categories) <= 1:
            show_warning(self, u"无法删除", u"列表中必须保留至少一个菜品分类！")
            return
        del self.categories[row]
        self._load_table_data()
        self._auto_save_categories()

    def _on_add_category(self):
        new_cat = {
            "id": f"custom_{len(self.categories) + 1}",
            "name": u"新分类",
            "keywords": [u"关键字1", u"关键字2"]
        }
        self.categories.append(new_cat)
        self._load_table_data()
        self._auto_save_categories()

    def _auto_save_categories(self):
        updated = []
        for r in range(self.table.rowCount()):
            name_widget = self.table.cellWidget(r, 1)
            kw_widget = self.table.cellWidget(r, 2)
            name_val = name_widget.text().strip() if name_widget else f"分类{r+1}"
            kw_val = kw_widget.text().strip() if kw_widget else ""
            kws = [k.strip() for k in kw_val.split(",") if k.strip()]
            updated.append({
                "id": f"cat_{r+1}",
                "name": name_val,
                "keywords": kws
            })
        self.categories = updated
        self.config["takeout_categories"] = updated
        mode_idx = self.cmb_match_mode.currentIndex()
        self.config["takeout_match_mode"] = "contains" if mode_idx == 0 else "exact"
        save_config(self.config)

    def _auto_save_format_settings(self):
        self.config["takeout_font_hdr"] = self.cmb_font_hdr.currentIndex()
        self.config["takeout_font_cat"] = self.cmb_font_cat.currentIndex()
        self.config["takeout_font_item"] = self.cmb_font_item.currentIndex()

        self.config["takeout_mark_star"] = self.chk_star.isChecked()
        self.config["takeout_show_prices"] = self.chk_prices.isChecked()
        self.config["takeout_kitchen_copies"] = self.spn_kitchen_copies.value()
        self.config["takeout_cust_copies"] = self.spn_cust_copies.value()

        self.config["takeout_show_address"] = self.chk_address.isChecked()
        self.config["takeout_show_time"] = self.chk_time.isChecked()
        self.config["takeout_show_full_id"] = self.chk_full_id.isChecked()
        self.config["takeout_show_preorder"] = self.chk_preorder.isChecked()
        self.config["takeout_proxy_port"] = self.spn_proxy_port.value()
        self.config["takeout_proxy_queue_name"] = self.txt_proxy_queue.text().strip()
        self.config["takeout_auto_print"] = self.chk_auto_print.isChecked()

        save_config(self.config)

    def _update_live_preview(self):
        parsed = self._parse_text(SAMPLE_RAW_TAKEOUT)
        self.txt_preview.setPlainText(parsed.get("sorted_text", ""))

    def _parse_text(self, raw_text):
        opts = {
            "mark_multi_qty_star": self.chk_star.isChecked(),
            "show_prices": self.chk_prices.isChecked(),
            "show_address": self.chk_address.isChecked(),
            "show_order_time": self.chk_time.isChecked(),
            "show_full_order_id": self.chk_full_id.isChecked(),
            "show_preorder_alert": self.chk_preorder.isChecked(),
            "custom_categories": self.categories,
            "takeout_match_mode": "contains" if self.cmb_match_mode.currentIndex() == 0 else "exact",
        }
        return parse_and_sort_takeout_text(raw_text, opts)

    def on_interceptor_status(self, status):
        self.lbl_pos_status.setText(status)
        if u"异常" in status or u"失败" in status or u"未加载" in status:
            color = "#EF4444"
        elif u"未启动" in status or u"停止" in status or u"正在启动" in status:
            color = "#F59E0B"
        else:
            color = "#10B981"
        self.lbl_pos_status.setStyleSheet(
            "color: %s; background: rgba(14,165,233,0.15); font-size: 13px; font-weight: bold; padding: 4px 10px; border-radius: 6px;" % color
        )

    def on_order_intercepted(self, parsed):
        raw_text = parsed.get("raw_text", "")
        dry_run = bool(parsed.get("dry_run"))
        parsed = self._parse_text(raw_text)
        job, created = self.job_store.create_or_get(parsed, raw_text)
        self.last_job = job
        self.txt_preview.setPlainText(parsed.get("sorted_text", ""))
        duplicate_tip = u"（重复任务，未自动重打）" if not created else u""
        self.lbl_last_job.setText(
            u"最近任务：%s %s，%d 项 %s" % (
                job.get("platform", u"外卖"), job.get("order_no", u"#---"), parsed.get("item_count", 0), duplicate_tip
            )
        )
        if parsed.get("item_count", 0) <= 0:
            show_warning(self, u"外卖单待人工核对", u"中继收到任务，但没有识别到菜品；未自动打印。请核对官方 POS 的打印驱动是否输出 RAW 文本。")
            return
        if created and not dry_run and self.chk_auto_print.isChecked():
            self._print_job(job, parsed, reprint=False)

    def _print_job(self, job, parsed, reprint=False):
        if not self.printer:
            show_warning(self, u"无法打印", u"没有可用的小票打印机。请先在系统设置中选择真实物理打印机。")
            return False
        proxy_queue_name = self.txt_proxy_queue.text().strip().casefold()
        physical_printer = str(self.config.get("printer_name", "")).strip().casefold()
        if proxy_queue_name and proxy_queue_name == physical_printer:
            show_warning(
                self, u"已阻止打印回环",
                u"系统设置中的真实打印机不能等于外卖中继队列。请把系统打印机改回物理热敏打印机后重试。",
            )
            return False
        kitchen = self.spn_kitchen_copies.value()
        stub = self.spn_cust_copies.value()
        if kitchen + stub <= 0:
            show_warning(self, u"未设置打印联数", u"制作联和存根联至少保留一联，否则中继收到订单后无法输出。")
            return False
        all_bytes = bytearray()
        for _ in range(kitchen):
            all_bytes.extend(build_takeout_escpos_ticket(parsed.get("sorted_text", ""), self.config, "kitchen"))
        for _ in range(stub):
            all_bytes.extend(build_takeout_escpos_ticket(parsed.get("sorted_text", ""), self.config, "stub"))
        success = self.printer.print_raw(bytes(all_bytes))
        updated = self.job_store.update_print_result(
            job.get("id"), success, kitchen + stub, getattr(self.printer, "last_error", "")
        )
        self.last_job = updated or job
        if success:
            suffix = u"重打" if reprint else u"已打印"
            self.lbl_last_job.setText(u"最近任务：%s %s，%s %d 联" % (
                job.get("platform", u"外卖"), job.get("order_no", u"#---"), suffix, kitchen + stub
            ))
        else:
            show_warning(self, u"外卖单打印失败", getattr(self.printer, "last_error", u"打印机未返回成功"))
        return success

    def _on_toggle(self):
        is_on = self.btn_toggle.isChecked()
        queue_name = self.txt_proxy_queue.text().strip()
        if is_on and not queue_name:
            self.btn_toggle.setChecked(False)
            show_warning(
                self, u"请先填写中继队列名",
                u"请填写刚在 Windows 创建、并供官方 POS 选择的外卖中继打印队列名。这样程序才能防止把转发单又打回中继队列。",
            )
            return
        self.config["takeout_interceptor_enabled"] = is_on
        self.config["takeout_proxy_port"] = self.spn_proxy_port.value()
        self.config["takeout_proxy_queue_name"] = queue_name
        self.config["takeout_auto_print"] = self.chk_auto_print.isChecked()
        save_config(self.config)
        self.btn_toggle.setText(u"停止中继" if is_on else u"启动中继")
        if self.interceptor:
            started = self.interceptor.update_config(self.config)
            if is_on and not started:
                self.btn_toggle.setChecked(False)
                self.config["takeout_interceptor_enabled"] = False
                save_config(self.config)
                self.btn_toggle.setText(u"启动中继")
                show_warning(self, u"中继未启动", self.interceptor.last_error or u"端口被占用或不可用")
            elif is_on:
                self.on_interceptor_status(u"ⓘ 正在启动独立中继守护进程…")
            else:
                self.on_interceptor_status(u"○ 已请求停止中继守护进程")
        else:
            show_warning(self, u"中继服务未加载", u"请重启 POS 后再启动外卖中继。")

    def _on_save_rules(self):
        self._auto_save_categories()
        self._auto_save_format_settings()
        self._update_live_preview()
        show_info(self, u"配置保存", u"所有排版、字号、多份⭐标记与元数据规则已自动保存！")

    def _on_test_print(self):
        parsed = self._parse_text(SAMPLE_RAW_TAKEOUT)
        job, _created = self.job_store.create_or_get(parsed, SAMPLE_RAW_TAKEOUT)
        self._print_job(job, parsed, reprint=True)

    def _on_test_proxy(self):
        parsed = self._parse_text(SAMPLE_RAW_TAKEOUT)
        parsed["raw_text"] = SAMPLE_RAW_TAKEOUT
        parsed["dry_run"] = True
        self.on_order_intercepted(parsed)
        show_info(self, u"中继识别测试", u"已完成本地识别测试，未发送物理打印。确认预览正确后，再在官方 POS 打印一张外卖单验证拦截。")

    def _on_reprint_last(self):
        if not self.last_job:
            show_warning(self, u"没有可重打的外卖单", u"本机还没有保存外卖中继任务。请先拦截一张外卖单。")
            return
        raw_text = self.last_job.get("raw_text", "")
        if not raw_text:
            show_warning(self, u"任务内容不完整", u"该历史任务没有原始订单文本，无法安全重打。")
            return
        parsed = self._parse_text(raw_text)
        if not parsed.get("item_count"):
            show_warning(self, u"订单无法识别", u"历史订单未识别到菜品，已阻止重打。")
            return
        self._print_job(self.last_job, parsed, reprint=True)

    def _check_proxy_setup(self):
        queue_name = self.txt_proxy_queue.text().strip()
        physical_name = str(self.config.get("printer_name", "")).strip()
        if not queue_name:
            show_warning(self, u"缺少中继队列名", u"请填写 Windows 中供官方 POS 使用的外卖中继打印队列名。")
            return
        if queue_name.casefold() == physical_name.casefold():
            show_warning(self, u"配置错误", u"外卖中继队列与真实物理打印机不能相同，否则会形成无限打印回环。")
            return
        try:
            import win32print
            names = [entry[2] for entry in win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS, None, 1
            )]
        except Exception as exc:
            show_warning(self, u"无法读取 Windows 打印机", str(exc))
            return
        if queue_name not in names:
            show_warning(
                self, u"未找到中继队列",
                u"Windows 中没有找到“%s”。请先按页面步骤创建本机 TCP/IP 队列，再让官方 POS 选择它。" % queue_name,
            )
            return
        running = bool(self.interceptor and self.interceptor._running)
        show_info(
            self, u"中继配置检查通过",
            u"中继队列：%s\n真实输出打印机：%s\n本地监听端口：127.0.0.1:%d\n守护进程状态：%s\n\n"
            u"下一步：在官方 POS 打印一张外卖单；本页“最近任务”应出现该订单，物理机只会收到重排后的单据。"
            u"中继启动后可以关闭本 POS 界面，守护进程不会随界面退出。"
            % (queue_name, physical_name or u"默认打印机", self.spn_proxy_port.value(), u"运行中" if running else u"未启动"),
        )

    def _on_reset_proxy_config(self):
        if not show_question(
            self, u"清除中继配置",
            u"将停止本 POS 的外卖中继并清除队列名称/端口配置。不会删除 Windows 中的打印队列，避免误删物理打印机。确定继续吗？",
        ):
            return
        self.config["takeout_interceptor_enabled"] = False
        self.config["takeout_proxy_queue_name"] = ""
        self.config["takeout_proxy_port"] = 9101
        save_config(self.config)
        self.txt_proxy_queue.clear()
        self.spn_proxy_port.setValue(9101)
        self.btn_toggle.setChecked(False)
        self.btn_toggle.setText(u"启动中继")
        if self.interceptor:
            self.interceptor.update_config(self.config)
        self.on_interceptor_status(u"○ 已清除本 POS 中继配置；Windows 队列未删除")
