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
import math
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QPoint, QRect, QRectF, QTimer
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

        # 88x84 黄金比例胶囊尺寸：顶部预留16px显示出票倒计时，底部
        # 仍保留原有暂停/锁定/对勾状态栏。
        # 右侧额外预留方向箭头区域，胶囊本体尺寸保持不变。
        self.setFixedSize(104, 84)

        # 移动到屏幕右上角默认位置
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 126, 110)

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
        self._countdown_total_ms = 10000.0
        self._countdown_start_time = 0.0
        self._countdown_remaining_sec = 0

        # 定时刷新界面以确保暂停图标能按时消失 (1Hz)
        self._state_refresh_timer = QTimer(self)
        self._state_refresh_timer.timeout.connect(self.update)
        self._state_refresh_timer.start(1000)

        # 决策通过的对钩指示符
        self._show_checkmark = False
        self._checkmark_timer = QTimer(self)
        self._checkmark_timer.setSingleShot(True)
        self._checkmark_timer.timeout.connect(self._hide_checkmark)

        # 分流配额可视化：当前累计进度与上一份累计进度同时保留。
        # 进度的分母是“目标私域重量占比”，达到 100% 表示已经到达目标。
        self._quota_progress = 0.0
        self._quota_previous_progress = 0.0
        self._quota_is_private = True
        self._quota_previous_is_private = True
        self._next_switch_is_private = None

    def set_quota_progress(self, private_ratio, target_private_ratio, is_private):
        """更新悬浮球内的配额水位，并保留上一份水位作浅色背景。"""
        try:
            private_ratio = max(0.0, float(private_ratio or 0.0))
            target = max(0.0, float(target_private_ratio or 0.0))
        except (TypeError, ValueError):
            private_ratio, target = 0.0, 0.0
        progress = 1.0 if target <= 0.0 else min(1.0, private_ratio / target)
        mode = bool(is_private)
        # 倒计时/状态刷新可能重复调用；相同快照不应伪造“上一份进度”。
        if (
            abs(progress - self._quota_progress) < 0.0001
            and mode == self._quota_is_private
        ):
            return
        self._quota_previous_progress = self._quota_progress
        self._quota_previous_is_private = self._quota_is_private
        self._quota_progress = progress
        self._quota_is_private = mode
        self.update()

    def set_switch_progress(self, progress, is_private, next_is_private=None):
        """设置“距离下一次自动切换”的本轮进度（0.0 至 1.0）。"""
        try:
            progress = max(0.0, min(1.0, float(progress or 0.0)))
        except (TypeError, ValueError):
            progress = 0.0
        mode = bool(is_private)
        next_mode = None if next_is_private is None else bool(next_is_private)
        if (
            abs(progress - self._quota_progress) < 0.0001
            and mode == self._quota_is_private
            and next_mode == self._next_switch_is_private
        ):
            return
        self._quota_previous_progress = self._quota_progress
        self._quota_previous_is_private = self._quota_is_private
        self._quota_progress = progress
        self._quota_is_private = mode
        self._next_switch_is_private = next_mode
        self.update()

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
        self._countdown_remaining_sec = max(0, int(math.ceil(float(seconds))))
        self._countdown_ratio = 1.0
        self._countdown_timer.start()
        self.update()

    def stop_countdown(self):
        """停止倒计时动效"""
        self._countdown_active = False
        self._countdown_remaining_sec = 0
        self._countdown_timer.stop()
        self.update()

    def _on_countdown_tick(self):
        elapsed_ms = (time.time() - self._countdown_start_time) * 1000.0
        remaining_ratio = max(0.0, 1.0 - (elapsed_ms / self._countdown_total_ms))
        self._countdown_ratio = remaining_ratio
        remaining_ms = max(0.0, self._countdown_total_ms - elapsed_ms)
        self._countdown_remaining_sec = int(math.ceil(remaining_ms / 1000.0))
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
            bg_color1 = QColor(110, 231, 183, 235)  # 未填充浅绿
            bg_color2 = QColor(16, 185, 129, 235)   # 胶囊末端背景
            border_outer = QColor(16, 185, 129, 235) # 与未填充背景一致
            led_color = QColor(52, 211, 153)
        else:
            bg_color1 = QColor(147, 197, 253, 235)  # 未填充浅蓝
            bg_color2 = QColor(37, 99, 235, 235)    # 胶囊末端背景
            border_outer = QColor(37, 99, 235, 235)  # 与未填充背景一致
            led_color = QColor(96, 165, 250)

        # 渐变底色
        grad = QLinearGradient(0, 16, 0, 66)
        grad.setColorAt(0.0, bg_color1)
        grad.setColorAt(1.0, bg_color2)

        # 2. 绘制主胶囊背景与外边框 (顶部预留倒计时区域)
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(border_outer, 2.0))
        painter.drawRoundedRect(1, 17, 86, 48, 24, 24)

        # 2.1 配额“水位”：上一份用浅色铺底，本次增加量用较深同色系填充。
        # 采用裁剪路径，水位不会溢出胶囊圆角；文字和状态图标仍绘制在其上方。
        painter.save()
        liquid_path = QPainterPath()
        liquid_path.addRoundedRect(QRectF(2, 18, 84, 46), 23, 23)
        painter.setClipPath(liquid_path)

        def liquid_gradient(private, alpha, start_x, end_x):
            """Create the translucent left-to-right liquid sheen."""
            if private:
                base = (5, 150, 105)    # 进度加深绿
            else:
                base = (29, 78, 216)    # 进度加深蓝
            grad = QLinearGradient(start_x, 0, max(start_x + 1.0, end_x), 0)
            grad.setColorAt(0.0, QColor(base[0], base[1], base[2], min(220, alpha + 30)))
            grad.setColorAt(0.45, QColor(base[0], base[1], base[2], alpha))
            grad.setColorAt(1.0, QColor(base[0], base[1], base[2], max(12, alpha - 22)))
            return grad

        track_x, track_y, track_w, track_h = 2.0, 18.0, 84.0, 46.0
        previous_w = track_w * max(0.0, min(1.0, self._quota_previous_progress))
        current_w = track_w * max(0.0, min(1.0, self._quota_progress))
        if previous_w > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(liquid_gradient(
                self._quota_previous_is_private, 92, track_x, track_x + previous_w
            )))
            painter.drawRect(QRectF(track_x, track_y, previous_w, track_h))

        # 同模式且水位上升时，只绘制新增区，能同时看出上一份和本次增加量。
        same_mode = self._quota_previous_is_private == self._quota_is_private
        if same_mode and current_w >= previous_w:
            current_x, current_width = track_x + previous_w, current_w - previous_w
        else:
            current_x, current_width = track_x, current_w
        if current_width > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(liquid_gradient(
                self._quota_is_private, 154, current_x, current_x + current_width
            )))
            painter.drawRect(QRectF(current_x, track_y, current_width, track_h))
        if current_w > 0:
            if self._quota_is_private:
                boundary = QColor(5, 150, 105, 225)
            else:
                boundary = QColor(29, 78, 216, 225)
            painter.setPen(QPen(boundary, 1.0))
            painter.drawLine(track_x + current_w, track_y + 5, track_x + current_w, track_y + track_h - 5)
        painter.restore()

        # 右侧小方向箭头：只在确实存在下一自动切换目标时显示。
        if self._next_switch_is_private is not None:
            arrow_color = QColor(52, 211, 153) if self._next_switch_is_private else QColor(96, 165, 250)
            painter.setPen(QPen(arrow_color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            arrow_y = 42
            if self._next_switch_is_private:
                # 下一次切到私有 POS：左箭头
                painter.drawLine(98, arrow_y - 6, 91, arrow_y)
                painter.drawLine(91, arrow_y, 98, arrow_y + 6)
            else:
                # 下一次切到官方 POS：右箭头
                painter.drawLine(92, arrow_y - 6, 99, arrow_y)
                painter.drawLine(99, arrow_y, 92, arrow_y + 6)

        # 3. 绘制内侧微高光倒角线 (3D 玻璃质感)
        painter.setBrush(Qt.NoBrush)
        # 内侧线也使用未填充背景色，避免白色高光把边框误显示成进度色。
        painter.setPen(QPen(QColor(bg_color2.red(), bg_color2.green(), bg_color2.blue(), 220), 1.0))
        painter.drawRoundedRect(3, 19, 82, 44, 22, 22)

        # 4. 边框嵌入式 LED 呼吸指示灯 (位于文字前方垂直居中)
        painter.setBrush(QBrush(led_color))
        painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
        # 文字居中，胶囊高 50。圆点大小 6x6，所以 y=38 刚好垂直居中。
        led_x = 22 if self.is_our_pos_active else 12
        painter.drawEllipse(led_x, 38, 6, 6)

        # 5. 两行居中文字排版
        title_text = u"私域" if self.is_our_pos_active else u"官方系统"
        font_title = QFont("Microsoft YaHei", 9, QFont.Bold)
        painter.setFont(font_title)
        painter.setPen(QColor(255, 255, 255))
        rect_title = QRect(6, 21, 82, 40) # 扩大标题矩形，使其完全居中
        painter.drawText(rect_title, Qt.AlignCenter, title_text)

        # 出票后倒计时数字放在悬浮球正上方，不占用底部暂停/锁定状态栏。
        # 顶部不再绘制进度条，只保留清晰的小数字。
        if self._countdown_active and self._countdown_remaining_sec > 0:
            painter.setBrush(QColor(15, 23, 42, 220))
            painter.setPen(QPen(QColor(254, 240, 138, 220), 1.0))
            painter.drawRoundedRect(31, 1, 26, 14, 7, 7)
            painter.setPen(QColor(254, 240, 138))
            painter.setFont(QFont("Microsoft YaHei", 8, QFont.Bold))
            painter.drawText(QRect(31, 1, 26, 14), Qt.AlignCenter, str(self._countdown_remaining_sec))

        # 6. 悬浮球下方独立状态指示栏 (小灵动岛，不与主胶囊重叠)
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
            painter.drawRoundedRect(bg_x, 67, bg_width, 16, 8, 8)
            
            # 逐个绘制图标
            icon_x = bg_x + 4 + 10  # 10 is the center offset of the first icon
            for icon in active_icons:
                if icon == "PAUSE":
                    painter.setPen(QPen(QColor(255, 255, 255), 2.0, Qt.SolidLine, Qt.RoundCap))
                    painter.drawLine(icon_x - 2, 71, icon_x - 2, 79)
                    painter.drawLine(icon_x + 2, 71, icon_x + 2, 79)
                elif icon == "LOCK":
                    painter.setPen(QPen(QColor(255, 255, 255), 1.5, Qt.SolidLine, Qt.RoundCap))
                    painter.setBrush(QColor(255, 255, 255))
                    painter.drawRect(icon_x - 3, 75, 6, 4)
                    painter.setBrush(Qt.NoBrush)
                    painter.drawArc(icon_x - 2, 71, 4, 6, 0, 180 * 16)
                elif icon == "CHECK":
                    painter.setPen(QPen(QColor(253, 224, 71), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    path = QPainterPath()
                    path.moveTo(icon_x - 4, 75)
                    path.lineTo(icon_x - 1, 78)
                    path.lineTo(icon_x + 4, 71)
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
            controller = getattr(self.main_window, "switch_controller", None)
            if controller and hasattr(controller, "reset_switch_cycle_for_manual"):
                controller.reset_switch_cycle_for_manual(False)
            elif controller and hasattr(controller, "refresh_floating_ball_progress"):
                controller.refresh_floating_ball_progress(False)
            self.update()
        else:
            bring_our_pos_to_front(self.main_window)
            self.is_our_pos_active = True
            controller = getattr(self.main_window, "switch_controller", None)
            if controller and hasattr(controller, "reset_switch_cycle_for_manual"):
                controller.reset_switch_cycle_for_manual(True)
            elif controller and hasattr(controller, "refresh_floating_ball_progress"):
                controller.refresh_floating_ball_progress(True)
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
