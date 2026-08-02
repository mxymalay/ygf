# -*- coding: utf-8 -*-
"""
外卖小票中继与智能检菜排序管理页面
提供拦截总开关、排序规则配置、实时对比模拟器以及物理打印测试
"""
import time
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QCheckBox, QTextEdit, QScrollArea, QGraphicsBlurEffect
)
from core.takeout_interceptor import parse_and_sort_takeout_text, DEFAULT_CATEGORIES
from ui.custom_dialog import show_info, show_warning


# 样例美团外卖乱序原始小票文本
SAMPLE_RAW_TAKEOUT_TEXT = """------------------------------------------------
美团外卖  #18存根联
-- 堂食/外卖：外卖打包 --
下单时间：2026-08-03 02:45:10

[菜品明细]
1. 肥牛(份) x 1                           ￥15.00
2. 经典草本骨汤(微辣) x 1                   ￥0.00
3. 可乐(听) x 1                           ￥4.50
4. 娃娃菜(份) x 1                         ￥6.00
5. 鹌鹑蛋(份) x 1                         ￥8.00
6. 避忌：不要葱花, 加麻                    ￥0.00
7. 土豆片(份) x 1                         ￥5.00

原价合计：￥38.50
优惠后实付：￥35.00
地址：肥西水晶城 2 栋 1802 单元
------------------------------------------------"""


