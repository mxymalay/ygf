"""
收钱吧 PC收款助手 多通道集成处理模块
包含：
1. 虚拟串口/串口推送金额 (支持 2400/9600 波特率，QA标记/纯数字)
2. 系统剪贴板自动复制 (金额自动写入 Windows 剪贴板)
3. 键盘快捷键模拟 (自动发送用户配置的唤起快捷键，如 F12 / Ctrl+F12)
4. 窗口自动唤起 (自动查找并唤起【收钱吧 PC收款】窗口至最前台)

PyQt5 + Python 3.8 兼容
"""
import serial
import serial.tools.list_ports
import threading
import logging
import ctypes
import time
import keyboard

logger = logging.getLogger("ShouqianbaSender")

# Virtual key mapping for Windows keybd_event
VK_MAPPING = {
    "CTRL": 0x11, "CONTROL": 0x11,
    "ALT": 0x12, "SHIFT": 0x10,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "SPACE": 0x20, "ENTER": 0x0D, "TAB": 0x09,
}
for i in range(26):
    ch = chr(ord('A') + i)
    VK_MAPPING[ch] = 0x41 + i
for i in range(10):
    VK_MAPPING[str(i)] = 0x30 + i


def send_hotkey(hotkey_str: str):
    """模拟键盘发送快捷键 (例如 F12, Ctrl+F12, Alt+S 等)"""
    if not hotkey_str:
        return False
    try:
        user32 = ctypes.windll.user32
        parts = [p.strip().upper() for p in hotkey_str.split("+") if p.strip()]
        vk_codes = [VK_MAPPING[p] for p in parts if p in VK_MAPPING]

        if not vk_codes:
            return False

        KEYEVENTF_KEYUP = 0x0002

        # 按下所有组合键
        for vk in vk_codes:
            scan_code = user32.MapVirtualKeyW(vk, 0)
            user32.keybd_event(vk, scan_code, 0, 0)
            time.sleep(0.02)

        time.sleep(0.05)

        # 逆序释放键
        for vk in reversed(vk_codes):
            scan_code = user32.MapVirtualKeyW(vk, 0)
            user32.keybd_event(vk, scan_code, KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)

        print(f"[快捷键唤起] 成功模拟发送收钱吧快捷键: {hotkey_str}")
        return True
    except Exception as e:
        logger.warning(f"发送快捷键 {hotkey_str} 异常: {e}")
        return False


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
    """把文本无痛复制到 Windows 系统剪贴板 (64位 ctypes 兼容)"""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

        GMEM_DDESHARE = 0x2000
        user32.OpenClipboard(0)
        user32.EmptyClipboard()
        text_bytes = text.encode('utf-16le') + b'\x00\x00'
        h_mem = kernel32.GlobalAlloc(GMEM_DDESHARE, len(text_bytes))
        if h_mem:
            p_mem = kernel32.GlobalLock(h_mem)
            if p_mem:
                ctypes.memmove(p_mem, text_bytes, len(text_bytes))
                kernel32.GlobalUnlock(h_mem)
                user32.SetClipboardData(13, h_mem)  # CF_UNICODETEXT
        user32.CloseClipboard()
        print(f"[剪贴板 Success] 已将金额 {text} 成功复制到剪贴板！")
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


