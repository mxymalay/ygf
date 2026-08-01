"""
纯触屏优化版 - 桌面常驻半透明悬浮球组件 (Touch-Friendly Floating Toggle Ball)
针对专用于纯触摸屏收银机设计：
- 单触 (Single Tap): 0.1秒极速切换 官方系统 ↔ 私域 POS
- 长触 (Long Press 1.2s) 或 三连击 (Triple Tap): 0.01秒触发紧急避险销毁退出
- 拖拽 (Touch Drag): 任意指尖顺滑拖拽悬浮球
"""
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QMenu, QAction
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont

from utils.window_utils import bring_official_to_front, bring_our_pos_to_front
from utils.panic_handler import execute_panic_exit


class FloatingBall(QWidget):
    """纯触屏极简悬浮球"""

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

        # 针对触屏加尺寸 (64x64) 方便手指直接按压
        self.setFixedSize(64, 64)

        # 移动到屏幕右上角默认位置
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 90, 120)

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
        layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_text = QLabel("YGF", self)
        self.lbl_text.setAlignment(Qt.AlignCenter)
        self.lbl_text.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-weight: bold;
                font-size: 14px;
                background: transparent;
            }
        """)
        layout.addWidget(self.lbl_text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景底色
        if self._is_long_press_progress:
            bg_color = QColor(220, 38, 38, 240)  # 正在长按时变红色警告色
            border_color = QColor(248, 113, 113)
        elif self.is_our_pos_active:
            bg_color = QColor(16, 185, 129, 215)  # 翡翠绿半透明
            border_color = QColor(52, 211, 153)
        else:
            bg_color = QColor(59, 130, 246, 215)  # 宝蓝色半透明
            border_color = QColor(147, 197, 253)

        # 外圈圆环
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 2))
        painter.drawEllipse(3, 3, 58, 58)

        # 内部触屏状态指示点
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(29, 48, 6, 6)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self._is_dragging = False

            # 启动长按定时器 (1.2秒未松开则触发紧急销毁)
            self._is_long_press_progress = False
            self._long_press_timer.start(1200)

            # 记录三连击
            self._tap_count += 1
            if self._tap_count >= 3:
                print("[FloatingBall] 触发触屏三连击，紧急销毁程序！")
                execute_panic_exit()
                return

            self._tap_reset_timer.start(600)
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            # 移动距离超过 6 像素判定为拖拽，取消长按与点击
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
                # 已经触发了长按避险，不处理单击
                self._is_long_press_progress = False
                self.update()
                return

            if not self._is_dragging and self._tap_count < 3:
                # 纯手指轻触：触发单次切换
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

    def _on_click_toggle(self):
        """手指轻点：快速在官方界面与私域 POS 之间切换"""
        if self.is_our_pos_active:
            # 隐藏本窗口，切出官方界面
            success = bring_official_to_front()
            if success:
                self.is_our_pos_active = False
                self.lbl_text.setText("官方")
                self.update()
            else:
                # 最小化本窗口
                self.main_window.showMinimized()
                self.is_our_pos_active = False
                self.lbl_text.setText("官方")
                self.update()
        else:
            # 唤醒本系统
            bring_our_pos_to_front(self.main_window)
            self.is_our_pos_active = True
            self.lbl_text.setText("YGF")
            self.update()
