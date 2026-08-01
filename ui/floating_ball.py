"""
纯触屏优化版 - 桌面常驻半透明悬浮球组件 (Touch-Friendly Floating Toggle Ball)
针对专用于纯触摸屏收银机设计：
- 单触 (Single Tap): 0.1秒极速切换 官方系统 ↔ 私域 POS
- 连触 3 下 (Triple Tap): 实时倒数提示，0.01秒触发防督导紧急销毁
- 长触 (Long Press 1.2s): 0.01秒触发防督导紧急销毁
- 拖拽 (Touch Drag): 任意指尖顺滑拖拽悬浮球
"""
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QPoint, QTimer
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont

from utils.window_utils import bring_official_to_front, bring_our_pos_to_front
from utils.panic_handler import execute_panic_exit


class FloatingBall(QWidget):
    """纯触屏极简悬浮球 — 专为店员设计的醒目防督导按钮"""

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

        # 针对触屏加尺寸 (76x76) 方便店员按压，显眼展示防督导提示
        self.setFixedSize(76, 76)

        # 移动到屏幕右上角默认位置
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 100, 110)

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

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 6, 2, 6)
        layout.setSpacing(1)

        # 第一行：主系统标识 (私域POS / 官方系统)
        self.lbl_title = QLabel("私域 POS", self)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-weight: bold;
                font-size: 12px;
                background: transparent;
            }
        """)
        layout.addWidget(self.lbl_title)

        # 第二行：防督导快速点击操作指引 (一目了然提示店员)
        self.lbl_sub = QLabel("快点3下销毁", self)
        self.lbl_sub.setAlignment(Qt.AlignCenter)
        self.lbl_sub.setStyleSheet("""
            QLabel {
                color: #FEF08A;
                font-weight: bold;
                font-size: 10px;
                background: transparent;
            }
        """)
        layout.addWidget(self.lbl_sub)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景底色动态反馈
        if self._is_long_press_progress or self._tap_count >= 2:
            bg_color = QColor(220, 38, 38, 245)  # 红色紧急防督导避险状态
            border_color = QColor(254, 202, 202)
        elif self._tap_count == 1:
            bg_color = QColor(234, 88, 12, 235)  # 橙色连击提示状态
            border_color = QColor(253, 186, 116)
        elif self.is_our_pos_active:
            bg_color = QColor(16, 185, 129, 225)  # 翡翠绿
            border_color = QColor(110, 231, 183)
        else:
            bg_color = QColor(37, 99, 235, 225)   # 宝蓝色
            border_color = QColor(147, 197, 253)

        # 外圈圆形卡片
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 2))
        painter.drawEllipse(3, 3, 70, 70)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self._is_dragging = False

            # 启动长按定时器 (1.2秒未松开则触发紧急销毁)
            self._is_long_press_progress = False
            self._long_press_timer.start(1200)

            # 记录连击数，给予店员实时动态反馈
            self._tap_count += 1
            if self._tap_count == 1:
                self.lbl_sub.setText("再点2次销毁")
                self.lbl_sub.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 10px;")
            elif self._tap_count == 2:
                self.lbl_sub.setText("再点1次销毁!")
                self.lbl_sub.setStyleSheet("color: #FEF08A; font-weight: bold; font-size: 10px;")
            elif self._tap_count >= 3:
                self.lbl_sub.setText("销毁退出中")
                print("[FloatingBall] 触发触屏三连击，0.01秒防督导紧急销毁程序！")
                execute_panic_exit()
                return

            self.update()
            self._tap_reset_timer.start(600)
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            # 移动距离超过 6 像素判定为拖拽
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
        self.lbl_sub.setText("快点3下销毁")
        self.lbl_sub.setStyleSheet("color: #FEF08A; font-weight: bold; font-size: 10px;")
        self.update()

    def _on_click_toggle(self):
        """手指轻点：快速在官方界面与私域 POS 之间切换"""
        if self.is_our_pos_active:
            success = bring_official_to_front()
            if not success and self.main_window:
                self.main_window.showMinimized()
            self.is_our_pos_active = False
            self.lbl_title.setText("官方系统")
            self.update()
        else:
            bring_our_pos_to_front(self.main_window)
            self.is_our_pos_active = True
            self.lbl_title.setText("私域 POS")
            self.update()
