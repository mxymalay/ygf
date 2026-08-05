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
from ctypes import wintypes
import os
import re
import time
try:
    import keyboard
except ImportError:
    # keyboard 只用于末尾的“扫码枪无回车补偿”，不是收钱吧串口通信的
    # 必需依赖。部分门店电脑只部署基础运行环境，不能让可选功能缺包时
    # 连登录页的收钱吧检测也直接退出。
    keyboard = None

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
SQB_TAB_FOCUS_DELAY = 0.2
_payment_probe_lock = threading.Lock()
_payment_probe_started_at = 0.0
_payment_probe_baseline_hwnds = set()
_payment_probe_baseline_foreground = 0
_sqb_log_lock = threading.Lock()
_sqb_log_files = {}
_sqb_log_install_dir = ""
_sqb_log_expected_cents = None
_sqb_log_session_started_at = 0.0
_sqb_log_session_status = "UNKNOWN"


def _write_sqb_monitor_event(message, detail=""):
    """Persist sparse state transitions for field diagnosis."""
    try:
        from core.app_logger import log_event, CAT_SYSTEM
        log_event(CAT_SYSTEM, message, detail)
    except Exception:
        pass

for i in range(26):
    ch = chr(ord('A') + i)
    VK_MAPPING[ch] = 0x41 + i
for i in range(10):
    VK_MAPPING[str(i)] = 0x30 + i


