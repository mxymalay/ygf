import os
import re
import time
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QWidget, QGraphicsDropShadowEffect, QSizePolicy, QProgressBar, QFrame
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont

from utils.port_scanner import scan_printers
from config import save_config, app_branding
from utils.window_utils import find_official_window_handle, is_official_window_configured
from core.app_logger import log_event, CAT_SYSTEM
from core.printer_relay_mode import validate_relay_config

def check_ygf_official_running(config=None) -> bool:
    """检测已配置的官方 POS 窗口是否正在运行。"""
    # Window identity is the shared truth for startup checks and foreground
    # switching.  The serial log is a data source, not proof that the correct
    # POS window is open.
    return find_official_window_handle(config) is not None


def probe_dibal_scale_connection(config, timeout_seconds=2.0):
    """主动查询 ACS-G315，并返回 ``(是否成功, 现场可读说明)``。

    不能只发送一次 ``$`` 后等 350ms：在 com0com / ScaleBridge 场景中，
    Windows 7 首次打开虚拟端口、服务线程转发和秤的 5Hz 查询周期叠加后，
    首包常常超过 350ms 才抵达。旧逻辑把这种短暂等待误报成“未连接”，
    但随后真正的读取器又能够正常读数。
    """
    ser = None
    port = str(config.get("scale_port", "COM3") or "COM3").strip().upper()
    try:
        import serial

        baudrate = int(config.get("scale_baudrate", 9600))
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1,
            write_timeout=0.5,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        ser.dtr = True
        ser.rts = False
        ser.reset_input_buffer()
        deadline = time.monotonic() + max(0.6, float(timeout_seconds))
        next_query = 0.0
        received = bytearray()
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_query:
                ser.write(b"$")
                ser.flush()
                next_query = now + 0.2

            waiting = int(getattr(ser, "in_waiting", 0) or 0)
            data = ser.read(min(64, waiting) if waiting else 1)
            if not data:
                continue
            received.extend(data)
            # 允许分片回包；只要收到一条合法数字帧即可确认链路可用。
            text = received.decode("ascii", errors="ignore")
            matches = re.findall(r"(?<!\d)([+-]?\d{1,5}\.\d{1,4})(?!\d)", text)
            if matches:
                return True, u"%s 已收到重量回包 %s kg" % (port, matches[-1])
            if len(received) > 256:
                del received[:-64]
        if received:
            preview = received.decode("ascii", errors="replace").strip()[:80]
            return False, u"%s 已打开，但未解析到有效重量回包（原始数据：%s）" % (port, preview)
        return False, u"%s 可以打开，但 %.1f 秒内没有收到秤回包" % (port, float(timeout_seconds))
    except Exception as exc:
        text = str(exc)
        winerror = getattr(exc, "winerror", None)
        lowered = text.lower()
        is_busy = (
            winerror in (5, 13, 32)
            or "permission denied" in lowered
            or "access is denied" in lowered
            or "already open" in lowered
            or "in use" in lowered
        )
        if is_busy:
            return False, u"%s 被其它程序占用，当前无法直接打开" % port
        return False, u"无法打开 %s：%s" % (port, text or exc.__class__.__name__)
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


