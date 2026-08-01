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
from ui.styles import DARK_STYLE, LIGHT_STYLE


class MainWindow(QMainWindow):
    """应用主窗口"""

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.db = Database()
        self.call_mgr = CallNumberManager(config)
        self.is_dark_mode = True

        self._init_window()
        self._build_ui()
        self._setup_clock()
        QTimer.singleShot(600, self._check_first_run_price)

    def _init_window(self):
        from config import APP_VERSION
        shop_name = self.config.get("shop_name", u"杨国福麻辣烫")
        self.setWindowTitle(u"%s · 独立称重与小票打印系统 %s" % (shop_name, APP_VERSION))
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

        # 页面 3: 叫号设置 (独立叫号避重菜单)
        self.queue_page = QueueWidget(self.config, self.call_mgr)
        self.stack.addWidget(self.queue_page)

        # 页面 4: 系统设置
        self.settings_page = SettingsWidget(self.config)
        self.stack.addWidget(self.settings_page)

        main_layout.addWidget(self.stack, stretch=1)

        # 3. 底部状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        from config import APP_VERSION
        self.lbl_ver = QLabel(f"版本: {APP_VERSION}")
        self.lbl_ver.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: bold; padding-right: 16px;")
        self.status.addPermanentWidget(self.lbl_ver)

        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("color: #9CA3AF; font-size: 13px; font-weight: bold; padding-right: 16px;")
        self.status.addPermanentWidget(self.lbl_clock)

        self.status.showMessage(u" ● 系统运行正常  |  官方称重日志实时同步模式  |  智能避重叫号引擎就绪")



    def _on_auto_update(self):
        """一键自动 Git 更新并无缝重启 POS 程序（静默无黑框）"""
        from ui.custom_dialog import show_question, show_warning
        import subprocess
        import sys
        import os

        if show_question(self, u"系统在线更新", u"确定要检查并自动拉取 GitHub 最新版本代码吗？\n更新完成后 POS 系统将自动重新启动。"):
            try:
                # 1. 释放称重串口与硬件资源
                if hasattr(self, 'sale_page'):
                    self.sale_page.cleanup()

                # 2. 静默后台执行 git pull，不弹出任何黑框终端
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0 # SW_HIDE

                subprocess.run(["git", "pull"], capture_output=True, text=True, startupinfo=startupinfo)

                # 3. 启动新的 Python 实例并平滑退出旧进程
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
        self.stack.setCurrentIndex(index)
        if index == 0:
            self.sale_page.restart_scale()
        elif index == 1:
            self.history_page._on_query()
        elif index == 2:
            self.report_page.reload_report()
        elif index == 3:
            self.queue_page._load_settings()

    def _check_first_run_price(self):
        """首次使用初始化弹窗，提示用户设定/修改公斤单价与分店名称"""
        if self.config.get("is_first_run", True):
            from ui.custom_dialog import get_first_run_input
            from config import save_config
            price, branch_name, ok = get_first_run_input(
                self,
                title=u"👋 欢迎使用 - 首次初始化设置",
                message=u"系统已切换为【默认按公斤 (KG) 称重计价】\n请设定本店的基础信息与计价单价：",
                default_price=self.config.get("unit_price", 1.00),
                default_branch=self.config.get("shop_subtitle", "杨国福(测试店)")
            )
            if ok:
                self.config["unit_price"] = price
                self.config["price_unit"] = "per_kg"
                self.config["shop_subtitle"] = branch_name
                self.config["is_first_run"] = False
                save_config(self.config)
                
                # 刷新各页面与窗口标题显示
                self._init_window()
                if hasattr(self, 'sale_page'):
                    self.sale_page.refresh_unit_price_info()
                if hasattr(self, 'settings_page'):
                    if hasattr(self.settings_page, 'spin_default_price'):
                        self.settings_page.spin_default_price.setValue(price)
                    if hasattr(self.settings_page, 'txt_sub'):
                        self.settings_page.txt_sub.setText(branch_name)

    def closeEvent(self, event):
        self.sale_page.cleanup()
        super().closeEvent(event)