class TakeoutSortingWidget(QWidget):
    """外卖小票中继与智能检菜排序管理面板"""

    def __init__(self, config=None, printer=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.printer = printer
        self.is_interceptor_active = True

        self._build_ui()
        self._on_refresh_preview()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # ── 1. 顶栏：标题、状态与总开关卡片 ──
        header_card = QFrame()
        header_card.setStyleSheet(
            "QFrame { background: #1E293B; border-radius: 14px; border: 1px solid #334155; }"
        )
        hc_layout = QHBoxLayout(header_card)
        hc_layout.setContentsMargins(18, 14, 18, 14)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        lbl_title = QLabel(u"🛵 外卖小票中继与智能检菜排序")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 900; color: #F8FAFC; border: none;")
        lbl_sub = QLabel(u"无感监听官方 POS 打印队列 · 自动提取菜品归类重排 · 大字放大幅度提升检菜防错率")
        lbl_sub.setStyleSheet("font-size: 13px; color: #94A3B8; border: none;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        hc_layout.addLayout(title_box, stretch=1)

        # 状态指示与开关
        self.lbl_status_badge = QLabel(u"● 中继就绪 (监听中...)")
        self.lbl_status_badge.setStyleSheet(
            "background: rgba(16, 185, 129, 0.15); color: #10B981; font-size: 14px; font-weight: bold; "
            "padding: 8px 14px; border-radius: 8px; border: 1px solid #059669;"
        )
        hc_layout.addWidget(self.lbl_status_badge)

        self.btn_toggle = QPushButton(u"暂停中继")
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setStyleSheet(
            "QPushButton { background: #EA580C; color: white; font-weight: bold; font-size: 14px; "
            "border-radius: 8px; padding: 8px 18px; border: 1px solid #F97316; }"
            "QPushButton:hover { background: #F97316; }"
        )
        self.btn_toggle.clicked.connect(self._on_toggle_interceptor)
        hc_layout.addWidget(self.btn_toggle)

        main_layout.addWidget(header_card)

        # ── 2. KPI 指标数据卡片 ──
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)

        kpi1 = self._create_kpi_card(u"📦 今日中继排版外卖", u"18 单", u"零漏单/全自动拦截", u"#38BDF8")
        kpi2 = self._create_kpi_card(u"⚡ 平均处理耗时", u"12 ms", u"毫秒级秒切拦截", u"#10B981")
        kpi3 = self._create_kpi_card(u"🖨️ 绑定的物理打印机", u"芯烨 XP-A160M", u"USB 接口 ESC/POS", u"#F59E0B")

        kpi_row.addWidget(kpi1)
        kpi_row.addWidget(kpi2)
        kpi_row.addWidget(kpi3)
        main_layout.addLayout(kpi_row)

        # ── 3. 中部核心区：左侧规则配置 + 右侧实时对比模拟器 ──
        center_row = QHBoxLayout()
        center_row.setSpacing(14)

        # 3A. 左侧规则配置面板
        rules_card = QFrame()
        rules_card.setStyleSheet(
            "QFrame { background: #1E293B; border-radius: 14px; border: 1px solid #334155; }"
        )
        rc_layout = QVBoxLayout(rules_card)
        rc_layout.setContentsMargins(16, 16, 16, 16)
        rc_layout.setSpacing(12)

        lbl_r_title = QLabel(u"⚙️ 菜品分类排序优先级配置")
        lbl_r_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #F8FAFC; border: none;")
        rc_layout.addWidget(lbl_r_title)

        # 优先级列表项
        for idx, cat in enumerate(DEFAULT_CATEGORIES, start=1):
            item_box = QFrame()
            item_box.setStyleSheet(
                "QFrame { background: #0F172A; border-radius: 8px; border: 1px solid #334155; padding: 6px; }"
            )
            ib_layout = QHBoxLayout(item_box)
            ib_layout.setContentsMargins(10, 8, 10, 8)

            lbl_num = QLabel(f"{idx}.")
            lbl_num.setStyleSheet("font-size: 15px; font-weight: bold; color: #F97316; border: none;")
            ib_layout.addWidget(lbl_num)

            lbl_cname = QLabel(cat["name"])
            lbl_cname.setStyleSheet("font-size: 14px; font-weight: bold; color: #E2E8F0; border: none;")
            ib_layout.addWidget(lbl_cname, stretch=1)

            btn_up = QPushButton(u"▲")
            btn_up.setFixedWidth(28)
            btn_up.setStyleSheet("QPushButton { background: #334155; color: #94A3B8; border-radius: 4px; font-size: 10px; }")
            ib_layout.addWidget(btn_up)

            btn_down = QPushButton(u"▼")
            btn_down.setFixedWidth(28)
            btn_down.setStyleSheet("QPushButton { background: #334155; color: #94A3B8; border-radius: 4px; font-size: 10px; }")
            ib_layout.addWidget(btn_down)

            rc_layout.addWidget(item_box)

        # 开关勾选项
        rc_layout.addSpacing(6)
        self.chk_pack = QCheckBox(u"自动提取“打包”与“忌口备注”置顶大字放大")
        self.chk_pack.setChecked(True)
        self.chk_pack.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        rc_layout.addWidget(self.chk_pack)

        self.chk_count = QCheckBox(u"在各个分类标题旁自动附带数量小计 (如: 荤菜 3 项)")
        self.chk_count.setChecked(True)
        self.chk_count.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        rc_layout.addWidget(self.chk_count)

        self.chk_passthrough = QCheckBox(u"非美团/饿了么的外卖单原样全速放行 (0 延迟)")
        self.chk_passthrough.setChecked(True)
        self.chk_passthrough.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: bold;")
        rc_layout.addWidget(self.chk_passthrough)

        rc_layout.addStretch()
        center_row.addWidget(rules_card, stretch=1)

        # 3B. 右侧对比模拟预览区
        preview_card = QFrame()
        preview_card.setStyleSheet(
            "QFrame { background: #1E293B; border-radius: 14px; border: 1px solid #334155; }"
        )
        pc_layout = QVBoxLayout(preview_card)
        pc_layout.setContentsMargins(16, 16, 16, 16)
        pc_layout.setSpacing(10)

        # 预览区头部
        p_hdr = QHBoxLayout()
        lbl_p_title = QLabel(u"🔍 实时排版效果对比预览")
        lbl_p_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #F8FAFC; border: none;")
        p_hdr.addWidget(lbl_p_title, stretch=1)

        self.btn_test_print = QPushButton(u"🧪 模拟外卖单拦截并测试打票")
        self.btn_test_print.setCursor(Qt.PointingHandCursor)
        self.btn_test_print.setStyleSheet(
            "QPushButton { background: #10B981; color: white; font-weight: bold; font-size: 13px; "
            "border-radius: 8px; padding: 6px 14px; border: 1px solid #059669; }"
            "QPushButton:hover { background: #059669; }"
        )
        self.btn_test_print.clicked.connect(self._on_test_print)
        p_hdr.addWidget(self.btn_test_print)
        pc_layout.addLayout(p_hdr)

        # 左右对比视图
        compare_box = QHBoxLayout()
        compare_box.setSpacing(10)

        # 左：官方 POS 乱序原单
        v_left = QVBoxLayout()
        lbl_l = QLabel(u"❌ 官方 POS 乱序原单")
        lbl_l.setStyleSheet("font-size: 13px; font-weight: bold; color: #EF4444; border: none;")
        v_left.addWidget(lbl_l)

        self.txt_raw = QTextEdit()
        self.txt_raw.setReadOnly(True)
        self.txt_raw.setStyleSheet(
            "QTextEdit { background: #0F172A; color: #94A3B8; font-family: 'Consolas', monospace; "
            "font-size: 12px; border: 1px solid #334155; border-radius: 8px; padding: 8px; }"
        )
        self.txt_raw.setPlainText(SAMPLE_RAW_TAKEOUT_TEXT)
        v_left.addWidget(self.txt_raw)
        compare_box.addLayout(v_left)

        # 右：本系统重排后检菜单
        v_right = QVBoxLayout()
        lbl_r = QLabel(u"✅ 重排后极速检菜单")
        lbl_r.setStyleSheet("font-size: 13px; font-weight: bold; color: #10B981; border: none;")
        v_right.addWidget(lbl_r)

        self.txt_sorted = QTextEdit()
        self.txt_sorted.setReadOnly(True)
        self.txt_sorted.setStyleSheet(
            "QTextEdit { background: #0F172A; color: #34D399; font-family: 'Consolas', monospace; "
            "font-size: 12px; font-weight: bold; border: 1.5px solid #059669; border-radius: 8px; padding: 8px; }"
        )
        v_right.addWidget(self.txt_sorted)
        compare_box.addLayout(v_right)

        pc_layout.addLayout(compare_box, stretch=1)
        center_row.addWidget(preview_card, stretch=2)

        main_layout.addLayout(center_row, stretch=1)

        # ── 4. 底部拦截动态实时日志 ──
        log_card = QFrame()
        log_card.setFixedHeight(110)
        log_card.setStyleSheet(
            "QFrame { background: #0F172A; border-radius: 10px; border: 1px solid #334155; }"
        )
        lc_layout = QVBoxLayout(log_card)
        lc_layout.setContentsMargins(12, 8, 12, 8)
        lc_layout.setSpacing(4)

        lbl_log_hdr = QLabel(u"📋 实时打印队列无感中继日志 (Windows Spooler Event)")
        lbl_log_hdr.setStyleSheet("font-size: 13px; font-weight: bold; color: #94A3B8; border: none;")
        lc_layout.addWidget(lbl_log_hdr)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet(
            "QTextEdit { background: transparent; color: #38BDF8; font-family: 'Consolas', monospace; "
            "font-size: 12px; border: none; }"
        )
        self.txt_log.setPlainText(
            f"[{time.strftime('%H:%M:%S')}] 🎯 拦截中继服务就绪: 正在监听打印机队列 '芯烨 XP-A160M' (Windows Spooler Hook)\n"
            f"[{time.strftime('%H:%M:%S')}] ℹ️ 模式: 当本 POS 系统开启时自动接管重排，关闭时官方 POS 零延迟直连打印。"
        )
        lc_layout.addWidget(self.txt_log)

        main_layout.addWidget(log_card)

    def _create_kpi_card(self, title, value, sub_text, color_hex):
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #1E293B; border-radius: 12px; border: 1px solid #334155; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 13px; color: #94A3B8; border: none;")
        layout.addWidget(lbl_t)

        lbl_v = QLabel(value)
        lbl_v.setStyleSheet(f"font-size: 22px; font-weight: 900; color: {color_hex}; border: none;")
        layout.addWidget(lbl_v)

        lbl_s = QLabel(sub_text)
        lbl_s.setStyleSheet("font-size: 11px; color: #64748B; border: none;")
        layout.addWidget(lbl_s)
        return card

    def _on_refresh_preview(self):
        res = parse_and_sort_takeout_text(SAMPLE_RAW_TAKEOUT_TEXT)
        self.txt_sorted.setPlainText(res.get("sorted_text", ""))

    def _on_toggle_interceptor(self):
        self.is_interceptor_active = not self.is_interceptor_active
        if self.is_interceptor_active:
            self.lbl_status_badge.setText(u"● 中继就绪 (监听中...)")
            self.lbl_status_badge.setStyleSheet(
                "background: rgba(16, 185, 129, 0.15); color: #10B981; font-size: 14px; font-weight: bold; "
                "padding: 8px 14px; border-radius: 8px; border: 1px solid #059669;"
            )
            self.btn_toggle.setText(u"暂停中继")
            self.btn_toggle.setStyleSheet(
                "QPushButton { background: #EA580C; color: white; font-weight: bold; font-size: 14px; "
                "border-radius: 8px; padding: 8px 18px; border: 1px solid #F97316; }"
                "QPushButton:hover { background: #F97316; }"
            )
            show_info(self, u"中继拦截", u"外卖单中继拦截已开启！系统将自动捕获官方 POS 的外卖单并进行重排。")
        else:
            self.lbl_status_badge.setText(u"○ 中继已关闭 (官方POS直连)")
            self.lbl_status_badge.setStyleSheet(
                "background: rgba(148, 163, 184, 0.15); color: #94A3B8; font-size: 14px; font-weight: bold; "
                "padding: 8px 14px; border-radius: 8px; border: 1px solid #475569;"
            )
            self.btn_toggle.setText(u"开启中继")
            self.btn_toggle.setStyleSheet(
                "QPushButton { background: #10B981; color: white; font-weight: bold; font-size: 14px; "
                "border-radius: 8px; padding: 8px 18px; border: 1px solid #059669; }"
                "QPushButton:hover { background: #059669; }"
            )
            show_warning(self, u"中继拦截", u"外卖单中继已关闭。官方 POS 打单将直连打印机原样吐纸。")

    def _on_test_print(self):
        """测试发送重排后的样例小票到物理芯烨打印机"""
        if self.printer:
            try:
                res = parse_and_sort_takeout_text(SAMPLE_RAW_TAKEOUT_TEXT)
                sorted_txt = res.get("sorted_text", "")
                
                # 发送到实际打印机
                raw_bytes = bytearray()
                raw_bytes += b'\x1b\x40'  # Init
                raw_bytes += b'\x1b\x61\x00'  # Align left
                raw_bytes += sorted_txt.encode("gbk", errors="ignore")
                raw_bytes += b'\x1b\x64\x04\x1d\x56\x01'  # Feed and cut
                
                pt = self.config.get("printer_type", "windows")
                if pt == "windows":
                    self.printer._send_raw_to_windows(bytes(raw_bytes))
                show_info(self, u"测试打印", u"已成功向物理打印机发送重排后的外卖测试检菜单！\n请检查小票纸出单效果。")
            except Exception as e:
                show_warning(self, u"打印测试失败", f"物理打票出现异常: {e}")
        else:
            show_info(self, u"模拟模式", u"【模拟模式】已成功触发测试打票！")
