# -*- coding: utf-8 -*-
"""
外卖小票中继与菜品排序配置页面
支持触摸屏垂直滚动 (QScrollArea)、下置大高度小票预览、自动【外卖打包】标识
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QComboBox, QSpinBox, QTabWidget, QTextEdit, QScrollArea
)
from core.takeout_interceptor import DEFAULT_CATEGORIES, parse_and_sort_takeout_text
from config import save_config
from utils.window_utils import find_official_window_handle, find_official_pids
from ui.custom_dialog import show_info, show_warning


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
    """外卖小票排序与中继拦截设置面板 (支持触屏滚动)"""

    def __init__(self, config=None, printer=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.printer = printer

        saved_cats = self.config.get("takeout_categories")
        if saved_cats and isinstance(saved_cats, list) and len(saved_cats) > 0:
            self.categories = saved_cats
        else:
            self.categories = list(DEFAULT_CATEGORIES)

        self._build_ui()
        self._refresh_printer_info()
        self._load_table_data()
        self._update_live_preview()
        self._check_official_pos_status()

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

        lbl_title = QLabel(u"🛵 外卖小票中继拦截与高级排版设置")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F8FAFC; border: none;")
        hc_layout.addWidget(lbl_title)

        hc_layout.addStretch()

        self.lbl_pos_status = QLabel(u"检测官方 POS 中...")
        self.lbl_pos_status.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: none;")
        hc_layout.addWidget(self.lbl_pos_status)

        self.lbl_printer = QLabel(u"监听打印机: 检测中...")
        self.lbl_printer.setStyleSheet("font-size: 13px; color: #38BDF8; font-weight: bold; border: none;")
        hc_layout.addWidget(self.lbl_printer)

        is_active = self.config.get("takeout_interceptor_enabled", True)
        self.btn_toggle = QPushButton(u"已开启中继" if is_active else u"已关闭中继")
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
        lbl_t_title = QLabel(u"📋 分类显示顺序与匹配关键字 (失焦自动保存)")
        lbl_t_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #F8FAFC; border: none;")
        tbl_hdr.addWidget(lbl_t_title)

        tbl_hdr.addStretch()

        lbl_mm = QLabel(u"🔍 关键词匹配算法:")
        lbl_mm.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        tbl_hdr.addWidget(lbl_mm)

        self.cmb_match_mode = QComboBox()
        self.cmb_match_mode.addItems([
            u"模糊包含匹配 (推荐，例: 填'牛'可配'肥牛/牛肉')",
            u"全字精准匹配 (菜品全名必须与关键字完全一致)"
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

        lbl_hint = QLabel(u"💡 提示：关键字分隔使用逗号。系统已自动脱去全角/半角空格、序号 (1.) 及数量后缀 (x2)，避免因空格导致漏匹配。")
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
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setMinimumHeight(240)
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
        self.tabs.addTab(tab_categories, u"📋 菜品分类排序与关键字")

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
        lbl_fc1 = QLabel(u"🔤 票据各区域字号大小控制")
        lbl_fc1.setStyleSheet("font-size: 14px; font-weight: bold; color: #38BDF8; border: none;")
        fc1_lay.addWidget(lbl_fc1)

        row_f1 = QHBoxLayout()
        lbl_f_hdr = QLabel(u"单号/序号字号 (#18):")
        lbl_f_hdr.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        self.cmb_font_hdr = QComboBox()
        self.cmb_font_hdr.addItems([u"标准字号 (Normal)", u"双倍大字 (Double Size)", u"特大四倍字 (Quad Size)"])
        self.cmb_font_hdr.setCurrentIndex(1)
        self.cmb_font_hdr.setStyleSheet("QComboBox { background: #1E293B; color: #F8FAFC; border: 1px solid #334155; padding: 4px; border-radius: 4px; }")
        self.cmb_font_hdr.currentIndexChanged.connect(self._auto_save_format_settings)

        lbl_f_cat = QLabel(u"  分类标题字号 ([肉类]):")
        lbl_f_cat.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        self.cmb_font_cat = QComboBox()
        self.cmb_font_cat.addItems([u"标准字号", u"加粗大字 (Bold)", u"双倍高度 (Double Height)"])
        self.cmb_font_cat.setCurrentIndex(1)
        self.cmb_font_cat.setStyleSheet("QComboBox { background: #1E293B; color: #F8FAFC; border: 1px solid #334155; padding: 4px; border-radius: 4px; }")
        self.cmb_font_cat.currentIndexChanged.connect(self._auto_save_format_settings)

        lbl_f_item = QLabel(u"  菜品明细字号:")
        lbl_f_item.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        self.cmb_font_item = QComboBox()
        self.cmb_font_item.addItems([u"标准字号", u"双倍高度 (后厨醒目)", u"双倍大字"])
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
        f_card2.setStyleSheet("QFrame { background: #0F172A; border-radius: 8px; border: 1px solid #334155; padding: 12px; }")
        fc2_lay = QVBoxLayout(f_card2)
        fc2_lay.setSpacing(10)
        lbl_fc2 = QLabel(u"⭐ 极速检菜醒目标记与打票联数")
        lbl_fc2.setStyleSheet("font-size: 14px; font-weight: bold; color: #10B981; border: none;")
        fc2_lay.addWidget(lbl_fc2)

        row_f2 = QHBoxLayout()
        self.chk_star = QCheckBox(u"同菜品多份 (≥2) 前缀自动增加 ⭐ 醒目标记 (例: ⭐【多份x2】肥牛 x 2)")
        self.chk_star.setChecked(self.config.get("takeout_mark_star", True))
        self.chk_star.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: bold;")
        self.chk_star.stateChanged.connect(self._auto_save_format_settings)
        row_f2.addWidget(self.chk_star)

        self.chk_prices = QCheckBox(u"制作联显示菜品单价与金额")
        self.chk_prices.setChecked(self.config.get("takeout_show_prices", False))
        self.chk_prices.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        self.chk_prices.stateChanged.connect(self._auto_save_format_settings)
        row_f2.addWidget(self.chk_prices)
        row_f2.addStretch()
        fc2_lay.addLayout(row_f2)

        row_f3 = QHBoxLayout()
        lbl_k_cnt = QLabel(u"👨‍🍳 制作联 (后厨单) 打印份数:")
        lbl_k_cnt.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold;")
        self.spn_kitchen_copies = QSpinBox()
        self.spn_kitchen_copies.setRange(0, 5)
        self.spn_kitchen_copies.setValue(self.config.get("takeout_kitchen_copies", 1))
        self.spn_kitchen_copies.setStyleSheet("QSpinBox { background: #1E293B; color: #10B981; font-weight: bold; padding: 4px; }")
        self.spn_kitchen_copies.valueChanged.connect(self._auto_save_format_settings)

        lbl_c_cnt = QLabel(u"  🧾 顾客联 (存根单) 打印份数:")
        lbl_c_cnt.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold;")
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
        self.tabs.addTab(tab_format, u"🖨️ 排版字号、多份⭐标记与联数")

        # Tab C: 外卖地址、单号与预订单
        tab_header = QWidget()
        th_lay = QVBoxLayout(tab_header)
        th_lay.setContentsMargins(16, 16, 16, 16)
        th_lay.setSpacing(14)

        h_card = QFrame()
        h_card.setStyleSheet("QFrame { background: #0F172A; border-radius: 8px; border: 1px solid #334155; padding: 14px; }")
        hc_box = QVBoxLayout(h_card)
        hc_box.setSpacing(12)

        lbl_hc_title = QLabel(u"📌 外卖地址、下单时间、订单号与预订单提醒配置")
        lbl_hc_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #F59E0B; border: none;")
        hc_box.addWidget(lbl_hc_title)

        self.chk_address = QCheckBox(u"小票顶部显示送餐地址 (例: 肥西水晶城 2 栋 1802)")
        self.chk_address.setChecked(self.config.get("takeout_show_address", True))
        self.chk_address.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold;")
        self.chk_address.stateChanged.connect(self._auto_save_format_settings)
        hc_box.addWidget(self.chk_address)

        self.chk_time = QCheckBox(u"小票显示下单时间 (例: 2026-08-03 02:45:10)")
        self.chk_time.setChecked(self.config.get("takeout_show_time", True))
        self.chk_time.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold;")
        self.chk_time.stateChanged.connect(self._auto_save_format_settings)
        hc_box.addWidget(self.chk_time)

        self.chk_full_id = QCheckBox(u"小票底部显示平台完整订单号 (100088921831920)")
        self.chk_full_id.setChecked(self.config.get("takeout_show_full_id", False))
        self.chk_full_id.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold;")
        self.chk_full_id.stateChanged.connect(self._auto_save_format_settings)
        hc_box.addWidget(self.chk_full_id)

        self.chk_preorder = QCheckBox(u"⏰ 预订单 (定时单) 密集置顶醒目提醒 (防漏单防提前制作)")
        self.chk_preorder.setChecked(self.config.get("takeout_show_preorder", True))
        self.chk_preorder.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: bold;")
        self.chk_preorder.stateChanged.connect(self._auto_save_format_settings)
        hc_box.addWidget(self.chk_preorder)

        th_lay.addWidget(h_card)
        th_lay.addStretch()
        self.tabs.addTab(tab_header, u"📌 地址、单号与预订单配置")

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
        self.txt_preview.setFixedHeight(320)  # 320px 宽大高度展示全张小票
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

    def _check_official_pos_status(self):
        try:
            hwnd = find_official_window_handle()
            pids = find_official_pids()
            is_pos_running = bool(hwnd or pids)

            if is_pos_running:
                self.lbl_pos_status.setText(u"● 官方 POS 运行中 (中继可就绪)")
                self.lbl_pos_status.setStyleSheet("color: #10B981; background: rgba(16,185,129,0.15); font-size: 13px; font-weight: bold; padding: 4px 10px; border-radius: 6px;")
                self.btn_toggle.setEnabled(True)
            else:
                self.lbl_pos_status.setText(u"⚠️ 未检测到官方 POS (中继已禁关)")
                self.lbl_pos_status.setStyleSheet("color: #F59E0B; background: rgba(245,158,11,0.15); font-size: 13px; font-weight: bold; padding: 4px 10px; border-radius: 6px;")
                if self.btn_toggle.isChecked():
                    self.btn_toggle.setChecked(False)
                    self.btn_toggle.setText(u"中继不可用 (官方POS未开启)")
                self.btn_toggle.setEnabled(False)
        except Exception as e:
            print("[TakeoutSortingWidget] 官方 POS 运行检测异常:", e)

    def _refresh_printer_info(self):
        printer_name = self.config.get("printer_name", "")
        try:
            import win32print
            default_p = win32print.GetDefaultPrinter()
            actual_name = printer_name if printer_name else default_p
            if hasattr(self, 'lbl_printer'):
                self.lbl_printer.setText(f"监听打印机: {actual_name}")
        except Exception:
            try:
                if hasattr(self, 'lbl_printer'):
                    self.lbl_printer.setText(f"监听打印机: {printer_name or '默认打印机'}")
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

        save_config(self.config)

    def _update_live_preview(self):
        opts = {
            "mark_multi_qty_star": self.chk_star.isChecked(),
            "show_prices": self.chk_prices.isChecked(),
            "show_address": self.chk_address.isChecked(),
            "show_order_time": self.chk_time.isChecked(),
            "show_full_order_id": self.chk_full_id.isChecked(),
            "show_preorder_alert": self.chk_preorder.isChecked(),
            "custom_categories": self.categories
        }
        res = parse_and_sort_takeout_text(SAMPLE_RAW_TAKEOUT, opts)
        self.txt_preview.setPlainText(res.get("sorted_text", ""))

    def _on_toggle(self):
        is_on = self.btn_toggle.isChecked()
        self.config["takeout_interceptor_enabled"] = is_on
        save_config(self.config)
        self.btn_toggle.setText(u"已开启中继" if is_on else u"已关闭中继")
        show_info(self, u"中继状态", u"外卖单中继已" + (u"开启" if is_on else u"关闭"))

    def _on_save_rules(self):
        self._auto_save_categories()
        self._auto_save_format_settings()
        self._update_live_preview()
        show_info(self, u"配置保存", u"所有排版、字号、多份⭐标记与元数据规则已自动保存！")

    def _on_test_print(self):
        if self.printer:
            try:
                opts = {
                    "mark_multi_qty_star": self.chk_star.isChecked(),
                    "show_prices": self.chk_prices.isChecked(),
                    "show_address": self.chk_address.isChecked(),
                    "show_order_time": self.chk_time.isChecked(),
                    "show_full_order_id": self.chk_full_id.isChecked(),
                    "show_preorder_alert": self.chk_preorder.isChecked(),
                    "custom_categories": self.categories
                }
                res = parse_and_sort_takeout_text(SAMPLE_RAW_TAKEOUT, opts)
                sorted_txt = res.get("sorted_text", "")
                
                raw_bytes = bytearray()
                raw_bytes += b'\x1b\x40\x1b\x61\x00'
                raw_bytes += sorted_txt.encode("gbk", errors="ignore")
                raw_bytes += b'\x1b\x64\x04\x1d\x56\x01'
                
                self.printer._send_raw_to_windows(bytes(raw_bytes))
                show_info(self, u"测试打印", u"已向物理打印机发送测试小票！")
            except Exception as e:
                show_warning(self, u"打印失败", str(e))
        else:
            show_info(self, u"测试", u"模拟打票完成")
