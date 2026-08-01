"""
收钱吧 PC收款助手 多通道集成处理模块
包含：
1. 虚拟串口/串口推关金额 (支持 2400/9600 波特率，QA标记/纯数字)
2. 系统剪贴板自动复制 (金额自动写入 Windows 剪贴板)
3. 窗口自动唤起 (自动查找并唤起【收钱吧 PC收款】窗口至最前台)

PyQt5 + Python 3.8 兼容
"""
import serial
import serial.tools.list_ports
import threading
import logging
import ctypes

logger = logging.getLogger("ShouqianbaSender")


def get_available_com_ports():
    """获取本机可用的 COM 串口列表"""
    ports = []
    try:
        for p in serial.tools.list_ports.comports():
            ports.append(p.device)
    except Exception as e:
        logger.error(f"扫描 COM 端口出错: {e}")
    return sorted(ports)


def copy_to_clipboard(text: str):
    """把文本无痛复制到 Windows 系统剪贴板"""
    try:
        GMEM_DDESHARE = 0x2000
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard(0)
        user32.EmptyClipboard()
        text_bytes = text.encode('utf-16le') + b'\x00\x00'
        h_mem = kernel32.GlobalAlloc(GMEM_DDESHARE, len(text_bytes))
        p_mem = kernel32.GlobalLock(h_mem)
        ctypes.memmove(p_mem, text_bytes, len(text_bytes))
        kernel32.GlobalUnlock(h_mem)
        user32.SetClipboardData(13, h_mem)  # CF_UNICODETEXT
        user32.CloseClipboard()
        print(f"[剪贴板] 已将金额 {text} 成功复制到剪贴板！")
    except Exception as e:
        logger.warning(f"复制剪贴板失败: {e}")


def bring_shouqianba_to_front():
    """查找收钱吧 PC收款 窗口并置顶唤起"""
    try:
        user32 = ctypes.windll.user32
        target_hwnd = []

        def foreach_window(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value
                    if any(kw in title for kw in ["PC收款", "收钱吧", "收款助手", "Shouqianba"]):
                        target_hwnd.append(hwnd)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        user32.EnumWindows(WNDENUMPROC(foreach_window), 0)

        if target_hwnd:
            hwnd = target_hwnd[0]
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            print(f"[收钱吧唤起] 已将【PC收款】窗口拉至最前端！")
            return True
    except Exception as e:
        logger.warning(f"唤起收钱吧窗口失败: {e}")
    return False


def _do_send_amount(amount: float, config: dict):
    """后台子线程多通道推送逻辑"""
    enabled = config.get("shouqianba_enabled", True)
    if not enabled:
        return

    amt_str = f"{amount:.2f}"
    
    # 1. 自动将金额复制到 Windows 剪贴板
    copy_to_clipboard(amt_str)

    # 2. 自动尝试将收钱吧窗口置顶前台
    bring_shouqianba_to_front()

    # 3. 串口推送逻辑
    port = config.get("shouqianba_port", "COM4")
    baudrate = int(config.get("shouqianba_baudrate", 2400))  # 默认 2400
    fmt = config.get("shouqianba_format", "QA")               # "QA" 或 "FLOAT"

    if fmt == "QA":
        payload = f"QA{amt_str}\r\n"
    else:
        payload = f"{amt_str}\r\n"

    try:
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baudrate
        ser.timeout = 0.5
        ser.write_timeout = 0.5
        ser.rtscts = False
        ser.dsrdtr = False

        ser.open()
        ser.dtr = True
        ser.rts = True
        ser.write(payload.encode("ascii"))
        logger.info(f"成功向收钱吧串口 {port} 发送金额: {payload.strip()}")
        print(f"[收钱吧串口 Success] 已成功向 {port} (波特率 {baudrate}) 发送数据: {payload.strip()}")
        ser.close()
    except Exception as e:
        logger.warning(f"推送金额到收钱吧串口 {port} 提示: {e}")
        print(f"[收钱吧串口 Notice] 端口 {port} 发送提示: {e}")


def send_shouqianba_amount(amount: float, config: dict):
    """
    非阻塞异步多通道发送金额到收钱吧（绝对不卡顿主界面）
    """
    t = threading.Thread(target=_do_send_amount, args=(amount, config), daemon=True)
    t.start()
