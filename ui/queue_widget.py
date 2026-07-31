"""
叫号系统独立配置与管理界面
包含：智能避重模式、自定义范围模式、手动模式
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QGroupBox, QSpinBox, QCheckBox, QFrame,
    QMessageBox, QButtonGroup
)
from PyQt5.QtCore import Qt
from config import save_config
from core.call_number_manager import CallNumberManager


class QueueWidget(QWidget):
    """叫号设置独立页面"""

    def __init__(self, config, call_mgr: CallNumberManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.call_mgr = call_mgr

        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 顶部提示 banner
        banner = QFrame()
        banner.setStyleSheet(
            "QFrame { background: #1E293B; border: 1px solid #0891B2; border-radius: 12px; padding: 14px; }"
        )
        b_layout = QVBoxLayout(banner)
        b_title = QLabel(u"💡 店员提示：智能叫号避重系统")
        b_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #06B6D4;")
        b_layout.addWidget(b_title)

        b_desc = QLabel(u"官方收银软件固定从 #1 号开始叫号。启用本避重系统可彻底避免与官方小票重号叫错！")
        b_desc.setStyleSheet("font-size: 14px; color: #9CA3AF; margin-top: 4px;")
        b_layout.addWidget(b_desc)

        layout.addWidget(banner)

        # 单选按钮组
        self.mode_group = QButtonGroup(self)

        # ── 模式一：智能避重模式 ──
        g_smart = QGroupBox(u"模式一：智能时段避重模式 (推荐)")
        s_layout = QVBoxLayout(g_smart)
        s_layout.setSpacing(8)

        self.rb_smart = QRadioButton(u"启用智能避重模式")
        self.rb_smart.setStyleSheet("font-size: 16px; font-weight: bold; color: #F97316;")
        self.mode_group.addButton(self.rb_smart, 1)
        s_layout.addWidget(self.rb_smart)

        lbl_s_desc = QLabel(
            u"  • 上午 (05:00-12:00): 在 50 - 100 之间随机叫号（绝不重复）\n"
            u"  • 下午 (12:00-18:00): 在 100 - 200 之间随机叫号（绝不重复）\n"
            u"  • 晚上 (18:00-05:00): 在 200 - 300 之间随机叫号（绝不重复）"
        )
        lbl_s_desc.setStyleSheet("color: #9CA3AF; font-size: 14px; margin-left: 24px;")
        s_layout.addWidget(lbl_s_desc)

        layout.addWidget(g_smart)

        # ── 模式二：自定义范围模式 ──
        g_custom = QGroupBox(u"模式二：自定义范围模式")
        c_layout = QVBoxLayout(g_custom)
        c_layout.setSpacing(12)

        self.rb_custom = QRadioButton(u"启用自定义范围模式")
        self.rb_custom.setStyleSheet("font-size: 16px; font-weight: bold; color: #F97316;")
        self.mode_group.addButton(self.rb_custom, 2)
        c_layout.addWidget(self.rb_custom)

        c_inputs = QHBoxLayout()
        c_inputs.setContentsMargins(24, 0, 0, 0)
        c_inputs.addWidget(QLabel(u"起始号码："))

        self.spin_start = QSpinBox()
        self.spin_start.setRange(1, 9999)
        self.spin_start.setValue(50)
        c_inputs.addWidget(self.spin_start)

        c_inputs.addWidget(QLabel(u" 至 结束号码："))

        self.spin_end = QSpinBox()
        self.spin_end.setRange(1, 9999)
        self.spin_end.setValue(500)
        c_inputs.addWidget(self.spin_end)

        c_inputs.addStretch()
        c_layout.addLayout(c_inputs)

        c_opts = QHBoxLayout()
        c_opts.setContentsMargins(24, 0, 0, 0)

        self.chk_custom_seq = QCheckBox(u"按顺序依次递增叫号 (未勾选则在范围内随机叫号不重复)")
        self.chk_custom_seq.setStyleSheet("font-size: 14px; color: #F9FAFB;")
        c_opts.addWidget(self.chk_custom_seq)

        c_layout.addLayout(c_opts)

        layout.addWidget(g_custom)

        # ── 模式三：传统手动模式 ──
        g_manual = QGroupBox(u"模式三：传统手动指定模式")
        m_layout = QVBoxLayout(g_manual)

        self.rb_manual = QRadioButton(u"启用手动模式 (由收银员在收银界面自由修改)")
        self.rb_manual.setStyleSheet("font-size: 16px; font-weight: bold; color: #F97316;")
        self.mode_group.addButton(self.rb_manual, 3)
        m_layout.addWidget(self.rb_manual)

        layout.addWidget(g_manual)

        # 底部控制块
        bottom_bar = QHBoxLayout()

        btn_save = QPushButton(u"保存叫号模式配置")
        btn_save.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #EF4444, stop:1 #F97316); color: white; font-weight: bold; "
            "font-size: 16px; min-height: 48px; border-radius: 10px; padding: 0 32px;"
        )
        btn_save.clicked.connect(self._save_settings)
        bottom_bar.addWidget(btn_save)

        btn_reset_pool = QPushButton(u"清空重置已叫号历史池")
        btn_reset_pool.setStyleSheet(
            "background: #1E293B; color: #F59E0B; border: 1px solid #F59E0B; "
            "font-weight: bold; font-size: 15px; min-height: 48px; border-radius: 10px;"
        )
        btn_reset_pool.clicked.connect(self._reset_pool)
        bottom_bar.addWidget(btn_reset_pool)

        bottom_bar.addStretch()
        layout.addLayout(bottom_bar)

        layout.addStretch()

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

        QMessageBox.information(self, u"保存成功", u"叫号模式设置已更新并生效！")

    def _reset_pool(self):
        self.call_mgr.reset_pool()
        QMessageBox.information(self, u"提示", u"已成功重置已叫号历史记录池！")
