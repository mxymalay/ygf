# -*- coding: utf-8 -*-
"""
外卖小票排版预览与菜品排序配置页面
支持触摸屏垂直滚动 (QScrollArea)、下置大高度小票预览、自动【外卖打包】标识
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QComboBox, QSpinBox, QDoubleSpinBox, QTabWidget, QStackedWidget, QTextEdit,
    QScrollArea, QSizePolicy
)
from core.takeout_interceptor import DEFAULT_CATEGORIES, parse_and_sort_takeout_text, build_takeout_escpos_ticket
from core.takeout_jobs import TakeoutJobStore
from core.takeout_relay import mode_label
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

    def _select_section(self, section_id):
        """切换外卖设置的二级菜单。"""
        if section_id not in ("initial", "format"):
            section_id = "initial"
        index = 0 if section_id == "initial" else 1
        if hasattr(self, "section_stack"):
            self.section_stack.setCurrentIndex(index)
            # QStackedWidget otherwise keeps the tallest page's size hint.
            # The long “外卖格式” form was making the compact initial page
            # inherit a huge empty area.  Size the stack to the active page.
            page_height = getattr(self, "_section_page_heights", {}).get(section_id)
            if page_height:
                self.section_stack.setFixedHeight(page_height)
        for current_id, button in getattr(self, "section_buttons", {}).items():
            active = current_id == section_id
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

    def _select_format_third_section(self, section_id):
        """切换“外卖设置 → 外卖格式”内部的三级菜单。"""
        if section_id not in getattr(self, "_format_third_targets", {}):
            section_id = "categories"
        self.format_third_stack.setCurrentIndex(self._format_third_targets[section_id])
        for current_id, button in self.format_third_buttons.items():
            button.setChecked(current_id == section_id)

    def _build_ui(self):
        # 1. 采用外层 QScrollArea 容器，完美适配触屏滑动
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        # Keep the second-level page tied to the available viewport.  Long
        # receipt previews and format canvases must not widen the whole page
        # on the narrow POS screen.
        scroll_content.setMinimumWidth(0)
        scroll_content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
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

        lbl_title = QLabel(u"↔ 外卖设置")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F8FAFC; border: none;")
        hc_layout.addWidget(lbl_title)

        hc_layout.addStretch()

        self.lbl_pos_status = QLabel(u"中继未启动")
        self.lbl_pos_status.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: none;")
        hc_layout.addWidget(self.lbl_pos_status)

        self.lbl_printer = QLabel(u"目标打印机：检测中...")
        self.lbl_printer.setStyleSheet("font-size: 13px; color: #38BDF8; font-weight: bold; border: none;")
        hc_layout.addWidget(self.lbl_printer)

        main_layout.addWidget(header_card)

        proxy_card = QFrame()
        proxy_card.setStyleSheet("QFrame { background: #0F172A; border-radius: 10px; border: 1px solid #0EA5E9; padding: 10px; }")
        proxy_layout = QVBoxLayout(proxy_card)
        proxy_layout.setContentsMargins(16, 16, 16, 16)
        proxy_layout.setSpacing(8)
        proxy_title = QLabel(u"官方 POS 中继状态与票据识别")
        proxy_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #38BDF8; border: none;")
        proxy_layout.addWidget(proxy_title)
        proxy_hint = QLabel(u"步骤 3：分别打印真实外卖单、堂食单或收款单，检查识别结果，再决定是否启用增强模式和金额分流。\n打印机、端口、Windows 队列和测试操作已统一在“系统设置 → 打印机中继”维护。本页只显示结果，不重复保存配置。")
        proxy_hint.setWordWrap(True)
        proxy_hint.setStyleSheet("font-size: 13px; color: #CBD5E1; border: none;")
        proxy_layout.addWidget(proxy_hint)
        mode_help = QLabel(
            u"模式说明：兼容模式保留原有连单锁和按重量分流；增强模式只在官方订单号、金额和明确付款状态"
            u"都验证通过后启用金额分流；候选、状态未知或异常时自动降级为兼容模式。"
        )
        mode_help.setWordWrap(True)
        mode_help.setStyleSheet("font-size: 13px; color: #BAE6FD; background: #082F49; border: 1px solid #0369A1; border-radius: 8px; padding: 9px;")
        proxy_layout.addWidget(mode_help)
        self.lbl_relay_guide = QLabel()
        self.lbl_relay_guide.setWordWrap(True)
        self.lbl_relay_guide.setStyleSheet("color: #FDE68A; background: #422006; border: 1px solid #A16207; border-radius: 8px; padding: 10px;")
        proxy_layout.addWidget(self.lbl_relay_guide)
        # Stack the two actions vertically: on Win7 high-DPI/narrow displays
        # two wide buttons in one row force the right one outside the page.
        proxy_action_row = QVBoxLayout()
        self.btn_reprint_last = QPushButton(u"重打最近外卖单")
        self.btn_reprint_last.clicked.connect(self._on_reprint_last)
        proxy_action_row.addWidget(self.btn_reprint_last)
        self.btn_open_relay_settings = QPushButton(u"前往打印机中继设置")
        self.btn_open_relay_settings.clicked.connect(self._open_relay_settings)
        proxy_action_row.addWidget(self.btn_open_relay_settings)
        for button in (self.btn_reprint_last, self.btn_open_relay_settings):
            button.setMinimumHeight(52)
            button.setCursor(Qt.PointingHandCursor)
        proxy_layout.addLayout(proxy_action_row)
        self.lbl_last_job = QLabel(u"最近任务：无")
        self.lbl_last_job.setStyleSheet("color: #94A3B8; font-size: 13px; border: none;")
        proxy_layout.addWidget(self.lbl_last_job)
        self._refresh_relay_guide()

        # ── 2. 配置区（由左侧二级菜单切换） ──
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 2px solid #475569; background: #1E293B; border-radius: 8px; }
            QTabBar::tab { background: #0B1220; color: #CBD5E1; font-weight: bold; font-size: 14px; padding: 10px 18px; border: 1px solid #334155; border-bottom: 2px solid #334155; border-top-left-radius: 7px; border-top-right-radius: 7px; }
            QTabBar::tab:hover { background: #17243A; color: #F8FAFC; }
            QTabBar::tab:selected { background: #243B53; color: #7DD3FC; border: 2px solid #38BDF8; border-bottom: 2px solid #243B53; }
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

        self.chk_auto_print = QCheckBox(u"识别成功后自动打印重排制作单")
        self.chk_auto_print.setChecked(self.config.get("takeout_auto_print", True))
        self.chk_auto_print.setStyleSheet("color: #34D399; font-size: 13px; font-weight: bold;")
        self.chk_auto_print.stateChanged.connect(self._auto_save_format_settings)
        hc_box.addWidget(self.chk_auto_print)

        th_lay.addWidget(h_card)
        th_lay.addStretch()
        self.tabs.addTab(tab_header, u"📌 地址与单号配置")

        # “初始设置”合并原来的分类排序、地址/单号配置；“外卖格式”
        # 保留字号、联数和打印内容相关设置。这样页面二级菜单只维护
        # 两个稳定入口，不再把三个横向 Tab 挤在窄屏顶部。
        self.tabs.removeTab(2)
        self.tabs.removeTab(1)
        self.tabs.removeTab(0)
        initial_panel = QWidget()
        initial_layout = QVBoxLayout(initial_panel)
        initial_layout.setContentsMargins(0, 0, 0, 0)
        initial_layout.setSpacing(12)
        initial_layout.addWidget(proxy_card)
        initial_layout.addStretch()

        format_panel = QWidget()
        format_layout = QVBoxLayout(format_panel)
        format_layout.setContentsMargins(0, 0, 0, 0)
        format_layout.setSpacing(12)
        # “外卖设置”是二级页面；外卖格式内部再用三级菜单拆分内容，
        # 保留原有三组配置，但一次只显示当前选中的一组。
        format_third_menu = QFrame()
        format_third_menu.setObjectName("TakeoutFormatThirdLevelMenu")
        format_third_menu.setStyleSheet(
            "QFrame#TakeoutFormatThirdLevelMenu { background: #111827; border-bottom: 1px solid #334155; }"
            "QPushButton { background: transparent; color: #94A3B8; border: none; "
            "border-bottom: 3px solid transparent; border-radius: 0; padding: 9px 14px; "
            "font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background: #1E293B; color: #F8FAFC; }"
            "QPushButton:checked { background: #172554; color: #7DD3FC; border-bottom-color: #38BDF8; }"
        )
        format_third_menu_layout = QHBoxLayout(format_third_menu)
        format_third_menu_layout.setContentsMargins(0, 0, 0, 0)
        format_third_menu_layout.setSpacing(3)
        self.format_third_buttons = {}
        self.format_third_stack = QStackedWidget()
        self.format_third_stack.setStyleSheet("QStackedWidget { background: transparent; }")
        format_groups = (
            ("categories", u"① 菜品分类", tab_categories),
            ("font", u"② 字号与联数", tab_format),
            ("header", u"③ 地址与单号", tab_header),
        )
        for section_id, label, content in format_groups:
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(0)
            content.setParent(panel)
            content.show()
            panel_layout.addWidget(content)
            self.format_third_stack.addWidget(panel)

            button = QPushButton(label)
            button.setCheckable(True)
            button.setMinimumHeight(46)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, sid=section_id: self._select_format_third_section(sid)
            )
            format_third_menu_layout.addWidget(button, 1)
            self.format_third_buttons[section_id] = button
        format_third_menu_layout.addStretch()
        self._format_third_targets = {
            section_id: index for index, (section_id, _label, _content) in enumerate(format_groups)
        }
        format_layout.addWidget(format_third_menu)
        format_layout.addWidget(self.format_third_stack)
        self._select_format_third_section("categories")
        self.section_stack = QStackedWidget()
        self.section_stack.setMinimumWidth(0)
        self.section_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.section_stack.setStyleSheet("QStackedWidget { background: transparent; }")
        self.section_stack.addWidget(initial_panel)
        self.section_stack.addWidget(format_panel)
        main_layout.addWidget(self.section_stack)

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

        btn_test = QPushButton(u"前往中继测试")
        btn_test.setCursor(Qt.PointingHandCursor)
        btn_test.setStyleSheet("QPushButton { background: #10B981; color: white; font-weight: bold; font-size: 13px; border-radius: 6px; padding: 6px 16px; border: 1px solid #059669; } QPushButton:hover { background: #059669; }")
        btn_test.clicked.connect(self._open_relay_settings)
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

        format_layout.addWidget(pv_card)
        self._section_page_heights = {
            "initial": max(1, initial_panel.sizeHint().height()),
            "format": max(1, format_panel.sizeHint().height()),
        }

        # ── 4. 左侧二级菜单 ──
        section_sidebar = QFrame()
        section_sidebar.setObjectName("TakeoutSidebar")
        section_sidebar.setFixedWidth(180)
        section_sidebar.setStyleSheet(
            "QFrame#TakeoutSidebar { background-color: #0F172A; border-right: 1px solid #1E293B; }"
            "QLabel { background: transparent; }"
        )
        sidebar_layout = QVBoxLayout(section_sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 18)
        sidebar_layout.setSpacing(8)
        sidebar_title = QLabel(u"↔ 外卖设置")
        sidebar_title.setStyleSheet(
            "font-size: 22px; font-weight: 900; color: #F8FAFC; "
            "padding-left: 8px; margin-bottom: 8px; border: none;"
        )
        sidebar_layout.addWidget(sidebar_title)
        self.section_buttons = {}
        for section_id, label in (("initial", u"⚙ 初始设置"), ("format", u"♨ 外卖格式")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setMinimumHeight(56)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, sid=section_id: self._select_section(sid))
            sidebar_layout.addWidget(button)
            self.section_buttons[section_id] = button
        sidebar_layout.addStretch()

        # 让左侧菜单固定在页面边缘，右侧内容继续使用原有触屏滚动区。
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(section_sidebar)
        outer_layout.addWidget(scroll_area, stretch=1)
        self._select_section("initial")

        # 设置布局外层为 scroll_area
        scroll_area.setWidget(scroll_content)

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
            self._refresh_relay_guide()
            return
        if hasattr(self.interceptor, "ensure_running"):
            self.interceptor.ensure_running()
        state = self.interceptor.get_status()
        if state.get("running"):
            self.on_interceptor_status(u"● 守护中继运行中：127.0.0.1:%d" % self.interceptor.port)
            last_order = state.get("last_order", "")
            if last_order:
                self.lbl_last_job.setText(u"守护中继最新：%s" % last_order)
            self._refresh_relay_guide(state)
            return
        if state.get("last_error"):
            self.on_interceptor_status(u"✕ 中继异常：%s" % state.get("last_error"))
            self._refresh_relay_guide(state)
            return
        self.on_interceptor_status(u"○ 中继未启动；发送到中继队列的官方 POS 打印任务不会被接收")
        self._refresh_relay_guide(state)

    def _refresh_relay_guide(self, state=None):
        if not hasattr(self, "lbl_relay_guide"):
            return
        state = state or (self.interceptor.get_status() if self.interceptor else {})
        queue = str(self.config.get("takeout_proxy_queue_name", "") or "").strip()
        physical = str(self.config.get("printer_name", "") or "").strip() if str(self.config.get("printer_type", "windows")).lower() == "windows" else ""
        if not queue:
            text = u"尚未配置中继：请先前往“打印机中继”完成端口、Windows 队列和实体打印机配置。"
        elif queue.casefold() == physical.casefold() and physical:
            text = u"配置异常：中继队列与实体输出打印机相同，存在打印回环风险。请前往设置修复。"
        elif state.get("last_error"):
            text = u"中继异常：%s\n系统会继续使用兼容模式；请前往设置检查队列和监听状态。" % state.get("last_error")
        elif state.get("running"):
            mode = state.get("mode") or self.config.get("takeout_relay_mode", "compatibility")
            policy = state.get("mode_policy") or self.config.get("takeout_relay_mode_policy", "auto")
            reason = state.get("mode_reason") or self.config.get("takeout_relay_mode_reason", "等待验证")
            policy_text = u"自动判断" if policy == "auto" else u"强制兼容"
            text = u"中继已配置且监听中。当前：%s；策略：%s。\n原因：%s\n只有唯一订单、最终金额和可靠结账状态均验证通过，才会进入增强模式。" % (
                mode_label(mode), policy_text, reason)
        else:
            text = u"中继配置已填写但监听未运行。当前使用兼容模式，请前往设置启动并完成真实测试单。"
        self.lbl_relay_guide.setText(text)

    def _open_relay_settings(self):
        parent = self.window()
        if hasattr(parent, "open_printer_relay_settings"):
            parent.open_printer_relay_settings()
        else:
            show_warning(self, u"无法打开设置", u"请从系统设置进入“打印机中继”。")

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
        incoming = dict(parsed or {})
        raw_text = incoming.get("raw_text", "")
        dry_run = bool(incoming.get("dry_run"))
        parsed = self._parse_text(raw_text)
        for key in (
            "full_order_id", "order_no", "order_amount", "amount_source", "amount_valid",
            "payment_status", "payment_status_evidence", "payment_status_confidence",
            "payload_type", "parse_failed", "raw_payload",
        ):
            if key in incoming:
                parsed[key] = incoming[key]
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
            # Recognition failures are expected during driver/template
            # validation.  Keep the page status explicit without opening a
            # modal on every retry; the relay host already attempts raw
            # forwarding and compatibility fallback.
            self.lbl_last_job.setText(u"最近任务：状态未知，已尝试原始转发；当前使用兼容模式")
            self.on_interceptor_status(u"ⓘ 打印数据无法完整解析，已降级兼容模式")
            return
        if created and not dry_run and bool(self.config.get("takeout_auto_print", True)):
            self._print_job(job, parsed, reprint=False)

    def _print_job(self, job, parsed, reprint=False):
        if not self.printer:
            show_warning(self, u"无法打印", u"没有可用的小票打印机。请先在系统设置中选择真实物理打印机。")
            return False
        proxy_queue_name = str(self.config.get("takeout_proxy_queue_name", "")).strip().casefold()
        physical_printer = str(self.config.get("printer_name", "")).strip().casefold()
        if not physical_printer:
            try:
                import win32print
                physical_printer = str(win32print.GetDefaultPrinter() or "").strip().casefold()
            except Exception:
                pass
        if proxy_queue_name and proxy_queue_name == physical_printer:
            show_warning(
                self, u"已阻止打印回环",
                u"系统设置中的真实输出打印机不能等于官方 POS 中继队列，否则会形成打印回环。请改回实体热敏打印机后重试。",
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
        self._open_relay_settings()

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
        self._open_relay_settings()

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
        self._open_relay_settings()

    def _on_reset_proxy_config(self):
        self._open_relay_settings()