def check_dibal_scale_connection(config) -> bool:
    """兼容旧调用方：只返回 ACS-G315 主动查询是否成功。"""
    return probe_dibal_scale_connection(config)[0]


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
        self.setFixedSize(580, 680)
        self.is_mock_mode = False
        self.active_input = None
        self.branding = app_branding(self.config)
        self._build_ui()

    def _on_debug_click(self):
        self.is_mock_mode = True
        self.accept()

    def _run_check_step_safely(self, label, callback, fallback=None):
        """Keep a hardware-check timer exception from terminating Win7 Qt."""
        try:
            callback()
        except Exception as exc:
            detail = "%s: %s" % (label, exc)
            log_event(CAT_SYSTEM, "登录检测步骤异常", detail)
            self.hardware_warnings.append(detail)
            self.lbl_err.setText(u"%s；已跳过此项检测" % detail)
            if fallback is not None:
                QTimer.singleShot(0, fallback)
            else:
                self.btn_debug.show()
        
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
        self.title_lbl = QLabel(self.branding["login_title"])
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.title_lbl.setStyleSheet("color: #F8FAFC; font-size: 24px; font-weight: 900; letter-spacing: 1px;")
        card_layout.addWidget(self.title_lbl)
        
        self.sub_lbl = QLabel(self.branding["login_subtitle"])
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

        # 四项独立卡片 (官方 POS 与 COM 秤串口分开检测)
        self.card1, self.lbl_title1, self.lbl_badge1 = self._create_check_card(u"💻  官方 POS 窗口（按配置识别）")
        self.card1_sub, self.lbl_title1_sub, self.lbl_badge1_sub = self._create_check_card(u"⚖️  COM 电子秤串口数据源")
        # 使用 Win7 字体稳定支持的单色符号，避免打印机 Emoji 显示成方框。
        self.card2, self.lbl_title2, self.lbl_badge2 = self._create_check_card(u"♨  热敏打印机与打印机中继")
        self.card3, self.lbl_title3, self.lbl_badge3 = self._create_check_card(u"💳  收钱吧串口通信联动")

        check_layout.addWidget(self.card1)
        check_layout.addWidget(self.card1_sub)
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
        
        self.btn_debug = QPushButton(u"🧪 切换为模拟调试模式")
        self.btn_debug.setFocusPolicy(Qt.NoFocus)
        self.btn_debug.hide()
        self.btn_debug.setCursor(Qt.PointingHandCursor)
        self.btn_debug.setStyleSheet("""
            QPushButton {
                color: #64748B; background: transparent; border: none; font-size: 13px; font-weight: bold; outline: none;
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
            # The first production startup must bind the real official POS
            # window before any detection or switching is allowed.
            if not self._ensure_official_window_selection():
                self.form_widget.hide()
                self.title_lbl.setText(self.branding["login_title"])
                self.sub_lbl.setText(u"请先完成官方 POS 窗口选择 · %s" % self.branding["category_label"])
                self.btn_close.setText(u"退出系统")
                self.check_widget.show()
                self.lbl_err.setText(u"未完成官方 POS 窗口配置；检测结束后可进入模拟模式或退出。")
                QTimer.singleShot(100, lambda: self._run_check_step_safely(
                    u"官方 POS 检测", self._check_official_software, self._check_printer
                ))
                return
            self.form_widget.hide()
            
            # 登录文案跟随快捷图标对应的应用分类，不再固定写成驱动向导。
            self.title_lbl.setText(self.branding["login_title"])
            self.sub_lbl.setText(self.branding["login_subtitle"])
            self.btn_close.setText(u"退出系统")
            
            self.check_widget.show()
            self.lbl_err.setText("")
            QTimer.singleShot(100, lambda: self._run_check_step_safely(
                u"官方 POS 检测", self._check_official_software, self._check_printer
            ))
        else:
            self.lbl_err.setText(u"账号或密码错误，请重试！")

    def _ensure_official_window_selection(self):
        """Prompt once for the official POS window when no identity is saved."""
        if is_official_window_configured(self.config):
            return True
        from ui.official_window_dialog import OfficialWindowPickerDialog

        dialog = OfficialWindowPickerDialog(parent=self)
        if dialog.exec_() != QDialog.Accepted or not dialog.selected_window:
            self.hardware_warnings.append("尚未选择官方 POS 窗口")
            return False
        from utils.window_utils import apply_official_window_selection
        if not apply_official_window_selection(self.config, dialog.selected_window):
            self.hardware_warnings.append("官方 POS 窗口选择无效")
            return False
        save_config(self.config)
        return True
            
    def _check_official_software(self):
        log_event(CAT_SYSTEM, "登录检测阶段", "开始官方 POS 与电子秤检测")
        self.progress_bar.setValue(15)
        self.lbl_badge1.setText(u"正在检测...")
        self.lbl_badge1.setStyleSheet("color: #38BDF8; background-color: #0369A1; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #0EA5E9;")
        self.lbl_badge1_sub.setText(u"正在检测...")
        self.lbl_badge1_sub.setStyleSheet("color: #38BDF8; background-color: #0369A1; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #0EA5E9;")
        QTimer.singleShot(250, lambda: self._run_check_step_safely(
            u"官方 POS 与电子秤检测", self._do_check_official_software, self._check_printer
        ))
        
    def _do_check_official_software(self):
        log_event(CAT_SYSTEM, "登录检测阶段", "执行官方 POS 与电子秤检测")
        self.progress_bar.setValue(35)
        official_running = check_ygf_official_running(self.config)
        scale_source = self.config.get("scale_source", "official")
        # 官方模式不碰 COM；直连/桥接模式才主动查询本 POS 使用的端口。
        # 该探测会重试 2 秒，避免 Win7/com0com 首包延迟造成假失败。
        if scale_source == "com":
            scale_ok, scale_detail = probe_dibal_scale_connection(self.config)
        else:
            scale_ok, scale_detail = False, u"当前配置跟随官方 POS，不打开独立 COM"

        # 1. 官方 POS 运行状态指示
        if not is_official_window_configured(self.config):
            self.lbl_badge1.setText(u"✖ 未配置官方窗口")
            self.lbl_badge1.setStyleSheet("color: #F87171; background-color: #7F1D1D; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #DC2626;")
        elif official_running:
            self.lbl_badge1.setText(u"✔ 官方 POS 运行中")
            self.lbl_badge1.setStyleSheet("color: #34D399; background-color: #064E3B; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #059669;")
        else:
            self.lbl_badge1.setText(u"✖ 未找到官方 POS 窗口")
            self.lbl_badge1.setStyleSheet("color: #F87171; background-color: #7F1D1D; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #DC2626;")

        # 2. COM 电子秤串口连接指示
        port = self.config.get("scale_port", "COM3")
        if scale_source != "com":
            self.lbl_badge1_sub.setText(u"— 跟随官方读数，无需独立 COM")
            self.lbl_badge1_sub.setStyleSheet("color: #BAE6FD; background-color: #0C4A6E; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #0284C7;")
        elif scale_ok:
            self.lbl_badge1_sub.setText(f"✔ {scale_detail}")
            self.lbl_badge1_sub.setStyleSheet("color: #34D399; background-color: #064E3B; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #059669;")
        else:
            self.lbl_badge1_sub.setText(f"! {scale_detail}")
            self.lbl_badge1_sub.setStyleSheet("color: #FBBF24; background-color: #78350F; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #D97706;")

        # 3. 准入判决：官方 POS 窗口、或本 POS 的已配置称通道，任一可用
        # 就允许进入。未选中的通道失败只显示告警，不能把一个可工作的
        # 官方读数链路误判为整套系统不能使用。
        if official_running or scale_ok:
            self.official_ok = True
        else:
            self.official_ok = False
            if scale_source == "official":
                if not is_official_window_configured(self.config):
                    self.hardware_warnings.append("尚未配置官方 POS 窗口识别词")
                else:
                    self.hardware_warnings.append("当前识别词未找到官方 POS 窗口")
            else:
                self.hardware_warnings.append("当前选择 COM 称重，但秤串口检测失败：%s" % scale_detail)
        if official_running and scale_source == "com" and not scale_ok:
            self.hardware_warnings.append(
                "官方 POS 已运行；本 POS 的 %s 尚未验证：%s" % (port, scale_detail)
            )
            
        QTimer.singleShot(250, self._check_printer)

    def _check_printer(self):
        log_event(CAT_SYSTEM, "登录检测阶段", "开始打印机检测")
        self.progress_bar.setValue(50)
        self.lbl_badge2.setText(u"正在检测...")
        self.lbl_badge2.setStyleSheet("color: #38BDF8; background-color: #0369A1; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #0EA5E9;")
        QTimer.singleShot(250, lambda: self._run_check_step_safely(
            u"打印机检测", self._do_check_printer, self._check_shouqianba
        ))

    def _do_check_printer(self):
        log_event(CAT_SYSTEM, "登录检测阶段", "执行打印机检测")
        self.progress_bar.setValue(70)
        printers = scan_printers()
        relay_ok, relay_detail = self._check_printer_relay()
        if printers and relay_ok:
            self.lbl_badge2.setText(u"✔ 打印机/中继正常")
            self.lbl_badge2.setStyleSheet("color: #34D399; background-color: #064E3B; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #059669;")
        elif printers:
            self.lbl_badge2.setText(u"✔ 打印机就绪 · %s" % relay_detail)
            self.lbl_badge2.setStyleSheet("color: #BAE6FD; background-color: #0C4A6E; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #0284C7;")
        else:
            self.lbl_badge2.setText(u"⚠️ 未连接")
            self.lbl_badge2.setStyleSheet("color: #FBBF24; background-color: #78350F; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #D97706;")
            self.hardware_warnings.append("打印机未连接")
        if not relay_ok and bool(self.config.get("printer_relay_enabled", False)):
            self.hardware_warnings.append(u"打印机中继：%s" % relay_detail)
        
        QTimer.singleShot(250, self._check_shouqianba)

    def _check_printer_relay(self):
        """Check configured printer-relay transport without starting it."""
        if not bool(self.config.get("printer_relay_enabled", False)):
            return True, u"未启用（兼容模式）"
        try:
            report = validate_relay_config(self.config, check_windows=True)
        except Exception as exc:
            return False, u"检测异常：%s" % exc
        if report.get("errors"):
            return False, u"配置异常：%s" % "；".join(report["errors"])
        if report.get("warnings"):
            return True, u"已配置（%s）" % "；".join(report["warnings"])
        return True, u"已配置并通过队列检查"

    def _check_shouqianba(self):
        log_event(CAT_SYSTEM, "登录检测阶段", "开始收钱吧检测")
        self.progress_bar.setValue(85)
        self.lbl_badge3.setText(u"正在检测...")
        self.lbl_badge3.setStyleSheet("color: #38BDF8; background-color: #0369A1; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #0EA5E9;")
        QTimer.singleShot(250, lambda: self._run_check_step_safely(
            u"收钱吧检测", self._do_check_shouqianba
        ))

    def _do_check_shouqianba(self):
        log_event(CAT_SYSTEM, "登录检测阶段", "执行收钱吧检测，进度 100%")
        self.progress_bar.setValue(100)
        try:
            from core.shouqianba_sender import test_shouqianba_port
            ok, msg = test_shouqianba_port(self.config)
        except Exception as exc:
            # 硬件自检失败只能形成告警，不能让 Qt 定时回调抛出异常并终止
            # 整个 POS 进程。详细原因保留在控制台，便于现场排障。
            ok = False
            msg = f"检测异常: {exc}"
            print(f"[登录检测] 收钱吧检测异常: {exc}")
        if ok:
            self.lbl_badge3.setText(u"✔ 串口通畅")
            self.lbl_badge3.setStyleSheet("color: #34D399; background-color: #064E3B; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #059669;")
        else:
            port = self.config.get("shouqianba_port", "COM10")
            self.lbl_badge3.setText(f"⚠️ {port} 未连通")
            self.lbl_badge3.setStyleSheet("color: #FBBF24; background-color: #78350F; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 6px; border: 1px solid #D97706;")
            self.hardware_warnings.append(f"收钱吧 {port} 未连通")

        if self.official_ok:
            log_event(CAT_SYSTEM, "登录检测完成", "硬件检测结束，准备进入主界面")
            QTimer.singleShot(400, self.accept)
        else:
            log_event(CAT_SYSTEM, "登录检测完成", "硬件检测结束，需要选择模拟模式或退出")
            self.btn_debug.show()

    def _on_debug_click(self):
        self.is_mock_mode = True
        self.accept()
