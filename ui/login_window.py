import os
import time
import subprocess
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QWidget, QGraphicsDropShadowEffect
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


class LoginWindow(QDialog):
    """现代化登录界面与环境检测"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.is_mock_mode = False
        self._build_ui()

    def _on_debug_click(self):
        self.is_mock_mode = True
        self.accept()
        
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
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
        card_layout.setContentsMargins(40, 50, 40, 50)
        card_layout.setSpacing(24)
        
        # 标题区
        self.title_lbl = QLabel(u"Realtek 外设驱动配置向导")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.title_lbl.setStyleSheet("color: #F8FAFC; font-size: 26px; font-weight: 900; letter-spacing: 2px;")
        card_layout.addWidget(self.title_lbl)
        
        self.sub_lbl = QLabel(u"Hardware Device Driver Setup Wizard")
        self.sub_lbl.setAlignment(Qt.AlignCenter)
        self.sub_lbl.setStyleSheet("color: #64748B; font-size: 14px; margin-bottom: 20px;")
        card_layout.addWidget(self.sub_lbl)
        
        # 输入表单区 (初始可见)
        self.form_widget = QWidget()
        form_layout = QVBoxLayout(self.form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(16)
        
        self.txt_user = QLineEdit("")
        self.txt_user.setPlaceholderText("请输入管理员账号")
        self.txt_user.setStyleSheet("""
            QLineEdit {
                background-color: #1E293B; color: #F8FAFC; font-size: 16px; font-weight: bold;
                padding: 14px 16px; border-radius: 12px; border: 2px solid #334155;
            }
            QLineEdit:focus { border: 2px solid #38BDF8; }
        """)
        form_layout.addWidget(self.txt_user)
        
        self.txt_pwd = QLineEdit("")
        self.txt_pwd.setPlaceholderText("请输入管理员密码")
        self.txt_pwd.setEchoMode(QLineEdit.Password)
        self.txt_pwd.setStyleSheet(self.txt_user.styleSheet())
        form_layout.addWidget(self.txt_pwd)
        
        self.btn_login = QPushButton(u"验证权限并启动向导")
        self.btn_login.setCursor(Qt.PointingHandCursor)
        self.btn_login.setStyleSheet("""
            QPushButton {
                background-color: #EA580C; color: white; font-size: 18px; font-weight: bold;
                padding: 14px 0; border-radius: 12px; border: none; margin-top: 10px;
            }
            QPushButton:hover { background-color: #C2410C; }
            QPushButton:pressed { background-color: #9A3412; }
        """)
        self.btn_login.clicked.connect(self._on_login_click)
        form_layout.addWidget(self.btn_login)
        
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
        check_layout.setSpacing(20)
        
        self.lbl_check1 = QLabel(u"⌛ 官方收银环境检测：等待中...")
        self.lbl_check1.setStyleSheet("color: #9CA3AF; font-size: 14px;")
        check_layout.addWidget(self.lbl_check1)
        
        self.lbl_check2 = QLabel(u"⌛ 打印机外设检测：等待中...")
        self.lbl_check2.setStyleSheet("color: #9CA3AF; font-size: 14px;")
        check_layout.addWidget(self.lbl_check2)
        
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
            QTimer.singleShot(500, self._check_official_software)
        else:
            self.lbl_err.setText(u"账号或密码错误，请重试！")
            
    def _check_official_software(self):
        self.lbl_check1.setText(u"🔄 官方收银环境检测：正在检测...")
        self.lbl_check1.setStyleSheet("color: #38BDF8; font-size: 14px; font-weight: bold;")
        QTimer.singleShot(600, self._do_check_official_software)
        
    def _do_check_official_software(self):
        if check_ygf_official_running():
            self.lbl_check1.setText(u"✔ 官方收银环境检测：通过")
            self.lbl_check1.setStyleSheet("color: #10B981; font-size: 14px; font-weight: bold;")
            QTimer.singleShot(400, self._check_printer)
        else:
            self.lbl_check1.setText(u"✖ 官方收银环境检测：失败 (未运行)")
            self.lbl_check1.setStyleSheet("color: #EF4444; font-size: 14px; font-weight: bold;")
            self.btn_debug.show()
            
    def _check_printer(self):
        self.lbl_check2.setText(u"🔄 打印机外设检测：正在检测...")
        self.lbl_check2.setStyleSheet("color: #38BDF8; font-size: 14px; font-weight: bold;")
        QTimer.singleShot(600, self._do_check_printer)

    def _do_check_printer(self):
        printers = scan_printers()
        if printers:
            self.lbl_check2.setText(u"✔ 打印机外设检测：通过")
            self.lbl_check2.setStyleSheet("color: #10B981; font-size: 14px; font-weight: bold;")
            QTimer.singleShot(800, self.accept)
        else:
            self.lbl_check2.setText(u"✖ 打印机外设检测：异常 (无驱动)")
            self.lbl_check2.setStyleSheet("color: #EF4444; font-size: 14px; font-weight: bold;")
            self.btn_debug.show()

    def _on_debug_click(self):
        self.is_mock_mode = True
        self.accept()
