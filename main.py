import sys
import os
import time
import subprocess

# 屏蔽 Qt 框架在控制台输出的 png 色彩警告与窗口尺寸适应性提示
os.environ["QT_LOGGING_RULES"] = "qt.png=false;qt.qpa.window=false;*.warning=false"

from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from config import load_config, save_config
from ui.main_window import MainWindow
from ui.login_window import LoginWindow


def setup_auto_start():
    """将当前打包好的 EXE 路径写入 Windows 注册表，实现开机自启"""
    if not getattr(sys, 'frozen', False):
        return  # 仅在打包后的 EXE 环境中生效

    try:
        import winreg
        exe_path = sys.executable
        # 打开注册表的自启项键
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, 
            r"Software\Microsoft\Windows\CurrentVersion\Run", 
            0, 
            winreg.KEY_SET_VALUE | winreg.KEY_READ
        )
        
        # 检查是否已经设置过，如果路径一致就不反复写
        try:
            val, _ = winreg.QueryValueEx(key, "YGF_POS_System")
            if val == f'"{exe_path}"':
                winreg.CloseKey(key)
                return
        except WindowsError:
            pass
            
        winreg.SetValueEx(key, "YGF_POS_System", 0, winreg.REG_SZ, f'"{exe_path}"')
        winreg.CloseKey(key)
        print("[*] 成功设置开机自启")
    except Exception as e:
        print("[!] 自动设置开机启动失败:", e)


def main():
    # 0. 尝试设置开机自启动
    setup_auto_start()

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

    # 加载配置
    config = load_config()

    # 首次运行时保存默认配置
    if not os.path.exists(os.path.join(os.path.dirname(__file__), "data", "settings.json")):
        save_config(config)

    # 1. 弹出登录与检测界面
    login_dlg = LoginWindow(config)
    if login_dlg.exec_() != QDialog.Accepted:
        # 用户点击退出或直接关闭窗口
        sys.exit(0)

    config["is_mock_mode"] = getattr(login_dlg, 'is_mock_mode', False)
    hw_warnings = getattr(login_dlg, 'hardware_warnings', [])

    # 2. 验证通过 (或选择跳过进入模拟调试)，打开主系统
    window = MainWindow(config, hardware_warnings=hw_warnings)
    window.showMaximized()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
