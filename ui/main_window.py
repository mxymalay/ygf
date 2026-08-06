"""
主窗口 — 原生竖向侧边栏布局 (收银台、订单查询、叫号设置、系统设置)
PyQt5 + Python 3.8 兼容
"""
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QStatusBar, QLabel, QWidget, QHBoxLayout,
    QPushButton
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

    def __init__(self, config, hardware_warnings=None, startup_loading=None):
        super().__init__()
        self.config = config
        self.hardware_warnings = hardware_warnings or []
        self._startup_loading = startup_loading
        self._hardware_check_running = False
        self._hardware_check_step = 0
        self._hardware_check_state = {}
        self.db = Database()
        self._startup_checkpoint(u"正在准备数据库", u"本地订单账本已打开", 10)
        self.call_mgr = CallNumberManager(config)
        self.is_dark_mode = True

        self._init_window()
        self._startup_checkpoint(u"正在创建收银界面", u"正在加载称重和点餐页面", 18)
        self._build_ui()
        self._startup_checkpoint(u"正在完成界面设置", u"正在启动时钟和状态栏", 92)
        self._setup_clock()
        QTimer.singleShot(600, self._check_first_run_price)

    def _startup_checkpoint(self, message, detail, progress):
        loading = getattr(self, "_startup_loading", None)
        if loading is None:
            return
        try:
            loading.set_message(message, detail)
            loading.pump(progress)
        except Exception:
            # A splash is only feedback; never let it prevent POS startup.
            pass

    def show_startup_notifications(self):
        """Display deferred notices only after the startup overlay has closed."""
        self.sale_page.show_pending_draft_restore_notice()

    def _init_window(self):
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setMinimumSize(960, 640)
        # Start below the screen's available geometry so the taskbar remains
        # visible on Win7 cashier displays (including 1366x768 panels).
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        if available:
            width = min(1180, max(960, available.width() - 40))
            height = min(700, max(640, available.height() - 40))
            self.resize(width, height)
        else:
            self.resize(1180, 700)
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
        self._startup_checkpoint(u"正在加载收银台", u"收银台和电子秤界面已准备", 35)

        # 页面 1: 订单查询
        self.history_page = HistoryWidget(self.db, printer=self.sale_page.printer, config=self.config)
        self.stack.addWidget(self.history_page)
        self._startup_checkpoint(u"正在加载订单查询", u"历史订单模块已准备", 45)

        # 页面 2: 交班报表
        self.report_page = ReportWidget(self.db, printer=self.sale_page.printer, config=self.config)
        self.stack.addWidget(self.report_page)
        self._startup_checkpoint(u"正在加载报表", u"营业统计模块已准备", 53)

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
        self._startup_checkpoint(u"正在加载外卖中继", u"外卖打印模块已准备", 62)

        # 页面 4: 叫号设置 (独立叫号避重菜单)
        self.queue_page = QueueWidget(self.config, self.call_mgr)
        self.stack.addWidget(self.queue_page)
        self._startup_checkpoint(u"正在加载叫号设置", u"叫号模块已准备", 68)

        # 页面 5: 切换算法设置
        self.switch_settings_page = SwitchSettingsWidget(self.config)
        self.stack.addWidget(self.switch_settings_page)
        self._startup_checkpoint(u"正在加载切换算法", u"自动分流设置已准备", 75)

        # 页面 6: 系统设置
        self.settings_page = SettingsWidget(self.config)
        self.stack.addWidget(self.settings_page)
        self._startup_checkpoint(u"正在加载系统设置", u"硬件和打印设置已准备", 84)

        # 页面 7: 运营日志
        self.log_page = LogWidget()
        self.stack.addWidget(self.log_page)

        main_layout.addWidget(self.stack, stretch=1)

        # 3. 底部状态栏
        self.status = QStatusBar()
        self.status.setFixedHeight(34)
        self.status.setStyleSheet(
            "QStatusBar { padding: 0px; min-height: 0px; }"
            "QStatusBar::item { border: none; margin: 0px; padding: 0px; }"
        )
        self.setStatusBar(self.status)

        self.hardware_status_panel = QWidget()
        hardware_status_layout = QHBoxLayout(self.hardware_status_panel)
        hardware_status_layout.setContentsMargins(12, 0, 0, 0)
        hardware_status_layout.setSpacing(4)
        self.lbl_hw_status = QLabel()
        hardware_status_layout.addWidget(self.lbl_hw_status)
        self.btn_hw_recheck = QPushButton(u"点击重检")
        self.btn_hw_recheck.setCursor(Qt.PointingHandCursor)
        self.btn_hw_recheck.setToolTip(u"重新检查硬件连接")
        self.btn_hw_recheck.clicked.connect(self._on_hardware_status_clicked)
        self.btn_hw_recheck.setStyleSheet(
            "QPushButton { color: #94A3B8; font-size: 13px; font-weight: bold; "
            "padding: 0px 2px; min-height: 0px; margin: 0px; border: none; "
            "background: transparent; }"
            "QPushButton:hover { color: #CBD5E1; text-decoration: underline; }"
        )
        hardware_status_layout.addWidget(self.btn_hw_recheck)
        self.status.addWidget(self.hardware_status_panel)
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
        self._startup_checkpoint(u"正在启动后台服务", u"称重、自动切换和悬浮球已准备", 96)

    def _init_smart_switch_components(self):
        """初始化称重自动弹出、常驻触屏悬浮球以及全局老板键避险线程"""
        try:
            from core.switch_controller import AutoSwitchController
            from ui.floating_ball import FloatingBall
            from utils.panic_handler import GlobalHotKeyThread, execute_panic_exit

            # A. 自动流转控制器
            self.switch_controller = AutoSwitchController(self, self.config)
            # SaleWidget exposes one stable event per bowl in both real and
            # simulation modes.  Connecting to the page instead of the
            # current ScaleReader also survives mock -> normal switching.
            self.sale_page.weighing_cycle_started.connect(
                self.switch_controller.on_weighing_cycle_started
            )
            self.sale_page.weighing_cycle_zeroed.connect(
                self.switch_controller.on_weighing_cycle_zeroed
            )
            # SaleWidget starts the reader before the controller exists.  A
            # bowl already sitting on the scale can therefore emit once too
            # early; replay that retained cycle after the listener is wired.
            if hasattr(self.sale_page, "replay_pending_weighing_cycle"):
                self.sale_page.replay_pending_weighing_cycle()

            # B. 常驻触屏悬浮球
            if self.config.get("floating_ball_enabled", True):
                self.floating_ball = FloatingBall(self)
                self.floating_ball.show()
                # 启动时把已持久化的当日配额同步到水位显示，避免必须
                # 等下一碗称重后悬浮球才出现进度。
                self.switch_controller.refresh_floating_ball_progress(True)

            # C. 全局老板键线程 (键盘 F10 备用)
            panic_key = self.config.get("panic_hotkey", "F10")
            self.panic_thread = GlobalHotKeyThread(hotkey_name=panic_key, parent=self)
            self.panic_thread.panic_signal.connect(execute_panic_exit)
            self.panic_thread.start()
        except Exception as e:
            print("[MainWindow] 初始化双系统智能组件异常:", e)

    def update_hardware_warnings(self, warnings: list):
        self.hardware_warnings = list(warnings or [])
        if not warnings:
            self.lbl_hw_status.setText(u"[√] 硬件设备连接良好")
            self.lbl_hw_status.setStyleSheet(
                "QLabel { color: #10B981; font-size: 13px; font-weight: bold; "
                "padding: 0px; background: transparent; }"
            )
            self.btn_hw_recheck.show()
        else:
            warn_msg = " | ".join(warnings)
            self.lbl_hw_status.setText(f"⚠️ 硬件告警: {warn_msg}")
            self.lbl_hw_status.setStyleSheet(
                "QLabel { color: #F59E0B; font-size: 13px; font-weight: bold; "
                "padding: 0px; background: transparent; }"
            )
            self.btn_hw_recheck.show()

    def _set_hardware_check_status(self, text):
        """Show the current recheck stage in the clickable status control."""
        self.lbl_hw_status.setText(u"⟳ " + text)
        self.lbl_hw_status.setStyleSheet(
            "QLabel { color: #38BDF8; font-size: 13px; font-weight: bold; "
            "padding: 0px; background: transparent; }"
        )
        self.btn_hw_recheck.hide()

    def _on_hardware_status_clicked(self):
        """Run the same four hardware checks used at login, one stage at a time."""
        if self._hardware_check_running:
            return
        self._hardware_check_running = True
        self._hardware_check_step = 0
        self._hardware_check_state = {}
        self.hardware_warnings = []
        self._set_hardware_check_status(u"正在检查：官方 POS 窗口")
        QTimer.singleShot(50, self._run_hardware_check_step)

    def _run_hardware_check_step(self):
        """Advance the non-blocking UI sequence for a hardware recheck."""
        steps = (
            (u"正在检查：官方 POS 窗口", self._check_official_window),
            (u"正在检查：电子秤通信", self._check_scale_connection),
            (u"正在检查：热敏打印机", self._check_printer_connection),
            (u"正在检查：收钱吧通信", self._check_shouqianba_connection),
        )
        if self._hardware_check_step >= len(steps):
            self._hardware_check_running = False
            self.update_hardware_warnings(self.hardware_warnings)
            return
        message, check = steps[self._hardware_check_step]
        self._set_hardware_check_status(message)
        try:
            check()
        except Exception as exc:
            self.hardware_warnings.append(u"检查异常：%s" % exc)
        self._hardware_check_step += 1
        QTimer.singleShot(50, self._run_hardware_check_step)

    def _check_official_window(self):
        from ui.login_window import check_ygf_official_running
        from utils.window_utils import is_official_window_configured

        configured = is_official_window_configured(self.config)
        running = check_ygf_official_running(self.config) if configured else False
        self._hardware_check_state["official_ok"] = running
        if not configured:
            self.hardware_warnings.append(u"尚未配置官方 POS 窗口识别词")
        elif not running:
            self.hardware_warnings.append(u"当前识别词未找到官方 POS 窗口")

    def _check_scale_connection(self):
        if self.config.get("scale_source", "official") != "com":
            return
        from ui.login_window import probe_dibal_scale_connection

        scale_ok, detail = probe_dibal_scale_connection(self.config)
        self._hardware_check_state["scale_ok"] = scale_ok
        if not scale_ok:
            self.hardware_warnings.append(
                u"当前选择 COM 称重，但秤串口检测失败：%s" % detail
            )
            if self._hardware_check_state.get("official_ok"):
                port = self.config.get("scale_port", "COM3")
                self.hardware_warnings.append(
                    u"官方 POS 已运行；本 POS 的 %s 尚未验证：%s" % (port, detail)
                )

    def _check_printer_connection(self):
        from utils.port_scanner import scan_printers

        if not scan_printers():
            self.hardware_warnings.append(u"打印机未连接")

    def _check_shouqianba_connection(self):
        from core.shouqianba_sender import test_shouqianba_port

        ok, _detail = test_shouqianba_port(self.config)
        if not ok:
            port = self.config.get("shouqianba_port", "COM10")
            self.hardware_warnings.append(u"收钱吧 %s 未连通" % port)



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

    def open_switch_chart(self):
        """从悬浮球的剩余重量提示直接打开并定位到分流折线图。"""
        self._on_page_changed(5)
        if hasattr(self.sidebar, "set_active_page"):
            self.sidebar.set_active_page(5)
        QTimer.singleShot(0, self.switch_settings_page.focus_weight_chart)

    def open_history_order(self, order_id=None, record=None):
        """Navigate to order details from the cashier's previous-order card."""
        self.stack.setCurrentIndex(1)
        # Keep the navigation rail in sync without emitting page_changed a
        # second time (which would reload the history list and lose selection).
        if hasattr(self.sidebar, "set_active_page"):
            self.sidebar.set_active_page(1)
        if not self.history_page.open_order(order_id=order_id, record=record):
            self.history_page._on_query()

    def _check_first_run_price(self):
        """首次使用初始化弹窗，提示用户设定/修改公斤单价与分店名称"""
        if self.config.get("is_first_run", True):
            from ui.custom_dialog import get_first_run_input
            from config import save_config
            price, special_price, branch_name, ok = get_first_run_input(
                self,
                title=u"👋 欢迎使用 - 首次初始化设置",
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
