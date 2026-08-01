"""
叫号系统配置界面 — 层次化卡片排版 (模式设置与叫号池解耦)
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QSpinBox, QCheckBox, QFrame, QButtonGroup, QScrollArea, QLayout
)
from PyQt5.QtCore import Qt, QRect, QPoint, QSize
from PyQt5.QtGui import QPainter, QRadialGradient, QColor, QBrush, QPen, QFont
from config import save_config
from core.call_number_manager import CallNumberManager


class FlowLayout(QLayout):
    """自动折行自适应流式布局"""

    def __init__(self, parent=None, margin=0, spacing=8):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Horizontal)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        margin = self.contentsMargins().left()
        return size + QSize(2 * margin, 2 * margin)

    def _doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        for item in self.itemList:
            spaceX = self.spacing()
            spaceY = self.spacing()
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()


class NumberBall(QWidget):
    """双色球/彩票风格 3D 炫彩数字球球 (使用 QPainter 抗锯齿真圆绘制，彻底消除黑框)"""

    BALL_PALETTES = [
        # (c_start, c_mid, c_end, border_color)
        ("#FF8787", "#EF4444", "#991B1B", "#FCA5A5"),  # 0: 红球 (双色球红球)
        ("#60A5FA", "#2563EB", "#1E3A8A", "#93C5FD"),  # 1: 蓝球 (双色球蓝球)
        ("#FBBF24", "#F59E0B", "#92400E", "#FDE68A"),  # 2: 琥珀金球
        ("#34D399", "#059669", "#064E3B", "#A7F3D0"),  # 3: 翡翠绿球
        ("#C084FC", "#9333EA", "#581C87", "#E9D5FF"),  # 4: 紫晶球
    ]

    def __init__(self, number: int, parent=None):
        super().__init__(parent)
        self.number = number
        self.num_str = "%02d" % number if number < 100 else str(number)
        self.setFixedSize(40, 40)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setToolTip(u"已使用餐牌号: #%s" % self.num_str)
        self.is_hovered = False

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        palette = self.BALL_PALETTES[self.number % len(self.BALL_PALETTES)]
        c_start, c_mid, c_end, c_border = palette

        # 1. 3D 径向渐变球体 (焦点在左上方 11, 11)
        radial = QRadialGradient(15, 15, 24)
        radial.setFocalPoint(11, 11)
        radial.setColorAt(0.0, QColor(c_start))
        radial.setColorAt(0.4, QColor(c_mid))
        radial.setColorAt(1.0, QColor(c_end))

        painter.setBrush(QBrush(radial))

        # 悬停时白色高亮外边框
        if self.is_hovered:
            pen = QPen(QColor("#FFFFFF"), 2.2)
        else:
            pen = QPen(QColor(c_border), 1.5)
        painter.setPen(pen)

        # 绘制抗锯齿正圆 (半径 18px)
        painter.drawEllipse(QPoint(20, 20), 18, 18)

        # 2. 居中绘制白色粗体数字
        font = QFont("Segoe UI", 11, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))

        rect = QRect(0, 0, 40, 40)
        painter.drawText(rect, Qt.AlignCenter, self.num_str)


class QueueWidget(QWidget):
    """叫号设置独立页面 — 明确层次与模块分离"""

    def __init__(self, config, call_mgr: CallNumberManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.call_mgr = call_mgr

        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        self.setStyleSheet("""
            * { border: none; outline: none; }
            QWidget { border: none; }
            QFrame { border: none; }
            QLabel { border: none; background: transparent; }
            QRadioButton { border: none; background: transparent; background-color: transparent; }
            QCheckBox { border: none; background: transparent; background-color: transparent; }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 动态滚动区域 (支持高分辨率与低分辨率屏幕)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 20, 24, 20)

        # ── 1. 顶部 Header 标题栏 ──
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)

        lbl_title = QLabel(u"⚡ 叫号避重与数据管理")
        lbl_title.setStyleSheet("font-size: 22px; font-weight: 900; color: #F9FAFB; border: none; background: transparent;")
        header_layout.addWidget(lbl_title)

        lbl_sub = QLabel(u"配置顾客餐牌叫号生成模式，防范与官方主 POS 重号，并实时监控已用号码池。")
        lbl_sub.setStyleSheet("font-size: 13px; color: #9CA3AF; border: none; background: transparent;")
        header_layout.addWidget(lbl_sub)

        layout.addLayout(header_layout)

        # 单选按钮组
        self.mode_group = QButtonGroup(self)

        # ══════════════════════════════════════════════════════════════
        # 模块 一：叫号生成模式 (Mode Selection)
        # ══════════════════════════════════════════════════════════════
        sec1_lbl = QLabel(u"一、叫号生成模式配置")
        sec1_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #38BDF8; margin-top: 6px;")
        layout.addWidget(sec1_lbl)

        mode_box = QFrame()
        mode_box.setStyleSheet("QFrame { background-color: #1E293B; border: 1px solid #334155; border-radius: 12px; }")
        mb_layout = QVBoxLayout(mode_box)
        mb_layout.setContentsMargins(16, 16, 16, 16)
        mb_layout.setSpacing(14)

        # ── 模式一：智能避重 ──
        card_smart = QFrame()
        card_smart.setStyleSheet("QFrame { background-color: #0F172A; border-radius: 8px; }")
        cs_layout = QVBoxLayout(card_smart)
        cs_layout.setContentsMargins(16, 12, 16, 12)
        cs_layout.setSpacing(8)

        radio_style = """
            QRadioButton {
                font-size: 15px; font-weight: bold; color: #F9FAFB; border: none; background: transparent; spacing: 10px;
            }
            QRadioButton::indicator {
                width: 20px; height: 20px; border-radius: 10px; border: 2px solid #64748B; background-color: #1E293B;
            }
            QRadioButton::indicator:hover {
                border-color: #F97316; background-color: #334155;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #F97316; background-color: #EA580C;
            }
        """

        cs_header = QHBoxLayout()
        self.rb_smart = QRadioButton(u"模式一：智能时段避重 (推荐)")
        self.rb_smart.setStyleSheet(radio_style)
        self.mode_group.addButton(self.rb_smart, 1)
        cs_header.addWidget(self.rb_smart)
        cs_header.addStretch()

        lbl_tag_rec = QLabel(u"🔥 店长推荐")
        lbl_tag_rec.setStyleSheet(
            "background-color: #EA580C; color: white; font-size: 11px; font-weight: bold; "
            "padding: 2px 8px; border-radius: 8px; border: none;"
        )
        cs_header.addWidget(lbl_tag_rec)
        cs_layout.addLayout(cs_header)

        lbl_s_desc = QLabel(
            u"根据营业时段自动分段生成随机避重号牌：\n"
            u"  • 上午 (05:00 - 12:00)：50 - 100 之间随机叫号\n"
            u"  • 下午 (12:00 - 18:00)：100 - 200 之间随机叫号\n"
            u"  • 晚上 (18:00 - 05:00)：200 - 300 之间随机叫号"
        )
        lbl_s_desc.setStyleSheet("color: #9CA3AF; font-size: 12px; border: none; background: transparent; line-height: 1.5;")
        cs_layout.addWidget(lbl_s_desc)

        mb_layout.addWidget(card_smart)

        # ── 模式二：自定义范围 ──
        card_custom = QFrame()
        card_custom.setStyleSheet("QFrame { background-color: #0F172A; border-radius: 8px; }")
        cc_layout = QVBoxLayout(card_custom)
        cc_layout.setContentsMargins(16, 12, 16, 12)
        cc_layout.setSpacing(10)

        self.rb_custom = QRadioButton(u"模式二：自定义范围叫号")
        self.rb_custom.setStyleSheet(radio_style)
        self.mode_group.addButton(self.rb_custom, 2)
        cc_layout.addWidget(self.rb_custom)

        c_inputs = QHBoxLayout()
        c_inputs.setContentsMargins(30, 2, 0, 2)

        lbl_start = QLabel(u"起始号码：")
        lbl_start.setStyleSheet("font-size: 13px; color: #D1D5DB; border: none; background: transparent;")
        c_inputs.addWidget(lbl_start)

        self.spin_start = QSpinBox()
        self.spin_start.setRange(1, 9999)
        self.spin_start.setStyleSheet(
            "QSpinBox { background-color: #1E293B; color: #F9FAFB; font-size: 13px; font-weight: bold; "
            "padding: 5px 10px; border-radius: 6px; border: 1px solid #334155; min-width: 70px; }"
        )
        c_inputs.addWidget(self.spin_start)

        lbl_to = QLabel(u"  至  结束号码：")
        lbl_to.setStyleSheet("font-size: 13px; color: #D1D5DB; border: none; background: transparent;")
        c_inputs.addWidget(lbl_to)

        self.spin_end = QSpinBox()
        self.spin_end.setRange(1, 9999)
        self.spin_end.setStyleSheet(
            "QSpinBox { background-color: #1E293B; color: #F9FAFB; font-size: 13px; font-weight: bold; "
            "padding: 5px 10px; border-radius: 6px; border: 1px solid #334155; min-width: 70px; }"
        )
        c_inputs.addWidget(self.spin_end)
        c_inputs.addStretch()

        cc_layout.addLayout(c_inputs)

        c_opts = QHBoxLayout()
        c_opts.setContentsMargins(30, 0, 0, 0)
        self.chk_custom_seq = QCheckBox(u"按顺序依次递增叫号 (未勾选则在指定范围内随机叫号)")
        self.chk_custom_seq.setStyleSheet("""
            QCheckBox { font-size: 12px; color: #9CA3AF; border: none; background: transparent; spacing: 8px; }
            QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1.5px solid #64748B; background-color: #1E293B; }
            QCheckBox::indicator:hover { border-color: #F97316; }
            QCheckBox::indicator:checked { border: 1.5px solid #F97316; background-color: #EA580C; }
        """)
        c_opts.addWidget(self.chk_custom_seq)
        cc_layout.addLayout(c_opts)

        mb_layout.addWidget(card_custom)

        # ── 模式三：手动指定 ──
        card_manual = QFrame()
        card_manual.setStyleSheet("QFrame { background-color: #0F172A; border-radius: 8px; }")
        cm_layout = QVBoxLayout(card_manual)
        cm_layout.setContentsMargins(16, 12, 16, 12)
        cm_layout.setSpacing(6)

        self.rb_manual = QRadioButton(u"模式三：传统手动模式")
        self.rb_manual.setStyleSheet(radio_style)
        self.mode_group.addButton(self.rb_manual, 3)
        cm_layout.addWidget(self.rb_manual)

        lbl_m_desc = QLabel(u"每次在收银台结账时，由收银员手动弹窗调整或指定本次餐牌号码。")
        lbl_m_desc.setStyleSheet("color: #9CA3AF; font-size: 12px; border: none; background: transparent; margin-left: 30px;")
        cm_layout.addWidget(lbl_m_desc)

        mb_layout.addWidget(card_manual)

        # 保存模式配置按钮
        btn_save = QPushButton(u"保存叫号模式设置")
        btn_save.setStyleSheet(
            "background: #EA580C; color: white; font-weight: bold; "
            "font-size: 14px; min-height: 40px; border-radius: 8px; padding: 0 24px; border: none;"
        )
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(self._save_settings)
        
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_box.addWidget(btn_save)
        mb_layout.addLayout(btn_box)

        layout.addWidget(mode_box)

        # ══════════════════════════════════════════════════════════════
        # 模块 二：已用叫号池与防重监控 (Pool Status Monitor)
        # ══════════════════════════════════════════════════════════════
        sec2_lbl = QLabel(u"二、已用叫号池实时监控")
        sec2_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #10B981; margin-top: 10px;")
        layout.addWidget(sec2_lbl)

        pool_frame = QFrame()
        pool_frame.setStyleSheet("QFrame { background-color: #1E293B; border: 1px solid #334155; border-radius: 12px; }")
        pf_layout = QVBoxLayout(pool_frame)
        pf_layout.setContentsMargins(20, 16, 20, 16)
        pf_layout.setSpacing(12)

        pf_header = QHBoxLayout()
        lbl_p_title = QLabel(u"🟢 今日已用号码池状态：")
        lbl_p_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #F9FAFB; border: none; background: transparent;")
        pf_header.addWidget(lbl_p_title)
        pf_header.addStretch()

        btn_reset_pool = QPushButton(u"清空重置号码池")
        btn_reset_pool.setStyleSheet(
            "background: #334155; color: #F59E0B; font-weight: bold; "
            "font-size: 13px; padding: 6px 16px; border-radius: 6px; border: none;"
        )
        btn_reset_pool.setCursor(Qt.PointingHandCursor)
        btn_reset_pool.clicked.connect(self._reset_pool)
        pf_header.addWidget(btn_reset_pool)

        pf_layout.addLayout(pf_header)

        # 球球容器与流式布局 (全透明无黑框)
        self.pool_balls_container = QWidget()
        self.pool_balls_container.setStyleSheet("background: transparent; border: none;")
        self.pool_flow_layout = FlowLayout(self.pool_balls_container, margin=2, spacing=10)
        pf_layout.addWidget(self.pool_balls_container)

        self.lbl_pool_empty = QLabel(u"暂无已使用号码，号码池为空。")
        self.lbl_pool_empty.setStyleSheet("font-size: 13px; color: #9CA3AF; border: none; background: transparent; padding: 6px 0;")
        pf_layout.addWidget(self.lbl_pool_empty)

        lbl_note = QLabel(u"(注：叫号池已开启本地安全持久化，软件重启/故障关机均不会重复号；跨营业时段时会自动重置。)")
        lbl_note.setStyleSheet("font-size: 12px; color: #64748B; border: none; background: transparent; margin-top: 6px;")
        pf_layout.addWidget(lbl_note)

        layout.addWidget(pool_frame)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_pool_display()

    def refresh_pool_display(self):
        # 清空已有球球控件
        while self.pool_flow_layout.count() > 0:
            item = self.pool_flow_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        used = self.call_mgr._used_numbers
        if not used:
            self.lbl_pool_empty.show()
            self.pool_balls_container.hide()
        else:
            self.lbl_pool_empty.hide()
            self.pool_balls_container.show()
            sorted_used = sorted(list(used))
            for num in sorted_used:
                ball = NumberBall(num)
                self.pool_flow_layout.addWidget(ball)

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
        self.call_mgr._cached_next_number = None
        self.refresh_pool_display()

        from ui.custom_dialog import show_info
        show_info(self, u"保存成功", u"叫号模式设置已成功更新并生效！")

    def _reset_pool(self):
        from ui.custom_dialog import show_info
        self.call_mgr.reset_pool()
        self.refresh_pool_display()
        show_info(self, u"提示", u"已成功清空重置叫号历史记录池！")
