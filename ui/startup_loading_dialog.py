"""启动阶段的轻量加载提示。

登录/硬件检测窗口关闭后，主窗口还需要创建数据库、收银台、打印和
自动切换组件。这个过程在 Win7 设备上可能有短暂空档，使用独立的
无边框提示避免用户看到空白桌面而误以为程序没有启动。
"""
from PyQt5.QtWidgets import QDialog, QFrame, QLabel, QProgressBar, QVBoxLayout, QApplication
from PyQt5.QtCore import Qt, QTimer


class StartupLoadingDialog(QDialog):
    """显示主界面创建进度的非阻塞提示框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(False)
        self.setFixedSize(500, 230)
        self._message = u"检测完成，正在加载收银系统"
        self._dots = 0

        panel = QFrame(self)
        panel.setObjectName("StartupLoadingPanel")
        panel.setGeometry(0, 0, 500, 230)
        panel.setStyleSheet(
            "QFrame#StartupLoadingPanel { background: #172235; border: 2px solid #334155; "
            "border-radius: 18px; }"
            "QLabel { background: transparent; border: none; }"
            "QProgressBar { background: #0F172A; border: none; border-radius: 5px; "
            "min-height: 10px; max-height: 10px; }"
            "QProgressBar::chunk { background: #38BDF8; border-radius: 5px; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        self.lbl_title = QLabel(u"POS辅助系统")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet("color: #F8FAFC; font-size: 23px; font-weight: 900;")
        layout.addWidget(self.lbl_title)

        self.lbl_message = QLabel(self._message)
        self.lbl_message.setAlignment(Qt.AlignCenter)
        self.lbl_message.setWordWrap(True)
        self.lbl_message.setStyleSheet("color: #CBD5E1; font-size: 16px; font-weight: bold;")
        layout.addWidget(self.lbl_message)

        self.progress = QProgressBar()
        # A determinate bar with a small automatic advance is more reassuring
        # on Win7 than Qt's indeterminate chunk, which can appear frozen while
        # the main thread is constructing widgets.
        self.progress.setRange(0, 100)
        self.progress.setValue(4)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        self.lbl_detail = QLabel(u"正在准备界面，请稍候……")
        self.lbl_detail.setAlignment(Qt.AlignCenter)
        self.lbl_detail.setStyleSheet("color: #94A3B8; font-size: 13px;")
        layout.addWidget(self.lbl_detail)

        self._timer = QTimer(self)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self._animate)
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(120)
        self._progress_timer.timeout.connect(self._advance_progress)

    def showEvent(self, event):
        super().showEvent(event)
        self._center_on_screen()
        self._timer.start()
        self._progress_timer.start()

    def closeEvent(self, event):
        self._timer.stop()
        self._progress_timer.stop()
        super().closeEvent(event)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.left() + (geo.width() - self.width()) // 2,
                geo.top() + (geo.height() - self.height()) // 2,
            )

    def _animate(self):
        self._dots = (self._dots + 1) % 4
        self.lbl_message.setText(self._message + ("." * self._dots))

    def _advance_progress(self):
        """Move the visual indicator while the event loop is responsive."""
        value = int(self.progress.value())
        if value < 92:
            self.progress.setValue(value + 1)

    def set_progress(self, value):
        """Set a real initialization checkpoint without moving backwards."""
        try:
            value = max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return
        self.progress.setValue(max(self.progress.value(), value))

    def pump(self, progress=None):
        """Refresh the splash during synchronous Win7 initialization stages."""
        if progress is not None:
            self.set_progress(progress)
        self._advance_progress()
        self._animate()
        QApplication.processEvents()

    def set_message(self, message, detail=None):
        self._message = str(message or u"正在加载收银系统")
        self._dots = 0
        self.lbl_message.setText(self._message)
        if detail is not None:
            self.lbl_detail.setText(str(detail))
