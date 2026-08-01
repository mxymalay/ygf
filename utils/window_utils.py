"""
Windows 窗口查找与句柄控制工具
用于在官方收银系统与本辅助 POS 系统之间进行前台切换
"""
import ctypes
import os
import sys
import time

try:
    user32 = ctypes.windll.user32
except Exception:
    user32 = None

# 常用的官方收银系统可能出现的窗口标题关键词或类名
OFFICIAL_WINDOW_TITLES = [
    "杨国福", "收银系统", "POS", "官方收银", "店长端", "餐饮管理"
]


def find_official_window_handle():
    """查找官方收银软件的窗口句柄 (HWND)"""
    if not user32:
        return None

    found_hwnd = [None]
    current_pid = os.getpid()

    def enum_windows_callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        # 排除本进程的窗口
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

        # 匹配关键字
        for kw in OFFICIAL_WINDOW_TITLES:
            if kw in title and "免安装" not in title and "辅助" not in title:
                found_hwnd[0] = hwnd
                return False  # 停止遍历

        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
    cb = WNDENUMPROC(enum_windows_callback)
    user32.EnumWindows(cb, 0)

    return found_hwnd[0]


def bring_official_to_front():
    """强行将官方收银系统拉至最前"""
    if not user32:
        return False

    hwnd = find_official_window_handle()
    if hwnd:
        try:
            # 还原窗口（如果被最小化）
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
            # 置顶窗口
            user32.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            print("[WindowUtils] 切换至官方软件失败:", e)
            return False
    return False


def bring_our_pos_to_front(main_window):
    """将本 POS 系统窗口拉至最前并全屏焦点"""
    if not main_window:
        return
    try:
        main_window.showMaximized()
        main_window.activateWindow()
        main_window.raise_()
        if user32:
            hwnd = int(main_window.winId())
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
    except Exception as e:
        print("[WindowUtils] 切换至本系统失败:", e)
