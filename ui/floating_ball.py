"""
纯触屏高颜值胶囊型悬浮球 (Capsule Floating Toggle Badge)
采用 iOS 灵动岛 / 微信悬浮窗流线型胶囊设计：
- 宽度 88px, 高度 50px，圆角 25px
- 彻底解决圆球顶部/底部文字溢出问题
- 单触 (Single Tap): 极速切换 官方系统 ↔ 私域 POS
- 连触 3 下 (Triple Tap): 0.01秒防督导紧急销毁
"""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QPoint, QRect, QTimer
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont, QLinearGradient

from utils.window_utils import bring_official_to_front, bring_our_pos_to_front
from utils.panic_handler import execute_panic_exit


class FloatingBall(QWidget):
    """纯触屏高颜值胶囊悬浮徽章"""

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

        # 88x50 黄金比例胶囊尺寸 (彻底消除文字溢出)
        self.setFixedSize(88, 50)

        # 移动到屏幕右上角默认位置
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 110, 110)

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

        # 1. 渐变背景与微光边框
        if self._is_long_press_progress or self._tap_count >= 2:
            bg_color1 = QColor(239, 68, 68, 245)   # 红色警报避险
            bg_color2 = QColor(185, 28, 28, 245)
            border_color = QColor(254, 202, 202)
        elif self._tap_count == 1:
            bg_color1 = QColor(249, 115, 22, 240)  # 橙色连击提示
            bg_color2 = QColor(194, 65, 12, 240)
            border_color = QColor(253, 186, 116)
        elif self.is_our_pos_active:
            bg_color1 = QColor(16, 185, 129, 230)  # 翡翠绿 (私域 POS)
            bg_color2 = QColor(5, 150, 105, 230)
            border_color = QColor(110, 231, 183)
        else:
            bg_color1 = QColor(37, 99, 235, 230)   # 宝蓝色 (官方系统)
            bg_color2 = QColor(29, 78, 216, 230)
            border_color = QColor(147, 197, 253)

        grad = QLinearGradient(0, 0, 0, 50)
        grad.setColorAt(0.0, bg_color1)
        grad.setColorAt(1.0, bg_color2)

        # 绘制流线型胶囊圆角矩形 (r=24)
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(border_color, 1.5))
        painter.drawRoundedRect(1, 1, 86, 48, 24, 24)

        # 2. 精致两行居中文字 (宽度 88 充足，绝不溢出)
        title_text = u"私域 POS" if self.is_our_pos_active else u"官方系统"
        font_title = QFont("Microsoft YaHei", 9, QFont.Bold)
        painter.setFont(font_title)
        painter.setPen(QColor(255, 255, 255))
        rect_title = QRect(0, 5, 88, 20)
        painter.drawText(rect_title, Qt.AlignCenter, title_text)

        # 副标题 (防督导提示与倒数)
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
            sub_text = u"快点3下销毁"
            sub_color = QColor(229, 231, 235, 220)

        font_sub = QFont("Microsoft YaHei", 8, QFont.Bold if self._tap_count > 0 else QFont.Normal)
        painter.setFont(font_sub)
        painter.setPen(sub_color)
        rect_sub = QRect(0, 25, 88, 18)
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
