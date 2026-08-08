"""
Windows 窗口查找与句柄控制工具
用于在官方收银系统与本辅助 POS 系统之间进行前台切换
"""
import ctypes
import os
import sys
import time
import subprocess
from collections import OrderedDict

try:
    user32 = ctypes.windll.user32
except Exception:
    user32 = None

# 常用的官方收银系统可能出现的窗口标题关键词或类名
OFFICIAL_WINDOW_TITLES = ["杨国福", "官方收银", "店长端", "餐饮管理"]

# 官方收银系统的可执行进程名列表
OFFICIAL_PROCESS_NAMES = ["yangguofu.exe", "ygf-pos.exe", "ygf.exe"]


def _configured_keywords(config, key, defaults):
    values = (config or {}).get(key, defaults)
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    return [str(item).strip().lower() for item in values if str(item).strip()]


def is_official_window_configured(config=None):
    """Return whether an operator has explicitly selected an official POS window.

    Window recognition is deliberately opt-in.  Generic historical defaults are
    not enough because they can accidentally match another checkout window.
    """
    cfg = config or {}
    keywords = _configured_keywords(cfg, "official_pos_window_keywords", [])
    return bool(cfg.get("official_pos_window_configured", False) and keywords)


def _process_name_for_pid(pid, cache):
    """Read a process executable basename without requiring psutil."""
    if pid in cache:
        return cache[pid]
    name = ""
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            PROCESS_QUERY_INFORMATION = 0x0400
            PROCESS_VM_READ = 0x0010
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
                False,
                int(pid),
            )
            if handle:
                try:
                    buffer = ctypes.create_unicode_buffer(1024)
                    size = ctypes.c_uint32(len(buffer))
                    query = getattr(kernel32, "QueryFullProcessImageNameW", None)
                    if query and query(handle, 0, buffer, ctypes.byref(size)):
                        name = os.path.basename(buffer.value)
                finally:
                    kernel32.CloseHandle(handle)
        except Exception:
            name = ""
    cache[pid] = name
    return name


def get_window_info(hwnd, process_cache=None):
    """Return a stable, displayable descriptor for a top-level HWND."""
    if not user32 or not hwnd:
        return None
    try:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return None
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        title = title_buffer.value.strip()
        if not title:
            return None

        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        class_buffer = ctypes.create_unicode_buffer(256)
        class_length = user32.GetClassNameW(hwnd, class_buffer, len(class_buffer))
        class_name = class_buffer.value[:class_length] if class_length else ""
        cache = process_cache if process_cache is not None else {}
        process_name = _process_name_for_pid(pid.value, cache)
        return {
            "hwnd": int(hwnd),
            "title": title,
            "pid": int(pid.value),
            "process_name": process_name,
            "class_name": class_name,
        }
    except Exception:
        return None


def _root_window_handle(hwnd):
    """Return the top-level owner for a foreground child/popup HWND."""
    if not user32 or not hwnd:
        return int(hwnd) if hwnd else None
    try:
        # GA_ROOT = 2.  A taskbar click can focus a child dialog, while the
        # configured identity is stored on the POS's top-level window.
        get_ancestor = getattr(user32, "GetAncestor", None)
        root = get_ancestor(hwnd, 2) if get_ancestor else hwnd
        return int(root or hwnd)
    except Exception:
        return int(hwnd)


def detect_foreground_pos_channel(main_window, config=None):
    """Detect which configured POS is currently in the Windows foreground.

    Returns ``True`` for the private POS, ``False`` for the configured official
    POS, and ``None`` when another application (or no titled window) is active.
    This is intentionally a read-only probe: it never raises, focuses windows,
    or changes routing decisions by itself.
    """
    if not user32:
        return None
    try:
        foreground = user32.GetForegroundWindow()
        if not foreground:
            return None
        foreground_root = _root_window_handle(foreground)

        if main_window is not None:
            private_hwnd = int(main_window.winId())
            if foreground_root == _root_window_handle(private_hwnd):
                return True

        # Read only the foreground descriptor instead of enumerating all
        # windows once per second.  The selected title prefix is the required
        # primary identity used by the POS picker; process matching remains a
        # preference there so a renamed executable is still recognized.
        info = get_window_info(foreground_root)
        if info and _window_title_matches(info, config):
            return False
    except Exception:
        return None
    return None


