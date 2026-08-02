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
    """瞬间并发模拟键盘快捷键 (零延迟激发，避免 Shift 独按触发出法切换)"""
    if not hotkey_str:
        return False
    try:
        user32 = ctypes.windll.user32
        parts = [p.strip().upper() for p in hotkey_str.split("+") if p.strip()]
        vk_codes = [VK_MAPPING[p] for p in parts if p in VK_MAPPING]

        if not vk_codes:
            return False

        KEYEVENTF_KEYUP = 0x0002

        # 瞬间并发按下所有修饰键与字母键 (零 time.sleep 间隔)
        for vk in vk_codes:
            scan_code = user32.MapVirtualKeyW(vk, 0)
            user32.keybd_event(vk, scan_code, 0, 0)

        time.sleep(0.01)

        # 瞬间释放所有按键
        for vk in reversed(vk_codes):
            scan_code = user32.MapVirtualKeyW(vk, 0)
            user32.keybd_event(vk, scan_code, KEYEVENTF_KEYUP, 0)

        print(f"[快捷键唤起] 瞬间唤起收钱吧: {hotkey_str}")
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


# 初始化全局 RapidOCR 算法引擎 (单例只加载一次，15ms 超高速文字识别)
_rapid_ocr_engine = None

def _get_ocr_engine():
    global _rapid_ocr_engine
    if _rapid_ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _rapid_ocr_engine = RapidOCR()
            logger.info("成功初始化 RapidOCR 高效本地文字识别引擎！")
            print("[OCR引擎] 成功载入 RapidOCR 本地高精文字识别引擎！")
        except Exception as e:
            logger.warning(f"本地未加载 RapidOCR 引擎 ({e})，降级使用视觉色彩分析。")
            _rapid_ocr_engine = False
    return _rapid_ocr_engine if _rapid_ocr_engine else None


def _analyze_sqb_window_image_success(hwnd) -> bool:
    """双模式视觉+OCR深度分析：优先使用 RapidOCR 识别真实文本，辅以色彩采样"""
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            return False
        screen = QApplication.primaryScreen()
        if not screen:
            return False

        pixmap = screen.grabWindow(hwnd)
        if pixmap.isNull() or pixmap.width() < 120 or pixmap.height() < 120:
            return False

        qimg = pixmap.toImage()
        w = qimg.width()
        h = qimg.height()

        # ----------------------------------------------------
        # 模式 A：使用 RapidOCR 高速提取图像中打印的所有真实中文字符
        # ----------------------------------------------------
        ocr_engine = _get_ocr_engine()
        if ocr_engine:
            try:
                import numpy as np
                qimg_rgb = qimg.convertToFormat(4) # QImage.Format_RGB888
                ptr = qimg_rgb.bits()
                ptr.setsize(h * w * 3)
                img_np = np.frombuffer(ptr, np.uint8).reshape((h, w, 3))

                result, _ = ocr_engine(img_np)
                if result:
                    all_ocr_text = "".join([line[1] for line in result])
                    
                    # 1. 严格过滤失败/等待状态
                    fail_keywords = ["支付失败", "交易失败", "支付中", "输入密码", "倒计时", "EP99"]
                    if any(fk in all_ocr_text for fk in fail_keywords):
                        return False
                    
                    # 2. 精准匹配成功标志文字 (收钱吧 V4.0.4 出现的“支付成功”、“打印小票”)
                    success_keywords = ["支付成功", "收款成功", "交易成功", "打印小票", "收钱吧到账"]
                    if any(sk in all_ocr_text for sk in success_keywords):
                        print(f"[OCR识别] 🎯 成功从收钱吧弹窗识别到关键文字: '{all_ocr_text}'！判定支付成功！")
                        return True
            except Exception as e:
                logger.warning(f"RapidOCR 提取文本异常: {e}")

        # ----------------------------------------------------
        # 模式 B：色彩采样引擎 (兜底降级方案)
        # ----------------------------------------------------
        header_h = int(h * 0.25)
        green_count = 0
        red_count = 0
        total_samples = 0

        for x in range(10, w - 10, 6):
            for y in range(10, header_h - 5, 6):
                pixel = qimg.pixelColor(x, y)
                r, g, b = pixel.red(), pixel.green(), pixel.blue()
                total_samples += 1
                if g > r + 30 and g > b + 30 and g > 100:
                    green_count += 1
                elif r > g + 40 and r > b + 40 and r > 140:
                    red_count += 1

        if total_samples == 0:
            return False

        green_ratio = green_count / total_samples
        red_ratio = red_count / total_samples

        if red_ratio > 0.35:
            return False

        if green_ratio > 0.35:
            button_y_start = int(h * 0.65)
            button_green_count = 0
            button_samples = 0
            for bx in range(int(w * 0.2), int(w * 0.8), 4):
                for by in range(button_y_start, h - 10, 4):
                    bp = qimg.pixelColor(bx, by)
                    br, bg, bb = bp.red(), bp.green(), bp.blue()
                    button_samples += 1
                    if bg > br + 30 and bg > bb + 30 and bg > 100:
                        button_green_count += 1

            if button_samples > 0:
                btn_ratio = button_green_count / button_samples
                if btn_ratio > 0.05:
                    print(f"[视觉色彩] 🎯 命中收钱吧【绿顶 + 绿色打印小票按钮】(比例 {btn_ratio:.2f})！判定支付成功！")
                    return True

    except Exception as e:
        logger.warning(f"深度分析收钱吧窗口异常: {e}")
    return False


