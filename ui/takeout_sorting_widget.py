# -*- coding: utf-8 -*-
"""
外卖小票中继与菜品排序配置页面
功能化更新：
1. 排序与关键字修改实时自动保存 (save_config 写入 settings.json)
2. 动态检测官方 POS 运行状态：未检测到官方 POS 软件时禁止开启中继
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit
)
from core.takeout_interceptor import DEFAULT_CATEGORIES, parse_and_sort_takeout_text
from config import save_config
from utils.window_utils import find_official_window_handle, find_official_pids
from ui.custom_dialog import show_info, show_warning


class TakeoutSortingWidget(QWidget):
    """外卖小票排序与中继拦截设置面板"""

    def __init__(self, config=None, printer=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.printer = printer
        
        # 1. 优先加载本地 saved 配置，不存在则使用默认分类
        saved_cats = self.config.get("takeout_categories")
        if saved_cats and isinstance(saved_cats, list) and len(saved_cats) > 0:
            self.categories = saved_cats
        else:
            self.categories = list(DEFAULT_CATEGORIES)

        self._build_ui()
        self._refresh_printer_info()
        self._load_table_data()

        # 2. 定时轮询检测官方 POS 软件是否处于运行状态
        self.pos_check_timer = QTimer(self)
        self.pos_check_timer.timeout.connect(self._check_official_pos_status)
        self.pos_check_timer.start(2000)
        self._check_official_pos_status()

    def showEvent(self, event):
        """进入该页面时立即刷新检测官方 POS 运行状态"""
        super().showEvent(event)
        self._check_official_pos_status()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # ── 1. 顶部控制栏 ──
        header_card = QFrame()
        header_card.setStyleSheet(
            "QFrame { background: #1E293B; border-radius: 10px; border: 1px solid #334155; }"
        )
        hc_layout = QHBoxLayout(header_card)
        hc_layout.setContentsMargins(18, 12, 18, 12)

        lbl_title = QLabel(u"🛵 外卖小票拦截与菜品排序设置")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F8FAFC; border: none;")
        hc_layout.addWidget(lbl_title)

        hc_layout.addStretch()

        # 官方 POS 运行状态徽章
        self.lbl_pos_status = QLabel(u"检测官方 POS 中...")
        self.lbl_pos_status.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: none;")
        hc_layout.addWidget(self.lbl_pos_status)

        # 动态打印机名称显示
        self.lbl_printer = QLabel(u"监听打印机: 检测中...")
        self.lbl_printer.setStyleSheet("font-size: 13px; color: #38BDF8; font-weight: bold; border: none;")
        hc_layout.addWidget(self.lbl_printer)

        # 开关按钮 (受官方 POS 运行状态管控)
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

        # ── 2. 菜品分类与关键字规则表格 ──
        table_card = QFrame()
        table_card.setStyleSheet(
            "QFrame { background: #1E293B; border-radius: 10px; border: 1px solid #334155; }"
        )
        tc_layout = QVBoxLayout(table_card)
        tc_layout.setContentsMargins(18, 16, 18, 16)
        tc_layout.setSpacing(12)

        tbl_hdr = QHBoxLayout()
        lbl_t_title = QLabel(u"📋 分类显示顺序与匹配关键字 (修改后自动保存)")
        lbl_t_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #F8FAFC; border: none;")
        tbl_hdr.addWidget(lbl_t_title)

        tbl_hdr.addStretch()

        btn_add_cat = QPushButton(u"+ 添加新分类")
        btn_add_cat.setCursor(Qt.PointingHandCursor)
        btn_add_cat.setStyleSheet(
            "QPushButton { background: #0284C7; color: white; font-weight: bold; font-size: 13px; "
            "border-radius: 6px; padding: 6px 14px; border: none; }"
            "QPushButton:hover { background: #0369A1; }"
        )
        btn_add_cat.clicked.connect(self._on_add_category)
        tbl_hdr.addWidget(btn_add_cat)

        tc_layout.addLayout(tbl_hdr)

        # 表格配置
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([u"排序", u"分类名称", u"匹配关键字 (逗号分隔)", u"顺序调整"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(54)

        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 70)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 230)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 170)

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
                border: 1px solid #334155;
                padding: 10px;
                font-size: 13px;
            }
        """)
        tc_layout.addWidget(self.table, stretch=1)

        main_layout.addWidget(table_card, stretch=1)

        # ── 3. 选项配置与控制栏 ──
        opts_card = QFrame()
        opts_card.setStyleSheet(
            "QFrame { background: #1E293B; border-radius: 10px; border: 1px solid #334155; }"
        )
        oc_layout = QHBoxLayout(opts_card)
        oc_layout.setContentsMargins(18, 12, 18, 12)
        oc_layout.setSpacing(20)

        self.chk_pack = QCheckBox(u"“打包”与“忌口”置顶大字")
        self.chk_pack.setChecked(self.config.get("takeout_pack_top", True))
        self.chk_pack.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold;")
        self.chk_pack.stateChanged.connect(self._auto_save_settings)
        oc_layout.addWidget(self.chk_pack)

        self.chk_count = QCheckBox(u"显示分类数量统计")
        self.chk_count.setChecked(self.config.get("takeout_show_count", True))
        self.chk_count.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold;")
        self.chk_count.stateChanged.connect(self._auto_save_settings)
        oc_layout.addWidget(self.chk_count)

        self.chk_pass = QCheckBox(u"非外卖单原样放行")
        self.chk_pass.setChecked(self.config.get("takeout_passthrough", True))
        self.chk_pass.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold;")
        self.chk_pass.stateChanged.connect(self._auto_save_settings)
        oc_layout.addWidget(self.chk_pass)

        oc_layout.addStretch()

        btn_save = QPushButton(u"💾 保存当前规则")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setStyleSheet(
            "QPushButton { background: #0284C7; color: white; font-weight: bold; font-size: 13px; "
            "border-radius: 6px; padding: 8px 20px; border: 1px solid #0369A1; }"
            "QPushButton:hover { background: #0369A1; }"
        )
        btn_save.clicked.connect(self._on_save_rules)
        oc_layout.addWidget(btn_save)

        btn_test = QPushButton(u"🧪 物理打票测试")
        btn_test.setCursor(Qt.PointingHandCursor)
        btn_test.setStyleSheet(
            "QPushButton { background: #10B981; color: white; font-weight: bold; font-size: 13px; "
            "border-radius: 6px; padding: 8px 20px; border: 1px solid #059669; }"
            "QPushButton:hover { background: #059669; }"
        )
        btn_test.clicked.connect(self._on_test_print)
        oc_layout.addWidget(btn_test)

        main_layout.addWidget(opts_card)

    def _check_official_pos_status(self):
        """检测官方 POS 是否开启运行，若未开启则禁止监听"""
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
        """动态查询当前 Windows 绑定的真实打印机"""
        printer_name = self.config.get("printer_name", "")
        try:
            import win32print
            default_p = win32print.GetDefaultPrinter()
            actual_name = printer_name if printer_name else default_p
            self.lbl_printer.setText(f"监听打印机: {actual_name}")
        except Exception:
            self.lbl_printer.setText(f"监听打印机: {printer_name or '默认打印机'}")

    def _load_table_data(self):
        """填充分类表格数据，绑定自动失焦与编辑修改事件"""
        self.table.setRowCount(0)
        for idx, cat in enumerate(self.categories):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setRowHeight(r, 52)

            # 序号
            item_seq = QTableWidgetItem(f"#{r + 1}")
            item_seq.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 0, item_seq)

            # 名称编辑
            txt_name = QLineEdit(cat.get("name", ""))
            txt_name.setStyleSheet(
                "QLineEdit { background: #0F172A; color: #F8FAFC; border: 1px solid #334155; "
                "border-radius: 6px; padding: 6px 10px; font-size: 14px; font-weight: bold; }"
            )
            txt_name.editingFinished.connect(self._auto_save_categories)
            self.table.setCellWidget(r, 1, txt_name)

            # 关键字编辑
            kw_str = ", ".join(cat.get("keywords", []))
            txt_kw = QLineEdit(kw_str)
            txt_kw.setStyleSheet(
                "QLineEdit { background: #0F172A; color: #38BDF8; border: 1px solid #334155; "
                "border-radius: 6px; padding: 6px 10px; font-size: 13px; font-weight: bold; }"
            )
            txt_kw.editingFinished.connect(self._auto_save_categories)
            self.table.setCellWidget(r, 2, txt_kw)

            # 顺序调整按钮栏
            btn_w = QWidget()
            btn_l = QHBoxLayout(btn_w)
            btn_l.setContentsMargins(4, 4, 4, 4)
            btn_l.setSpacing(6)

            btn_up = QPushButton(u"▲ 上移")
            btn_up.setEnabled(r > 0)
            btn_up.setCursor(Qt.PointingHandCursor)
            btn_up.setStyleSheet(
                "QPushButton { background: #334155; color: #F8FAFC; font-size: 12px; "
                "font-weight: bold; padding: 6px 10px; border-radius: 4px; border: 1px solid #475569; }"
                "QPushButton:hover { background: #475569; }"
                "QPushButton:disabled { background: #1E293B; color: #475569; border-color: #334155; }"
            )
            btn_up.clicked.connect(lambda _, row=r: self._move_row(row, -1))
            btn_l.addWidget(btn_up)

            btn_down = QPushButton(u"▼ 下移")
            btn_down.setEnabled(r < len(self.categories) - 1)
            btn_down.setCursor(Qt.PointingHandCursor)
            btn_down.setStyleSheet(
                "QPushButton { background: #334155; color: #F8FAFC; font-size: 12px; "
                "font-weight: bold; padding: 6px 10px; border-radius: 4px; border: 1px solid #475569; }"
                "QPushButton:hover { background: #475569; }"
                "QPushButton:disabled { background: #1E293B; color: #475569; border-color: #334155; }"
            )
            btn_down.clicked.connect(lambda _, row=r: self._move_row(row, 1))
            btn_l.addWidget(btn_down)

            self.table.setCellWidget(r, 3, btn_w)

    def _move_row(self, row, direction):
        target = row + direction
        if 0 <= target < len(self.categories):
            self.categories[row], self.categories[target] = self.categories[target], self.categories[row]
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
        """收集表格中的所有修改并自动序列化存入 config"""
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
        save_config(self.config)

    def _auto_save_settings(self):
        self.config["takeout_pack_top"] = self.chk_pack.isChecked()
        self.config["takeout_show_count"] = self.chk_count.isChecked()
        self.config["takeout_passthrough"] = self.chk_pass.isChecked()
        save_config(self.config)

    def _on_toggle(self):
        is_on = self.btn_toggle.isChecked()
        self.config["takeout_interceptor_enabled"] = is_on
        save_config(self.config)
        self.btn_toggle.setText(u"已开启中继" if is_on else u"已关闭中继")
        show_info(self, u"中继状态", u"外卖单中继已" + (u"开启" if is_on else u"关闭"))

    def _on_save_rules(self):
        self._auto_save_categories()
        self._auto_save_settings()
        show_info(self, u"规则保存", u"菜品分类与关键字排序规则已自动持久化保存！")

    def _on_test_print(self):
        if self.printer:
            try:
                sample_text = """美团外卖 #18
1. 肥牛 x 1
2. 草本骨汤(微辣) x 1
3. 娃娃菜 x 1
4. 可乐 x 1"""
                res = parse_and_sort_takeout_text(sample_text)
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
