# -*- coding: utf-8 -*-
"""
POS 现代极简风格统一弹窗组件 (去系统原生框、圆角、无缝高颜值对话框)
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSpinBox
)

class ModernDialog(QDialog):
    """现代风通用提示与确认对话框"""

    TYPE_INFO = "info"
    TYPE_WARNING = "warning"
    TYPE_QUESTION = "question"

    def __init__(self, title, message, dialog_type=TYPE_INFO, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        self.result_choice = False

        # 主卡片容器
        card = QFrame(self)
        card.setObjectName("DialogCard")
        card.setStyleSheet(
            "QFrame#DialogCard { background: #1E293B; border-radius: 16px; "
            "border: 1px solid #334155; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(16)

        # 头部标题与图标
        head_box = QHBoxLayout()
        head_box.setSpacing(10)

        icon_lbl = QLabel()
        if dialog_type == self.TYPE_WARNING:
            icon_lbl.setText("⚠️")
            icon_lbl.setStyleSheet("font-size: 24px; border: none; background: transparent;")
        elif dialog_type == self.TYPE_QUESTION:
            icon_lbl.setText("❓")
            icon_lbl.setStyleSheet("font-size: 24px; border: none; background: transparent;")
        else:
            icon_lbl.setText("ℹ️")
            icon_lbl.setStyleSheet("font-size: 24px; border: none; background: transparent;")

        head_box.addWidget(icon_lbl)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 17px; font-weight: bold; color: #F9FAFB; border: none; background: transparent;")
        head_box.addWidget(lbl_title, stretch=1)

        card_layout.addLayout(head_box)

        # 内容消息文本
        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("font-size: 14px; color: #9CA3AF; border: none; background: transparent; line-height: 1.4;")
        card_layout.addWidget(lbl_msg)

        card_layout.addSpacing(4)

        # 底部按钮栏
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        if dialog_type == self.TYPE_QUESTION:
            btn_no = QPushButton("取消")
            btn_no.setCursor(Qt.PointingHandCursor)
            btn_no.setStyleSheet(
                "QPushButton { background: #334155; color: #9CA3AF; font-weight: bold; font-size: 14px; "
                "border-radius: 8px; padding: 8px 18px; border: 1px solid #475569; }"
                "QPushButton:hover { background: #475569; color: #FFFFFF; }"
            )
            btn_no.clicked.connect(self._on_cancel)
            btn_box.addWidget(btn_no)

            btn_yes = QPushButton("确定")
            btn_yes.setCursor(Qt.PointingHandCursor)
            btn_yes.setStyleSheet(
                "QPushButton { background: #EA580C; color: white; font-weight: bold; font-size: 14px; "
                "border-radius: 8px; padding: 8px 22px; border: 1px solid #F97316; }"
                "QPushButton:hover { background: #F97316; }"
            )
            btn_yes.clicked.connect(self._on_confirm)
            btn_box.addWidget(btn_yes)
        else:
            btn_ok = QPushButton("好的")
            btn_ok.setCursor(Qt.PointingHandCursor)
            btn_ok.setStyleSheet(
                "QPushButton { background: #EA580C; color: white; font-weight: bold; font-size: 14px; "
                "border-radius: 8px; padding: 8px 24px; border: 1px solid #F97316; }"
                "QPushButton:hover { background: #F97316; }"
            )
            btn_ok.clicked.connect(self.accept)
            btn_box.addWidget(btn_ok)

        card_layout.addLayout(btn_box)
        self.resize(360, 200)

    def _on_confirm(self):
        self.result_choice = True
        self.accept()

    def _on_cancel(self):
        self.result_choice = False
        self.reject()


class ModernInputDialog(QDialog):
    """现代风数字与文本输入对话框 (代替原生 QInputDialog)"""

    def __init__(self, title, message, value=1, min_val=1, max_val=9999, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        self.input_value = value
        self.confirmed = False

        card = QFrame(self)
        card.setObjectName("DialogCard")
        card.setStyleSheet(
            "QFrame#DialogCard { background: #1E293B; border-radius: 16px; "
            "border: 1px solid #334155; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(16)

        # 标题
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 17px; font-weight: bold; color: #F9FAFB; border: none; background: transparent;")
        card_layout.addWidget(lbl_title)

        # 提示词
        lbl_msg = QLabel(message)
        lbl_msg.setStyleSheet("font-size: 14px; color: #9CA3AF; border: none; background: transparent;")
        card_layout.addWidget(lbl_msg)

        # 输入框
        self.spin = QSpinBox()
        self.spin.setRange(min_val, max_val)
        self.spin.setValue(value)
        self.spin.setStyleSheet(
            "QSpinBox { background: #0F172A; color: #F97316; font-size: 20px; font-weight: bold; "
            "border: 1.5px solid #EA580C; border-radius: 8px; padding: 6px 12px; font-family: 'Consolas', monospace; }"
        )
        card_layout.addWidget(self.spin)

        card_layout.addSpacing(6)

        # 按钮栏
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet(
            "QPushButton { background: #334155; color: #9CA3AF; font-weight: bold; font-size: 14px; "
            "border-radius: 8px; padding: 8px 18px; border: 1px solid #475569; }"
            "QPushButton:hover { background: #475569; color: #FFFFFF; }"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_ok = QPushButton("确认调整")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setStyleSheet(
            "QPushButton { background: #EA580C; color: white; font-weight: bold; font-size: 14px; "
            "border-radius: 8px; padding: 8px 22px; border: 1px solid #F97316; }"
            "QPushButton:hover { background: #F97316; }"
        )
        btn_ok.clicked.connect(self._on_ok)
        btn_box.addWidget(btn_ok)

        card_layout.addLayout(btn_box)
        self.resize(360, 220)

    def _on_ok(self):
        self.input_value = self.spin.value()
        self.confirmed = True
        self.accept()


# 便捷调用的封装函数
def show_info(parent, title, message):
    dlg = ModernDialog(title, message, ModernDialog.TYPE_INFO, parent)
    dlg.exec_()

def show_warning(parent, title, message):
    dlg = ModernDialog(title, message, ModernDialog.TYPE_WARNING, parent)
    dlg.exec_()

def show_question(parent, title, message) -> bool:
    dlg = ModernDialog(title, message, ModernDialog.TYPE_QUESTION, parent)
    dlg.exec_()
    return dlg.result_choice

def get_int_input(parent, title, message, value=1, min_val=1, max_val=9999):
    dlg = ModernInputDialog(title, message, value, min_val, max_val, parent)
    res = dlg.exec_()
    return dlg.input_value, (res == QDialog.Accepted)
