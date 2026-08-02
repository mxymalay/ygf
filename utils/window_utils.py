"""
Windows 窗口查找与句柄控制工具
用于在官方收银系统与本辅助 POS 系统之间进行前台切换
"""
import ctypes
import os
import sys
import time
import subprocess

try:
    user32 = ctypes.windll.user32
except Exception:
    user32 = None

# 常用的官方收银系统可能出现的窗口标题关键词或类名
OFFICIAL_WINDOW_TITLES = [
    "杨国福", "收银系统", "POS", "官方收银", "店长端", "餐饮管理", "收银", "YGF"
]

# 官方收银系统的可执行进程名列表
OFFICIAL_PROCESS_NAMES = [
    "yangguofu.exe", "ygf-pos.exe", "ygf.exe", "pos.exe", "cashier.exe"
]


def find_official_pids():
    """通过系统进程列表精准获取官方收银软件的 PID 集合"""
    pids = set()
    try:
        cmd = 'tasklist /NH /FO CSV'
        output = subprocess.check_output(cmd, shell=True).decode('gbk', errors='ignore')
        current_pid = os.getpid()
        for line in output.splitlines():
            line_lower = line.lower()
            if 'python' in line_lower:
                continue
            for proc_name in OFFICIAL_PROCESS_NAMES:
                if proc_name in line_lower and "uninstall" not in line_lower:
                    parts = line.split('","')
                    if len(parts) >= 2:
                        try:
                            pid_val = int(parts[1].replace('"', ''))
                            if pid_val != current_pid:
                                pids.add(pid_val)
                        except ValueError:
                            pass
    except Exception as e:
        print("[WindowUtils] 获取进程列表失败:", e)
    return pids


def find_official_window_handle():
    """查找官方收银软件的窗口句柄 (HWND) - 优先纯 Win32 零阻塞匹配，匹配失败才回退进程列表"""
    if not user32:
        return None

    found_hwnd = [None]
    current_pid = os.getpid()

    # 1. 优先极速遍历窗口标题 (纯 C API，耗时 < 0.1ms，绝不阻塞主线程)
    def enum_title_callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == current_pid:
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True

        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value

        for kw in OFFICIAL_WINDOW_TITLES:
            if kw in title and "免安装" not in title and "辅助" not in title and "排序" not in title:
                found_hwnd[0] = hwnd
                return False

        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
    cb = WNDENUMPROC(enum_title_callback)
    user32.EnumWindows(cb, 0)

    if found_hwnd[0]:
        return found_hwnd[0]

    # 2. 若标题未命中，回退到进程 PID 检测
    official_pids = find_official_pids()
    if not official_pids:
        return None

    def enum_pid_callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in official_pids:
            found_hwnd[0] = hwnd
            return False
        return True

    cb_pid = WNDENUMPROC(enum_pid_callback)
    user32.EnumWindows(cb_pid, 0)
    return found_hwnd[0]


def bring_official_to_front():
    """强行将官方收银系统拉至最前"""
    if not user32:
        return False

    hwnd = find_official_window_handle()
    if hwnd:
        try:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9 还原窗口
            user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE = 3 保持全屏
            user32.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            print("[WindowUtils] 切换至官方软件失败:", e)
            return False
    return False


def bring_our_pos_to_front(main_window):
    """将本 POS 系统窗口拉至最前并全屏最大化"""
    if not main_window:
        return
    try:
        main_window.showMaximized()
        main_window.activateWindow()
        main_window.raise_()
        if user32:
            hwnd = int(main_window.winId())
            user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE = 3 (保持 100% 最大化全屏，严禁变成窗口化)
            user32.SetForegroundWindow(hwnd)
    except Exception as e:
        print("[WindowUtils] 切换至本系统失败:", e)
