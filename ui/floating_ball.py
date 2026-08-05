"""
纯触屏高颜值胶囊型悬浮球 (Capsule Floating Toggle Badge)
采用 iOS 灵动岛 / 微信悬浮窗流线型胶囊设计：
- 双层高科技玻璃倒角边框 (Double Bevel Glass Border)
- 边框嵌入式 LED 呼吸指示灯 (Embedded LED Status Dot)
- 边框隐退倒计时动态进度条 (Dynamic Countdown Border Stroke)
- 单触 (Single Tap): 极速切换 官方系统 ↔ 私域 POS
- 连触 3 下 / 长按 1.2 秒: 0.01秒防督导紧急销毁
"""
import time
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QPoint, QRect, QTimer
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont, QLinearGradient, QPainterPath

from utils.window_utils import (
    bring_official_to_front,
    bring_our_pos_to_front,
    is_official_pos_available,
)
from utils.panic_handler import execute_panic_exit


class FloatingBall(QWidget):
    """纯触屏高颜值胶囊悬浮徽章 — 科技感动态边框版"""

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

        # 88x68 黄金比例胶囊尺寸 (底部预留18px显示状态图标)
        self.setFixedSize(88, 68)

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

        # 边框出票隐退倒计时动效
        self._countdown_active = False
        self._countdown_ratio = 1.0
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(40)  # 25 fps 顺滑刷新
        self._countdown_timer.timeout.connect(self._on_countdown_tick)
        self._countdown_total_ms = 3000.0
        self._countdown_start_time = 0.0

        # 定时刷新界面以确保暂停图标能按时消失 (1Hz)
        self._state_refresh_timer = QTimer(self)
        self._state_refresh_timer.timeout.connect(self.update)
        self._state_refresh_timer.start(1000)

        # 决策通过的对钩指示符
        self._show_checkmark = False
        self._checkmark_timer = QTimer(self)
        self._checkmark_timer.setSingleShot(True)
        self._checkmark_timer.timeout.connect(self._hide_checkmark)

    def show_decision_checkmark(self):
        """显示右下角的决策对钩，1.5秒后消失"""
        self._show_checkmark = True
        self.update()
        self._checkmark_timer.start(1500)

    def _hide_checkmark(self):
        self._show_checkmark = False
        self.update()

    def start_countdown(self, seconds: float):
        """出票后启动边框隐退倒计时动效"""
        self._countdown_active = True
        self._countdown_total_ms = seconds * 1000.0
        self._countdown_start_time = time.time()
        self._countdown_ratio = 1.0
        self._countdown_timer.start()
        self.update()

    def stop_countdown(self):
        """停止倒计时动效"""
        self._countdown_active = False
        self._countdown_timer.stop()
        self.update()

    def _on_countdown_tick(self):
        elapsed_ms = (time.time() - self._countdown_start_time) * 1000.0
        remaining_ratio = max(0.0, 1.0 - (elapsed_ms / self._countdown_total_ms))
        self._countdown_ratio = remaining_ratio
        if remaining_ratio <= 0.0:
            self.stop_countdown()
        else:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # 1. 颜色风格与边框主题
        if self.is_our_pos_active:
            bg_color1 = QColor(16, 185, 129, 235)   # 翡翠绿 (私域 POS)
            bg_color2 = QColor(5, 150, 105, 235)
            border_outer = QColor(52, 211, 153)     # 亮高光绿外框
            led_color = QColor(52, 211, 153)
        else:
            bg_color1 = QColor(37, 99, 235, 235)    # 宝蓝色 (官方系统)
            bg_color2 = QColor(29, 78, 216, 235)
            border_outer = QColor(147, 197, 253)    # 浅亮蓝外框
            led_color = QColor(96, 165, 250)

        # 渐变底色
        grad = QLinearGradient(0, 0, 0, 50)
        grad.setColorAt(0.0, bg_color1)
        grad.setColorAt(1.0, bg_color2)

        # 2. 绘制主胶囊背景与外边框 (r=24)
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(border_outer, 2.0))
        painter.drawRoundedRect(1, 1, 86, 48, 24, 24)

        # 3. 绘制内侧微高光倒角线 (3D 玻璃质感)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 70), 1.0))
        painter.drawRoundedRect(3, 3, 82, 44, 22, 22)

        # 4. 如果处在【出票倒计时隐退】状态，在边框上绘制动态倒计时进度弧/线条
        if self._countdown_active and self._countdown_ratio > 0:
            progress_pen = QPen(QColor(254, 240, 138), 3.0)  # 亮黄色倒计时进度线
            progress_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(progress_pen)
            
            # 在顶部边框沿线绘制进度条 (从左到右缩短)
            bar_width = int(80 * self._countdown_ratio)
            if bar_width > 4:
                painter.drawLine(4, 2, 4 + bar_width, 2)

        # 5. 边框嵌入式 LED 呼吸指示灯 (位于文字前方垂直居中)
        painter.setBrush(QBrush(led_color))
        painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
        # 文字居中，胶囊高 50。圆点大小 6x6，所以 y=22 刚好垂直居中 (22+3=25)
        led_x = 22 if self.is_our_pos_active else 12
        painter.drawEllipse(led_x, 22, 6, 6)

        # 6. 两行居中文字排版
        title_text = u"私域" if self.is_our_pos_active else u"官方系统"
        font_title = QFont("Microsoft YaHei", 9, QFont.Bold)
        painter.setFont(font_title)
        painter.setPen(QColor(255, 255, 255))
        rect_title = QRect(6, 5, 82, 40) # 扩大标题矩形，使其完全居中
        painter.drawText(rect_title, Qt.AlignCenter, title_text)

        # 7. 悬浮球下方独立状态指示栏 (小灵动岛，不与主胶囊重叠)
        is_paused = False
        is_locked = False
        now_ts = time.time()
        
        if hasattr(self.main_window, 'switch_controller') and self.main_window.switch_controller:
            sc = self.main_window.switch_controller
            is_paused = (not sc._auto_switch_enabled) or (now_ts < sc._manual_override_until)
            
            if not is_paused:
                if sc._last_official_time > 0 and (now_ts - sc._last_official_time < sc._official_lock_sec):
                    is_locked = True
                elif hasattr(self.main_window, 'sale_page') and self.main_window.sale_page:
                    cart_items = getattr(self.main_window.sale_page, 'cart_items', [])
                    if cart_items and (now_ts - sc._last_private_time < sc._private_lock_sec):
                        is_locked = True

        active_icons = []
        if is_paused:
            active_icons.append("PAUSE")
        if is_locked:
            active_icons.append("LOCK")
        if self._show_checkmark:
            active_icons.append("CHECK")
            
        if active_icons:
            # 绘制底部的半透明黑色小胶囊背景 (动态宽度)
            num_icons = len(active_icons)
            bg_width = num_icons * 20 + 8
            bg_x = 44 - bg_width // 2
            painter.setBrush(QColor(0, 0, 0, 140))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bg_x, 51, bg_width, 16, 8, 8)
            
            # 逐个绘制图标
            icon_x = bg_x + 4 + 10  # 10 is the center offset of the first icon
            for icon in active_icons:
                if icon == "PAUSE":
                    painter.setPen(QPen(QColor(255, 255, 255), 2.0, Qt.SolidLine, Qt.RoundCap))
                    painter.drawLine(icon_x - 2, 55, icon_x - 2, 63)
                    painter.drawLine(icon_x + 2, 55, icon_x + 2, 63)
                elif icon == "LOCK":
                    painter.setPen(QPen(QColor(255, 255, 255), 1.5, Qt.SolidLine, Qt.RoundCap))
                    painter.setBrush(QColor(255, 255, 255))
                    painter.drawRect(icon_x - 3, 59, 6, 4)
                    painter.setBrush(Qt.NoBrush)
                    painter.drawArc(icon_x - 2, 55, 4, 6, 0, 180 * 16)
                elif icon == "CHECK":
                    painter.setPen(QPen(QColor(253, 224, 71), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    path = QPainterPath()
                    path.moveTo(icon_x - 4, 59)
                    path.lineTo(icon_x - 1, 62)
                    path.lineTo(icon_x + 4, 55)
                    painter.drawPath(path)
                
                icon_x += 20

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self._is_dragging = False

            # 启动长按定时器 (1.2秒未松开则触发紧急销毁)
            self._long_press_timer.start(1200)

            # 记录连击数
            self._tap_count += 1
            if self._tap_count >= 3:
                print("[FloatingBall] 触发触屏三连击，0.01秒防督导紧急销毁程序！")
                execute_panic_exit()
                return

            self._tap_reset_timer.start(600)
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if (event.globalPos() - self._drag_pos - self.pos()).manhattanLength() > 6:
                self._is_dragging = True
                self._long_press_timer.stop()

            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._long_press_timer.stop()

            if not self._is_dragging and self._tap_count < 3:
                self._on_click_toggle()

            self._is_dragging = False
            event.accept()

    def _on_long_press_panic(self):
        """长按 1.2 秒触屏紧急销毁避险"""
        print("[FloatingBall] 触发触屏长按 1.2 秒，紧急销毁避险！")
        execute_panic_exit()

    def _reset_tap_count(self):
        self._tap_count = 0

    def _on_click_toggle(self):
        """手指轻点：快速在官方界面与私域 POS 之间切换"""
        self.stop_countdown()
        
        # 记录手动干预，触发 30 秒自动决策锁定 (防止秤抖动立刻抢抓)
        if hasattr(self.main_window, 'switch_controller') and self.main_window.switch_controller:
            self.main_window.switch_controller.notify_manual_switch()
            
        if self.is_our_pos_active:
            config = getattr(self.main_window, "config", None)
            if not is_official_pos_available(config):
                self._show_official_unavailable(
                    "官方 POS 未运行，当前保持私有 POS，不隐藏窗口。"
                )
                return
            success = bring_official_to_front(getattr(self.main_window, "config", None))
            if not success:
                self._show_official_unavailable(
                    "官方 POS 已关闭或窗口识别失效，当前保持私有 POS。"
                )
                return
            self.is_our_pos_active = False
            self.update()
        else:
            bring_our_pos_to_front(self.main_window)
            self.is_our_pos_active = True
            self.update()

    def _show_official_unavailable(self, message):
        """Show a visible touch-friendly warning instead of a hidden status hint."""
        try:
            from ui.custom_dialog import show_warning
            show_warning(self.main_window, "无法切换到官方 POS", message)
        except Exception:
            # The fallback keeps the guard effective even if a packaged UI
            # component is unavailable during early startup.
            if hasattr(self.main_window, "status"):
                self.main_window.status.showMessage(message, 5000)
