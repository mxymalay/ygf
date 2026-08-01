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

    # 取消固定色板，改用动态 HSV 颜色生成

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

        # 使用动态 HSV 颜色空间，让相邻数字颜色相近（每增加1，色相增加4度，90个数字循环一次彩虹色）
        h = (self.number * 4) % 360
        c_start = QColor.fromHsv(h, 120, 255)   # 较亮、饱和度较低（反光点）
        c_mid = QColor.fromHsv(h, 200, 230)     # 中间主色
        c_end = QColor.fromHsv(h, 255, 150)     # 暗部，高饱和、低亮度
        c_border = QColor.fromHsv(h, 80, 255)   # 边框色，极亮

        # 1. 3D 径向渐变球体 (焦点在左上方 11, 11)
        radial = QRadialGradient(15, 15, 24)
        radial.setFocalPoint(11, 11)
        radial.setColorAt(0.0, c_start)
        radial.setColorAt(0.4, c_mid)
        radial.setColorAt(1.0, c_end)

        painter.setBrush(QBrush(radial))

        # 悬停时白色高亮外边框
        if self.is_hovered:
            pen = QPen(QColor("#FFFFFF"), 2.2)
        else:
            pen = QPen(c_border, 1.5)
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

        lbl_title = QLabel(u"☕ 取餐号管理")
        lbl_title.setStyleSheet("font-size: 22px; font-weight: 900; color: #F9FAFB; border: none; background: transparent;")
        header_layout.addWidget(lbl_title)

        lbl_sub = QLabel(u"配置取餐号生成方式，避免与主收银系统重号。")
        lbl_sub.setStyleSheet("font-size: 13px; color: #9CA3AF; border: none; background: transparent;")
        header_layout.addWidget(lbl_sub)

        layout.addLayout(header_layout)

        # 模式选择下拉框
        mode_box = QFrame()
        mode_box.setStyleSheet("QFrame { background-color: #1E293B; border: 1px solid #334155; border-radius: 12px; }")
        mb_layout = QVBoxLayout(mode_box)
        mb_layout.setContentsMargins(16, 16, 16, 16)
        mb_layout.setSpacing(14)
        
        from PyQt5.QtWidgets import QComboBox, QStackedWidget, QStyledItemDelegate
        mode_select_layout = QHBoxLayout()
        lbl_ms = QLabel(u"取餐号模式：")
        lbl_ms.setStyleSheet("font-size: 15px; font-weight: bold; color: #F8FAFC; border: none; background: transparent;")
        mode_select_layout.addWidget(lbl_ms)
        
        self.cmb_mode = QComboBox()
        self.cmb_mode.setItemDelegate(QStyledItemDelegate())
        self.cmb_mode.addItems([
            u"模式一：智能时段避重 (推荐)",
            u"模式二：自定义范围叫号",
            u"模式三：传统手动模式"
        ])
        self.cmb_mode.setStyleSheet("""
            QComboBox { 
                font-size: 15px; font-weight: bold; padding: 10px 18px; 
                border-radius: 8px; background: #0F172A; color: #F8FAFC; border: 1px solid #334155;
                min-width: 260px;
            }
            QComboBox::drop-down { 
                border: none; 
                width: 30px;
            }
            QComboBox QAbstractItemView {
                background-color: #0F172A;
                color: #F8FAFC;
                selection-background-color: #EA580C;
                selection-color: #FFFFFF;
                font-size: 15px;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                min-height: 46px;
                padding: 8px 14px;
                border-radius: 6px;
            }
        """)
        mode_select_layout.addWidget(self.cmb_mode)
        mode_select_layout.addStretch()
        mb_layout.addLayout(mode_select_layout)
        
        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("border: none; background: #334155; max-height: 1px; margin: 4px 0;")
        mb_layout.addWidget(line)
        
        self.stack_mode = QStackedWidget()
        self.stack_mode.setStyleSheet("background: transparent;")
        mb_layout.addWidget(self.stack_mode)
        
        self.cmb_mode.currentIndexChanged.connect(self.stack_mode.setCurrentIndex)

        # ── 模式一：智能避重 ──
        card_smart = QFrame()
        card_smart.setStyleSheet("QFrame { background: #0F172A; border-radius: 10px; border: 1px solid #334155; }")
        cs_layout = QVBoxLayout(card_smart)
        cs_layout.setContentsMargins(16, 14, 16, 14)
        cs_layout.setSpacing(8)

        lbl_s_desc = QLabel(
            u"💡 机制说明：根据营业时段自动分段生成随机避重号牌\n"
            u"  • 上午 (05:00 - 12:00)：50 - 100 之间随机叫号\n"
            u"  • 下午 (12:00 - 18:00)：100 - 200 之间随机叫号\n"
            u"  • 晚上 (18:00 - 05:00)：200 - 300 之间随机叫号"
        )
        lbl_s_desc.setStyleSheet("color: #94A3B8; font-size: 13px; border: none; background: transparent; line-height: 1.6;")
        cs_layout.addWidget(lbl_s_desc)

        self.stack_mode.addWidget(card_smart)

        # ── 模式二：自定义范围 ──
        card_custom = QFrame()
        card_custom.setStyleSheet("QFrame { background: #0F172A; border-radius: 10px; border: 1px solid #334155; }")
        cc_layout = QVBoxLayout(card_custom)
        cc_layout.setContentsMargins(16, 14, 16, 14)
        cc_layout.setSpacing(12)

        c_inputs = QHBoxLayout()
        c_inputs.setContentsMargins(0, 0, 0, 0)
        c_inputs.setSpacing(10)

        lbl_start = QLabel(u"起始号码：")
        lbl_start.setStyleSheet("font-size: 13px; color: #E2E8F0; border: none; background: transparent;")
        c_inputs.addWidget(lbl_start)

        self.spin_start = QSpinBox()
        self.spin_start.setRange(1, 9999)
        self.spin_start.setStyleSheet(
            "QSpinBox { background-color: #1E293B; color: #F8FAFC; font-size: 14px; font-weight: bold; "
            "padding: 6px 12px; border-radius: 6px; border: 1px solid #475569; min-width: 80px; }"
        )
        c_inputs.addWidget(self.spin_start)

        lbl_to = QLabel(u"  至  结束号码：")
        lbl_to.setStyleSheet("font-size: 13px; color: #E2E8F0; border: none; background: transparent;")
        c_inputs.addWidget(lbl_to)

        self.spin_end = QSpinBox()
        self.spin_end.setRange(1, 9999)
        self.spin_end.setStyleSheet(
            "QSpinBox { background-color: #1E293B; color: #F8FAFC; font-size: 14px; font-weight: bold; "
            "padding: 6px 12px; border-radius: 6px; border: 1px solid #475569; min-width: 80px; }"
        )
        c_inputs.addWidget(self.spin_end)
        c_inputs.addStretch()

        cc_layout.addLayout(c_inputs)

        c_opts = QHBoxLayout()
        c_opts.setContentsMargins(0, 0, 0, 0)
        self.chk_custom_seq = QCheckBox(u"按顺序依次递增叫号 (未勾选则在指定范围内随机叫号)")
        self.chk_custom_seq.setStyleSheet("""
            QCheckBox { font-size: 13px; color: #94A3B8; border: none; background: transparent; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1.5px solid #64748B; background-color: #1E293B; }
            QCheckBox::indicator:hover { border-color: #F97316; }
            QCheckBox::indicator:checked { border: 1.5px solid #F97316; background-color: #EA580C; }
        """)
        c_opts.addWidget(self.chk_custom_seq)
        cc_layout.addLayout(c_opts)

        self.stack_mode.addWidget(card_custom)

        # ── 模式三：手动指定 ──
        card_manual = QFrame()
        card_manual.setStyleSheet("QFrame { background: #0F172A; border-radius: 10px; border: 1px solid #334155; }")
        cm_layout = QVBoxLayout(card_manual)
        cm_layout.setContentsMargins(16, 14, 16, 14)
        cm_layout.setSpacing(6)

        lbl_m_desc = QLabel(u"💡 机制说明：每次在收银台结账时，由收银员手动弹窗调整或指定本次餐牌号码。")
        lbl_m_desc.setStyleSheet("color: #94A3B8; font-size: 13px; border: none; background: transparent; line-height: 1.6;")
        cm_layout.addWidget(lbl_m_desc)

        self.stack_mode.addWidget(card_manual)

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
        sec2_lbl = QLabel(u"二、已用取餐号池")
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
            self.cmb_mode.setCurrentIndex(0)
        elif mode == CallNumberManager.MODE_CUSTOM:
            self.cmb_mode.setCurrentIndex(1)
        else:
            self.cmb_mode.setCurrentIndex(2)

        self.stack_mode.setCurrentIndex(self.cmb_mode.currentIndex())

        self.spin_start.setValue(self.config.get("custom_start_no", 50))
        self.spin_end.setValue(self.config.get("custom_end_no", 500))
        self.chk_custom_seq.setChecked(self.config.get("custom_is_seq", False))

    def _save_settings(self):
        idx = self.cmb_mode.currentIndex()
        if idx == 0:
            mode = CallNumberManager.MODE_SMART
        elif idx == 1:
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
