"""Touch-friendly official POS window selection dialog."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from utils.window_utils import list_visible_windows


class OfficialWindowPickerDialog(QDialog):
    """Let the operator select the real official POS top-level window."""

    def __init__(self, current=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.current = current or {}
        self.selected_window = None
        self._windows = []

        card = QFrame(self)
        card.setObjectName("OfficialWindowPickerCard")
        card.setStyleSheet(
            "QFrame#OfficialWindowPickerCard { background: #1E293B; "
            "border: 2px solid #8B5CF6; border-radius: 16px; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title = QLabel(u"选择官方 POS 窗口")
        title.setStyleSheet(
            "color: #F8FAFC; font-size: 22px; font-weight: 900; "
            "border: none; background: transparent;"
        )
        layout.addWidget(title)

        hint = QLabel(
            u"请选择杨国福官方收银系统的主窗口。程序以后将按窗口标题识别它，"
            u"用于启动检测和官方/本 POS 界面切换。请先打开官方 POS，再点击刷新。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color: #CBD5E1; font-size: 15px; border: none; background: transparent;"
        )
        layout.addWidget(hint)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(
            "color: #C4B5FD; font-size: 14px; border: none; background: transparent;"
        )
        layout.addWidget(self.lbl_status)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(300)
        self.list_widget.setFocusPolicy(Qt.NoFocus)
        self.list_widget.setStyleSheet(
            "QListWidget { background: #0F172A; color: #F8FAFC; "
            "border: 1px solid #475569; border-radius: 10px; padding: 6px; "
            "font-size: 15px; outline: none; }"
            "QListWidget::item { min-height: 58px; padding: 10px 14px; "
            "margin: 3px 2px; border-radius: 8px; }"
            "QListWidget::item:selected { background: #7C3AED; color: #FFFFFF; }"
            "QListWidget::item:hover { background: #4C1D95; color: #FFFFFF; }"
        )
        self.list_widget.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self.list_widget, stretch=1)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        self.btn_refresh = QPushButton(u"刷新窗口")
        self.btn_refresh.setMinimumHeight(56)
        self.btn_refresh.setFocusPolicy(Qt.NoFocus)
        self.btn_refresh.setStyleSheet(
            "QPushButton { background: #334155; color: #F8FAFC; border: 1px solid #64748B; "
            "border-radius: 10px; font-size: 16px; font-weight: bold; }"
            "QPushButton:hover { background: #475569; }"
        )
        self.btn_refresh.clicked.connect(self.refresh_windows)
        buttons.addWidget(self.btn_refresh)

        self.btn_cancel = QPushButton(u"取消")
        self.btn_cancel.setMinimumHeight(56)
        self.btn_cancel.setFocusPolicy(Qt.NoFocus)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background: #475569; color: #F8FAFC; border-radius: 10px; "
            "font-size: 16px; font-weight: bold; }"
        )
        self.btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(self.btn_cancel)

        self.btn_confirm = QPushButton(u"确认此窗口")
        self.btn_confirm.setMinimumHeight(56)
        self.btn_confirm.setFocusPolicy(Qt.NoFocus)
        self.btn_confirm.setStyleSheet(
            "QPushButton { background: #6D28D9; color: #FFFFFF; border: 1px solid #A78BFA; "
            "border-radius: 10px; font-size: 16px; font-weight: bold; }"
            "QPushButton:hover { background: #7C3AED; }"
        )
        self.btn_confirm.clicked.connect(self._accept_selection)
        buttons.addWidget(self.btn_confirm)
        layout.addLayout(buttons)

        self.resize(720, 620)
        self.refresh_windows()

    @staticmethod
    def _display_text(info):
        process = info.get("process_name") or u"未知进程"
        return u"{title}\n进程：{process}    PID：{pid}".format(
            title=info.get("title", ""), process=process, pid=info.get("pid", "")
        )

    def refresh_windows(self):
        self._windows = list_visible_windows()
        self.list_widget.clear()
        selected_row = -1
        current_title = str(self.current.get("title", "") or "").strip().lower()
        current_process = str(self.current.get("process_name", "") or "").strip().lower()
        for index, info in enumerate(self._windows):
            item = QListWidgetItem(self._display_text(info))
            item.setData(Qt.UserRole, info)
            self.list_widget.addItem(item)
            if current_title and current_title == str(info.get("title", "")).lower():
                selected_row = index
            elif (
                selected_row < 0
                and current_process
                and current_process == str(info.get("process_name", "")).lower()
            ):
                selected_row = index

        if selected_row >= 0:
            self.list_widget.setCurrentRow(selected_row)
        elif self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
            selected_row = 0

        if not self._windows:
            self.lbl_status.setText(
                u"未发现可选择的窗口。请先启动官方 POS，再点击“刷新窗口”。"
            )
            self.btn_confirm.setEnabled(False)
        else:
            self.lbl_status.setText(
                u"检测到 %d 个可选窗口，请选择官方 POS 主窗口。" % len(self._windows)
            )
            self.btn_confirm.setEnabled(True)

    def _accept_selection(self):
        item = self.list_widget.currentItem()
        if item is None:
            return
        self.selected_window = item.data(Qt.UserRole)
        self.accept()
