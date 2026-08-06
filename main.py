import sys
import os
import time
import subprocess
import traceback
import faulthandler

# 屏蔽 Qt 框架在控制台输出的 png 色彩警告与窗口尺寸适应性提示
os.environ["QT_LOGGING_RULES"] = "qt.png=false;qt.qpa.window=false;*.warning=false"

from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QIcon

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

    # 启用高分辨率屏幕(High DPI)自适应缩放支持 (必须在创建 QApplication 之前设置)
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    # 对于更新版本的 PyQt5，确保系统缩放策略生效
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)

    # Keep a native/Python fatal-error trace even when the packaged Win7
    # executable has no console.  This is separate from app_events.jsonl so a
    # Qt/driver crash that bypasses Python exceptions still leaves evidence.
    try:
        crash_base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        crash_dir = os.path.join(crash_base, "data")
        os.makedirs(crash_dir, exist_ok=True)
        crash_stream = open(os.path.join(crash_dir, "startup_crash.log"), "a", encoding="utf-8")
        faulthandler.enable(file=crash_stream, all_threads=True)
        app._startup_crash_stream = crash_stream
    except Exception:
        crash_stream = None

    # Exceptions raised by queued Qt slots are otherwise invisible in a
    # packaged Win7 build (the console is hidden), which looks like a silent
    # crash exactly after the final startup progress update.  Route them to
    # the same Win7-safe dialog used by the rest of the POS and keep a trace.
    def _handle_unhandled_exception(exc_type, exc_value, exc_tb):
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            log_event(CAT_SYSTEM, "界面未处理异常", detail[-6000:])
        except Exception:
            pass
        try:
            from ui.custom_dialog import show_error
            show_error(
                None,
                u"POS 运行异常",
                u"程序遇到未处理异常，原始数据未被删除。\n\n%s\n\n详细信息已写入 data/app_events.jsonl。" % str(exc_value),
            )
        except Exception:
            try:
                sys.__stderr__.write(detail)
            except Exception:
                pass

    sys.excepthook = _handle_unhandled_exception

    # 设置默认字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    # Windows 7 lacks the emoji fonts used by newer Windows releases.  Keep
    # the UI readable by replacing emoji at the presentation boundary.
    from ui.win7_text_compat import install_win7_text_compat
    install_win7_text_compat(app)

    # Win7 收银机启动较慢，登录窗口涉及串口/打印机扫描和多个 UI 模块，
    # 不能让用户在双击后长时间只看到桌面。这里故意只加载一个轻量提示框，
    # 再延迟导入 LoginWindow/MainWindow 等重模块，确保启动反馈尽快出现。
    from ui.startup_loading_dialog import StartupLoadingDialog

    boot_loading = StartupLoadingDialog()
    boot_loading.set_message(
        u"正在启动 POS",
        u"程序已启动，正在准备配置和登录界面……",
    )
    boot_loading.show()
    boot_loading.raise_()
    app.processEvents()

    # Detect after QApplication/splash is visible so even legacy-config
    # checks have visible feedback on slow Win7 hardware.
    from config import detect_legacy_config, load_config
    legacy_info = detect_legacy_config()

    if legacy_info:
        boot_loading.set_message(
            u"正在检查旧配置",
            u"发现历史配置，准备打开迁移选项……",
        )
        app.processEvents()
        from ui.config_migration_dialog import ConfigMigrationDialog

        boot_loading.close()
        boot_loading.deleteLater()
        boot_loading = None
        app.processEvents()
        migration_dialog = ConfigMigrationDialog(legacy_info)
        if migration_dialog.exec_() != QDialog.Accepted:
            sys.exit(0)
        config = load_config(
            migration_dialog.choice,
            selected_keys=migration_dialog.selected_keys,
        )
    else:
        boot_loading.set_message(
            u"正在准备登录界面",
            u"配置已读取，正在加载账户、密码和硬件检测……",
        )
        app.processEvents()
        config = load_config()

    # Apply the saved Logo before the login dialog is created so every window
    # in the session, including the Win7 taskbar entry, uses the same icon.
    try:
        from config import app_logo_path
        app_icon = QIcon(app_logo_path(config.get("app_logo_preset", "yangguofu")))
        if not app_icon.isNull():
            app.setWindowIcon(app_icon)
    except Exception:
        pass

    # 启动时自动清理超过 3 天的旧日志
    try:
        removed = cleanup_old_logs()
        if removed > 0:
            print(f"[Logger] 自动清理了 {removed} 条过期日志")
    except Exception:
        pass

    log_event(CAT_SYSTEM, "系统启动", f"POS 辅助系统开始初始化")

    # Keep an explicit close marker so the chart can distinguish a real
    # offline interval from stale/imported weighing rows in the database.
    shutdown_logged = [False]

    def _log_system_shutdown():
        if shutdown_logged[0]:
            return
        shutdown_logged[0] = True
        log_event(CAT_SYSTEM, "系统关闭", "POS 辅助系统正常退出")

    app.aboutToQuit.connect(_log_system_shutdown)

    # 0. 尝试同步开机自启动设置
    from utils.system_utils import apply_auto_start_settings

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

    # 1. 弹出登录与检测界面。构造登录窗口可能触发打印机/串口扫描，
    #    所以要等对象创建完毕后再关闭启动提示。
    from ui.login_window import LoginWindow

    login_dlg = None
    try:
        login_dlg = LoginWindow(config)
    except Exception as exc:
        detail = traceback.format_exc()
        log_event(CAT_SYSTEM, "登录界面创建失败", detail[-6000:])
        from ui.custom_dialog import show_error
        show_error(None, u"登录界面启动失败", u"检测页面无法打开：\n%s\n\n详细信息已写入 data/app_events.jsonl。" % exc)
        _log_system_shutdown()
        return 1
    if boot_loading is not None:
        boot_loading.close()
        boot_loading.deleteLater()
        boot_loading = None
        app.processEvents()
    try:
        login_result = login_dlg.exec_()
    except Exception as exc:
        detail = traceback.format_exc()
        log_event(CAT_SYSTEM, "登录检测异常退出", detail[-6000:])
        from ui.custom_dialog import show_error
        show_error(None, u"登录检测异常", u"检测页面运行失败：\n%s\n\n详细信息已写入 data/app_events.jsonl。" % exc)
        _log_system_shutdown()
        return 1
    if login_result != QDialog.Accepted:
        # 用户点击退出或直接关闭窗口
        _log_system_shutdown()
        sys.exit(0)

    config["is_mock_mode"] = getattr(login_dlg, 'is_mock_mode', False)
    hw_warnings = getattr(login_dlg, 'hardware_warnings', [])

    # 2. 验证通过 (或选择跳过进入模拟调试)，打开主系统。
    # 主窗口创建会初始化数据库、收银台、打印和自动切换组件，Win7 上
    # 可能出现短暂空档；在这段时间保留明确的加载提示，不让用户看到空白桌面。
    startup_loading = StartupLoadingDialog()
    startup_loading.show()
    app.processEvents()
    window = None
    startup_error = None
    try:
        # Keep the loading dialog visible while importing/constructing the
        # heavy main window modules on slower Win7 cashiers.
        from ui.main_window import MainWindow

        startup_loading.set_message(
            u"检测完成，正在加载收银系统",
            u"正在初始化数据库、称重、打印和自动切换服务，请稍候。",
        )
        app.processEvents()
        window = MainWindow(
            config,
            hardware_warnings=hw_warnings,
            startup_loading=startup_loading,
        )
        startup_loading.set_progress(100)
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
    except Exception as exc:
        startup_error = exc
        detail = traceback.format_exc()
        log_event(CAT_SYSTEM, "主窗口启动失败", detail[-6000:])
    finally:
        startup_loading.close()
        startup_loading.deleteLater()
    if window is None:
        # Keep the final splash cleanup from turning the actual exception into
        # a silent process exit.  The user gets an actionable dialog instead.
        from ui.custom_dialog import show_error
        show_error(
            None,
            u"POS 启动失败",
            u"主界面在启动收尾阶段未能打开，程序没有删除订单或配置。\n\n原因：%s\n\n详细信息已写入 data/app_events.jsonl。" % startup_error,
        )
        _log_system_shutdown()
        return 1
    # A recovered order is detected during widget construction.  Let the
    # startup overlay close first, then show the notice with the maximized
    # window's final screen geometry.
    def _show_startup_notifications_safely():
        try:
            window.show_startup_notifications()
        except Exception as exc:
            detail = traceback.format_exc()
            log_event(CAT_SYSTEM, "启动提示显示失败", detail[-6000:])
            from ui.custom_dialog import show_error
            show_error(None, u"启动提示异常", u"主界面已打开，但启动提示显示失败：\n%s" % exc)

    QTimer.singleShot(0, _show_startup_notifications_safely)
    log_event(CAT_SYSTEM, "主界面就绪", f"开始运营服务，模拟模式: {config.get('is_mock_mode', False)}")

    sys.exit(app.exec_())


if __name__ == "__main__":
    # Preserve a non-zero status for launchers/installers when the startup
    # dialog reports a failure; normal operation exits from app.exec_().
    result = main()
    if result:
        sys.exit(result)
