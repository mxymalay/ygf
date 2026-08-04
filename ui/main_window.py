"""
主窗口 — 原生竖向侧边栏布局 (收银台、订单查询、叫号设置、系统设置)
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QMainWindow, QStackedWidget, QStatusBar, QLabel, QWidget, QHBoxLayout
)
from PyQt5.QtCore import QTimer, Qt
from datetime import datetime

from core.database import Database
from core.call_number_manager import CallNumberManager
from ui.sidebar import SideNavBar
from ui.sale_widget import SaleWidget
from ui.history_widget import HistoryWidget
from ui.report_widget import ReportWidget
from ui.queue_widget import QueueWidget
from ui.settings_widget import SettingsWidget
from ui.log_widget import LogWidget
from ui.switch_settings_widget import SwitchSettingsWidget
from ui.styles import DARK_STYLE, LIGHT_STYLE


class MainWindow(QMainWindow):
    """应用主窗口"""

    def __init__(self, config, hardware_warnings=None):
        super().__init__()
        self.config = config
        self.hardware_warnings = hardware_warnings or []
        self.db = Database()
        self.call_mgr = CallNumberManager(config)
        self.is_dark_mode = True

        self._init_window()
        self._build_ui()
        self._setup_clock()
        QTimer.singleShot(600, self._check_first_run_price)

    def _init_window(self):
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setMinimumSize(960, 640)
        self.resize(1180, 760)
        self.setStyleSheet(DARK_STYLE)



    def _build_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. 经典杨国福红 竖向固定侧边栏 (SideNavBar)
        self.sidebar = SideNavBar()
        self.sidebar.page_changed.connect(self._on_page_changed)
        self.sidebar.update_requested.connect(self._on_auto_update)
        self.sidebar.minimized_requested.connect(self.showMinimized)
        self.sidebar.exit_requested.connect(self.close)

        main_layout.addWidget(self.sidebar)

        # 2. 页面堆栈容器 (QStackedWidget)
        self.stack = QStackedWidget()

        # 页面 0: 称重收银 (收银台)
        self.sale_page = SaleWidget(self.config, self.db, self.call_mgr)
        self.stack.addWidget(self.sale_page)

        # 页面 1: 订单查询
        self.history_page = HistoryWidget(self.db, printer=self.sale_page.printer, config=self.config)
        self.stack.addWidget(self.history_page)

        # 页面 2: 交班报表
        self.report_page = ReportWidget(self.db, printer=self.sale_page.printer, config=self.config)
        self.stack.addWidget(self.report_page)

        # 页面 3: 外卖 RAW 打印中继与排序
        from ui.takeout_sorting_widget import TakeoutSortingWidget
        from core.takeout_proxy_host import TakeoutProxyController
        # This object only controls a detached per-user proxy host.  It does
        # not own the TCP listener, so closing this window cannot cut off the
        # official POS's configured external-order printer channel.
        self.takeout_interceptor = TakeoutProxyController(self.config)
        self.takeout_page = TakeoutSortingWidget(
            config=self.config, printer=self.sale_page.printer, interceptor=self.takeout_interceptor
        )
        if self.config.get("takeout_interceptor_enabled", False) and self.config.get("takeout_proxy_queue_name", "").strip():
            self.takeout_interceptor.start()
        self.stack.addWidget(self.takeout_page)

        # 页面 4: 叫号设置 (独立叫号避重菜单)
        self.queue_page = QueueWidget(self.config, self.call_mgr)
        self.stack.addWidget(self.queue_page)

        # 页面 5: 切换算法设置
        self.switch_settings_page = SwitchSettingsWidget(self.config)
        self.stack.addWidget(self.switch_settings_page)

        # 页面 6: 系统设置
        self.settings_page = SettingsWidget(self.config)
        self.stack.addWidget(self.settings_page)

        # 页面 7: 运营日志
        self.log_page = LogWidget()
        self.stack.addWidget(self.log_page)

        main_layout.addWidget(self.stack, stretch=1)

        # 3. 底部状态栏
        self.status = QStatusBar()
        self.status.setStyleSheet("QStatusBar::item { border: none; }")
        self.setStatusBar(self.status)

        self.lbl_hw_status = QLabel()
        self.status.addWidget(self.lbl_hw_status)
        self.update_hardware_warnings(self.hardware_warnings)

        from config import APP_VERSION
        self.lbl_ver = QLabel(f"版本: {APP_VERSION}")
        self.lbl_ver.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: bold; padding-right: 16px;")
        self.status.addPermanentWidget(self.lbl_ver)

        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("color: #9CA3AF; font-size: 13px; font-weight: bold; padding-right: 16px;")
        self.status.addPermanentWidget(self.lbl_clock)

        # 4. 智能双系统切换与老板键组件初始化
        self._init_smart_switch_components()

    def _init_smart_switch_components(self):
        """初始化称重自动弹出、常驻触屏悬浮球以及全局老板键避险线程"""
        try:
            from core.switch_controller import AutoSwitchController
            from ui.floating_ball import FloatingBall
            from utils.panic_handler import GlobalHotKeyThread, execute_panic_exit

            # A. 自动流转控制器
            self.switch_controller = AutoSwitchController(self, self.config)
            if hasattr(self.sale_page, 'scale') and self.sale_page.scale:
                self.sale_page.scale.weight_updated.connect(self.switch_controller.on_weight_changed)

            # B. 常驻触屏悬浮球
            if self.config.get("floating_ball_enabled", True):
                self.floating_ball = FloatingBall(self)
                self.floating_ball.show()

            # C. 全局老板键线程 (键盘 F10 备用)
            panic_key = self.config.get("panic_hotkey", "F10")
            self.panic_thread = GlobalHotKeyThread(hotkey_name=panic_key, parent=self)
            self.panic_thread.panic_signal.connect(execute_panic_exit)
            self.panic_thread.start()
        except Exception as e:
            print("[MainWindow] 初始化双系统智能组件异常:", e)

    def update_hardware_warnings(self, warnings: list):
        if not warnings:
            self.lbl_hw_status.setText(u"[√] 硬件设备连接良好")
            self.lbl_hw_status.setStyleSheet("color: #10B981; font-size: 13px; font-weight: bold; padding-left: 12px;")
        else:
            warn_msg = " | ".join(warnings)
            self.lbl_hw_status.setText(f"! 硬件告警: {warn_msg}")
            self.lbl_hw_status.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: bold; padding-left: 12px;")



    def _on_auto_update(self):
        """一键自动 Git 更新并无缝重启 POS 程序（静默无黑框）"""
        from ui.custom_dialog import show_question, show_warning
        import subprocess
        import sys
        import os

        if show_question(self, u"系统在线更新", u"确定要检查并自动拉取 GitHub 最新版本代码吗？\n更新完成后 POS 系统将自动重新启动。"):
            try:
                # 1. 先检查更新前提，避免被取消更新时把正在使用的秤停掉。
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0 # SW_HIDE

                status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, startupinfo=startupinfo)
                if status.returncode != 0:
                    raise RuntimeError("无法读取版本库状态")
                if status.stdout.strip():
                    show_warning(self, u"暂不能在线更新", u"检测到本机有未提交修改。为防止覆盖门店配置，已取消更新；请先备份或联系维护人员。")
                    return
                pull = subprocess.run(["git", "pull", "--ff-only"], capture_output=True, text=True, startupinfo=startupinfo)
                if pull.returncode != 0:
                    raise RuntimeError((pull.stderr or pull.stdout or "git pull 失败").strip())

                # 2. 更新完成后再释放硬件，并启动新的 Python 实例。
                if hasattr(self, 'sale_page'):
                    self.sale_page.cleanup()
                subprocess.Popen([sys.executable, "main.py"])
                sys.exit(0)
            except Exception as e:
                show_warning(self, u"更新错误", f"启动更新逻辑失败: {str(e)}")

    def _setup_clock(self):
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.lbl_clock.setText(now)

    def _on_page_changed(self, index):
        page_names = {0: "收银台", 1: "订单查询", 2: "交班报表", 3: "外卖中继", 4: "叫号设置", 5: "切换算法", 6: "系统设置", 7: "日志信息"}
        from core.app_logger import log_event, CAT_USER
        log_event(CAT_USER, f"切换页面: {page_names.get(index, index)}", "")
        self.stack.setCurrentIndex(index)
        if index == 1:
            self.history_page._on_query()
        elif index == 2:
            self.report_page.reload_report()
        elif index == 4:
            self.queue_page._load_settings()
        elif index == 7:
            self.log_page._load_logs()

    def _check_first_run_price(self):
        """首次使用初始化弹窗，提示用户设定/修改公斤单价与分店名称"""
        if self.config.get("is_first_run", True):
            from ui.custom_dialog import get_first_run_input
            from config import save_config
            price, special_price, branch_name, ok = get_first_run_input(
                self,
                title=u"欢迎使用 - 首次初始化设置",
                message=u"系统已切换为【默认按公斤 (KG) 称重计价】\n请设定本店的基础信息与计价单价：",
                default_price=self.config.get("unit_price", 47.60),
                default_special_price=self.config.get("special_soup_price", 50.00),
                default_branch=self.config.get("shop_subtitle", "杨国福(测试店)")
            )
            if ok:
                self.config["unit_price"] = price
                self.config["special_soup_price"] = special_price
                self.config["price_unit"] = "per_kg"
                self.config["shop_subtitle"] = branch_name
                self.config["is_first_run"] = False
                save_config(self.config)
                
                # 刷新各页面与窗口标题显示
                self.setWindowTitle(f"杨国福麻辣烫称重系统 - {branch_name}")
                if hasattr(self, 'sale_page'):
                    self.sale_page.refresh_unit_price_info()
                if hasattr(self, 'settings_page'):
                    if hasattr(self.settings_page, 'spin_default_price'):
                        self.settings_page.spin_default_price.setValue(price)
                    if hasattr(self.settings_page, 'spin_special_price'):
                        self.settings_page.spin_special_price.setValue(special_price)
                    if hasattr(self.settings_page, 'txt_sub'):
                        self.settings_page.txt_sub.setText(branch_name)

    def closeEvent(self, event):
        self.sale_page.cleanup()
        # Do not stop the detached takeout proxy here.  Official POS may still
        # print external orders after this UI is closed or during an update.
        super().closeEvent(event)
