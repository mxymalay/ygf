"""
紧急避险（老板键）处理器
用于在督导抽查时 0.01 秒内切回官方收银软件并彻底杀掉当前辅助 POS 进程
"""
import ctypes
import os
import sys
from PyQt5.QtCore import QThread, pyqtSignal
from utils.window_utils import bring_official_to_front


def execute_panic_exit():
    """彻底避险销毁操作：切回官方软件 + 强行杀死当前 Python 进程"""
    print("[Panic] 触发紧急避险，正在销毁程序...")
    try:
        # 1. 强行将官方系统拉至最前
        bring_official_to_front()
    except Exception:
        pass

    # 2. 直接操作系统底层杀死进程（无延时，不弹任何提示框）
    os._exit(0)


class GlobalHotKeyThread(QThread):
    """全局热键监听线程 (使用 Win32 RegisterHotKey)"""
    panic_signal = pyqtSignal()

    def __init__(self, hotkey_name="F10", parent=None):
        super().__init__(parent)
        self.hotkey_name = hotkey_name
        self._running = True

    def run(self):
        if os.name != 'nt':
            return

        try:
            user32 = ctypes.windll.user32
            # VK 键码映射
            vk_map = {
                "F10": 0x79,
                "F9": 0x78,
                "F11": 0x7A,
                "F12": 0x7B,
                "ESC": 0x1B,
                "PAUSE": 0x13
            }
            vk = vk_map.get(self.hotkey_name.upper(), 0x79) # 默认 F10

            HOTKEY_ID = 9999
            MOD_ALT = 0x0001
            MOD_CONTROL = 0x0002
            MOD_NOREPEAT = 0x4000

            # 注册全局热键 (不需要 Modifiers，按 F10 即可)
            if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, vk):
                print(f"[PanicHandler] 注册热键 {self.hotkey_name} 失败，可能冲突")

            msg = ctypes.wintypes.MSG()
            while self._running:
                # 阻塞式获取 Windows 消息
                if user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                    if msg.message == 0x0312:  # WM_HOTKEY
                        if msg.wParam == HOTKEY_ID:
                            print(f"[PanicHandler] 检测到按键 {self.hotkey_name}，触发紧急避险！")
                            self.panic_signal.emit()
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))

            user32.UnregisterHotKey(None, HOTKEY_ID)
        except Exception as e:
            print("[PanicHandler] 监听线程异常:", e)

    def stop(self):
        self._running = False
        self.quit()
