"""
自动切换算法设置页面 (Auto Switch Algorithm Settings)
包含：全自动分流参数调节、折线图，以及单屏分页算法日志
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QCheckBox, QFormLayout, QFrame, QMessageBox, QScrollArea, QGroupBox, QTextEdit,
    QComboBox,
    QStackedWidget,
    QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF, QDate
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QFont
from datetime import datetime
from config import save_config
from core.app_logger import log_event, CAT_SYSTEM, read_logs, CAT_DECISION, CAT_SWITCH, CAT_PANIC


class TouchSpinBox(QWidget):
    """触屏友好的数字加减控件 (整数)"""
    def __init__(self, value, min_val, max_val, step=1, suffix="", parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.suffix = suffix
        self._value = value
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        self.btn_minus = QPushButton(u"－")
        self.btn_minus.setFixedSize(40, 40)
        self.btn_minus.setCursor(Qt.PointingHandCursor)
        self.btn_minus.clicked.connect(self.decrement)
        
        self.lbl_val = QLabel()
        self.lbl_val.setAlignment(Qt.AlignCenter)
        self.lbl_val.setMinimumWidth(80)
        
        self.btn_plus = QPushButton(u"＋")
        self.btn_plus.setFixedSize(40, 40)
        self.btn_plus.setCursor(Qt.PointingHandCursor)
        self.btn_plus.clicked.connect(self.increment)
        
        layout.addWidget(self.btn_minus)
        layout.addWidget(self.lbl_val)
        layout.addWidget(self.btn_plus)
        layout.addStretch()
        
        self.update_display()
        self.setStyleSheet("""
            QPushButton {
                background-color: #334155; color: white;
                font-size: 20px; font-weight: bold; border-radius: 6px; border: none;
            }
            QPushButton:hover { background-color: #475569; }
            QPushButton:pressed { background-color: #64748B; }
            QLabel {
                background-color: #0F172A; color: #F8FAFC;
                font-size: 16px; font-weight: bold; border-radius: 6px;
                border: 1px solid #475569; padding: 4px;
            }
        """)

    def value(self):
        return self._value
        
    def setValue(self, val):
        if isinstance(self.step, float):
            self._value = round(max(self.min_val, min(self.max_val, val)), 3)
        else:
            self._value = max(self.min_val, min(self.max_val, val))
        self.update_display()
        
    def increment(self):
        self.setValue(self._value + self.step)
        
    def decrement(self):
        self.setValue(self._value - self.step)
        
    def update_display(self):
        self.lbl_val.setText(f"{self._value}{self.suffix}")


class TouchDoubleSpinBox(TouchSpinBox):
    """触屏友好的数字加减控件 (浮点数)"""
    def update_display(self):
        self.lbl_val.setText(f"{self._value:.2f}{self.suffix}")


class DecisionWeightChart(QWidget):
    """轻量级 Qt 绘图控件，显示今日每次称重的分流方向。

    不依赖 matplotlib 等额外库，避免 Win7 打包后缺少绘图库。每个
    通道分别绘制折线，节点标注本次稳定重量；横轴标签按可用宽度采样
    并旋转 45 度，避免触屏窄窗口下相互遮挡。
    """

    OFFICIAL_COLOR = QColor("#38BDF8")
    PRIVATE_COLOR = QColor("#22C55E")
    GRID_COLOR = QColor("#26364D")
    TEXT_COLOR = QColor("#CBD5E1")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.events = []
        self.setMinimumHeight(330)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background: transparent;")

    def set_events(self, events):
        self.events = list(events or [])
        # 每个时间节点预留固定触屏可读宽度。事件很多时由外层
        # QScrollArea 提供横向滚动，避免把时间标签压缩到不可读。
        self.setMinimumWidth(max(720, 110 + len(self.events) * 72))
        self.update()

    @staticmethod
    def _event_time(event):
        value = str(event.get("created_at") or event.get("ts") or "")
        value = value.strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except (TypeError, ValueError):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    return datetime.strptime(value[:26], fmt)
                except (TypeError, ValueError):
                    pass
        return None

    @staticmethod
    def _weight(event):
        try:
            return max(0.0, float(event.get("weight_kg") or 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _normalised_events(self):
        result = []
        for event in self.events:
            when = self._event_time(event)
            if when is None:
                continue
            channel = str(event.get("channel") or "official").lower()
            if channel not in ("private", "official"):
                channel = "official"
            result.append((when, self._weight(event), channel, event))
        return sorted(result, key=lambda item: item[0])

    def _draw_text(self, painter, x, y, text, color=None, font=None):
        if color is not None:
            painter.setPen(color)
        if font is not None:
            painter.setFont(font)
        painter.drawText(QPointF(float(x), float(y)), str(text))

    def paintEvent(self, event):  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor("#334155"), 1))
        painter.setBrush(QBrush(QColor("#0F172A")))
        painter.drawRoundedRect(outer, 10, 10)

        points = self._normalised_events()
        if not points:
            painter.setPen(self.TEXT_COLOR)
            painter.setFont(QFont("Microsoft YaHei", 13))
            painter.drawText(outer, Qt.AlignCenter, u"今日暂无称重决策记录")
            painter.end()
            return

        width = float(self.width())
        height = float(self.height())
        plot = QRectF(68, 48, max(120.0, width - 92), max(120.0, height - 112))
        max_weight = max(item[1] for item in points)
        y_max = max(1.0, max_weight)
        # Leave a little headroom above the largest point while keeping a
        # stable 0.1kg scale for small orders.
        y_max = max(0.1, ((y_max * 1.12) * 10.0 + 0.9999) // 1 / 10.0)
        start_day = points[0][0].replace(hour=0, minute=0, second=0, microsecond=0)
        end_day = start_day.replace(hour=23, minute=59, second=59, microsecond=999999)
        total_seconds = max(1.0, (end_day - start_day).total_seconds())

        title_font = QFont("Microsoft YaHei", 12)
        title_font.setBold(True)
        self._draw_text(painter, 16, 28, u"今日称重决策（重量 kg）", self.TEXT_COLOR, title_font)

        legend_font = QFont("Microsoft YaHei", 10)
        legend_x = max(210.0, width - 245.0)
        for color, label, offset in ((self.OFFICIAL_COLOR, u"官方", 0),
                                     (self.PRIVATE_COLOR, u"私有", 80)):
            painter.setPen(QPen(color, 3))
            painter.drawLine(QPointF(legend_x + offset, 22), QPointF(legend_x + offset + 22, 22))
            self._draw_text(painter, legend_x + offset + 28, 26, label, self.TEXT_COLOR, legend_font)

        painter.setFont(QFont("Microsoft YaHei", 9))
        painter.setPen(QPen(self.GRID_COLOR, 1))
        tick_count = 4
        for index in range(tick_count + 1):
            ratio = float(index) / tick_count
            y = plot.bottom() - ratio * plot.height()
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(self.TEXT_COLOR)
            label = "%.3f" % (y_max * ratio)
            painter.drawText(QRectF(5, y - 8, 57, 16), Qt.AlignRight | Qt.AlignVCenter, label)
            painter.setPen(QPen(self.GRID_COLOR, 1))

        painter.setPen(QPen(QColor("#64748B"), 1))
        painter.drawLine(QPointF(plot.left(), plot.top()), QPointF(plot.left(), plot.bottom()))
        painter.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))

        def point_for(when, weight):
            x = plot.left() + ((when - start_day).total_seconds() / total_seconds) * plot.width()
            y = plot.bottom() - (weight / y_max) * plot.height()
            return QPointF(x, y)

        # Draw one line per channel, so a channel's trend remains readable
        # even when the other channel is used for several consecutive orders.
        for channel, color in (("official", self.OFFICIAL_COLOR), ("private", self.PRIVATE_COLOR)):
            channel_points = [point_for(item[0], item[1]) for item in points if item[2] == channel]
            if len(channel_points) > 1:
                painter.setPen(QPen(color, 2.5))
                painter.drawPolyline(channel_points)

        # Also colour the chronological transitions.  This keeps a visible
        # line when today's data contains only one event per channel and makes
        # the actual decision sequence (official/private/official...) clear.
        for previous, current in zip(points, points[1:]):
            painter.setPen(QPen(
                self.PRIVATE_COLOR if current[2] == "private" else self.OFFICIAL_COLOR,
                2.5,
            ))
            painter.drawLine(point_for(previous[0], previous[1]), point_for(current[0], current[1]))

        value_font = QFont("Microsoft YaHei", 8)
        for index, (when, weight, channel, _event) in enumerate(points):
            color = self.PRIVATE_COLOR if channel == "private" else self.OFFICIAL_COLOR
            point = point_for(when, weight)
            painter.setPen(QPen(QColor("#0F172A"), 1))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(point, 4.5, 4.5)
            painter.setPen(color)
            value_y = point.y() - 8 if index % 2 == 0 else point.y() + 16
            painter.setFont(value_font)
            painter.drawText(QPointF(point.x() + 5, max(plot.top() + 10, min(plot.bottom() - 2, value_y))),
                             "%.3f" % weight)

        # Use actual event times, sampled to the available width.  Labels are
        # rotated after translation so they remain fully visible below the axis.
        max_labels = max(2, int(plot.width() / 74.0))
        label_count = min(len(points), max_labels)
        indexes = sorted(set(int(round(i * (len(points) - 1) / max(1, label_count - 1)))
                             for i in range(label_count)))
        axis_font = QFont("Microsoft YaHei", 8)
        painter.setFont(axis_font)
        for idx in indexes:
            when = points[idx][0]
            point = point_for(when, 0.0)
            label = when.strftime("%H:%M:%S")
            painter.save()
            painter.translate(point.x(), plot.bottom() + 13)
            painter.rotate(-45)
            painter.setPen(self.TEXT_COLOR)
            painter.drawText(QPointF(0, 0), label)
            painter.restore()

        painter.end()


class SwitchSettingsWidget(QWidget):

    # One page must fit on a touch POS screen.  Each entry may wrap to a
    # second line, so keep the page deliberately short and use the buttons
    # below for older/newer entries instead of an internal scrolling log.
    LOG_PAGE_SIZE = 8

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.filtered_algo_logs = []
        self.log_current_page = 1
        self.total_log_pages = 1
        self._date_filters = {}

        self._build_ui()
        self._load_config()
        
        # 定时刷新日志 (仅当页面可见时)
        self.log_timer = QTimer(self)
        self.log_timer.setInterval(2000)
        self.log_timer.timeout.connect(self._refresh_logs)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_logs()
        self.log_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.log_timer.stop()

    def _build_ui(self):
        # Use one page-level vertical scroll area.  The configuration form and
        # the trace panel are both allowed to use their natural height; the
        # operator scrolls the whole page instead of fighting nested scrollbars.
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.page_scroll = QScrollArea(self)
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setMinimumWidth(0)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.page_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                width: 14px; background: #0F172A; border-radius: 7px;
            }
            QScrollBar::handle:vertical {
                background: #475569; border-radius: 7px; min-height: 60px;
            }
        """)
        page_container = QWidget()
        page_container.setMinimumWidth(0)
        page_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        page_layout = QVBoxLayout(page_container)
        page_layout.setContentsMargins(16, 12, 16, 24)
        page_layout.setSpacing(18)

        # ==========================================
        # 左侧：配置项 (占 60% 宽度)
        # ==========================================
        left_panel = QWidget()
        left_panel.setMinimumWidth(0)
        left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 标题区
        lbl_title = QLabel(u"全自动分流算法设置")
        lbl_title.setStyleSheet("font-size: 26px; font-weight: 900; color: #F8FAFC;")
        left_layout.addWidget(lbl_title)

        # 配置表单不再使用内层滚动框；它完整展开，由页面级滚动条统一承载。
        left_panel.setStyleSheet("""
            QGroupBox {
                background-color: #1E293B; border-radius: 12px; border: 1px solid #334155;
                margin-top: 24px; padding-top: 24px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 4px 12px; color: #38BDF8; font-size: 16px; font-weight: bold;
                background-color: #0F172A; border-radius: 8px; border: 1px solid #334155;
            }
            QLabel {
                font-size: 15px; color: #E2E8F0; font-weight: bold; border: none; background: transparent;
            }
            QCheckBox {
                font-size: 15px; color: #F8FAFC; font-weight: bold;
            }
            QCheckBox::indicator {
                width: 24px; height: 24px;
            }
        """)

        form_container = QWidget()
        form_container.setMinimumWidth(0)
        form_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        form_vlayout = QVBoxLayout(form_container)
        form_vlayout.setContentsMargins(10, 10, 20, 20)
        form_vlayout.setSpacing(20)

        # --- 场景 1：总控与智能过滤 ---
        grp1 = QGroupBox(u"总控与智能过滤设置")
        lay1 = QFormLayout(grp1)
        lay1.setContentsMargins(20, 30, 20, 20)
        lay1.setSpacing(16)
        
        self.chk_enabled = QCheckBox(u"开启智能自动分流 (若关闭，则需要手动控制悬浮球)")
        lay1.addRow(QLabel(u"系统总控开关:"), self.chk_enabled)
        
        self.sp_ratio = TouchSpinBox(30, 0, 100, 5, " %")
        lay1.addRow(QLabel(u"目标私域重量占比:"), self.sp_ratio)

        lbl_ratio_tip = QLabel(u"算法按称重重量控制目标比例，不是按订单次数，也不是官方实际营业额。官方金额无法读取时，重量是最可靠的可观测代理。")
        lbl_ratio_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_ratio_tip.setWordWrap(True)
        lay1.addRow(QLabel(), lbl_ratio_tip)
        
        self.sp_weight = TouchDoubleSpinBox(0.25, 0.00, 5.00, 0.05, " kg")
        lay1.addRow(QLabel(u"轻量小单切回门限:"), self.sp_weight)
        
        lbl_w_tip = QLabel(u"场景说明：低于该重量的一律判定为小单/加菜，自动分配给官方收银机。")
        lbl_w_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_w_tip.setWordWrap(True)
        lay1.addRow(QLabel(), lbl_w_tip)

        self.sp_weekday_max_daily_limit = TouchDoubleSpinBox(500.0, 0.0, 999999.0, 100.0, " 元")
        lay1.addRow(QLabel(u"周中累计收款上限:"), self.sp_weekday_max_daily_limit)

        self.sp_weekend_max_daily_limit = TouchDoubleSpinBox(1000.0, 0.0, 999999.0, 100.0, " 元")
        lay1.addRow(QLabel(u"周末累计收款上限:"), self.sp_weekend_max_daily_limit)

        lbl_limit_tip = QLabel(u"场景说明：周中为周一至周五，周末为周六、周日。当天私域累计收款达到上限后，全自动停止切换为本POS，分配给官方收银；0 元表示不限制。")
        lbl_limit_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_limit_tip.setWordWrap(True)
        lay1.addRow(QLabel(), lbl_limit_tip)
        lay1.addRow(QLabel(), self._group_save_button(u"保存总控设置", self._save_control_group))
        form_vlayout.addWidget(grp1)

        # --- 场景 2：连续收银防打断 ---
        grp2 = QGroupBox(u"连续收银防打断保护")
        lay2 = QFormLayout(grp2)
        lay2.setContentsMargins(20, 30, 20, 20)
        lay2.setSpacing(16)
        
        self.sp_official_lock = TouchSpinBox(60, 0, 300, 5, " 秒")
        lay2.addRow(QLabel(u"官方界面连单保护:"), self.sp_official_lock)
        lbl_o_tip = QLabel(u"场景说明：一单刚分配给官方，此时间内就算来了大单也继续走官方，防止弹窗打断店员。")
        lbl_o_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_o_tip.setWordWrap(True)
        lay2.addRow(QLabel(), lbl_o_tip)

        self.sp_zeroing_unlock = TouchSpinBox(5, 1, 60, 1, " 秒")
        lay2.addRow(QLabel(u"称重归零离场解锁:"), self.sp_zeroing_unlock)
        lbl_z_tip = QLabel(u"场景说明：顾客端走碗，秤归零保持该时长后，自动解除上述连单保护，重新开始评判。")
        lbl_z_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_z_tip.setWordWrap(True)
        lay2.addRow(QLabel(), lbl_z_tip)

        self.sp_private_lock = TouchSpinBox(300, 10, 3600, 10, " 秒")
        lay2.addRow(QLabel(u"私域连单判定时长:"), self.sp_private_lock)
        lbl_p_tip = QLabel(u"场景说明：此时长内的新碗视为同一笔私域连单；超过后若购物车仍有商品，系统继续保留订单，不会自动清空。")
        lbl_p_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_p_tip.setWordWrap(True)
        lay2.addRow(QLabel(), lbl_p_tip)
        lay2.addRow(QLabel(), self._group_save_button(u"保存连续收银设置", self._save_continuity_group))
        form_vlayout.addWidget(grp2)

        # --- 场景 3：异常抖动与人工干预 ---
        grp3 = QGroupBox(u"秤具防抖与人工干预门限")
        lay3 = QFormLayout(grp3)
        lay3.setContentsMargins(20, 30, 20, 20)
        lay3.setSpacing(16)
        
        self.sp_min_valid_weight = TouchDoubleSpinBox(0.08, 0.01, 0.50, 0.01, " kg")
        lay3.addRow(QLabel(u"起漂过滤门限:"), self.sp_min_valid_weight)
        
        self.sp_stable_threshold = TouchDoubleSpinBox(0.01, 0.01, 0.05, 0.01, " kg")
        lay3.addRow(QLabel(u"稳定读数波动范围:"), self.sp_stable_threshold)
        try:
            stable_count = max(2, int(self.config.get("stable_count", 5) or 5))
        except (TypeError, ValueError):
            stable_count = 5
        lbl_stable_tip = QLabel(u"连续 %d 次读数的最大差值不超过此范围，才认定重量稳定。" % stable_count)
        lbl_stable_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_stable_tip.setWordWrap(True)
        lay3.addRow(QLabel(), lbl_stable_tip)
        
        self.sp_manual_override_lock = TouchSpinBox(30, 5, 120, 5, " 秒")
        lay3.addRow(QLabel(u"悬浮球手动强锁定:"), self.sp_manual_override_lock)
        lbl_m_tip = QLabel(u"场景说明：只要店员手点悬浮球切屏，该时长内算法绝对静默，100% 尊重人工。")
        lbl_m_tip.setStyleSheet("font-size: 13px; color: #64748B; font-weight: normal;")
        lbl_m_tip.setWordWrap(True)
        lay3.addRow(QLabel(), lbl_m_tip)
        lay3.addRow(QLabel(), self._group_save_button(u"保存秤具设置", self._save_scale_group))
        form_vlayout.addWidget(grp3)

        # --- 场景 4：订单收尾 ---
        grp4 = QGroupBox(u"结账收尾动作设置")
        lay4 = QFormLayout(grp4)
        lay4.setContentsMargins(20, 30, 20, 20)
        lay4.setSpacing(16)
        
        self.sp_delay = TouchSpinBox(10, 0, 30, 1, " 秒")
        lay4.addRow(QLabel(u"结账出票后隐退延时:"), self.sp_delay)
        lay4.addRow(QLabel(), self._group_save_button(u"保存收尾设置", self._save_finish_group))
        form_vlayout.addWidget(grp4)

        left_layout.addWidget(form_container)

        # 底部保存按钮
        self.btn_save = QPushButton(u"保存全部分流设置")
        self.btn_save.setFixedHeight(50)
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #0284C7; color: white;
                font-size: 16px; font-weight: bold; border-radius: 8px; border: none;
            }
            QPushButton:hover { background-color: #0369A1; }
            QPushButton:pressed { background-color: #075985; }
        """)
        self.btn_save.clicked.connect(self._on_save)
        left_layout.addWidget(self.btn_save)

        # ==========================================
        # 右侧：实时日志监控 (占 40% 宽度，带分页)
        # ==========================================
        right_panel = QWidget()
        right_panel.setMinimumWidth(0)
        # Keep a generous touch-friendly log viewport.  The previous 170-230px
        # cap made the real-time trace practically unreadable on POS screens.
        right_panel.setMinimumHeight(520)
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(10)

        lbl_log_title = QLabel(u"📡 算法实时追踪 (自动刷新)")
        lbl_log_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #38BDF8;")
        right_layout.addWidget(lbl_log_title)

        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.txt_logs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.txt_logs.setLineWrapMode(QTextEdit.WidgetWidth)
        self.txt_logs.setMinimumHeight(430)
        self.txt_logs.setStyleSheet("""
            QTextEdit {
                background-color: #0F172A; color: #F8FAFC; font-size: 13px; font-family: monospace;
                border: 1px solid #334155; border-radius: 8px; padding: 10px;
            }
        """)
        right_layout.addWidget(self.txt_logs, stretch=1)

        # ── 右侧底部分页控制栏 ──
        log_paging_bar = QHBoxLayout()
        log_paging_bar.setContentsMargins(0, 4, 0, 0)
        log_paging_bar.setSpacing(8)

        self.btn_log_prev = QPushButton(u"◀ 上一页")
        self.btn_log_prev.setMinimumHeight(46)
        self.btn_log_prev.setCursor(Qt.PointingHandCursor)
        self.btn_log_prev.setStyleSheet("""
            QPushButton {
                background-color: #1E293B; color: #F8FAFC; font-size: 13px; font-weight: bold;
                padding: 4px 14px; border-radius: 6px; border: 1px solid #334155;
            }
            QPushButton:hover { background-color: #334155; color: #38BDF8; border-color: #38BDF8; }
            QPushButton:disabled { background-color: #0F172A; color: #475569; border-color: #1E293B; }
        """)
        self.btn_log_prev.clicked.connect(self._prev_log_page)
        log_paging_bar.addWidget(self.btn_log_prev)

        self.lbl_log_page = QLabel(u"第 1 / 1 页 (共 0 条)")
        self.lbl_log_page.setAlignment(Qt.AlignCenter)
        self.lbl_log_page.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: bold;")
        log_paging_bar.addWidget(self.lbl_log_page, stretch=1)

        self.btn_log_next = QPushButton(u"下一页 ▶")
        self.btn_log_next.setMinimumHeight(46)
        self.btn_log_next.setCursor(Qt.PointingHandCursor)
        self.btn_log_next.setStyleSheet("""
            QPushButton {
                background-color: #1E293B; color: #F8FAFC; font-size: 13px; font-weight: bold;
                padding: 4px 14px; border-radius: 6px; border: 1px solid #334155;
            }
            QPushButton:hover { background-color: #334155; color: #38BDF8; border-color: #38BDF8; }
            QPushButton:disabled { background-color: #0F172A; color: #475569; border-color: #1E293B; }
        """)
        self.btn_log_next.clicked.connect(self._next_log_page)
        log_paging_bar.addWidget(self.btn_log_next)

        # 图表区域显示当天每次稳定称重的决策方向。图表使用数据库
        # 的 route-event 明细，而不是日志文本，避免日志截断后丢失节点。
        chart_title = QLabel(u"今日称重决策折线图")
        chart_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #38BDF8; margin-top: 12px;")
        right_layout.addWidget(chart_title)
        chart_tip = QLabel(u"蓝线：官方通道　绿线：私有通道；每个圆点旁标注本次稳定称重重量。")
        chart_tip.setWordWrap(True)
        chart_tip.setStyleSheet("font-size: 12px; color: #94A3B8; font-weight: normal;")
        right_layout.addWidget(chart_tip)
        self.weight_chart = DecisionWeightChart()
        self.chart_scroll = QScrollArea()
        self.chart_scroll.setWidgetResizable(True)
        self.chart_scroll.setMinimumHeight(350)
        self.chart_scroll.setFrameShape(QFrame.NoFrame)
        self.chart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.chart_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chart_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:horizontal {
                height: 14px; background: #0F172A; border-radius: 7px;
            }
            QScrollBar::handle:horizontal {
                background: #475569; border-radius: 7px; min-width: 60px;
            }
        """)
        self.chart_scroll.setWidget(self.weight_chart)
        right_layout.addWidget(self.chart_scroll)

        # 图表放在算法日志之前：操作员先看今日分流走势，再向下查看
        # 对应的逐条实时日志。此前图表追加在日志末尾，阅读顺序相反。
        for chart_widget in (chart_title, chart_tip, self.chart_scroll):
            right_layout.removeWidget(chart_widget)
        right_layout.insertWidget(0, chart_title)
        right_layout.insertWidget(1, chart_tip)
        right_layout.insertWidget(2, self.chart_scroll)

        # 切换算法页的二级目录，布局与系统设置保持一致：左侧固定
        # 导航栏，右侧为可纵向滚动的内容区。
        section_sidebar = QFrame()
        section_sidebar.setObjectName("SwitchSidebar")
        section_sidebar.setFixedWidth(220)
        section_sidebar.setStyleSheet("""
            QFrame#SwitchSidebar {
                background-color: #0F172A;
                border-right: 1px solid #1E293B;
            }
            QLabel { background: transparent; }
        """)
        sidebar_layout = QVBoxLayout(section_sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 18)
        sidebar_layout.setSpacing(8)

        sidebar_title = QLabel(u"⇄ 切换算法")
        sidebar_title.setStyleSheet(
            "font-size: 22px; font-weight: 900; color: #F8FAFC; "
            "padding-left: 8px; margin-bottom: 8px;"
        )
        sidebar_layout.addWidget(sidebar_title)

        self.section_buttons = []
        for section_id, label in (("settings", u"⚙ 算法设置"),
                                  ("chart", u"▥ 查看图表"),
                                  ("logs", u"≡ 查看日志")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setMinimumHeight(56)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet("""
                QPushButton {
                    text-align: left; padding: 12px 14px; font-size: 17px;
                    font-weight: 600; color: #94A3B8; background-color: transparent;
                    border-radius: 10px; border: none;
                }
                QPushButton:hover { color: #F1F5F9; background-color: #1E293B; }
                QPushButton:checked {
                    color: #38BDF8; background-color: #1E293B;
                    font-weight: bold; border-left: 4px solid #38BDF8;
                }
            """)
            button.clicked.connect(lambda checked=False, sid=section_id: self._select_switch_section(sid))
            sidebar_layout.addWidget(button)
            self.section_buttons.append((section_id, button))
        sidebar_layout.addStretch()

        # 将算法设置、图表、日志拆成真正独立的二级页面，避免三个区域
        # 在同一张长页面里同时展开。
        chart_panel = QWidget()
        chart_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(10, 0, 10, 20)
        chart_layout.setSpacing(10)
        self.chart_date_bar = self._build_date_filter("chart")
        chart_layout.addWidget(self.chart_date_bar)
        chart_layout.addWidget(chart_title)
        chart_layout.addWidget(chart_tip)
        chart_layout.addWidget(self.chart_scroll, stretch=1)

        logs_panel = QWidget()
        # 日志必须是单屏分页，不随设置页的超高 sizeHint 一起被撑开。
        logs_panel.setMinimumHeight(560)
        logs_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        logs_layout = QVBoxLayout(logs_panel)
        logs_layout.setContentsMargins(10, 0, 10, 20)
        logs_layout.setSpacing(10)
        self.logs_date_bar = self._build_date_filter("logs")
        logs_layout.addWidget(self.logs_date_bar)
        logs_title = QLabel(u"▣ 算法实时追踪（自动刷新）")
        logs_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #38BDF8;")
        logs_layout.addWidget(logs_title)
        logs_layout.addWidget(self.txt_logs, stretch=1)
        logs_layout.addLayout(log_paging_bar)

        # 上面控件先在临时布局中创建，这里移出后分别挂到两个独立页面。
        for widget in (chart_title, chart_tip, self.chart_scroll, lbl_log_title, self.txt_logs):
            right_layout.removeWidget(widget)
        # 不要延迟销毁这个临时容器。Win7 的旧版 PyQt5 在布局重挂载后
        # 仍可能持有其 C++ 子对象引用，deleteLater() 会在首次切页时
        # 造成“wrapped C/C++ object ... has been deleted”式闪退。
        self._legacy_right_panel = right_panel
        right_panel.hide()

        self.section_stack = QStackedWidget()
        self.section_stack.setStyleSheet("QStackedWidget { background: transparent; }")
        self.section_stack.addWidget(left_panel)
        self.section_stack.addWidget(chart_panel)
        self.section_stack.addWidget(logs_panel)
        self._section_page_heights = {
            "settings": max(1, left_panel.sizeHint().height()),
            "chart": max(1, chart_panel.sizeHint().height()),
            "logs": 560,
        }

        # 右侧内容区默认支持设置页纵向滚动；日志页会在切换时关闭
        # 页面滚动并固定为单屏，图表内部另有横向滚动条。
        page_layout.addWidget(self.section_stack)
        self.page_scroll.setWidget(page_container)
        root.addWidget(section_sidebar)
        root.addWidget(self.page_scroll, stretch=1)
        self._section_targets = {
            "settings": 0,
            "chart": 1,
            "logs": 2,
        }
        self._select_switch_section("settings", scroll=False)

    def _build_date_filter(self, key):
        """创建与订单查询相同风格的触屏年月日筛选栏。"""
        bar = QFrame()
        bar.setObjectName("SwitchDateFilter")
        bar.setStyleSheet(
            "QFrame#SwitchDateFilter { background: transparent; border: none; }"
            "QLabel { color: #94A3B8; font-size: 15px; font-weight: bold; border: none; }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(u"日期")
        layout.addWidget(label)

        combo_style = """
            QComboBox { background: #1F2937; color: #F9FAFB; font-size: 16px;
                        font-weight: bold; padding: 8px 12px; border: 1px solid #334155;
                        border-radius: 6px; min-height: 42px; }
            QComboBox QAbstractItemView { background: #1F2937; color: #F9FAFB;
                        selection-background-color: #0EA5E9; font-size: 18px; }
            QComboBox QAbstractItemView::item { min-height: 44px; }
        """
        year = QComboBox()
        month = QComboBox()
        day = QComboBox()
        for combo, width in ((year, 112), (month, 96), (day, 96)):
            combo.setStyleSheet(combo_style)
            combo.setMinimumWidth(width)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            combo.view().setTextElideMode(Qt.ElideNone)
            combo.view().setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            combo.view().setMinimumWidth(width + 16)
            try:
                from ui.styles import apply_touch_combo_style
                apply_touch_combo_style(combo, item_height=48)
            except Exception:
                pass

        current = QDate.currentDate()
        for value in range(2020, current.year() + 5):
            year.addItem(u"%d年" % value, value)
        for value in range(1, 13):
            month.addItem(u"%02d月" % value, value)
        year.setCurrentText(u"%d年" % current.year())
        month.setCurrentText(u"%02d月" % current.month())
        self._date_filters[key] = {"year": year, "month": month, "day": day}
        self._update_filter_days(key)
        day.setCurrentText(u"%02d日" % current.day())

        year.currentIndexChanged.connect(lambda _index, k=key: self._on_filter_year_month_changed(k))
        month.currentIndexChanged.connect(lambda _index, k=key: self._on_filter_year_month_changed(k))
        day.currentIndexChanged.connect(lambda _index, k=key: self._on_filter_date_changed(k))
        layout.addWidget(year)
        layout.addWidget(month)
        layout.addWidget(day)

        quick_style = (
            "QPushButton { background: #374151; color: white; font-weight: bold; "
            "font-size: 14px; padding: 8px 14px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #475569; }"
        )
        today = QPushButton(u"今天")
        yesterday = QPushButton(u"昨天")
        for button in (today, yesterday):
            button.setMinimumHeight(42)
            button.setStyleSheet(quick_style)
        today.clicked.connect(lambda _checked=False, k=key: self._set_filter_date(k, 0))
        yesterday.clicked.connect(lambda _checked=False, k=key: self._set_filter_date(k, -1))
        layout.addWidget(today)
        layout.addWidget(yesterday)
        layout.addStretch()
        return bar

    def _update_filter_days(self, key):
        fields = self._date_filters.get(key)
        if not fields:
            return
        year = fields["year"].currentData()
        month = fields["month"].currentData()
        day = fields["day"]
        if not year or not month:
            return
        old_day = int(day.currentData() or 1)
        days = QDate(int(year), int(month), 1).daysInMonth()
        day.blockSignals(True)
        day.clear()
        for value in range(1, days + 1):
            day.addItem(u"%02d日" % value, value)
        day.setCurrentText(u"%02d日" % min(old_day, days))
        day.blockSignals(False)

    def _selected_filter_date(self, key):
        fields = self._date_filters.get(key, {})
        year = fields.get("year")
        month = fields.get("month")
        day = fields.get("day")
        if not year or not month or not day:
            return QDate.currentDate().toString("yyyy-MM-dd")
        return "%04d-%02d-%02d" % (
            int(year.currentData() or QDate.currentDate().year()),
            int(month.currentData() or QDate.currentDate().month()),
            int(day.currentData() or QDate.currentDate().day()),
        )

    def _on_filter_year_month_changed(self, key):
        self._update_filter_days(key)
        self._on_filter_date_changed(key)

    def _on_filter_date_changed(self, key):
        if key == "logs":
            self.log_current_page = 1
            self._refresh_logs()
        elif key == "chart":
            self._refresh_weight_chart()

    def _set_filter_date(self, key, days_offset):
        fields = self._date_filters.get(key)
        if not fields:
            return
        target = QDate.currentDate().addDays(days_offset)
        for combo in fields.values():
            combo.blockSignals(True)
        fields["year"].setCurrentText(u"%d年" % target.year())
        fields["month"].setCurrentText(u"%02d月" % target.month())
        self._update_filter_days(key)
        fields["day"].setCurrentText(u"%02d日" % target.day())
        for combo in fields.values():
            combo.blockSignals(False)
        self._on_filter_date_changed(key)

    def _refresh_logs(self):
        """拉取日志，仅筛选 决策、切换、避险"""
        all_logs = read_logs(limit=2000)
        selected_date = self._selected_filter_date("logs")
        self.filtered_algo_logs = [
            entry for entry in all_logs
            if entry.get("cat") in (CAT_DECISION, CAT_SWITCH, CAT_PANIC)
            and str(entry.get("ts", "")).startswith(selected_date)
        ]
        self._render_log_page()
        self._refresh_weight_chart()

    def _refresh_weight_chart(self):
        """刷新今日称重图；数据库不可用时保留空态，不阻断设置页。"""
        parent_mw = self.window()
        db = getattr(parent_mw, "db", None)
        if db is None or not hasattr(db, "get_weighing_route_events"):
            self.weight_chart.set_events([])
            return
        selected_date = self._selected_filter_date("chart")
        try:
            events = db.get_weighing_route_events(selected_date)
        except Exception as exc:
            log_event(CAT_SYSTEM, "称重决策图表读取失败", str(exc))
            events = []
        self.weight_chart.set_events(events)

    def focus_weight_chart(self):
        """将页面滚动到折线图，供悬浮球顶部剩余重量入口调用。"""
        self._refresh_logs()
        self._select_switch_section("chart")
        # 页面布局可能在本轮刷新后才完成尺寸计算，再确保一次位置。
        QTimer.singleShot(0, lambda: self._select_switch_section("chart"))

    def _select_switch_section(self, section_id, scroll=True):
        """选择切换算法二级目录，并定位到对应区域。"""
        if section_id not in getattr(self, "_section_targets", {}):
            return
        for current_id, button in getattr(self, "section_buttons", []):
            button.setChecked(current_id == section_id)
        self.section_stack.setCurrentIndex(self._section_targets[section_id])
        # QStackedWidget normally keeps the largest page's height (the
        # settings form), which would leave a huge blank area below the log
        # page.  Resize it to the selected page so the log page is genuinely
        # one screen with its pagination bar visible.
        if section_id == "logs":
            # The log page has pagination, so it must never require a second
            # vertical scroll.  Fill the viewport when it is taller than the
            # minimum content height, while keeping the controls visible.
            viewport_height = self.page_scroll.viewport().height()
            page_height = max(560, int(viewport_height or 0))
            self.page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            self.page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            page_height = getattr(self, "_section_page_heights", {}).get(section_id)
            if section_id == "chart":
                page_height = max(int(page_height or 0), int(self.page_scroll.viewport().height() or 0))
        if page_height:
            self.section_stack.setFixedHeight(page_height)
        if scroll:
            self.page_scroll.verticalScrollBar().setValue(0)

    def _render_log_page(self):
        """仅渲染当前页面的少量算法日志，保证单屏可读并避免卡顿"""
        total = len(self.filtered_algo_logs)
        self.total_log_pages = max(1, (total + self.LOG_PAGE_SIZE - 1) // self.LOG_PAGE_SIZE)

        if self.log_current_page > self.total_log_pages:
            self.log_current_page = self.total_log_pages
        if self.log_current_page < 1:
            self.log_current_page = 1

        if not self.filtered_algo_logs:
            self.txt_logs.setHtml("<div style='color: #475569; text-align: center; margin-top: 40px; font-weight: bold;'>暂无算法追踪日志</div>")
            self.lbl_log_page.setText("第 0 / 0 页")
            self.btn_log_prev.setEnabled(False)
            self.btn_log_next.setEnabled(False)
            return

        start_idx = (self.log_current_page - 1) * self.LOG_PAGE_SIZE
        end_idx = min(start_idx + self.LOG_PAGE_SIZE, total)
        page_entries = self.filtered_algo_logs[start_idx:end_idx]

        html = ""
        for entry in page_entries:
            cat = entry.get("cat")
            msg = entry.get("msg", "")
            detail = entry.get("detail", "")
            ts = entry.get("ts", "")[-8:] # 只取时间部分 HH:MM:SS

            color = "#94A3B8"
            if cat == CAT_DECISION: color = "#A855F7"
            elif cat == CAT_SWITCH: color = "#FF781F"
            elif cat == CAT_PANIC: color = "#EF4444"

            html += f"<div style='margin-bottom: 8px; border-bottom: 1px dashed #1E293B; padding-bottom: 6px;'>"
            html += f"<span style='color: #475569;'>[{ts}]</span> "
            html += f"<b style='color: {color};'>[{cat}]</b> "
            html += f"<span style='color: #E2E8F0;'>{msg}</span><br>"
            if detail:
                html += f"<span style='color: #94A3B8; font-size: 12px;'> - {detail}</span>"
            html += f"</div>"

        self.txt_logs.setHtml(html)
        self.lbl_log_page.setText(f"第 {self.log_current_page} / {self.total_log_pages} 页 · 共 {total} 条")

        self.btn_log_prev.setEnabled(self.log_current_page > 1)
        self.btn_log_next.setEnabled(self.log_current_page < self.total_log_pages)

    def _prev_log_page(self):
        if self.log_current_page > 1:
            self.log_current_page -= 1
            self._render_log_page()

    def _next_log_page(self):
        if self.log_current_page < self.total_log_pages:
            self.log_current_page += 1
            self._render_log_page()

    def _group_save_button(self, text, slot):
        """创建触屏友好的分组保存按钮，避免用户必须滚到底部才会生效。"""
        button = QPushButton(text)
        button.setMinimumHeight(44)
        button.setMinimumWidth(170)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet("""
            QPushButton {
                background-color: #0EA5E9; color: white; font-size: 15px;
                font-weight: bold; border-radius: 8px; padding: 8px 18px;
            }
            QPushButton:hover { background-color: #0284C7; }
            QPushButton:pressed { background-color: #0369A1; }
        """)
        button.clicked.connect(slot)
        return button

    def _load_config(self):
        self.chk_enabled.setChecked(self.config.get("auto_switch_enabled", True))
        self.sp_ratio.setValue(int(self.config.get("private_ratio_percent", 30)))
        self.sp_weight.setValue(float(self.config.get("min_private_weight_kg", 0.25)))
        legacy_limit = float(self.config.get("max_daily_revenue_limit", 500.0) or 500.0)
        self.sp_weekday_max_daily_limit.setValue(float(self.config.get("weekday_max_daily_revenue_limit", legacy_limit)))
        weekend_default = legacy_limit if "max_daily_revenue_limit" in self.config else 1000.0
        self.sp_weekend_max_daily_limit.setValue(float(self.config.get("weekend_max_daily_revenue_limit", weekend_default)))
        self.sp_min_valid_weight.setValue(float(self.config.get("min_valid_weight_kg", 0.08)))
        self.sp_stable_threshold.setValue(float(self.config.get("stable_threshold", 0.01)))
        
        self.sp_official_lock.setValue(int(self.config.get("official_lock_sec", 60)))
        self.sp_zeroing_unlock.setValue(int(self.config.get("zeroing_unlock_sec", 5)))
        self.sp_private_lock.setValue(int(self.config.get("private_lock_sec", 300)))
        self.sp_manual_override_lock.setValue(int(self.config.get("manual_override_lock_sec", 30)))
        self.sp_delay.setValue(int(self.config.get("auto_hide_delay_sec", 10)))

    def _refresh_runtime(self, title, restart_scale=False):
        """持久化当前配置，并让运行中的控制器/称重线程及时读取新值。"""
        save_config(self.config)
        parent_mw = self.window()
        if hasattr(parent_mw, "switch_controller") and parent_mw.switch_controller:
            parent_mw.switch_controller.update_config(self.config)
            parent_mw.switch_controller._update_floating_ball_status(
                is_private=getattr(parent_mw.switch_controller, "_current_is_private", False),
                reason=title,
            )
        if restart_scale and hasattr(parent_mw, "sale_page") and parent_mw.sale_page:
            if not parent_mw.sale_page.restart_scale():
                QMessageBox.warning(
                    self, u"称重读取器尚未重启",
                    u"设置已保存，但旧称重线程未能安全退出。请退出并重新打开本 POS 后生效。",
                )
                return False
        log_event(CAT_SYSTEM, title, "分组设置已保存")
        QMessageBox.information(self, u"保存成功", title + u"，已立即生效。")
        self._refresh_logs()
        return True

    def _save_control_group(self):
        self.config["auto_switch_enabled"] = self.chk_enabled.isChecked()
        self.config["private_ratio_percent"] = self.sp_ratio.value()
        self.config["min_private_weight_kg"] = self.sp_weight.value()
        self.config["weekday_max_daily_revenue_limit"] = self.sp_weekday_max_daily_limit.value()
        self.config["weekend_max_daily_revenue_limit"] = self.sp_weekend_max_daily_limit.value()
        # 供旧版组件读取的兼容值，以周中上限为准。
        self.config["max_daily_revenue_limit"] = self.sp_weekday_max_daily_limit.value()
        self._refresh_runtime(u"总控与智能过滤设置")

    def _save_continuity_group(self):
        self.config["official_lock_sec"] = self.sp_official_lock.value()
        self.config["zeroing_unlock_sec"] = self.sp_zeroing_unlock.value()
        self.config["private_lock_sec"] = self.sp_private_lock.value()
        self._refresh_runtime(u"连续收银防打断设置")

    def _save_scale_group(self):
        self.config["min_valid_weight_kg"] = self.sp_min_valid_weight.value()
        self.config["stable_threshold"] = self.sp_stable_threshold.value()
        self.config["manual_override_lock_sec"] = self.sp_manual_override_lock.value()
        self._refresh_runtime(u"秤具防抖与人工干预设置", restart_scale=True)

    def _save_finish_group(self):
        self.config["auto_hide_delay_sec"] = self.sp_delay.value()
        self._refresh_runtime(u"结账收尾动作设置")

    def _on_save(self):
        """保留页面底部的“保存全部”入口，兼容旧操作习惯。"""
        self.config["auto_switch_enabled"] = self.chk_enabled.isChecked()
        self.config["private_ratio_percent"] = self.sp_ratio.value()
        self.config["min_private_weight_kg"] = self.sp_weight.value()
        self.config["weekday_max_daily_revenue_limit"] = self.sp_weekday_max_daily_limit.value()
        self.config["weekend_max_daily_revenue_limit"] = self.sp_weekend_max_daily_limit.value()
        self.config["max_daily_revenue_limit"] = self.sp_weekday_max_daily_limit.value()
        self.config["min_valid_weight_kg"] = self.sp_min_valid_weight.value()
        self.config["stable_threshold"] = self.sp_stable_threshold.value()
        self.config["official_lock_sec"] = self.sp_official_lock.value()
        self.config["zeroing_unlock_sec"] = self.sp_zeroing_unlock.value()
        self.config["private_lock_sec"] = self.sp_private_lock.value()
        self.config["manual_override_lock_sec"] = self.sp_manual_override_lock.value()
        self.config["auto_hide_delay_sec"] = self.sp_delay.value()
        self._refresh_runtime(u"全部分流算法设置", restart_scale=True)