def _visible_external_window_hwnds():
    """Return visible top-level windows owned by another process."""
    if os.name != "nt":
        return []
    try:
        user32 = ctypes.windll.user32
        current_pid = os.getpid()
        result = []

        def callback(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if not pid.value or pid.value == current_pid:
                    return True
                rect = wintypes.RECT()
                if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    return True
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                # Ignore tooltips, tray helpers and full desktop/shell windows.
                if 160 <= width <= 1500 and 100 <= height <= 1100:
                    result.append(int(hwnd))
            except Exception:
                pass
            return True

        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
        user32.EnumWindows(callback_type(callback), 0)
        return result
    except Exception:
        return []


def begin_sqb_payment_probe(amount=None, config=None):
    """Snapshot windows before sending the amount/opening the payment UI.

    Older SQB builds use changing or empty window titles.  A window that
    appears after the hotkey, or becomes the foreground external window, is a
    stronger runtime signal than guessing a fixed product title.
    """
    global _payment_probe_started_at, _payment_probe_baseline_hwnds
    global _payment_probe_baseline_foreground
    baseline = set(_visible_external_window_hwnds())
    foreground = 0
    try:
        foreground = int(ctypes.windll.user32.GetForegroundWindow() or 0)
    except Exception:
        pass
    with _payment_probe_lock:
        _payment_probe_baseline_hwnds = baseline
        _payment_probe_baseline_foreground = foreground
        _payment_probe_started_at = time.monotonic()
    _begin_sqb_log_probe(amount, config)


def _version_sort_key(path):
    """Return a numeric key for directories such as v4.0.4."""
    name = os.path.basename(os.path.normpath(path))
    numbers = re.findall(r"\d+", name)
    return tuple(int(value) for value in numbers) if numbers else (0,)


def _sqb_version_dirs(install_dir):
    """Resolve either the smskv3 root, a version folder, or its logs folder."""
    if not install_dir:
        return []
    root = os.path.abspath(os.path.expandvars(os.path.expanduser(str(install_dir).strip().strip('"'))))
    if os.path.basename(root).lower() == "logs":
        root = os.path.dirname(root)
    if os.path.isdir(os.path.join(root, "logs")):
        return [root]
    if not os.path.isdir(root):
        return []

    versions = []
    try:
        for name in os.listdir(root):
            candidate = os.path.join(root, name)
            if os.path.isdir(os.path.join(candidate, "logs")):
                versions.append(candidate)
    except OSError:
        return []
    return sorted(versions, key=_version_sort_key, reverse=True)


def discover_shouqianba_install_dir(config=None):
    """Find the SQB installation root without assuming one fixed version.

    A user-selected folder has priority.  The default PC plugin currently
    installs below ``C:\\smskv3``, but scanning drive roots also keeps the
    integration usable when a store chooses another disk.
    """
    configured = ""
    if isinstance(config, dict):
        configured = str(config.get("shouqianba_install_dir", "") or "").strip()
    if configured and _sqb_version_dirs(configured):
        return os.path.normpath(os.path.abspath(os.path.expandvars(configured.strip('"'))))

    candidates = []
    system_drive = os.environ.get("SystemDrive", "C:")
    candidates.append(os.path.join(system_drive + os.sep, "smskv3"))
    for drive_letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        candidate = drive_letter + r":\smskv3"
        if candidate not in candidates:
            candidates.append(candidate)
    for candidate in candidates:
        if _sqb_version_dirs(candidate):
            return os.path.normpath(candidate)
    return ""


def get_shouqianba_log_paths(config=None, install_dir=None):
    """Return current info/debug logs from the newest installed SQB version.

    ``biz.log`` is deliberately excluded.  SQB v4.0.4 writes “支付取消” there
    even after a successful payment because its success cleanup calls an
    internal function named payCancel.
    """
    root = install_dir or discover_shouqianba_install_dir(config)
    for version_dir in _sqb_version_dirs(root):
        logs_dir = os.path.join(version_dir, "logs")
        paths = []
        for category in ("info", "debug"):
            path = os.path.join(logs_dir, category, category + ".log")
            if os.path.isfile(path):
                paths.append(os.path.normpath(path))
        if paths:
            return paths
    return []


def validate_shouqianba_install_dir(path):
    """Validate a setting-page folder and explain which log will be used."""
    value = str(path or "").strip().strip('"')
    if not value:
        return False, u"尚未选择收钱吧安装目录。"
    normalized = os.path.abspath(os.path.expandvars(os.path.expanduser(value)))
    if not os.path.isdir(normalized):
        return False, u"目录不存在：%s" % normalized
    paths = get_shouqianba_log_paths(install_dir=normalized)
    if not paths:
        return False, u"没有找到 logs\\info\\info.log 或 logs\\debug\\debug.log。请选择 smskv3 根目录或 v版本目录。"
    return True, u"支付日志可用：%s" % u"；".join(paths)


def _amount_matches_log_text(text, expected_cents, require_amount=False):
    """Match SQB's integer-cent JSON amount or its printed yuan amount."""
    if expected_cents is None:
        return True
    cents_values = [int(value) for value in re.findall(
        r'"total_amount"\s*:\s*"?(\d+)"?', text
    )]
    yuan_values = []
    for value in re.findall(r"订单总金额\s*[：:]\s*(\d+(?:\.\d+)?)\s*元", text):
        try:
            yuan_values.append(int(round(float(value) * 100)))
        except (TypeError, ValueError):
            pass
    values = cents_values + yuan_values
    if values:
        return int(expected_cents) in values
    return not require_amount


def _classify_sqb_log_text(text, expected_cents=None, source_kind="info"):
    """Classify only conclusive records appended during the current payment.

    The outer API field ``biz_response.result_code=SUCCESS`` only means that
    a query was handled successfully.  The money is received exclusively
    when the nested transaction is ``status=SUCCESS`` and
    ``order_status=PAID`` for the expected amount.
    """
    if not text:
        return "UNKNOWN"

    # info.log writes each server response on one line.  Keeping both fields
    # on the same line prevents unrelated records from being combined.
    for line in text.splitlines():
        if (
            re.search(r'"status"\s*:\s*"SUCCESS"', line)
            and re.search(r'"order_status"\s*:\s*"PAID"', line)
            and _amount_matches_log_text(line, expected_cents, require_amount=True)
        ):
            return "SUCCESS"

    # debug.log contains a multi-line receipt.  It is a valid fallback only
    # when the receipt amount agrees with the POS checkout amount.
    success_marker = text.rfind("ui.upaySuccess")
    if success_marker >= 0:
        success_block = text[success_marker:]
        if _amount_matches_log_text(success_block, expected_cents, require_amount=True):
            return "SUCCESS"

    # Generic payCancel is also emitted after success, so only the explicit
    # upay failure (or the info log's poll-cancel record) means failure.
    if re.search(r"upay failed\s*:\s*PAY_CANCEL", text, re.IGNORECASE):
        return "FAILED"
    if u"取消支付结果轮询" in text:
        return "FAILED"
    if re.search(r'"(?:status|order_status)"\s*:\s*"(?:FAILED|FAIL|CANCELLED|CANCELED)"', text):
        return "FAILED"

    if (
        "PAY_IN_PROGRESS" in text
        or re.search(r'"status"\s*:\s*"IN_PROG"', text)
        or u"正在发起支付" in text
    ):
        return "WAITING"
    return "UNKNOWN"


def _begin_sqb_log_probe(amount=None, config=None):
    """Snapshot current log ends so historical payments can never match."""
    global _sqb_log_files, _sqb_log_install_dir, _sqb_log_expected_cents
    global _sqb_log_session_started_at, _sqb_log_session_status
    expected_cents = None
    if amount is not None:
        try:
            expected_cents = int(round(float(amount) * 100))
        except (TypeError, ValueError):
            expected_cents = None

    started_at = time.time()
    install_dir = discover_shouqianba_install_dir(config)
    file_states = {}
    for path in get_shouqianba_log_paths(install_dir=install_dir):
        try:
            offset = os.path.getsize(path)
        except OSError:
            continue
        file_states[path] = {
            "offset": offset,
            "buffer": "",
            "kind": os.path.basename(os.path.dirname(path)).lower(),
        }
    with _sqb_log_lock:
        _sqb_log_files = file_states
        _sqb_log_install_dir = install_dir
        _sqb_log_expected_cents = expected_cents
        _sqb_log_session_started_at = started_at
        _sqb_log_session_status = "UNKNOWN"
    logger.info(
        "开始监听收钱吧日志：金额=%s分，文件=%s",
        expected_cents,
        list(file_states),
    )
    _write_sqb_monitor_event(
        u"收钱吧支付日志监听已启动",
        u"预期金额=%s分；安装目录=%s；日志=%s" % (
            expected_cents,
            install_dir or u"未找到",
            u" | ".join(file_states) if file_states else u"未找到",
        ),
    )


def _sqb_log_probe_available():
    with _sqb_log_lock:
        return bool(_sqb_log_session_started_at and _sqb_log_files)


def _get_sqb_log_payment_status(config=None):
    """Tail only newly appended SQB records for the active checkout."""
    global _sqb_log_session_status
    with _sqb_log_lock:
        if not _sqb_log_session_started_at:
            return "UNKNOWN"

        # A log may be created only after the plugin starts.  Add it from byte
        # zero when its modification time belongs to this active session;
        # otherwise begin at EOF to avoid accepting an old transaction.
        current_paths = (
            get_shouqianba_log_paths(install_dir=_sqb_log_install_dir)
            if _sqb_log_install_dir else []
        )
        for path in current_paths:
            if path in _sqb_log_files:
                continue
            try:
                size = os.path.getsize(path)
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            _sqb_log_files[path] = {
                "offset": 0 if mtime >= _sqb_log_session_started_at - 1.0 else size,
                "buffer": "",
                "kind": os.path.basename(os.path.dirname(path)).lower(),
            }

        observed = []
        for path, state in list(_sqb_log_files.items()):
            try:
                size = os.path.getsize(path)
                if size < state["offset"]:
                    state["offset"] = 0
                    state["buffer"] = ""
                if size > state["offset"]:
                    with open(path, "rb") as handle:
                        handle.seek(state["offset"])
                        payload = handle.read()
                        state["offset"] = handle.tell()
                    state["buffer"] = (
                        state["buffer"] + payload.decode("utf-8", errors="ignore")
                    )[-262144:]
                observed.append(_classify_sqb_log_text(
                    state["buffer"],
                    _sqb_log_expected_cents,
                    state["kind"],
                ))
            except (OSError, ValueError) as exc:
                logger.debug("读取收钱吧日志失败 %s: %s", path, exc)

        previous_status = _sqb_log_session_status
        if "SUCCESS" in observed:
            _sqb_log_session_status = "SUCCESS"
        elif _sqb_log_session_status != "SUCCESS" and "FAILED" in observed:
            _sqb_log_session_status = "FAILED"
        elif _sqb_log_session_status == "UNKNOWN" and "WAITING" in observed:
            _sqb_log_session_status = "WAITING"
        if _sqb_log_session_status != previous_status:
            _write_sqb_monitor_event(
                u"收钱吧支付日志状态变化",
                u"%s -> %s；预期金额=%s分" % (
                    previous_status,
                    _sqb_log_session_status,
                    _sqb_log_expected_cents,
                ),
            )
        return _sqb_log_session_status


def _find_runtime_payment_hwnds():
    """Find newly shown/foreground external windows during active payment."""
    if os.name != "nt":
        return []
    with _payment_probe_lock:
        started_at = _payment_probe_started_at
        baseline = set(_payment_probe_baseline_hwnds)
        baseline_foreground = _payment_probe_baseline_foreground
    if not started_at or time.monotonic() - started_at > 120.0:
        return []

    visible = _visible_external_window_hwnds()
    candidates = [hwnd for hwnd in visible if hwnd not in baseline]
    try:
        foreground = int(ctypes.windll.user32.GetForegroundWindow() or 0)
        if (
            foreground and foreground != baseline_foreground
            and foreground in visible and foreground not in candidates
        ):
            candidates.append(foreground)
    except Exception:
        pass
    return candidates


def _find_shouqianba_hwnds():
    """Return only top-level windows that belong to the 收钱吧 process.

    Payment completion must never inspect unrelated programs.  收钱吧 has no
    callback API in this deployment, so its own window identity is the first
    guard before the colour detector is allowed to run.
    """
    try:
        user32 = ctypes.windll.user32
        target_hwnds = []

        # 1. 获取收钱吧相关进程 PID 集合 (bqsqq / shouqianba / sqb)
        sqb_pids = set()
        try:
            import psutil
            for p in psutil.process_iter(['pid', 'name']):
                pname = (p.info['name'] or "").lower()
                if any(k in pname for k in ['bqsqq', 'shouqianba', 'sqb', 'pc收款']):
                    sqb_pids.add(p.info['pid'])
        except Exception:
            pass

        # Keep the strong identifiers first, but retain the V4 window titles
        # used by older PC收款 builds.  A generic "收款" candidate is still
        # passed through the colour/status classifier below; it is never
        # accepted as payment success from the title alone.
        keywords = [
            "收钱吧", "PC收款", "收款助手", "Shouqianba", "bqsqq",
            "收款", "V4.", "V3.",
        ]

        def foreach_window(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                # 优先匹配进程 ID
                if sqb_pids:
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value in sqb_pids:
                        target_hwnds.append(hwnd)
                        return True

                # 文本标题匹配。旧版仅显示“收款”/“V4.”时，必须再用
                # 对话框尺寸过滤，避免把普通银行/POS窗口当成收钱吧。
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value
                    strong_match = any(kw in title for kw in keywords[:5])
                    legacy_match = any(kw in title for kw in keywords[5:])
                    if strong_match:
                        target_hwnds.append(hwnd)
                    elif legacy_match:
                        rect = wintypes.RECT()
                        user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        width = rect.right - rect.left
                        height = rect.bottom - rect.top
                        if 200 <= width <= 900 and 200 <= height <= 900:
                            target_hwnds.append(hwnd)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
        user32.EnumWindows(WNDENUMPROC(foreach_window), 0)
        return target_hwnds
    except Exception:
        return []


def _find_shouqianba_hwnd():
    """Return the first identified 收钱吧 window for focus and barcode input."""
    windows = _find_shouqianba_hwnds()
    return windows[0] if windows else None


def send_hotkey(hotkey_str: str):
    """模拟键盘发送快捷键 (使用全局 keybd_event 触发系统级热键)"""
    if not hotkey_str:
        return False
    try:
        user32 = ctypes.windll.user32
        parts = [p.strip().upper() for p in hotkey_str.split("+") if p.strip()]
        if not parts or any(p not in VK_MAPPING for p in parts):
            return False
        vk_codes = [VK_MAPPING[p] for p in parts]

        KEYEVENTF_KEYUP = 0x0002

        # 为了防止修饰键(Shift/Ctrl/Alt)卡死导致鼠标键盘行为怪异，使用 try...finally 确保释放
        try:
            # 按下所有组合键
            for vk in vk_codes:
                scan_code = user32.MapVirtualKeyW(vk, 0)
                user32.keybd_event(vk, scan_code, 0, 0)
                time.sleep(0.02)

            time.sleep(0.05)
        finally:
            # 逆序释放键，保证必定执行
            for vk in reversed(vk_codes):
                scan_code = user32.MapVirtualKeyW(vk, 0)
                user32.keybd_event(vk, scan_code, KEYEVENTF_KEYUP, 0)
                time.sleep(0.02)
                
            # 额外保险：显式释放 Shift, Ctrl, Alt 防止卡死
            user32.keybd_event(VK_MAPPING["SHIFT"], user32.MapVirtualKeyW(VK_MAPPING["SHIFT"], 0), KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_MAPPING["CTRL"], user32.MapVirtualKeyW(VK_MAPPING["CTRL"], 0), KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_MAPPING["ALT"], user32.MapVirtualKeyW(VK_MAPPING["ALT"], 0), KEYEVENTF_KEYUP, 0)

        print(f"[快捷键唤起] 成功模拟发送全局快捷键: {hotkey_str}")
        return True
    except Exception as e:
        logger.warning(f"发送快捷键 {hotkey_str} 异常: {e}")
        return False


def is_supported_hotkey(hotkey_str: str) -> bool:
    """Validate a stored hotkey without injecting it into the system."""
    parts = [part.strip().upper() for part in str(hotkey_str or "").split("+") if part.strip()]
    return bool(parts) and all(part in VK_MAPPING for part in parts)


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
    """强行夺取键盘焦点并置顶收钱吧窗口 (突破 Windows 焦点锁定)"""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        target_hwnd = []

        def foreach_window(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value
                    if any(kw in title for kw in ["PC收款", "收钱吧", "收款助手", "Shouqianba", "bqsqq"]):
                        target_hwnd.append(hwnd)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
        user32.EnumWindows(WNDENUMPROC(foreach_window), 0)

        if target_hwnd:
            hwnd = target_hwnd[0]
            
            # 常规显示和置顶
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002) # HWND_TOPMOST
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002) # HWND_NOTOPMOST
            
            # 突破 Windows 限制，强行附加线程抢夺真正的键盘输入焦点
            foreground_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
            target_thread = user32.GetWindowThreadProcessId(hwnd, None)
            current_thread = kernel32.GetCurrentThreadId()

            if foreground_thread != current_thread:
                user32.AttachThreadInput(current_thread, foreground_thread, True)
                user32.SetForegroundWindow(hwnd)
                user32.SetFocus(hwnd)
                user32.AttachThreadInput(current_thread, foreground_thread, False)
            else:
                user32.SetForegroundWindow(hwnd)
                user32.SetFocus(hwnd)

            print(f"[收钱吧唤起] 已强行突破限制，为【PC收款】窗口注入真正的键盘焦点！")
            return True
    except Exception as e:
        logger.warning(f"强行唤起收钱吧窗口失败: {e}")
    return False


def _build_sqb_amount_payloads(amount: float, fmt: str):
    """按收钱吧插件配置生成“清零、金额”两个串口帧。"""
    amount_text = f"{amount:.2f}"
    if fmt == "QA":
        return "QA0.00\r\n", f"QA{amount_text}\r\n"
    return "0.00\r\n", f"{amount_text}\r\n"


def _open_shouqianba_payment(hotkey: str):
    """保持现场验证通过的收钱吧付款码聚焦顺序。

    Tab 必须使用 send_hotkey() 的全局 keybd_event 路径，并且无论置前函数的
    返回值如何都要发送一次。收钱吧 V4 能识别该全局 Tab；PostMessage、UIA
    或坐标点击都不能替代这一行为。
    """
    if hotkey:
        send_hotkey(hotkey)
    bring_shouqianba_to_front()
    time.sleep(SQB_TAB_FOCUS_DELAY)
    send_hotkey("TAB")


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


def _qimage_to_numpy_rgb(qimg):
    """Convert QImage to packed RGB safely for RapidOCR.

    ``convertToFormat(4)`` is RGB32 (four bytes/pixel), not RGB888.  The old
    code then reshaped that buffer as three bytes/pixel, corrupting OCR input.
    Qt also pads scanlines, so bytesPerLine must be handled explicitly.
    """
    import numpy as np
    from PyQt5.QtGui import QImage

    rgb = qimg.convertToFormat(QImage.Format_RGB888)
    width, height = rgb.width(), rgb.height()
    stride = rgb.bytesPerLine()
    ptr = rgb.bits()
    ptr.setsize(rgb.byteCount())
    rows = np.frombuffer(ptr, np.uint8).reshape((height, stride))
    return rows[:, :width * 3].reshape((height, width, 3)).copy()


def _grab_qt_window(screen, hwnd):
    """Grab a window, falling back to its screen rectangle on Win7.

    Some Chromium/Qt layered windows return a black or null pixmap when
    passed directly to QScreen.grabWindow().  Capturing the same rectangle
    from the desktop is reliable while the payment UI is visible.
    """
    def usable(candidate):
        if candidate.isNull() or candidate.width() < 120 or candidate.height() < 120:
            return False
        try:
            image = candidate.toImage()
            values = []
            for gx in range(1, 8):
                x = min(image.width() - 1, int(image.width() * gx / 8))
                for gy in range(1, 8):
                    y = min(image.height() - 1, int(image.height() * gy / 8))
                    pixel = image.pixelColor(x, y)
                    values.append(pixel.red() + pixel.green() + pixel.blue())
            return bool(values and max(values) > 45 and max(values) - min(values) > 24)
        except Exception:
            return False

    pixmap = screen.grabWindow(hwnd)
    if usable(pixmap):
        return pixmap
    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            rect = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width >= 120 and height >= 120:
                    desktop_pixmap = screen.grabWindow(0, rect.left, rect.top, width, height)
                    if usable(desktop_pixmap):
                        return desktop_pixmap
        except Exception:
            pass
    return pixmap


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

        pixmap = _grab_qt_window(screen, hwnd)
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
                img_np = _qimage_to_numpy_rgb(qimg)

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
    # 收钱吧是独立插件且没有回调；只信任已确认属于收钱吧进程的窗口色彩。
    return get_sqb_overall_status() == "SUCCESS"

    # Historical implementation retained below for compatibility reference only.
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

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
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
                rect = wintypes.RECT()
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


def check_shouqianba_payment_state() -> str:
    """
    三态全自动感知识别 (复用 OCR + Win32 双引擎)：
    - "SUCCESS": 检测到【支付成功/收款成功】
    - "WAITING": 检测到收钱吧【付款中/等待扫码/付款码框】界面 (保持静默等待)
    - "CLOSED" : 收钱吧付款界面已关闭或未找到
    """
    return get_sqb_overall_status()

    import sys
    if sys.platform != "win32":
        return "CLOSED"

    try:
        user32 = ctypes.windll.user32
        
        success_keywords = ["支付成功", "收款成功", "交易成功", "收钱吧到账", "打印小票"]
        waiting_keywords = [
            "付款码", "支付方式", "显示虚拟键盘", "电脑扫码", "请扫码", "主扫", "被扫", 
            "待支付", "输入密码", "倒计时", "EP99", "收款", "V4.0.4", "PC收款", "收钱吧"
        ]

        state = ["CLOSED"]

        def get_text_from_hwnd(h):
            texts = []
            try:
                l = user32.GetWindowTextLengthW(h)
                if l > 0:
                    buf = ctypes.create_unicode_buffer(l + 1)
                    user32.GetWindowTextW(h, buf, l + 1)
                    texts.append(buf.value.strip())
            except Exception:
                pass
            return " ".join(texts)

        def foreach_window(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                title_txt = get_text_from_hwnd(hwnd)
                
                # A. Win32 标题/子控件文本匹配
                if title_txt:
                    if any(sk in title_txt for sk in success_keywords):
                        state[0] = "SUCCESS"
                        return False
                    if any(wk in title_txt for wk in waiting_keywords):
                        state[0] = "WAITING"

                # B. 视觉/RapidOCR 提取识别
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if 200 <= w <= 900 and 200 <= h <= 900:
                    if _analyze_sqb_window_image_success(hwnd):
                        state[0] = "SUCCESS"
                        return False
                        
                    ocr_engine = _get_ocr_engine()
                    if ocr_engine:
                        try:
                            from PyQt5.QtWidgets import QApplication
                            screen = QApplication.primaryScreen()
                            if screen:
                                pixmap = _grab_qt_window(screen, hwnd)
                                if not pixmap.isNull() and pixmap.width() >= 120 and pixmap.height() >= 120:
                                    qimg = pixmap.toImage()
                                    img_np = _qimage_to_numpy_rgb(qimg)
                                    result, _ = ocr_engine(img_np)
                                    if result:
                                        ocr_text = "".join([line[1] for line in result])
                                        if any(sk in ocr_text for sk in success_keywords):
                                            state[0] = "SUCCESS"
                                            return False
                                        if any(wk in ocr_text for wk in waiting_keywords):
                                            state[0] = "WAITING"
                        except Exception:
                            pass
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
        user32.EnumWindows(WNDENUMPROC(foreach_window), 0)
        
        if state[0] != "SUCCESS" and check_shouqianba_payment_success():
            return "SUCCESS"
            
        return state[0]
    except Exception as e:
        logger.warning(f"三态检测收钱吧状态异常: {e}")
        return "CLOSED"


def _analyze_sqb_window_colour_status(hwnd) -> str:
    """Classify the known 收钱吧 window by its V4 visual colours only.

    OCR is intentionally excluded: the deployed V4 client renders text in a
    way that produces unreliable OCR.  Green must also appear in the lower
    action area, which avoids treating a random green title bar as a payment.
    """
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        screen = QApplication.primaryScreen() if app else None
        if not screen:
            return "NONE"
        pixmap = _grab_qt_window(screen, hwnd)
        if pixmap.isNull() or pixmap.width() < 120 or pixmap.height() < 120:
            return "NONE"
        qimg = pixmap.toImage()
        w, h = qimg.width(), qimg.height()
        header_h = max(20, int(h * 0.25))
        green = blue = samples = 0
        for x in range(10, max(11, w - 10), 6):
            for y in range(10, max(11, header_h - 5), 6):
                pixel = qimg.pixelColor(x, y)
                r, g, b = pixel.red(), pixel.green(), pixel.blue()
                samples += 1
                # Allow Win7/DPI antialiasing to desaturate the V4 header;
                # requiring a large pure-green/blue delta made valid frames
                # disappear on some store displays.
                if g > r + 18 and g > b + 8 and g > 90:
                    green += 1
                elif b > r + 18 and b > g + 8 and b > 85:
                    blue += 1
        if not samples:
            return "NONE"
        if green / samples > 0.20:
            button_green = button_samples = 0
            for x in range(int(w * 0.20), int(w * 0.80), 5):
                for y in range(int(h * 0.62), max(int(h * 0.62) + 1, h - 8), 5):
                    pixel = qimg.pixelColor(x, y)
                    r, g, b = pixel.red(), pixel.green(), pixel.blue()
                    button_samples += 1
                    if g > r + 18 and g > b + 8 and g > 90:
                        button_green += 1
            if button_samples and button_green / button_samples > 0.025:
                return "SUCCESS"
        if blue / samples > 0.20:
            return "WAITING"
    except Exception as exc:
        logger.warning("收钱吧颜色状态识别异常: %s", exc)
    return "NONE"


def _analyze_sqb_window_image_status(hwnd) -> str:
    """
    复用 RapidOCR + 宝蓝/亮绿顶栏色彩双引擎深度分类收钱吧窗口状态:
    返回 "SUCCESS" / "WAITING" / "NONE"
    """
    # The V4 colour detector is the primary path validated on the store PC.
    # OCR remains only a fallback for themed/scaled windows whose pixels do
    # not meet the colour thresholds.
    colour_state = _analyze_sqb_window_colour_status(hwnd)
    if colour_state != "NONE":
        return colour_state

    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            return "NONE"
        screen = QApplication.primaryScreen()
        if not screen:
            return "NONE"

        pixmap = _grab_qt_window(screen, hwnd)
        if pixmap.isNull() or pixmap.width() < 120 or pixmap.height() < 120:
            return "NONE"

        qimg = pixmap.toImage()
        w = qimg.width()
        h = qimg.height()

        # A. RapidOCR 深度文字提取
        ocr_engine = _get_ocr_engine()
        if ocr_engine:
            try:
                img_np = _qimage_to_numpy_rgb(qimg)

                result, _ = ocr_engine(img_np)
                if result:
                    all_ocr_text = "".join([line[1] for line in result])
                    
                    success_keywords = ["支付成功", "收款成功", "交易成功", "打印小票", "收钱吧到账"]
                    if any(sk in all_ocr_text for sk in success_keywords):
                        return "SUCCESS"

                    waiting_keywords = [
                        "付款码", "支付方式", "显示虚拟键盘", "电脑扫码", "请扫码", "主扫", "被扫", 
                        "待支付", "输入密码", "倒计时", "EP99", "收款", "V4.0", "V4.", "PC收款", "收钱吧"
                    ]
                    if any(wk in all_ocr_text for wk in waiting_keywords):
                        return "WAITING"
            except Exception as e:
                logger.warning(f"RapidOCR 提取状态异常: {e}")

        # B. 色彩采样引擎 (蓝顶=付款中, 绿顶=支付成功)
        header_h = int(h * 0.25)
        green_count = 0
        blue_count = 0
        total_samples = 0

        for x in range(10, w - 10, 6):
            for y in range(10, header_h - 5, 6):
                pixel = qimg.pixelColor(x, y)
                r, g, b = pixel.red(), pixel.green(), pixel.blue()
                total_samples += 1
                if g > r + 18 and g > b + 8 and g > 90:
                    green_count += 1
                elif b > r + 18 and b > g + 8 and b > 85:
                    blue_count += 1

        if total_samples > 0:
            if green_count / total_samples > 0.20:
                return "SUCCESS"
            if blue_count / total_samples > 0.20: # 经典宝蓝顶栏 = 正处于等待付款界面
                return "WAITING"

    except Exception as e:
        logger.warning(f"分析收钱吧窗口图像状态异常: {e}")

    return "NONE"


_PAYMENT_SUCCESS_KEYWORDS = ("支付成功", "收款成功", "交易成功", "收钱吧到账")
_PAYMENT_FAILURE_KEYWORDS = ("支付失败", "交易失败", "支付中", "输入密码", "待支付")
_toast_probe_lock = threading.Lock()
_toast_probe_at = 0.0
_toast_probe_result = False


def _rect_is_bottom_right_toast(rect, screen_width, screen_height):
    """Return whether a window rectangle looks like a lower-right POS toast."""
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return (
        140 <= width <= 760 and 45 <= height <= 420
        and rect.left >= int(screen_width * 0.52)
        and rect.top >= int(screen_height * 0.48)
        and rect.right >= int(screen_width * 0.78)
    )


def _window_contains_payment_success_text(hwnd, user32):
    """Read normal Win32 text from a toast and its child controls.

    The official POS notification in the store build is often a separate
    lower-right window.  Its text can be available through Win32 even when
    screenshot OCR is unavailable, so this is deliberately tried first.
    """
    def text_of(handle):
        try:
            length = user32.GetWindowTextLengthW(handle)
            if length <= 0 or length > 2048:
                return ""
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(handle, buffer, length + 1)
            return buffer.value.strip()
        except Exception:
            return ""

    texts = [text_of(hwnd)]
    found = [any(k in texts[0] for k in _PAYMENT_SUCCESS_KEYWORDS)]

    def child_callback(child_hwnd, _lparam):
        txt = text_of(child_hwnd)
        if txt:
            texts.append(txt)
            if any(k in txt for k in _PAYMENT_SUCCESS_KEYWORDS):
                found[0] = True
                return False
        return True

    try:
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
        user32.EnumChildWindows(hwnd, callback_type(child_callback), 0)
    except Exception:
        pass
    if found[0]:
        return True
    # Do not interpret a text-free white window, or a visible
    # failure/waiting toast, as success.
    return False


def _detect_payment_success_toast_text(config=None):
    """Detect the official POS lower-right success notification without OCR."""
    if os.name != "nt":
        return False
    try:
        user32 = ctypes.windll.user32
        screen_width = int(user32.GetSystemMetrics(0))
        screen_height = int(user32.GetSystemMetrics(1))
        if screen_width <= 0 or screen_height <= 0:
            return False

        configured_hwnd = None
        try:
            from utils.window_utils import find_official_window_handle
            configured_hwnd = find_official_window_handle(config)
        except Exception:
            configured_hwnd = None

        current_pid = os.getpid()
        found = [False]

        def inspect_window(hwnd, require_toast_rect=True):
            if not user32.IsWindowVisible(hwnd):
                return
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == current_pid:
                return
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return
            if require_toast_rect and not _rect_is_bottom_right_toast(rect, screen_width, screen_height):
                return
            if _window_contains_payment_success_text(hwnd, user32):
                found[0] = True

        # Prefer the operator-selected official POS window.  Its main window
        # is full-screen, so its child toast controls are inspected directly.
        if configured_hwnd:
            def configured_child_callback(child_hwnd, _lparam):
                rect = wintypes.RECT()
                if user32.IsWindowVisible(child_hwnd) and user32.GetWindowRect(child_hwnd, ctypes.byref(rect)):
                    if _rect_is_bottom_right_toast(rect, screen_width, screen_height):
                        if _window_contains_payment_success_text(child_hwnd, user32):
                            found[0] = True
                            return False
                return True
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
            user32.EnumChildWindows(configured_hwnd, callback_type(configured_child_callback), 0)
        else:
            def foreach_window(hwnd, _lparam):
                if found[0]:
                    return False
                inspect_window(hwnd, True)
                return not found[0]
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
            user32.EnumWindows(callback_type(foreach_window), 0)
        return found[0]
    except Exception as exc:
        logger.debug("读取官方 POS 支付通知失败: %s", exc)
        return False


def _detect_payment_success_toast_ocr(config=None):
    """OCR the lower-right notification region on every attached screen."""
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        screens = QApplication.screens() if app else []
        if not screens:
            return False
        engine = _get_ocr_engine()
        if not engine:
            return False

        def pixmap_has_success(pixmap):
            if pixmap.isNull() or pixmap.width() < 180 or pixmap.height() < 80:
                return False
            left = int(pixmap.width() * 0.50)
            top = int(pixmap.height() * 0.46)
            crop = pixmap.copy(
                left,
                top,
                pixmap.width() - left,
                pixmap.height() - top,
            )
            values = _qimage_to_numpy_rgb(crop.toImage())
            result, _ = engine(values)
            if not result:
                return False
            text = "".join(line[1] for line in result)
            # The crop can contain background words such as “待支付”; an
            # explicit “支付成功” notification must take precedence.
            return any(k in text for k in _PAYMENT_SUCCESS_KEYWORDS)

        # First inspect the configured official POS window itself.  This can
        # still expose its rendered toast on Win11 even when another window
        # overlaps it on the desktop.
        official_hwnd = None
        try:
            from utils.window_utils import find_official_window_handle
            official_hwnd = find_official_window_handle(config)
        except Exception:
            official_hwnd = None
        if official_hwnd:
            for screen in screens:
                pixmap = screen.grabWindow(official_hwnd)
                if pixmap_has_success(pixmap):
                    return True

        for screen in screens:
            geometry = screen.availableGeometry()
            left = geometry.left() + int(geometry.width() * 0.56)
            top = geometry.top() + int(geometry.height() * 0.52)
            width = geometry.width() - (left - geometry.left())
            height = int(geometry.height() * 0.46)
            pixmap = screen.grabWindow(0, left, top, width, height)
            if pixmap.isNull() or pixmap.width() < 180 or pixmap.height() < 80:
                continue
            values = _qimage_to_numpy_rgb(pixmap.toImage())
            result, _ = engine(values)
            if not result:
                continue
            text = "".join(line[1] for line in result)
            if any(k in text for k in _PAYMENT_SUCCESS_KEYWORDS):
                return True
        return False
    except Exception as exc:
        logger.debug("读取官方 POS 支付通知 OCR 失败: %s", exc)
        return False


def _detect_payment_success_toast(config=None):
    """Throttled notification probe used only while a payment is active."""
    global _toast_probe_at, _toast_probe_result
    now = time.monotonic()
    with _toast_probe_lock:
        if now - _toast_probe_at < 0.45:
            return _toast_probe_result
        result = _detect_payment_success_toast_text(config)
        if not result:
            result = _detect_payment_success_toast_ocr(config)
        _toast_probe_at = now
        _toast_probe_result = bool(result)
        return _toast_probe_result


def reset_payment_toast_probe():
    """Forget a previous toast before starting a new checkout monitor."""
    global _toast_probe_at, _toast_probe_result
    with _toast_probe_lock:
        _toast_probe_at = 0.0
        _toast_probe_result = False


def get_sqb_overall_status(config=None) -> str:
    """
    获取收钱吧实时状态。安装目录可用时以插件自身日志为准：
    - "SUCCESS" : 扣款成功
    - "FAILED"  : 本次支付取消或失败
    - "WAITING" : 付款码弹窗显示中 (蓝顶/付款文本)
    - "CLOSED"  : 无付款弹窗
    """
    log_status = _get_sqb_log_payment_status(config)
    if log_status in ("SUCCESS", "FAILED"):
        return log_status

    # Once info/debug logs are available, they are the authoritative signal.
    # OCR and colours remain only a compatibility fallback for old installs
    # that expose no logs.  This prevents an unrelated official-POS toast or
    # a stale green window from completing the current SQB order.
    if _sqb_log_probe_available():
        return "WAITING"

    # Never enumerate all visible Windows windows here: only the verified
    # 收钱吧 process/window is eligible for visual payment detection.
    # Use both stable identity matching and the payment-session window
    # snapshot.  The latter covers SQB builds with empty/changing titles.
    candidates = list(dict.fromkeys(
        _find_shouqianba_hwnds() + _find_runtime_payment_hwnds()
    ))
    saw_waiting = False
    for hwnd in candidates:
        result = _analyze_sqb_window_image_status(hwnd)
        if result == "SUCCESS":
            return "SUCCESS"
        if result == "WAITING":
            saw_waiting = True
    # The lower-right “支付成功” notification has higher priority than the
    # payment window.  Some SQB builds keep their blue waiting window alive
    # for a short time after payment; suppressing toast detection while
    # saw_waiting=True made successful payments impossible to observe.
    if _detect_payment_success_toast(config):
        return "SUCCESS"
    # A recognised 收钱吧 payment window whose pixels are temporarily
    # unavailable (DWM/Win7 repaint, animation, remote desktop) is safer to
    # treat as WAITING than as CLOSED.  Only a missing candidate window may
    # trigger the "是否到账" confirmation dialog.
    if candidates:
        return "WAITING"
    return "CLOSED"

    import sys
    if sys.platform != "win32":
        return "CLOSED"

    try:
        user32 = ctypes.windll.user32
        status = ["CLOSED"]

        def foreach_window(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                
                if 200 <= w <= 900 and 200 <= h <= 900:
                    res = _analyze_sqb_window_image_status(hwnd)
                    if res == "SUCCESS":
                        status[0] = "SUCCESS"
                        return False
                    elif res == "WAITING":
                        status[0] = "WAITING"
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
        user32.EnumWindows(WNDENUMPROC(foreach_window), 0)
        return status[0]
    except Exception:
        return "CLOSED"


def _do_send_amount(amount: float, config: dict):
    """后台子线程多通道推送逻辑"""
    enabled = config.get("shouqianba_enabled", True)
    if not enabled:
        return

    # 1. 串口推送逻辑 (先通过COM发送金额)
    port = config.get("shouqianba_port", "COM10")
    baudrate = int(config.get("shouqianba_baudrate", 2400))  # 默认 2400
    fmt = config.get("shouqianba_format", "QA")               # "QA" 或 "FLOAT"
    reset_payload, payload = _build_sqb_amount_payloads(amount, fmt)

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

    # 如果是归零/重置清空 (amount <= 0)，只静默向串口发送 0.00 冲刷缓存，不触发快捷键唤起和窗口置顶
    if amount <= 0.0:
        print("[收钱吧串口] 已完成静默 0.00 金额重置，隐藏前台唤起。")
        return

    # 2. 唤起收款界面并把焦点从金额框跳到付款码框。
    _open_shouqianba_payment(config.get("shouqianba_hotkey", "Shift+Q"))


def send_shouqianba_amount(amount: float, config: dict):
    """
    非阻塞异步多通道发送金额到收钱吧（绝对不卡顿主界面）
    """
    t = threading.Thread(target=_do_send_amount, args=(amount, config), daemon=True)
    t.start()


def clear_shouqianba_amount(config: dict):
    """取消/退出时清空收钱吧插件金额框 (发送 0.00 重置包)"""
    send_shouqianba_amount(0.00, config)


def is_shouqianba_window_open() -> bool:
    """检查收钱吧前台/支付窗口是否正处于打开/可见状态"""
    import sys
    if sys.platform != "win32":
        return False
    return _find_shouqianba_hwnd() is not None


def test_shouqianba_port(config: dict):
    """
    自检测试：向配置的收钱吧串口发送数据测试连通性
    返回 (is_ok: bool, message: str)
    """
    enabled = config.get("shouqianba_enabled", True)
    if not enabled:
        return False, "功能已禁用"

    port = config.get("shouqianba_port", "COM10")
    baudrate = int(config.get("shouqianba_baudrate", 2400))
    fmt = config.get("shouqianba_format", "QA")

    _, payload = _build_sqb_amount_payloads(0.0, fmt)

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
            # 精准向收钱吧窗口发送 Enter，不干扰全局键鼠
            sqb_hwnd = _find_shouqianba_hwnd()
            if sqb_hwnd:
                user32 = ctypes.windll.user32
                VK_RETURN = 0x0D
                scan = user32.MapVirtualKeyW(VK_RETURN, 0)
                user32.PostMessageW(sqb_hwnd, 0x0100, VK_RETURN, (1 | (scan << 16)))
                time.sleep(0.02)
                user32.PostMessageW(sqb_hwnd, 0x0101, VK_RETURN, (1 | (scan << 16) | (3 << 30)))
                print("[扫码补偿] 精准向收钱吧窗口补发 Enter")
            else:
                # 降级：全局发送（仅在收钱吧窗口找不到时）
                send_hotkey("ENTER")

if keyboard is not None:
    try:
        keyboard.on_press(_global_key_listener)
        _t = threading.Thread(target=_barcode_checker_loop, daemon=True)
        _t.start()
        logger.info("支付宝碰一碰设备无回车补偿器已启动")
    except Exception as _e:
        logger.warning(f"碰一碰监听器启动失败（可能需要管理员权限）: {_e}")
else:
    logger.info("未安装 keyboard，可选的碰一碰无回车补偿器未启动")