def check_shouqianba_payment_success() -> bool:
    """自动检测【收钱吧】PC插件是否弹出了“收款成功/支付成功/交易成功”等结果窗口"""
    import sys
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        found_success = [False]

        def foreach_window(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value
                    # 匹配收钱吧成功窗口或提示关键字
                    if any(kw in title for kw in ["收款成功", "支付成功", "交易成功", "收钱吧到账"]):
                        found_success[0] = True
                        return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        user32.EnumWindows(WNDENUMPROC(foreach_window), 0)
        return found_success[0]
    except Exception as e:
        logger.warning(f"检测收钱吧成功窗口异常: {e}")
        return False


def _do_send_amount(amount: float, config: dict):
    """后台子线程多通道推送逻辑"""
    enabled = config.get("shouqianba_enabled", True)
    if not enabled:
        return

    amt_str = f"{amount:.2f}"
    
    # 1. 串口推送逻辑 (先通过COM发送金额)
    port = config.get("shouqianba_port", "COM1")
    baudrate = int(config.get("shouqianba_baudrate", 2400))  # 默认 2400
    fmt = config.get("shouqianba_format", "QA")               # "QA" 或 "FLOAT"

    if fmt == "QA":
        reset_payload = "QA0.00\r\n"
        payload = f"QA{amt_str}\r\n"
    else:
        reset_payload = "0.00\r\n"
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
        
        # 先发一次 0.00 重置包，强行抹除上一次扫码枪误扫入金额栏的长数字/残留金额
        ser.write(reset_payload.encode("ascii"))
        time.sleep(0.08)
        
        # 再发真实金额包，确保收钱吧 100% 触发金额变动事件
        ser.write(payload.encode("ascii"))
        logger.info(f"成功向收钱吧串口 {port} 发送重置与金额: {payload.strip()}")
        print(f"[收钱吧串口 Success] 已冲刷重置并向 {port} 发送金额: {payload.strip()}")
        ser.close()
    except Exception as e:
        logger.warning(f"推送金额到收钱吧串口 {port} 提示: {e}")
        print(f"[收钱吧串口 Notice] 端口 {port} 发送提示: {e}")

    # 等待 0.15 秒，确保收钱吧后台已处理完串口数据
    time.sleep(0.15)

    # 2. 自动模拟发送快捷键 (再调出收钱吧界面)
    hotkey = config.get("shouqianba_hotkey", "Shift+Q")
    if hotkey:
        send_hotkey(hotkey)

    # 3. 自动尝试将收钱吧窗口置顶前台
    bring_shouqianba_to_front()
    
    # 4. 解决 USB标准模式 下扫码枪误扫入金额栏的问题
    # 置顶后延迟0.6秒(等收钱吧界面彻底渲染完毕再敲TAB)，强行让光标从“金额栏”跳跃到“扫码栏”
    time.sleep(0.6)
    send_hotkey("TAB")


def send_shouqianba_amount(amount: float, config: dict):
    """
    非阻塞异步多通道发送金额到收钱吧（绝对不卡顿主界面）
    """
    t = threading.Thread(target=_do_send_amount, args=(amount, config), daemon=True)
    t.start()


def clear_shouqianba_amount(config: dict):
    """取消/退出时清空收钱吧插件金额框 (发送 0.00 重置包)"""
    send_shouqianba_amount(0.00, config)


def test_shouqianba_port(config: dict):
    """
    自检测试：向配置的收钱吧串口发送数据测试连通性
    返回 (is_ok: bool, message: str)
    """
    enabled = config.get("shouqianba_enabled", True)
    if not enabled:
        return False, "功能已禁用"

    port = config.get("shouqianba_port", "COM1")
    baudrate = int(config.get("shouqianba_baudrate", 2400))
    fmt = config.get("shouqianba_format", "QA")

    payload = "QA0.00\r\n" if fmt == "QA" else "0.00\r\n"

    try:
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baudrate
        ser.timeout = 0.3
        ser.write_timeout = 0.3
        ser.rtscts = False
        ser.dsrdtr = False

        ser.open()
        ser.dtr = True
        ser.rts = True
        ser.write(payload.encode("ascii"))
        ser.close()
        return True, f"端口 {port} ({baudrate}bps) 连通正常"
    except Exception as e:
        return False, f"端口 {port} 未连通"


# =========================================================================
# 硬件补偿：全局扫码枪/碰一碰设备无回车自动补全逻辑
# 检测极速输入，自动补一个 Enter
# =========================================================================

_barcode_buffer = ""
_last_key_time = 0

def _global_key_listener(e):
    global _barcode_buffer, _last_key_time
    now = time.time()
    
    # 遇到自带回车的扫码设备，清空缓存，不需要补偿
    if e.name == "enter":
        _barcode_buffer = ""
        _last_key_time = now
        return
        
    # 只监听普通字符（数字、字母等通常用于付款码的字符）
    if e.name and len(e.name) == 1 and e.name.isalnum():
        if now - _last_key_time > 0.05:
            _barcode_buffer = e.name  # 超过50ms重新计算
        else:
            _barcode_buffer += e.name
        _last_key_time = now

def _barcode_checker_loop():
    global _barcode_buffer, _last_key_time
    while True:
        time.sleep(0.1)
        now = time.time()
        # 如果缓存累积了超过 10 位极速输入（支付码一般都在15位以上），且 0.1 秒没有新输入
        if len(_barcode_buffer) >= 10 and (now - _last_key_time) > 0.1:
            logger.info(f"[扫码补偿] 检测到支付宝碰一碰极速输入({len(_barcode_buffer)}位): {_barcode_buffer}，自动补充 Enter")
            _barcode_buffer = ""  # 清空防止重复触发
            send_hotkey("ENTER")

try:
    keyboard.on_press(_global_key_listener)
    _t = threading.Thread(target=_barcode_checker_loop, daemon=True)
    _t.start()
    logger.info("支付宝碰一碰设备无回车补偿器已启动")
except Exception as _e:
    logger.warning(f"碰一碰监听器启动失败（可能需要管理员权限）: {_e}")
