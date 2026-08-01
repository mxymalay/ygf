import os
import time
import subprocess
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QWidget, QGraphicsDropShadowEffect, QSizePolicy, QProgressBar, QFrame
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont

from utils.port_scanner import scan_printers
from config import load_config

def check_ygf_official_running() -> bool:
    """检测官方收银系统主程序是否正在运行"""
    try:
        cmd = 'tasklist /NH /FO CSV'
        output = subprocess.check_output(cmd, shell=True).decode('gbk', errors='ignore')
        for line in output.splitlines():
            line_lower = line.lower()
            if 'python' in line_lower:
                continue
            if ('yangguofu' in line_lower or 'ygf-pos' in line_lower or 'ygf.exe' in line_lower) and ('uninstall' not in line_lower):
                return True
    except Exception:
        pass

    serial_dir = r"C:\\YANGGUOFU-POS\\serial"
    if os.path.exists(serial_dir):
        try:
            for fname in os.listdir(serial_dir):
                if fname.startswith("log_serial_ports"):
                    fp = os.path.join(serial_dir, fname)
                    if os.path.isfile(fp) and (time.time() - os.path.getmtime(fp) < 5.0):
                        return True
        except Exception:
            pass

    return False


class NumericKeypad(QWidget):
    """虚拟触摸数字键盘 (4x4 包含 0-9, 00, ., 清空, 确定)"""

    def __init__(self, on_key_press, on_clear, on_confirm, parent=None):
        super().__init__(parent)
        self.on_key_press = on_key_press
        self.on_clear = on_clear
        self.on_confirm = on_confirm
        self._build_ui()

    def _build_ui(self):
        from PyQt5.QtWidgets import QGridLayout
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        # 键盘按键布局数据
        # (row, col, text, row_span, col_span, style_class)
        buttons = [
            (0, 0, "1", 1, 1, "num"),
            (0, 1, "2", 1, 1, "num"),
            (0, 2, "3", 1, 1, "num"),
            (0, 3, u"清空", 1, 1, "clear"),

            (1, 0, "4", 1, 1, "num"),
            (1, 1, "5", 1, 1, "num"),
            (1, 2, "6", 1, 1, "num"),
            (1, 3, u"确定", 3, 1, "confirm"),

            (2, 0, "7", 1, 1, "num"),
            (2, 1, "8", 1, 1, "num"),
            (2, 2, "9", 1, 1, "num"),

            (3, 0, "0", 1, 1, "num"),
            (3, 1, "00", 1, 1, "num"),
            (3, 2, ".", 1, 1, "num"),
        ]

        for r, c, txt, r_span, c_span, btype in buttons:
            btn = QPushButton(txt)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            if btype == "num":
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #1E293B; color: #F8FAFC; font-size: 18px; font-weight: bold;
                        border: 1px solid #334155; border-radius: 10px; min-height: 44px;
                    }
                    QPushButton:hover { background-color: #334155; border-color: #475569; }
                    QPushButton:pressed { background-color: #475569; }
                """)
                btn.clicked.connect(lambda _, t=txt: self.on_key_press(t))
            elif btype == "clear":
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #334155; color: #F8FAFC; font-size: 15px; font-weight: bold;
                        border: 1px solid #475569; border-radius: 10px; min-height: 44px;
                    }
                    QPushButton:hover { background-color: #475569; }
                    QPushButton:pressed { background-color: #64748B; }
                """)
                btn.clicked.connect(self.on_clear)
            elif btype == "confirm":
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #EA580C; color: #FFFFFF; font-size: 18px; font-weight: bold;
                        border: none; border-radius: 10px; min-height: 140px;
                    }
                    QPushButton:hover { background-color: #C2410C; }
                    QPushButton:pressed { background-color: #9A3412; }
                """)
                btn.clicked.connect(self.on_confirm)

            grid.addWidget(btn, r, c, r_span, c_span)


class LoginWindow(QDialog):
    """现代化登录界面与环境检测"""
    
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.hardware_warnings = []
        self.official_ok = False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.is_mock_mode = False
        self.active_input = None
        self._build_ui()

    def _on_debug_click(self):
        self.is_mock_mode = True
        self.accept()
        
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        self.card = QWidget()
        self.card.setObjectName("LoginCard")
        self.card.setStyleSheet("""
            QWidget#LoginCard {
                background-color: #0F172A;
                border-radius: 20px;
                border: 1px solid #1E293B;
            }
        """)
        
        # 阴影特效
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.card.setGraphicsEffect(shadow)
        
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(30, 35, 30, 35)
        card_layout.setSpacing(16)
        
        # 标题区
        self.title_lbl = QLabel(u"Realtek 外设驱动配置向导")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.title_lbl.setStyleSheet("color: #F8FAFC; font-size: 24px; font-weight: 900; letter-spacing: 1px;")
        card_layout.addWidget(self.title_lbl)
        
        self.sub_lbl = QLabel(u"Hardware Device Driver Setup Wizard")
        self.sub_lbl.setAlignment(Qt.AlignCenter)
        self.sub_lbl.setStyleSheet("color: #64748B; font-size: 13px; margin-bottom: 10px;")
        card_layout.addWidget(self.sub_lbl)
        
        # 输入表单区 (初始可见)
        self.form_widget = QWidget()
        form_layout = QVBoxLayout(self.form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)
        
        self.txt_user = QLineEdit("")
        self.txt_user.setPlaceholderText("请输入账号")
        self.txt_user.setStyleSheet("""
            QLineEdit {
                background-color: #1E293B; color: #F8FAFC; font-size: 16px; font-weight: bold;
                padding: 12px 14px; border-radius: 10px; border: 2px solid #334155;
            }
            QLineEdit:focus { border: 2px solid #38BDF8; }
        """)
        self.txt_user.installEventFilter(self)
        form_layout.addWidget(self.txt_user)
        
        self.txt_pwd = QLineEdit("")
        self.txt_pwd.setPlaceholderText("请输入密码")
        self.txt_pwd.setEchoMode(QLineEdit.Password)
        self.txt_pwd.setStyleSheet(self.txt_user.styleSheet())
        self.txt_pwd.installEventFilter(self)
        form_layout.addWidget(self.txt_pwd)

        # 默认选中账号输入框
        self.active_input = self.txt_user
        
        self.btn_login = QPushButton(u"确认登录")
        self.btn_login.setCursor(Qt.PointingHandCursor)
        self.btn_login.setStyleSheet("""
            QPushButton {
                background-color: #EA580C; color: white; font-size: 17px; font-weight: bold;
                padding: 12px 0; border-radius: 10px; border: none; margin-top: 4px;
            }
            QPushButton:hover { background-color: #C2410C; }
            QPushButton:pressed { background-color: #9A3412; }
        """)
        self.btn_login.clicked.connect(self._on_login_click)
        form_layout.addWidget(self.btn_login)

        # 数字触控键盘
        self.keypad = NumericKeypad(
            on_key_press=self._on_keypad_press,
            on_clear=self._on_keypad_clear,
            on_confirm=self._on_login_click
        )
        form_layout.addWidget(self.keypad)
        
        self.lbl_err = QLabel("")
        self.lbl_err.setAlignment(Qt.AlignCenter)
        self.lbl_err.setStyleSheet("color: #EF4444; font-size: 13px; font-weight: bold;")
        form_layout.addWidget(self.lbl_err)
        
        card_layout.addWidget(self.form_widget)
        
        # 检测过程区 (初始隐藏)
        self.check_widget = QWidget()
        self.check_widget.hide()
        check_layout = QVBoxLayout(self.check_widget)
        check_layout.setContentsMargins(0, 0, 0, 0)
        check_layout.setSpacing(12)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1E293B; border-radius: 3px; border: none;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38BDF8, stop:1 #818CF8);
                border-radius: 3px;
            }
        """)
        check_layout.addWidget(self.progress_bar)

        # 三项卡片
        self.card1, self.lbl_title1, self.lbl_badge1 = self._create_check_card(u"💻  官方收银运行环境")
        self.card2, self.lbl_title2, self.lbl_badge2 = self._create_check_card(u"🖨️  热敏小票打印机外设")
        self.card3, self.lbl_title3, self.lbl_badge3 = self._create_check_card(u"💳  收钱吧串口通信联动")

        check_layout.addWidget(self.card1)
        check_layout.addWidget(self.card2)
        check_layout.addWidget(self.card3)

        card_layout.addWidget(self.check_widget)
        card_layout.addStretch()
        
        # 底部按键组 (取消安装 & 跳过检测)
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        bottom_bar.setSpacing(24)
        bottom_bar.setAlignment(Qt.AlignCenter)
        
        self.btn_close = QPushButton(u"取消安装")
        self.btn_close.setFocusPolicy(Qt.NoFocus)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setStyleSheet("""
            QPushButton {
                color: #64748B; background: transparent; border: none; font-size: 14px; font-weight: bold; outline: none;
            }
            QPushButton:hover { color: #EF4444; }
            QPushButton:focus { outline: none; border: none; }
        """)
        self.btn_close.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_close)
        
        self.btn_debug = QPushButton(u"跳过检测 (模拟调试模式)")
        self.btn_debug.setFocusPolicy(Qt.NoFocus)
        self.btn_debug.hide()
        self.btn_debug.setCursor(Qt.PointingHandCursor)
        self.btn_debug.setStyleSheet("""
            QPushButton {
                color: #64748B; background: transparent; border: none; font-size: 14px; font-weight: bold; outline: none;
            }
            QPushButton:hover { color: #F59E0B; }
            QPushButton:focus { outline: none; border: none; }
        """)
        self.btn_debug.clicked.connect(self._on_debug_click)
        bottom_bar.addWidget(self.btn_debug)
        
        card_layout.addLayout(bottom_bar)
        main_layout.addWidget(self.card)

    def _create_check_card(self, title_str):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border-radius: 10px;
                border: 1px solid #334155;
            }
        """)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        
        lbl_title = QLabel(title_str)
        lbl_title.setStyleSheet("color: #F8FAFC; font-size: 14px; font-weight: bold; border: none;")
        lay.addWidget(lbl_title)
        lay.addStretch()
        
        lbl_badge = QLabel(u"等待检测")
        lbl_badge.setStyleSheet("""
            QLabel {
                color: #94A3B8; background-color: #0F172A; font-size: 12px; font-weight: bold;
                padding: 4px 10px; border-radius: 6px; border: 1px solid #334155;
            }
        """)
        lay.addWidget(lbl_badge)
        return card, lbl_title, lbl_badge

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        if event.type() == QEvent.FocusIn:
            if obj in (self.txt_user, self.txt_pwd):
                self.active_input = obj
        return super().eventFilter(obj, event)

    def _set_active_input(self, widget):
        self.active_input = widget

    def _on_keypad_press(self, text):
        if self.active_input and isinstance(self.active_input, QLineEdit):
            self.active_input.insert(text)
            self.active_input.setFocus()

    def _on_keypad_clear(self):
        if self.active_input and isinstance(self.active_input, QLineEdit):
            self.active_input.clear()
            self.active_input.setFocus()

    def _on_login_click(self):
        user = self.txt_user.text().strip()
        pwd = self.txt_pwd.text().strip()
        
        if user == "002" and pwd == "002":
            self.form_widget.hide()
            
            # 取消伪装，显示真实标题
            self.title_lbl.setText(u"POS辅助系统")
            self.sub_lbl.setText(u"POS Auxiliary System Environment Check")
            self.btn_close.setText(u"退出系统")
            
            self.check_widget.show()
            self.lbl_err.setText("")
            QTimer.singleShot(100, self._check_official_software)
        else:
            self.lbl_err.setText(u"账号或密码错误，请重试！")
            
    def _check_official_software(self):
        self.progress_bar.setValue(15)
        self.lbl_badge1.setText(u"正在检测...")
        self.lbl_badge1.setStyleSheet("color: #38BDF8; background-color: #0369A1; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #0EA5E9;")
        QTimer.singleShot(250, self._do_check_official_software)
        
    def _do_check_official_software(self):
        self.progress_bar.setValue(35)
        if check_ygf_official_running():
            self.official_ok = True
            self.lbl_badge1.setText(u"✔ 运行正常")
            self.lbl_badge1.setStyleSheet("color: #34D399; background-color: #064E3B; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #059669;")
        else:
            self.official_ok = False
            self.lbl_badge1.setText(u"✖ 未运行")
            self.lbl_badge1.setStyleSheet("color: #F87171; background-color: #7F1D1D; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #DC2626;")
            self.hardware_warnings.append("官方收银软件未运行")
            
        QTimer.singleShot(250, self._check_printer)

    def _check_printer(self):
        self.progress_bar.setValue(50)
        self.lbl_badge2.setText(u"正在检测...")
        self.lbl_badge2.setStyleSheet("color: #38BDF8; background-color: #0369A1; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #0EA5E9;")
        QTimer.singleShot(250, self._do_check_printer)

    def _do_check_printer(self):
        self.progress_bar.setValue(70)
        printers = scan_printers()
        if printers:
            self.lbl_badge2.setText(u"✔ 设备就绪")
            self.lbl_badge2.setStyleSheet("color: #34D399; background-color: #064E3B; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #059669;")
        else:
            self.lbl_badge2.setText(u"⚠️ 未连接")
            self.lbl_badge2.setStyleSheet("color: #FBBF24; background-color: #78350F; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #D97706;")
            self.hardware_warnings.append("打印机未连接")
        
        QTimer.singleShot(250, self._check_shouqianba)

    def _check_shouqianba(self):
        self.progress_bar.setValue(85)
        self.lbl_badge3.setText(u"正在检测...")
        self.lbl_badge3.setStyleSheet("color: #38BDF8; background-color: #0369A1; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #0EA5E9;")
        QTimer.singleShot(250, self._do_check_shouqianba)

    def _do_check_shouqianba(self):
        self.progress_bar.setValue(100)
        from core.shouqianba_sender import test_shouqianba_port
        ok, msg = test_shouqianba_port(self.config)
        if ok:
            self.lbl_badge3.setText(u"✔ 串口通畅")
            self.lbl_badge3.setStyleSheet("color: #34D399; background-color: #064E3B; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #059669;")
        else:
            port = self.config.get("shouqianba_port", "COM1")
            self.lbl_badge3.setText(f"⚠️ {port} 未连通")
            self.lbl_badge3.setStyleSheet("color: #FBBF24; background-color: #78350F; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #D97706;")
            self.hardware_warnings.append(f"收钱吧 {port} 未连通")

        if self.official_ok:
            QTimer.singleShot(400, self.accept)
        else:
            self.btn_debug.show()

    def _on_debug_click(self):
        self.is_mock_mode = True
        self.accept()
