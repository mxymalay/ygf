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
        self.setFixedSize(480, 560)
        
        self._build_ui()
        
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
        title_lbl = QLabel(u"Realtek 外设驱动配置向导")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("color: #F8FAFC; font-size: 26px; font-weight: 900; letter-spacing: 2px;")
        card_layout.addWidget(title_lbl)
        
        sub_lbl = QLabel(u"Hardware Device Driver Setup Wizard")
        sub_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl.setStyleSheet("color: #64748B; font-size: 14px; margin-bottom: 20px;")
        card_layout.addWidget(sub_lbl)
        
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
        
        self.lbl_status = QLabel(u"准备系统环境...")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color: #38BDF8; font-size: 16px; font-weight: bold;")
        check_layout.addWidget(self.lbl_status)
        
        self.lbl_detail = QLabel(u"正在初始化验证模块")
        self.lbl_detail.setAlignment(Qt.AlignCenter)
        self.lbl_detail.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        check_layout.addWidget(self.lbl_detail)
        
        self.btn_debug = QPushButton(u"跳过检测 (模拟调试模式)")
        self.btn_debug.hide()
        self.btn_debug.setCursor(Qt.PointingHandCursor)
        self.btn_debug.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #F59E0B; font-size: 15px; font-weight: bold;
                padding: 14px 0; border-radius: 12px; border: 2px solid #F59E0B; margin-top: 20px;
            }
            QPushButton:hover { background-color: rgba(245, 158, 11, 0.1); }
        """)
        self.btn_debug.clicked.connect(self.accept)
        check_layout.addWidget(self.btn_debug)
        
        card_layout.addWidget(self.check_widget)
        card_layout.addStretch()
        
        # 退出按钮
        btn_close = QPushButton(u"取消安装")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                color: #64748B; background: transparent; border: none; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { color: #EF4444; }
        """)
        btn_close.clicked.connect(self.reject)
        card_layout.addWidget(btn_close)
        
        main_layout.addWidget(self.card)
        
    def _on_login_click(self):
        user = self.txt_user.text().strip()
        pwd = self.txt_pwd.text().strip()
        
        if user == "002" and pwd == "002":
            self.form_widget.hide()
            self.check_widget.show()
            self.lbl_err.setText("")
            QTimer.singleShot(500, self._check_official_software)
        else:
            self.lbl_err.setText(u"账号或密码错误，请重试！")
            
    def _check_official_software(self):
        self.lbl_status.setText(u"正在检测官方环境...")
        self.lbl_detail.setText(u"检测官方收银秤重服务是否已启动")
        self.lbl_status.setStyleSheet("color: #38BDF8; font-size: 16px; font-weight: bold;")
        
        if check_ygf_official_running():
            QTimer.singleShot(800, self._check_printer)
        else:
            self.lbl_status.setText(u"环境检测失败")
            self.lbl_status.setStyleSheet("color: #EF4444; font-size: 16px; font-weight: bold;")
            self.lbl_detail.setText(u"未检测到官方收银系统在运行")
            self.btn_debug.show()
            
    def _check_printer(self):
        self.lbl_status.setText(u"正在检测外设...")
        self.lbl_detail.setText(u"扫描系统打印机列表")
        
        printers = scan_printers()
        if printers:
            self.lbl_status.setText(u"所有检测通过！")
            self.lbl_status.setStyleSheet("color: #10B981; font-size: 18px; font-weight: 900;")
            self.lbl_detail.setText(u"正在进入系统主界面...")
            QTimer.singleShot(800, self.accept)
        else:
            self.lbl_status.setText(u"外设检测异常")
            self.lbl_status.setStyleSheet("color: #F59E0B; font-size: 16px; font-weight: bold;")
            self.lbl_detail.setText(u"未检测到任何已安装的打印机驱动")
            self.btn_debug.show()