def list_visible_windows():
    """List visible, titled top-level windows for the operator's picker."""
    if not user32:
        return []
    current_pid = os.getpid()
    process_cache = {}
    result = []

    def callback(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == current_pid:
                return True
            info = get_window_info(hwnd, process_cache)
            if info:
                result.append(info)
        except Exception:
            pass
        return True

    try:
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
        user32.EnumWindows(callback_type(callback), 0)
    except Exception:
        return []

    # Keep one entry per HWND and make the list deterministic for touch use.
    unique = OrderedDict((item["hwnd"], item) for item in result)
    return sorted(unique.values(), key=lambda item: (item["title"].lower(), item["pid"]))


def _window_title_matches(info, config):
    keywords = _configured_keywords(config, "official_pos_window_keywords", [])
    if not keywords:
        return False
    title = info.get("title", "")
    title_lower = title.lower()
    if any(marker in title for marker in ("免安装", "辅助", "排序")):
        return False
    return any(keyword in title_lower for keyword in keywords)


def _window_process_matches(info, config):
    keywords = _configured_keywords(config, "official_pos_process_keywords", [])
    if not keywords:
        return True
    process_name = info.get("process_name", "").lower()
    if not process_name:
        return False
    return any(keyword in process_name for keyword in keywords)


def find_official_window_info(config=None):
    """Find the configured official POS window and return its descriptor."""
    if not user32 or not is_official_window_configured(config):
        return None
    windows = list_visible_windows()
    title_matches = [item for item in windows if _window_title_matches(item, config)]
    if not title_matches:
        return None

    # Prefer the selected process identity, but retain title matching as the
    # required primary signal so a renamed executable can still be diagnosed.
    process_matches = [item for item in title_matches if _window_process_matches(item, config)]
    return (process_matches or title_matches)[0]


def find_official_pids(config=None):
    """通过系统进程列表精准获取官方收银软件的 PID 集合"""
    pids = set()
    try:
        process_names = _configured_keywords(config, "official_pos_process_keywords", [])
        if not process_names:
            return pids
        cmd = 'tasklist /NH /FO CSV'
        output = subprocess.check_output(cmd, shell=True).decode('gbk', errors='ignore')
        current_pid = os.getpid()
        for line in output.splitlines():
            line_lower = line.lower()
            if 'python' in line_lower:
                continue
            for proc_name in process_names:
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


def find_official_window_handle(config=None):
    """查找已配置的官方 POS 窗口；未配置窗口识别词时绝不猜测。"""
    info = find_official_window_info(config)
    return info.get("hwnd") if info else None


def is_official_pos_available(config=None):
    """Return whether the configured official POS is currently visible.

    Auto-switching must use this explicit probe before hiding the private POS;
    a missing official window is a valid development/standalone scenario, not
    a reason to send the operator to an empty desktop.
    """
    return find_official_window_info(config) is not None


def apply_official_window_selection(config, info):
    """Persist the operator-selected window identity into the shared config."""
    if not config or not info:
        return False
    title = str(info.get("title", "")).strip()
    if not title:
        return False
    # Titles often append a changing order/state suffix.  Keep the stable
    # prefix as the required recognition word while retaining the full title
    # for display and future diagnostics.
    prefix = title
    for separator in (" - ", " | ", " — ", " – "):
        if separator in prefix:
            prefix = prefix.split(separator, 1)[0].strip()
    config["official_pos_window_configured"] = True
    config["official_pos_window_title"] = title
    config["official_pos_window_class"] = str(info.get("class_name", "")).strip()
    config["official_pos_process_name"] = str(info.get("process_name", "")).strip()
    config["official_pos_window_keywords"] = [prefix or title]
    process_name = str(info.get("process_name", "")).strip()
    config["official_pos_process_keywords"] = [process_name] if process_name else []
    return True


def bring_official_to_front(config=None):
    """将官方收银系统切到前台，但不强制最大化。"""
    if not user32:
        return False

    if config is None:
        # The emergency hotkey has no Qt/MainWindow argument.  Load the
        # persisted identity so panic switching uses the same configured
        # window as login detection and the normal auto-switch controller.
        try:
            from config import load_config
            config = load_config()
        except Exception:
            config = {}

    hwnd = find_official_window_handle(config)
    if hwnd:
        try:
            # When the official POS is already active, avoid sending another
            # foreground/maximize request.  On Win7 that request causes a
            # visible flash even though no real channel switch occurred.
            if user32.GetForegroundWindow() == hwnd and not user32.IsIconic(hwnd):
                return True
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9 还原窗口
            user32.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            print("[WindowUtils] 切换至官方软件失败:", e)
            return False
    return False


def bring_our_pos_to_front(main_window):
    """将本 POS 切到前台并保持最大化普通窗口（保留任务栏）。"""
    if not main_window:
        return
    try:
        hwnd = int(main_window.winId())
        if user32 and user32.GetForegroundWindow() == hwnd and not user32.IsIconic(hwnd):
            # The POS is already active; do not touch its window state.  This
            # is the important anti-flicker path for repeated scale samples.
            return
        main_window.showMaximized()
        main_window.activateWindow()
        main_window.raise_()
        if user32:
            user32.SetForegroundWindow(hwnd)
    except Exception as e:
        print("[WindowUtils] 切换至本系统失败:", e)
