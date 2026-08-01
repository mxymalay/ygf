"""
纯触屏优化版 - 桌面常驻半透明悬浮球组件 (Touch-Friendly Floating Toggle Ball)
针对专用于纯触摸屏收银机设计：
- 精密 Paint 渐变排版，极致高颜值
- 单触 (Single Tap): 0.1秒极速切换 官方系统 ↔ 私域 POS
- 连触 3 下 (Triple Tap): 实时倒数提示，0.01秒触发防督导紧急销毁
- 长触 (Long Press 1.2s): 0.01秒触发防督导紧急销毁
- 拖拽 (Touch Drag): 任意指尖顺滑拖拽悬浮球
"""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QPoint, QRect, QTimer
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont, QLinearGradient

from utils.window_utils import bring_official_to_front, bring_our_pos_to_front
from utils.panic_handler import execute_panic_exit


class FloatingBall(QWidget):
    """纯触屏高颜值悬浮球 — 精密绘制防督导按钮"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.is_our_pos_active = True

        # 设置无边框、置顶、不在任务栏生成独立按钮
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.Tool | 
            Qt.SubWindow
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # 固定 68x68 黄金尺寸
        self.setFixedSize(68, 68)

        # 移动到屏幕右上角默认位置
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 90, 110)

        self._drag_pos = QPoint()
        self._is_dragging = False

        # 长按 (1.2秒) 触发避险
        self._long_press_timer = QTimer(self)
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.timeout.connect(self._on_long_press_panic)

        # 多次连续触碰计数 (三连击避险)
        self._tap_count = 0
        self._tap_reset_timer = QTimer(self)
        self._tap_reset_timer.setSingleShot(True)
        self._tap_reset_timer.timeout.connect(self._reset_tap_count)

        self._is_long_press_progress = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # 1. 渐变背景与边框选择
        if self._is_long_press_progress or self._tap_count >= 2:
            bg_color1 = QColor(239, 68, 68)   # 红色紧急防督导避险状态
            bg_color2 = QColor(185, 28, 28)
            border_color = QColor(254, 202, 202)
        elif self._tap_count == 1:
            bg_color1 = QColor(249, 115, 22)  # 橙色连击提示状态
            bg_color2 = QColor(194, 65, 12)
            border_color = QColor(253, 186, 116)
        elif self.is_our_pos_active:
            bg_color1 = QColor(16, 185, 129)  # 翡翠绿 (私域 POS)
            bg_color2 = QColor(5, 150, 105)
            border_color = QColor(110, 231, 183)
        else:
            bg_color1 = QColor(59, 130, 246)  # 宝蓝色 (官方系统)
            bg_color2 = QColor(29, 78, 216)
            border_color = QColor(147, 197, 253)

        grad = QLinearGradient(0, 0, 0, 68)
        grad.setColorAt(0.0, bg_color1)
        grad.setColorAt(1.0, bg_color2)

        # 绘制背景底圈
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(border_color, 2))
        painter.drawEllipse(2, 2, 64, 64)

        # 2. 精密排版绘制文字
        # 标题 (私域 POS / 官方系统)
        title_text = u"私域 POS" if self.is_our_pos_active else u"官方系统"
        font_title = QFont("Microsoft YaHei", 9, QFont.Bold)
        painter.setFont(font_title)
        painter.setPen(QColor(255, 255, 255))
        rect_title = QRect(0, 10, 68, 20)
        painter.drawText(rect_title, Qt.AlignCenter, title_text)

        # 中间精致半透明分割线
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
        painter.drawLine(14, 33, 54, 33)

        # 副标题 (防督导手势指引与实时连击倒数)
        if self._tap_count == 1:
            sub_text = u"再点2次销毁"
            sub_color = QColor(254, 240, 138)
        elif self._tap_count == 2:
            sub_text = u"再点1次销毁!"
            sub_color = QColor(254, 202, 202)
        elif self._tap_count >= 3:
            sub_text = u"销毁退出中"
            sub_color = QColor(255, 255, 255)
        else:
            sub_text = u"三连击销毁"
            sub_color = QColor(229, 231, 235)

        font_sub = QFont("Microsoft YaHei", 8, QFont.Bold if self._tap_count > 0 else QFont.Normal)
        painter.setFont(font_sub)
        painter.setPen(sub_color)
        rect_sub = QRect(0, 36, 68, 20)
        painter.drawText(rect_sub, Qt.AlignCenter, sub_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self._is_dragging = False

            # 启动长按定时器 (1.2秒未松开则触发紧急销毁)
            self._is_long_press_progress = False
            self._long_press_timer.start(1200)

            # 记录连击数
            self._tap_count += 1
            if self._tap_count >= 3:
                self.update()
                print("[FloatingBall] 触发触屏三连击，0.01秒防督导紧急销毁程序！")
                execute_panic_exit()
                return

            self.update()
            self._tap_reset_timer.start(600)
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if (event.globalPos() - self._drag_pos - self.pos()).manhattanLength() > 6:
                self._is_dragging = True
                self._long_press_timer.stop()
                self._is_long_press_progress = False
                self.update()

            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._long_press_timer.stop()

            if self._is_long_press_progress:
                self._is_long_press_progress = False
                self.update()
                return

            if not self._is_dragging and self._tap_count < 3:
                self._on_click_toggle()

            self._is_dragging = False
            self._is_long_press_progress = False
            self.update()
            event.accept()

    def _on_long_press_panic(self):
        """长按 1.2 秒触屏紧急销毁避险"""
        self._is_long_press_progress = True
        self.update()
        print("[FloatingBall] 触发触屏长按 1.2 秒，紧急销毁避险！")
        execute_panic_exit()

    def _reset_tap_count(self):
        self._tap_count = 0
        self.update()

    def _on_click_toggle(self):
        """手指轻点：快速在官方界面与私域 POS 之间切换"""
        if self.is_our_pos_active:
            success = bring_official_to_front()
            if not success and self.main_window:
                self.main_window.showMinimized()
            self.is_our_pos_active = False
            self.update()
        else:
            bring_our_pos_to_front(self.main_window)
            self.is_our_pos_active = True
            self.update()
