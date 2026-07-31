"""
叫号系统配置界面 — 极简去边框与现代卡片排版
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QSpinBox, QCheckBox, QFrame, QButtonGroup
)
from PyQt5.QtCore import Qt
from config import save_config
from core.call_number_manager import CallNumberManager


class QueueWidget(QWidget):
    """叫号设置独立页面 — 极简深色卡片风格"""

    def __init__(self, config, call_mgr: CallNumberManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.call_mgr = call_mgr

        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(24, 20, 24, 20)

        # ── 1. 顶部 Header 标题栏 ──
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)

        lbl_title = QLabel(u"⚡ 叫号避重模式设置")
        lbl_title.setStyleSheet("font-size: 22px; font-weight: 900; color: #F9FAFB; border: none;")
        header_layout.addWidget(lbl_title)

        lbl_sub = QLabel(u"设置顾客餐牌叫号生成模式，智能避开官方主POS重号，提升翻台与叫号体验。")
        lbl_sub.setStyleSheet("font-size: 13px; color: #9CA3AF; border: none;")
        header_layout.addWidget(lbl_sub)

        main_layout.addLayout(header_layout)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #374151; border: none; margin-top: 4px; margin-bottom: 4px;")
        main_layout.addWidget(line)

        # 单选按钮组
        self.mode_group = QButtonGroup(self)

        # ── 2. 模式一：智能避重卡片 ──
        card_smart = QFrame()
        card_smart.setStyleSheet("QFrame { background: #1E293B; border: none; border-radius: 12px; }")
        cs_layout = QVBoxLayout(card_smart)
        cs_layout.setContentsMargins(20, 16, 20, 16)
        cs_layout.setSpacing(10)

        cs_header = QHBoxLayout()
        self.rb_smart = QRadioButton(u"模式一：智能时段避重 (推荐)")
        self.rb_smart.setStyleSheet(
            "QRadioButton { font-size: 16px; font-weight: bold; color: #F9FAFB; border: none; }"
            "QRadioButton::indicator { width: 18px; height: 18px; }"
            "QRadioButton::indicator:checked { background: #EA580C; border-radius: 9px; }"
        )
        self.mode_group.addButton(self.rb_smart, 1)
        cs_header.addWidget(self.rb_smart)
        cs_header.addStretch()

        lbl_tag_rec = QLabel(u"🔥 店长推荐")
        lbl_tag_rec.setStyleSheet(
            "background: #EA580C; color: white; font-size: 12px; font-weight: bold; "
            "padding: 3px 10px; border-radius: 10px; border: none;"
        )
        cs_header.addWidget(lbl_tag_rec)
        cs_layout.addLayout(cs_header)

        lbl_s_desc = QLabel(
            u"根据营业时段自动分段生成随机避重号牌：\n"
            u"  • 上午 (05:00 - 12:00)：50 - 100 之间随机叫号\n"
            u"  • 下午 (12:00 - 18:00)：100 - 200 之间随机叫号\n"
            u"  • 晚上 (18:00 - 05:00)：200 - 300 之间随机叫号"
        )
        lbl_s_desc.setStyleSheet("color: #9CA3AF; font-size: 13px; border: none; line-height: 1.5;")
        cs_layout.addWidget(lbl_s_desc)

        main_layout.addWidget(card_smart)

        # ── 3. 模式二：自定义范围卡片 ──
        card_custom = QFrame()
        card_custom.setStyleSheet("QFrame { background: #1E293B; border: none; border-radius: 12px; }")
        cc_layout = QVBoxLayout(card_custom)
        cc_layout.setContentsMargins(20, 16, 20, 16)
        cc_layout.setSpacing(12)

        self.rb_custom = QRadioButton(u"模式二：自定义范围叫号")
        self.rb_custom.setStyleSheet(
            "QRadioButton { font-size: 16px; font-weight: bold; color: #F9FAFB; border: none; }"
            "QRadioButton::indicator { width: 18px; height: 18px; }"
            "QRadioButton::indicator:checked { background: #EA580C; border-radius: 9px; }"
        )
        self.mode_group.addButton(self.rb_custom, 2)
        cc_layout.addWidget(self.rb_custom)

        c_inputs = QHBoxLayout()
        c_inputs.setContentsMargins(24, 4, 0, 4)

        lbl_start = QLabel(u"起始号码：")
        lbl_start.setStyleSheet("font-size: 14px; color: #D1D5DB; border: none;")
        c_inputs.addWidget(lbl_start)

        self.spin_start = QSpinBox()
        self.spin_start.setRange(1, 9999)
        self.spin_start.setStyleSheet(
            "QSpinBox { background: #334155; color: #F9FAFB; font-size: 14px; font-weight: bold; "
            "padding: 6px 12px; border-radius: 6px; border: none; min-width: 80px; }"
        )
        c_inputs.addWidget(self.spin_start)

        lbl_to = QLabel(u"  至  结束号码：")
        lbl_to.setStyleSheet("font-size: 14px; color: #D1D5DB; border: none;")
        c_inputs.addWidget(lbl_to)

        self.spin_end = QSpinBox()
        self.spin_end.setRange(1, 9999)
        self.spin_end.setStyleSheet(
            "QSpinBox { background: #334155; color: #F9FAFB; font-size: 14px; font-weight: bold; "
            "padding: 6px 12px; border-radius: 6px; border: none; min-width: 80px; }"
        )
        c_inputs.addWidget(self.spin_end)
        c_inputs.addStretch()

        cc_layout.addLayout(c_inputs)

        c_opts = QHBoxLayout()
        c_opts.setContentsMargins(24, 0, 0, 0)
        self.chk_custom_seq = QCheckBox(u"按顺序依次递增叫号 (未勾选则在指定范围内随机叫号)")
        self.chk_custom_seq.setStyleSheet("font-size: 13px; color: #9CA3AF; border: none;")
        c_opts.addWidget(self.chk_custom_seq)
        cc_layout.addLayout(c_opts)

        main_layout.addWidget(card_custom)

        # ── 4. 模式三：手动指定模式卡片 ──
        card_manual = QFrame()
        card_manual.setStyleSheet("QFrame { background: #1E293B; border: none; border-radius: 12px; }")
        cm_layout = QVBoxLayout(card_manual)
        cm_layout.setContentsMargins(20, 16, 20, 16)
        cm_layout.setSpacing(6)

        self.rb_manual = QRadioButton(u"模式三：传统手动模式")
        self.rb_manual.setStyleSheet(
            "QRadioButton { font-size: 16px; font-weight: bold; color: #F9FAFB; border: none; }"
            "QRadioButton::indicator { width: 18px; height: 18px; }"
            "QRadioButton::indicator:checked { background: #EA580C; border-radius: 9px; }"
        )
        self.mode_group.addButton(self.rb_manual, 3)
        cm_layout.addWidget(self.rb_manual)

        lbl_m_desc = QLabel(u"每次在收银台结账时，由收银员手动弹窗调整或指定本次餐牌号码。")
        lbl_m_desc.setStyleSheet("color: #9CA3AF; font-size: 13px; border: none; margin-left: 24px;")
        cm_layout.addWidget(lbl_m_desc)

        main_layout.addWidget(card_manual)

        main_layout.addStretch()

        # ── 5. 底部控制操作栏 ──
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(14)

        btn_save = QPushButton(u"保存叫号配置")
        btn_save.setStyleSheet(
            "background: #EA580C; color: white; font-weight: bold; "
            "font-size: 15px; min-height: 44px; border-radius: 8px; padding: 0 28px; border: none;"
        )
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(self._save_settings)
        bottom_bar.addWidget(btn_save)

        btn_reset_pool = QPushButton(u"清空重置已用号池")
        btn_reset_pool.setStyleSheet(
            "background: #334155; color: #F59E0B; font-weight: bold; "
            "font-size: 14px; min-height: 44px; border-radius: 8px; padding: 0 20px; border: none;"
        )
        btn_reset_pool.setCursor(Qt.PointingHandCursor)
        btn_reset_pool.clicked.connect(self._reset_pool)
        bottom_bar.addWidget(btn_reset_pool)

        bottom_bar.addStretch()
        main_layout.addLayout(bottom_bar)

    def _load_settings(self):
        mode = self.config.get("call_mode", CallNumberManager.MODE_SMART)
        if mode == CallNumberManager.MODE_SMART:
            self.rb_smart.setChecked(True)
        elif mode == CallNumberManager.MODE_CUSTOM:
            self.rb_custom.setChecked(True)
        else:
            self.rb_manual.setChecked(True)

        self.spin_start.setValue(self.config.get("custom_start_no", 50))
        self.spin_end.setValue(self.config.get("custom_end_no", 500))
        self.chk_custom_seq.setChecked(self.config.get("custom_is_seq", False))

    def _save_settings(self):
        if self.rb_smart.isChecked():
            mode = CallNumberManager.MODE_SMART
        elif self.rb_custom.isChecked():
            mode = CallNumberManager.MODE_CUSTOM
        else:
            mode = CallNumberManager.MODE_MANUAL

        self.config["call_mode"] = mode
        self.config["custom_start_no"] = self.spin_start.value()
        self.config["custom_end_no"] = self.spin_end.value()
        self.config["custom_is_seq"] = self.chk_custom_seq.isChecked()

        save_config(self.config)
        self.call_mgr.reset_pool()

        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"叫号模式设置已成功更新并生效！")

    def _reset_pool(self):
        from ui.custom_dialog import show_info
        self.call_mgr.reset_pool()
        show_info(self, u"提示", u"已成功清空重置叫号历史记录池！")

