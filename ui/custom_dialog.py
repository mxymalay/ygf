# -*- coding: utf-8 -*-
"""
POS 现代极简风格统一弹窗组件 (去系统原生框、圆角、无缝高颜值对话框)
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSpinBox,
    QGraphicsBlurEffect
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

    def exec_(self):
        parent_w = self.parent()
        if parent_w and hasattr(parent_w, 'window'):
            parent_w = parent_w.window()
        
        if parent_w:
            try:
                blur = QGraphicsBlurEffect(parent_w)
                blur.setBlurRadius(42)
                parent_w.setGraphicsEffect(blur)
            except Exception:
                pass

        try:
            return super().exec_()
        finally:
            if parent_w:
                try:
                    parent_w.setGraphicsEffect(None)
                except Exception:
                    pass


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


class ModernDoubleInputDialog(QDialog):
    """现代风双精度浮点数输入对话框 (用于单价等金额输入)"""

    def __init__(self, title, message, value=1.00, min_val=0.01, max_val=999.99, decimals=2, parent=None):
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
        card_layout.setContentsMargins(22, 22, 22, 22)
        card_layout.setSpacing(16)

        # 标题
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F9FAFB; border: none; background: transparent;")
        card_layout.addWidget(lbl_title)

        # 提示词
        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("font-size: 14px; color: #9CA3AF; border: none; background: transparent; line-height: 1.4;")
        card_layout.addWidget(lbl_msg)

        # 浮点输入框
        from PyQt5.QtWidgets import QDoubleSpinBox
        self.spin = QDoubleSpinBox()
        self.spin.setRange(min_val, max_val)
        self.spin.setDecimals(decimals)
        self.spin.setValue(value)
        self.spin.setSuffix(" 元/KG")
        self.spin.setStyleSheet(
            "QDoubleSpinBox { background: #0F172A; color: #10B981; font-size: 22px; font-weight: bold; "
            "border: 2px solid #10B981; border-radius: 10px; padding: 8px 14px; font-family: 'Consolas', monospace; }"
        )
        card_layout.addWidget(self.spin)

        card_layout.addSpacing(6)

        # 按钮栏
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        btn_ok = QPushButton("保存单价并开始使用")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setStyleSheet(
            "QPushButton { background: #10B981; color: white; font-weight: bold; font-size: 15px; "
            "border-radius: 10px; padding: 10px 24px; border: 1px solid #059669; }"
            "QPushButton:hover { background: #059669; }"
        )
        btn_ok.clicked.connect(self._on_ok)
        btn_box.addWidget(btn_ok)

        card_layout.addLayout(btn_box)
        self.resize(400, 250)

    def _on_ok(self):
        self.input_value = self.spin.value()
        self.confirmed = True
        self.accept()

    def exec_(self):
        parent_w = self.parent()
        if parent_w and hasattr(parent_w, 'window'):
            parent_w = parent_w.window()
        
        if parent_w:
            try:
                blur = QGraphicsBlurEffect(parent_w)
                blur.setBlurRadius(42)
                parent_w.setGraphicsEffect(blur)
            except Exception:
                pass

        try:
            return super().exec_()
        finally:
            if parent_w:
                try:
                    parent_w.setGraphicsEffect(None)
                except Exception:
                    pass


from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QDoubleSpinBox, QLineEdit

class FocusSelectDoubleSpinBox(QDoubleSpinBox):
    """获得焦点时自动全选文本，方便直接输入覆盖已有数值"""
    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)

class FocusSelectLineEdit(QLineEdit):
    """获得焦点时自动全选文本，方便直接输入覆盖已有文本"""
    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)


class FirstRunInitDialog(QDialog):
    """首次使用初始化对话框 (设置公斤单价与分店名称)"""

    def __init__(self, title, message, default_price=1.00, default_special_price=50.00, default_branch="杨国福(测试店)", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        self.price_val = default_price
        self.special_price_val = default_special_price
        self.branch_val = default_branch
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
        card_layout.setContentsMargins(22, 22, 22, 22)
        card_layout.setSpacing(10)

        # 标题
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F9FAFB; border: none; background: transparent;")
        card_layout.addWidget(lbl_title)

        # 提示词
        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("font-size: 13px; color: #9CA3AF; border: none; background: transparent; line-height: 1.4;")
        card_layout.addWidget(lbl_msg)

        # 字段 1: 麻辣烫标准单价
        lbl_p = QLabel("1. 本店标准麻辣烫单价 (元/KG)：")
        lbl_p.setStyleSheet("font-size: 14px; font-weight: bold; color: #F3F4F6; border: none;")
        card_layout.addWidget(lbl_p)

        self.spin = FocusSelectDoubleSpinBox()
        self.spin.setRange(0.01, 999.99)
        self.spin.setDecimals(2)
        self.spin.setValue(default_price)
        self.spin.setSuffix(" 元/KG")
        self.spin.setStyleSheet(
            "QDoubleSpinBox { background: #0F172A; color: #10B981; font-size: 20px; font-weight: bold; "
            "border: 2px solid #10B981; border-radius: 8px; padding: 6px 12px; font-family: 'Consolas', monospace; }"
        )
        card_layout.addWidget(self.spin)

        # 字段 2: 精品汤底单价
        lbl_sp = QLabel("2. 本店精品汤底单价 (元/KG)：")
        lbl_sp.setStyleSheet("font-size: 14px; font-weight: bold; color: #F3F4F6; border: none; margin-top: 2px;")
        card_layout.addWidget(lbl_sp)

        self.spin_special = FocusSelectDoubleSpinBox()
        self.spin_special.setRange(0.01, 999.99)
        self.spin_special.setDecimals(2)
        self.spin_special.setValue(default_special_price)
        self.spin_special.setSuffix(" 元/KG")
        self.spin_special.setStyleSheet(
            "QDoubleSpinBox { background: #0F172A; color: #F59E0B; font-size: 20px; font-weight: bold; "
            "border: 2px solid #F59E0B; border-radius: 8px; padding: 6px 12px; font-family: 'Consolas', monospace; }"
        )
        card_layout.addWidget(self.spin_special)

        # 字段 3: 分店名称 (锁定杨国福与括号，用户仅填写括号内容)
        lbl_b = QLabel("3. 本店分店名称：")
        lbl_b.setStyleSheet("font-size: 14px; font-weight: bold; color: #F3F4F6; border: none; margin-top: 2px;")
        card_layout.addWidget(lbl_b)

        branch_row = QHBoxLayout()
        branch_row.setSpacing(4)

        lbl_prefix = QLabel("杨国福(")
        lbl_prefix.setStyleSheet("font-size: 17px; font-weight: bold; color: #38BDF8; border: none; background: transparent;")
        branch_row.addWidget(lbl_prefix)

        # 提取内部默认店名 (如 "测试店" 或 "肥西水晶城店")
        inner_branch = default_branch
        if "(" in inner_branch and ")" in inner_branch:
            inner_branch = inner_branch.split("(")[1].split(")")[0]
        elif inner_branch.startswith("杨国福"):
            inner_branch = inner_branch.replace("杨国福", "").replace("(", "").replace(")", "").strip()

        self.txt_branch = FocusSelectLineEdit(inner_branch)
        self.txt_branch.setPlaceholderText("例如：肥西水晶城店")
        self.txt_branch.setStyleSheet(
            "QLineEdit { background: #0F172A; color: #38BDF8; font-size: 16px; font-weight: bold; "
            "border: 2px solid #0284C7; border-radius: 8px; padding: 8px 12px; }"
        )
        branch_row.addWidget(self.txt_branch, stretch=1)

        lbl_suffix = QLabel(")")
        lbl_suffix.setStyleSheet("font-size: 17px; font-weight: bold; color: #38BDF8; border: none; background: transparent;")
        branch_row.addWidget(lbl_suffix)

        card_layout.addLayout(branch_row)

        card_layout.addSpacing(6)

        # 按钮栏
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        btn_ok = QPushButton("保存初始化配置并开始使用")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setStyleSheet(
            "QPushButton { background: #10B981; color: white; font-weight: bold; font-size: 15px; "
            "border-radius: 10px; padding: 10px 24px; border: 1px solid #059669; }"
            "QPushButton:hover { background: #059669; }"
        )
        btn_ok.clicked.connect(self._on_ok)
        btn_box.addWidget(btn_ok)

        card_layout.addLayout(btn_box)
        self.resize(460, 420)

    def _on_ok(self):
        self.price_val = self.spin.value()
        self.special_price_val = self.spin_special.value()
        user_inner = self.txt_branch.text().strip()
        user_inner = user_inner.replace("杨国福", "").replace("(", "").replace(")", "").strip()
        if not user_inner:
            user_inner = "测试店"
        self.branch_val = f"杨国福({user_inner})"
        self.confirmed = True
        self.accept()

    def exec_(self):
        parent_w = self.parent()
        if parent_w and hasattr(parent_w, 'window'):
            parent_w = parent_w.window()
        
        if parent_w:
            try:
                blur = QGraphicsBlurEffect(parent_w)
                blur.setBlurRadius(42)
                parent_w.setGraphicsEffect(blur)
            except Exception:
                pass

        try:
            return super().exec_()
        finally:
            if parent_w:
                try:
                    parent_w.setGraphicsEffect(None)
                except Exception:
                    pass


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

def get_price_input(parent, title, message, value=1.00, min_val=0.01, max_val=999.99):
    dlg = ModernDoubleInputDialog(title, message, value, min_val, max_val, decimals=2, parent=parent)
    res = dlg.exec_()
    return dlg.input_value, (res == QDialog.Accepted)

def get_first_run_input(parent, title, message, default_price=1.00, default_special_price=50.00, default_branch="杨国福(测试店)"):
    dlg = FirstRunInitDialog(title, message, default_price, default_special_price, default_branch, parent=parent)
    res = dlg.exec_()
    return dlg.price_val, dlg.special_price_val, dlg.branch_val, (res == QDialog.Accepted)


class ReceiptPreviewDialog(QDialog):
    """小票模拟预览与确认打票对话框 (含闪烁收款提醒 & 10 秒倒计时，自适应各分辨率屏幕)"""

    def __init__(self, sale_data, countdown_sec=10, parent=None):
        super().__init__(parent)
        self.sale_data = sale_data
        self.countdown = countdown_sec
        self._flash_flag = False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        card = QFrame(self)
        card.setObjectName("ReceiptCard")
        card.setStyleSheet(
            "QFrame#ReceiptCard { background: #0F172A; border-radius: 16px; "
            "border: 2px dashed #334155; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # 0. 顶部固定：闪烁收款提醒 Banner (独立在外)
        self.notice_banner = QLabel(u"⚠️ 请确认已通过其他工具完成收款！")
        self.notice_banner.setAlignment(Qt.AlignCenter)
        self.notice_banner.setStyleSheet(
            "background: #DC2626; color: #FFFFFF; font-size: 14px; font-weight: 900; "
            "padding: 8px; border-radius: 8px; border: none;"
        )
        layout.addWidget(self.notice_banner)

        layout.addWidget(card, stretch=1)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)

        # 1. 中部滚动区域：模拟小票完整票面
        from PyQt5.QtWidgets import QScrollArea, QWidget
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: #1E293B; border-radius: 3px; }"
            "QScrollBar::handle:vertical { background: #475569; border-radius: 3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(8)

        # Header: POS点餐 堂食
        lbl_top_hdr = QLabel("POS点餐  堂食")
        lbl_top_hdr.setAlignment(Qt.AlignCenter)
        lbl_top_hdr.setStyleSheet("font-size: 13px; font-weight: bold; color: #94A3B8; border: none;")
        scroll_layout.addWidget(lbl_top_hdr)

        lbl_shop = QLabel(sale_data.get("shop_name", u"杨国福麻辣烫"))
        lbl_shop.setAlignment(Qt.AlignCenter)
        lbl_shop.setStyleSheet("font-size: 19px; font-weight: 900; color: #F9FAFB; border: none;")
        scroll_layout.addWidget(lbl_shop)

        sub_title = sale_data.get("shop_subtitle", "")
        if not sub_title:
            sub_title = u"门店名称：杨国福(肥西水晶城店)"
        elif not sub_title.startswith(u"门店名称："):
            sub_title = u"门店名称：" + sub_title
        lbl_sub = QLabel(sub_title)
        lbl_sub.setAlignment(Qt.AlignCenter)
        lbl_sub.setStyleSheet("font-size: 12px; color: #9CA3AF; border: none;")
        scroll_layout.addWidget(lbl_sub)

        # 叫号大牌
        call_no_box = QFrame()
        call_no_box.setStyleSheet("background: rgba(249, 115, 22, 0.15); border-radius: 10px; padding: 4px;")
        cn_layout = QVBoxLayout(call_no_box)
        lbl_call = QLabel(f"取餐号: {sale_data.get('call_no', '050')}")
        lbl_call.setAlignment(Qt.AlignCenter)
        lbl_call.setStyleSheet("font-size: 24px; font-weight: 900; color: #F97316; border: none;")
        cn_layout.addWidget(lbl_call)
        scroll_layout.addWidget(call_no_box)

        # 虚线分隔
        line1 = QLabel("----------------------------------------")
        line1.setAlignment(Qt.AlignCenter)
        line1.setStyleSheet("color: #475569; font-family: monospace; border: none;")
        scroll_layout.addWidget(line1)

        # 细项表头 (使用 Flex 弹性布局实现绝对垂直对齐)
        hdr_w = QWidget()
        hdr_w.setStyleSheet("background: transparent; border: none;")
        hdr_l = QHBoxLayout(hdr_w)
        hdr_l.setContentsMargins(0,0,0,0)
        
        l_name = QLabel("菜品名")
        l_name.setStyleSheet("font-size: 12px; font-weight: bold; color: #64748B;")
        hdr_l.addWidget(l_name, stretch=1)
        
        for t in ["规格", "单价", "数量", "小计"]:
            l = QLabel(t)
            l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            l.setStyleSheet("font-size: 12px; font-weight: bold; color: #64748B;")
            l.setFixedWidth(45)
            hdr_l.addWidget(l)
            
        scroll_layout.addWidget(hdr_w)

        # 商品明细列表
        items_layout = QVBoxLayout()
        items_layout.setSpacing(6)
        cart_items = sale_data.get("cart_items", [])
        m_count = 0

        for item in cart_items:
            is_soup = (item.get("type") == "soup" or "weight" in item)
            name_str = item.get("name", u"经典草本骨汤(KG)(KG)")
            tag_str = item.get("tag", "")

            item_box = QVBoxLayout()
            item_box.setSpacing(2)

            if is_soup:
                m_count += 1
                title_lbl = QLabel(f"【制{m_count}】{name_str}")
                title_lbl.setStyleSheet("font-size: 14px; font-weight: 900; color: #F8FAFC; border: none;")
                item_box.addWidget(title_lbl)

                w_val = item.get("weight", sale_data.get("weight_kg", 0.0))
                p_val = item.get("unit_price", sale_data.get("unit_price", 47.60))
                sub_total = item.get("price", 0.0)
                
                det_w = QWidget()
                det_l = QHBoxLayout(det_w)
                det_l.setContentsMargins(0,0,0,0)
                det_l.addStretch(1)
                for t in ["KG", f"{p_val:.2f}", f"{w_val:.3f}", f"{sub_total:.2f}"]:
                    l = QLabel(t)
                    l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    l.setStyleSheet("font-size: 13px; color: #F59E0B; font-family: monospace; border: none;")
                    l.setFixedWidth(45)
                    det_l.addWidget(l)
                item_box.addWidget(det_w)
            else:
                title_lbl = QLabel(name_str)
                title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #E2E8F0; border: none;")
                item_box.addWidget(title_lbl)

                qty = item.get("qty", 1)
                unit_label = item.get("unit", "份")
                base_p = item.get("base_price", item.get("price", 0.0) / max(1, qty))
                sub_total = item.get("price", 0.0)
                
                det_w = QWidget()
                det_l = QHBoxLayout(det_w)
                det_l.setContentsMargins(0,0,0,0)
                det_l.addStretch(1)
                for t in [unit_label, f"{base_p:.2f}", f"{qty}", f"{sub_total:.2f}"]:
                    l = QLabel(t)
                    l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    l.setStyleSheet("font-size: 13px; color: #F59E0B; font-family: monospace; border: none;")
                    l.setFixedWidth(45)
                    det_l.addWidget(l)
                item_box.addWidget(det_w)

            if tag_str:
                lbl_tag = QLabel(f"  {tag_str}")
                lbl_tag.setStyleSheet("font-size: 12px; color: #34D399; font-weight: bold; border: none;")
                item_box.addWidget(lbl_tag)

            items_layout.addLayout(item_box)

        scroll_layout.addLayout(items_layout)

        line2 = QLabel("----------------------------------------")
        line2.setAlignment(Qt.AlignCenter)
        line2.setStyleSheet("color: #475569; font-family: monospace; border: none;")
        scroll_layout.addWidget(line2)

        # 金额 (小票内)
        total_p = sum(i.get("price", 0.0) for i in cart_items)
        lbl_total = QLabel(f"应收金额：￥{total_p:.2f}")
        lbl_total.setAlignment(Qt.AlignRight)
        lbl_total.setStyleSheet("font-size: 20px; font-weight: 900; color: #34D399; border: none;")
        scroll_layout.addWidget(lbl_total)

        scroll_area.setWidget(scroll_widget)
        card_layout.addWidget(scroll_area, stretch=1)

        # 打印单据说明标语 (独立在外)
        slip_info = f"[打印] 打印单据：1张顾客单 + {m_count}张后厨制作单"
        lbl_slip_info = QLabel(slip_info)
        lbl_slip_info.setAlignment(Qt.AlignCenter)
        lbl_slip_info.setStyleSheet(
            "background: rgba(52, 211, 153, 0.12); color: #34D399; font-size: 13px; "
            "font-weight: bold; padding: 6px; border-radius: 6px; border: none;"
        )
        layout.addWidget(lbl_slip_info)

        # 2. 底部固定：操作按钮
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        self.btn_cancel = QPushButton("取消打票")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background: #334155; color: #F87171; font-weight: bold; font-size: 14px; "
            "border-radius: 8px; padding: 10px 16px; border: 1px solid #7F1D1D; }"
            "QPushButton:hover { background: #7F1D1D; color: #FFFFFF; }"
        )
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_box.addWidget(self.btn_cancel, stretch=1)

        self.btn_print = QPushButton(f"确认已收款并打票 ({self.countdown}s)")
        self.btn_print.setCursor(Qt.PointingHandCursor)
        self.btn_print.setStyleSheet(
            "QPushButton { background: #EA580C; color: white; font-weight: bold; font-size: 14px; "
            "border-radius: 8px; padding: 10px 20px; border: 1px solid #F97316; }"
            "QPushButton:hover { background: #F97316; }"
        )
        self.btn_print.clicked.connect(self._on_print_now)
        btn_box.addWidget(self.btn_print, stretch=2)

        layout.addLayout(btn_box)

        # 定时器: 倒计时 Timer & 高亮闪烁 Timer
        from PyQt5.QtCore import QTimer
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        self.flash_timer = QTimer(self)
        self.flash_timer.setInterval(500)
        self.flash_timer.timeout.connect(self._flash_tick)
        self.flash_timer.start()

    def _flash_tick(self):
        self._flash_flag = not self._flash_flag
        if self._flash_flag:
            self.notice_banner.setStyleSheet(
                "background: #EF4444; color: #FFFFFF; font-size: 14px; font-weight: 900; "
                "padding: 8px; border-radius: 8px; border: none;"
            )
        else:
            self.notice_banner.setStyleSheet(
                "background: #7F1D1D; color: #FEF08A; font-size: 14px; font-weight: 900; "
                "padding: 8px; border-radius: 8px; border: none;"
            )

    def _stop_all_timers(self):
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
        if hasattr(self, 'flash_timer') and self.flash_timer.isActive():
            self.flash_timer.stop()

    def _tick(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.btn_print.setText(f"确认已收款并打票 ({self.countdown}s)")
        else:
            self._stop_all_timers()
            self._on_print_now()

    def _on_print_now(self):
        self._stop_all_timers()
        self.accept()

    def _on_cancel(self):
        self._stop_all_timers()
        self.reject()

    def exec_(self):
        parent_w = self.parent()
        if parent_w and hasattr(parent_w, 'window'):
            parent_w = parent_w.window()
        
        # 适应小屏幕收银机（如 1024x768 / 1024x600）
        screen_h = 768
        if parent_w:
            screen_h = parent_w.height()
            try:
                blur = QGraphicsBlurEffect(parent_w)
                blur.setBlurRadius(42)
                parent_w.setGraphicsEffect(blur)
            except Exception:
                pass

        max_dlg_h = min(540, max(400, screen_h - 70))
        self.setFixedHeight(max_dlg_h)
        self.setFixedWidth(440)

        try:
            return super().exec_()
        finally:
            if parent_w:
                try:
                    parent_w.setGraphicsEffect(None)
                except Exception:
                    pass
