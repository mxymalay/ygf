import sys
import os
import time
import subprocess

# 屏蔽 Qt 框架在控制台输出的 png 色彩警告与窗口尺寸适应性提示
os.environ["QT_LOGGING_RULES"] = "qt.png=false;qt.qpa.window=false;*.warning=false"

from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from config import detect_legacy_config, load_config
from ui.main_window import MainWindow
from ui.login_window import LoginWindow
from ui.startup_loading_dialog import StartupLoadingDialog
from utils.system_utils import apply_auto_start_settings
from core.app_logger import log_event, cleanup_old_logs, CAT_SYSTEM
from core.safe_console import install_safe_console_streams


def main():
    # A detached/UAC-launched Win7 console may return ERROR_GEN_FAILURE from
    # print() even though the Qt application and hardware are healthy. Keep
    # diagnostics best-effort so a log line never aborts a sale or checkout.
    install_safe_console_streams()

    # The RAW listener intentionally runs outside the PyQt POS process.  It
    # must remain available when the cashier closes/restarts the main screen.
    if "--takeout-proxy-host" in sys.argv:
        from core.takeout_proxy_host import run_takeout_proxy_host
        sys.exit(run_takeout_proxy_host())

    # Detect before loading so the legacy monolithic file is still available
    # for the touch migration dialog.  Detached takeout-host mode returns
    # above and keeps the historical automatic migration behaviour.
    legacy_info = detect_legacy_config()

    # 启用高分辨率屏幕(High DPI)自适应缩放支持 (必须在创建 QApplication 之前设置)
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    # 对于更新版本的 PyQt5，确保系统缩放策略生效
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)

    # 设置默认字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    if legacy_info:
        from ui.config_migration_dialog import ConfigMigrationDialog

        migration_dialog = ConfigMigrationDialog(legacy_info)
        if migration_dialog.exec_() != QDialog.Accepted:
            sys.exit(0)
        config = load_config(
            migration_dialog.choice,
            selected_keys=migration_dialog.selected_keys,
        )
    else:
        config = load_config()

    # 启动时自动清理超过 3 天的旧日志
    try:
        removed = cleanup_old_logs()
        if removed > 0:
            print(f"[Logger] 自动清理了 {removed} 条过期日志")
    except Exception:
        pass

    log_event(CAT_SYSTEM, "系统启动", f"POS 辅助系统开始初始化")

    # 0. 尝试同步开机自启动设置
    apply_auto_start_settings(
        config.get("auto_start_enabled", True),
        config.get("auto_start_delay", 8)
    )

    # 0.5 如果是被系统的“开机自启”拉起的，等待指定秒数让硬件驱动(串口/网卡)先加载完毕
    if "--delayed-start" in sys.argv:
        try:
            delay_idx = sys.argv.index("--delayed-start") + 1
            delay_sec = int(sys.argv[delay_idx])
        except (ValueError, IndexError):
            delay_sec = 8
        if delay_sec > 0:
            time.sleep(delay_sec)

    # 1. 弹出登录与检测界面
    login_dlg = LoginWindow(config)
    if login_dlg.exec_() != QDialog.Accepted:
        # 用户点击退出或直接关闭窗口
        sys.exit(0)

    config["is_mock_mode"] = getattr(login_dlg, 'is_mock_mode', False)
    hw_warnings = getattr(login_dlg, 'hardware_warnings', [])

    # 2. 验证通过 (或选择跳过进入模拟调试)，打开主系统。
    # 主窗口创建会初始化数据库、收银台、打印和自动切换组件，Win7 上
    # 可能出现短暂空档；在这段时间保留明确的加载提示，不让用户看到空白桌面。
    startup_loading = StartupLoadingDialog()
    startup_loading.show()
    app.processEvents()
    try:
        startup_loading.set_message(
            u"检测完成，正在加载收银系统",
            u"正在初始化数据库、称重、打印和自动切换服务，请稍候。",
        )
        app.processEvents()
        window = MainWindow(config, hardware_warnings=hw_warnings)
        startup_loading.set_message(
            u"界面即将显示",
            u"收银系统已准备完成，正在打开主窗口。",
        )
        app.processEvents()
        # Use a maximized *normal* window: it fills the available work area while
        # keeping the Windows taskbar visible.  Full-screen mode hid the taskbar
        # and made every automatic channel switch look like a restore/maximize
        # flicker.
        window.showMaximized()
        window.raise_()
        window.activateWindow()
        app.processEvents()
    finally:
        startup_loading.close()
        startup_loading.deleteLater()
    log_event(CAT_SYSTEM, "主界面就绪", f"开始运营服务，模拟模式: {config.get('is_mock_mode', False)}")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
