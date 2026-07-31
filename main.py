"""
杨国福麻辣烫 · 独立称重打印系统
主入口 (含官方系统运行强制校验)
"""
import sys
import os
import time
import subprocess

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from config import load_config, save_config
from ui.main_window import MainWindow


def check_ygf_official_running() -> bool:
    """检测官方收银系统主程序是否正在运行"""
    # 方式 1: 检查 Windows 运行进程列表中是否有官方 POS 程序 (排除本 python 程序)
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

    # 方式 2: 检查官方串口日志文件在 5 秒内是否有实时更新 (官方开着时每秒都会更新)
    serial_dir = r"C:\YANGGUOFU-POS\serial"
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


def main():
    app = QApplication(sys.argv)

    # 设置默认字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    # 校验官方软件是否在运行
    if not check_ygf_official_running():
        QMessageBox.warning(
            None,
            u"提示 - 请先打开官方收银系统",
            u"检测到【杨国福官方收银系统】未打开！\n\n"
            u"本称重打印系统需依赖官方电子秤服务，\n"
            u"请先打开【杨国福官方收银软件】，然后再启动本系统。",
            QMessageBox.Ok
        )
        sys.exit(0)

    # 加载配置
    config = load_config()

    # 首次运行时保存默认配置
    if not os.path.exists(os.path.join(os.path.dirname(__file__), "data", "settings.json")):
        save_config(config)

    # 创建主窗口
    window = MainWindow(config)
    window.showMaximized()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