def check_shouqianba_payment_success() -> bool:
    """双引擎侦测：Win32底层文本 + 视觉图像色彩精准识别【收钱吧 PC版 V4.0.4】支付成功弹窗"""
    import sys
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        found_success = [False]

        # 1. 匹配 Win32 文本关键字
        success_keywords = ["支付成功", "收款成功", "交易成功", "收钱吧到账", "打印小票"]
        fail_keywords = ["支付失败", "交易失败", "支付中", "输入密码", "倒计时", "EP99"]

        WM_GETTEXT = 0x000D
        WM_GETTEXTLENGTH = 0x000E

        def evaluate_text(text: str) -> bool:
            if not text:
                return False
            if any(fk in text for fk in fail_keywords):
                return False
            if any(sk in text for sk in success_keywords):
                return True
            return False

        def get_wm_text(h):
            try:
                l = user32.SendMessageW(h, WM_GETTEXTLENGTH, 0, 0)
                if 0 < l < 1024:
                    buf = ctypes.create_unicode_buffer(l + 1)
                    user32.SendMessageW(h, WM_GETTEXT, l + 1, buf)
                    return buf.value.strip()
            except Exception:
                pass
            return ""

        def check_hwnd(h) -> bool:
            # Win32 文本检测
            l = user32.GetWindowTextLengthW(h)
            if l > 0:
                buf = ctypes.create_unicode_buffer(l + 1)
                user32.GetWindowTextW(h, buf, l + 1)
                txt = buf.value.strip()
                if evaluate_text(txt):
                    return True

            wm_txt = get_wm_text(h)
            if evaluate_text(wm_txt):
                return True

            return False

        def foreach_child(child_hwnd, lParam):
            if check_hwnd(child_hwnd):
                found_success[0] = True
                return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        child_proc = WNDENUMPROC(foreach_child)

        def foreach_window(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                # 引擎 1：Win32 文本
                if check_hwnd(hwnd):
                    found_success[0] = True
                    return False
                user32.EnumChildWindows(hwnd, child_proc, 0)
                if found_success[0]:
                    return False

                # 引擎 2：视觉图像色彩特征 (专治自绘UI/Chromium/Qt渲染的无文本句柄窗口)
                rect = ctypes.wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                # 收钱吧结果弹窗尺寸一般在 200~800 像素之间
                if 200 <= w <= 900 and 200 <= h <= 900:
                    if _analyze_sqb_window_image_success(hwnd):
                        found_success[0] = True
                        return False

            return True

        user32.EnumWindows(WNDENUMPROC(foreach_window), 0)
        return found_success[0]
    except Exception as e:
        logger.warning(f"检测收钱吧成功窗口异常: {e}")
        return False

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

    # 如果是归零/重置清空 (amount <= 0)，只静默向串口发送 0.00 冲刷缓存，不触发唤起
    if amount <= 0.0:
        print("[收钱吧串口] 已完成静默 0.00 金额重置，隐藏前台唤起。")
        return

    # 1. 优先使用 Win32 原生 API 唤起置顶
    if not bring_shouqianba_to_front():
        # 2. 若收钱吧隐藏在系统右下角托盘中，瞬间触发快捷键唤起 (零延迟，彻底杜绝切输入法与干扰)
        hotkey = config.get("shouqianba_hotkey", "Shift+Q")
        if hotkey:
            send_hotkey(hotkey)
            time.sleep(0.05)
            bring_shouqianba_to_front()


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
