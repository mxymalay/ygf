"""Small self-contained Windows installer/uninstaller for the YGF POS bundle.

The build script embeds a zip payload into this file with PyInstaller.  This
module intentionally uses only the Python standard library so the setup EXE
does not depend on the POS application's virtual environment.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

import ctypes
from ctypes import wintypes

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False
    tk = filedialog = messagebox = simpledialog = ttk = None

try:
    import winreg
except ImportError:  # pragma: no cover - only used on Windows
    winreg = None


def _native_showinfo(title, message):
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(0, str(message), str(title), 0x40)


def _install_complete_message(display_name, target_dir):
    """Return the same explicit completion notice for both installer UIs."""
    return (
        "安装完成！\n\n"
        "%s 已安装/更新完成。\n\n"
        "点击“现在打开”可立即启动 POS，点击“完成”只关闭安装器。\n"
        "实际程序文件：启动.exe\n"
        "安装路径：%s"
        % (display_name, target_dir)
    )


def _open_installed_app(target_dir):
    """Start the installed launcher after the completion dialog is closed."""
    launcher = os.path.join(os.path.abspath(target_dir), "启动.exe")
    if not os.path.isfile(launcher):
        return False
    try:
        subprocess.Popen([launcher], cwd=os.path.dirname(launcher), close_fds=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _native_install_complete(display_name, target_dir):
    """Win32 fallback with explicit Open/Finish choices for Win7."""
    message = _install_complete_message(display_name, target_dir)
    if os.name == "nt":
        result = ctypes.windll.user32.MessageBoxW(
            0,
            message,
            "安装/更新完成",
            0x00000004 | 0x00000040 | 0x00010000,  # MB_YESNO | MB_ICONINFORMATION | MB_SETFOREGROUND
        )
        if result == 6:  # IDYES = 现在打开
            _open_installed_app(target_dir)
        return result == 6
    _native_showinfo("安装/更新完成", message)
    return False


def _show_install_complete(root, display_name, target_dir):
    """Show a foreground completion dialog with ``现在打开`` / ``完成``."""
    if not HAS_TKINTER or root is None:
        return _native_install_complete(display_name, target_dir)

    dialog = tk.Toplevel(root)
    dialog.title("安装/更新完成")
    dialog.geometry("520x260")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    try:
        dialog.grab_set()
        dialog.focus_force()
        dialog.lift()
    except tk.TclError:
        pass

    frame = ttk.Frame(dialog, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="安装/更新完成", font=("Microsoft YaHei", 18, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text=("%s 已安装/更新完成。\n\n"
               "现在打开：立即启动 POS\n"
               "完成：关闭安装器，不启动 POS") % display_name,
        justify="left",
        wraplength=460,
    ).pack(anchor="w", pady=(16, 20))
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", side="bottom")

    def close_and_open():
        try:
            dialog.grab_release()
        except tk.TclError:
            pass
        dialog.destroy()
        root.destroy()
        _open_installed_app(target_dir)

    def close_only():
        try:
            dialog.grab_release()
        except tk.TclError:
            pass
        dialog.destroy()

    ttk.Button(buttons, text="现在打开", command=close_and_open).pack(side="left", ipadx=24, ipady=8)
    ttk.Button(buttons, text="完成", command=close_only).pack(side="right", ipadx=24, ipady=8)
    dialog.wait_window()
    return False


def _native_showerror(title, message):
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(0, str(message), str(title), 0x10)


def _native_askyesno(title, message):
    if os.name == "nt":
        return ctypes.windll.user32.MessageBoxW(0, str(message), str(title), 0x24) == 6
    return True


def _native_select_folder(initial_dir):
    """Win32 folder picker used when the packaged Tk runtime is unavailable."""
    if os.name != "nt":
        return None
    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    ole32 = ctypes.windll.ole32

    class BROWSEINFO(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", ctypes.c_void_p),
            ("pidlRoot", ctypes.c_void_p),
            ("pszDisplayName", ctypes.c_wchar_p),
            ("lpszTitle", ctypes.c_wchar_p),
            ("ulFlags", ctypes.c_uint),
            ("lpfn", ctypes.c_void_p),
            ("lParam", ctypes.c_void_p),
            ("iImage", ctypes.c_int),
        ]

    BFFM_INITIALIZED = 1
    BFFM_SETSELECTIONW = 0x467
    BIF_RETURNONLYFSDIRS = 0x0001
    BIF_NEWDIALOGSTYLE = 0x0040
    initial = os.path.abspath(initial_dir or os.getcwd())
    initial_buffer = ctypes.create_unicode_buffer(initial)

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, message, _lparam, data):
        if message == BFFM_INITIALIZED:
            user32.SendMessageW(hwnd, BFFM_SETSELECTIONW, 1, ctypes.c_wchar_p(data))
        return 0

    display = ctypes.create_unicode_buffer(260)
    info = BROWSEINFO(
        0,
        0,
        ctypes.cast(display, ctypes.c_wchar_p),
        "请选择安装目录",
        BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE,
        ctypes.cast(callback, ctypes.c_void_p),
        ctypes.cast(initial_buffer, ctypes.c_void_p),
        0,
    )
    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
    pidl = shell32.SHBrowseForFolderW(ctypes.byref(info))
    if not pidl:
        return None
    try:
        path = ctypes.create_unicode_buffer(32768)
        if shell32.SHGetPathFromIDListW(pidl, path):
            return path.value
        return None
    finally:
        ole32.CoTaskMemFree(pidl)


def _native_prompt_string(title, prompt, initial_value=""):
    """Small native Win32 text dialog for the no-Tk fallback path."""
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    WM_COMMAND = 0x0111
    WM_CLOSE = 0x0010
    WM_DESTROY = 0x0002
    ID_OK = 1
    ID_CANCEL = 2
    WS_OVERLAPPED = 0x00000000
    WS_CAPTION = 0x00C00000
    WS_SYSMENU = 0x00080000
    WS_VISIBLE = 0x10000000
    WS_CHILD = 0x40000000
    WS_TABSTOP = 0x00010000
    ES_AUTOHSCROLL = 0x0080
    BS_DEFPUSHBUTTON = 0x00000001
    COLOR_WINDOW = 5
    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p
    )

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", ctypes.c_uint),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", ctypes.c_void_p),
            ("hIcon", ctypes.c_void_p),
            ("hCursor", ctypes.c_void_p),
            ("hbrBackground", ctypes.c_void_p),
            ("lpszMenuName", ctypes.c_wchar_p),
            ("lpszClassName", ctypes.c_wchar_p),
        ]

    class_name = "YGFInstallerInput_%d" % os.getpid()
    state = {"done": False, "accepted": False, "edit": None, "value": ""}

    def loword(value):
        return int(value) & 0xFFFF

    @WNDPROC
    def wndproc(hwnd, message, wparam, lparam):
        if message == WM_COMMAND and loword(wparam) in (ID_OK, ID_CANCEL):
            if loword(wparam) == ID_OK:
                edit = state["edit"]
                length = user32.GetWindowTextLengthW(edit)
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(edit, buffer, length + 1)
                state["value"] = buffer.value
                state["accepted"] = True
            state["done"] = True
            user32.DestroyWindow(hwnd)
            return 0
        if message == WM_CLOSE:
            state["done"] = True
            user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    instance = kernel32.GetModuleHandleW(None)
    class_info = WNDCLASSW(0, wndproc, 0, 0, instance, 0, 0, COLOR_WINDOW + 1, None, class_name)
    if not user32.RegisterClassW(ctypes.byref(class_info)):
        return None
    try:
        hwnd = user32.CreateWindowExW(
            0,
            class_name,
            str(title),
            WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_VISIBLE,
            0,
            0,
            520,
            190,
            0,
            0,
            instance,
            0,
        )
        if not hwnd:
            return None
        static_class = "STATIC"
        edit_class = "EDIT"
        button_class = "BUTTON"
        user32.CreateWindowExW(0, static_class, str(prompt), WS_CHILD | WS_VISIBLE, 18, 18, 480, 34, hwnd, 0, instance, 0)
        state["edit"] = user32.CreateWindowExW(
            0, edit_class, str(initial_value or ""),
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_AUTOHSCROLL,
            18, 58, 480, 32, hwnd, 100, instance, 0,
        )
        user32.CreateWindowExW(
            0, button_class, "确定", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
            300, 112, 90, 34, hwnd, ID_OK, instance, 0,
        )
        user32.CreateWindowExW(
            0, button_class, "取消", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            405, 112, 90, 34, hwnd, ID_CANCEL, instance, 0,
        )
        user32.SetFocus(state["edit"])
        user32.UpdateWindow(hwnd)
        message = wintypes.MSG()
        while not state["done"] and user32.GetMessageW(ctypes.byref(message), 0, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        return state["value"] if state["accepted"] else None
    finally:
        user32.UnregisterClassW(class_name, instance)


APP_DISPLAY_NAME = "YGF POS 称重打印系统"
DISPLAY_NAME_OPTIONS = ("私有 POS 系统", "门店称重助手", "称重桥接管理器", "用户自定")
APP_ICON_OPTIONS = (
    ("yangguofu", "内置杨国福"),
    ("netease_music", "网易云音乐"),
    ("windows", "Windows"),
    ("qq_penguin", "QQ 企鹅"),
    ("dollar", "美元"),
    ("settings_gears", "蓝色齿轮"),
    ("red_music_note", "红色音符"),
    ("gold_blue_mark", "蓝金图标"),
    ("green_dollar", "绿色美元"),
    ("instagram", "Instagram"),
    ("google", "Google"),
    ("alert", "警告"),
    ("coca_cola", "可口可乐"),
)
APP_ICON_FILES = dict(
    (preset_id, "app_icon_%s.ico" % preset_id)
    for preset_id, _label in APP_ICON_OPTIONS
)
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\YGF-POS"
SERVICE_NAME = "YgfScaleBridge"
PAYLOAD_NAME = "YGF-POS-Payload.zip"


def _application_dir():
    return os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))


def _payload_path():
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", _application_dir()), "payload", PAYLOAD_NAME)
    return os.path.join(_application_dir(), PAYLOAD_NAME)


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _run_hidden(command, timeout=60):
    startupinfo = None
    kwargs = {"capture_output": True, "check": False, "timeout": timeout}
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(command, **kwargs)


def _registry_install_dir():
    if not winreg:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY) as key:
            return str(winreg.QueryValueEx(key, "InstallLocation")[0] or "")
    except (OSError, TypeError, ValueError):
        return ""


def _registry_display_name():
    if not winreg:
        return ""


def _registry_icon_preset():
    if not winreg:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY) as key:
            value = str(winreg.QueryValueEx(key, "IconPreset")[0] or "")
            return value if value in APP_ICON_FILES else ""
    except (OSError, TypeError, ValueError):
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY) as key:
            return str(winreg.QueryValueEx(key, "DisplayName")[0] or "")
    except (OSError, TypeError, ValueError):
        return ""


def _existing_install_dir():
    candidates = []
    registered = _registry_install_dir()
    if registered:
        candidates.append(registered)
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidates.extend([
        os.path.join(program_files, "YGF-POS"),
        r"C:\驱动\YGF-POS",
        os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", "YGF-POS"),
    ])
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "启动.exe")):
            return os.path.abspath(candidate)
        # Recognise installations created by the previous portable build.
        if candidate and os.path.isfile(os.path.join(candidate, "驱动.exe")):
            return os.path.abspath(candidate)
    return ""


def _write_uninstall_entry(install_dir, display_name, icon_preset):
    if not winreg:
        return
    with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, display_name)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "1.0")
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "YGF POS")
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
        winreg.SetValueEx(key, "IconPreset", 0, winreg.REG_SZ, icon_preset)
        winreg.SetValueEx(
            key,
            "UninstallString",
            0,
            winreg.REG_SZ,
            '"%s" /uninstall' % os.path.join(install_dir, "卸载.exe"),
        )
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


def _remove_uninstall_entry():
    if not winreg:
        return
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY)
    except OSError:
        pass


def _powershell_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def _create_shortcut(shortcut_path, target_path, working_dir, display_name, icon_path=""):
    os.makedirs(os.path.dirname(shortcut_path), exist_ok=True)
    icon_line = "$l.IconLocation=%s;" % _powershell_quote("%s,0" % icon_path) if icon_path else ""
    script = (
        "$s=New-Object -ComObject WScript.Shell;"
        "$l=$s.CreateShortcut(%s);"
        "$l.TargetPath=%s;"
        "$l.WorkingDirectory=%s;"
        "$l.Description=%s;"
        "%s"
        "$l.Save()"
        % (
            _powershell_quote(shortcut_path),
            _powershell_quote(target_path),
            _powershell_quote(working_dir),
            _powershell_quote(display_name),
            icon_line,
        )
    )
    try:
        result = _run_hidden([
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script
        ], timeout=30)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _shortcut_paths(display_name=APP_DISPLAY_NAME):
    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    program_data = os.environ.get("ProgramData", "")
    start_menu = os.path.join(program_data, "Microsoft", "Windows", "Start Menu", "Programs", "YGF POS")
    return (
        os.path.join(desktop, "%s.lnk" % display_name),
        os.path.join(start_menu, "%s.lnk" % display_name),
        os.path.join(start_menu, "卸载 %s.lnk" % display_name),
    )


def _remove_shortcuts(display_name=APP_DISPLAY_NAME):
    paths = list(_shortcut_paths(display_name))
    # Remove the names used by earlier releases as well as the current
    # selected display name, so an update does not leave stale shortcuts.
    for legacy_name in ("YGF POS", APP_DISPLAY_NAME):
        paths.extend(_shortcut_paths(legacy_name))
    for path in set(paths):
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        start_menu = os.path.dirname(_shortcut_paths()[1])
        if os.path.isdir(start_menu) and not os.listdir(start_menu):
            os.rmdir(start_menu)
    except OSError:
        pass


def _stop_service(install_dir, remove=False):
    service_exe = os.path.join(install_dir, "ScaleBridgeService.exe")
    try:
        if os.path.isfile(service_exe):
            _run_hidden([service_exe, "stop"], timeout=60)
            if remove:
                _run_hidden([service_exe, "remove"], timeout=60)
        elif remove:
            _run_hidden(["sc.exe", "delete", SERVICE_NAME], timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def _service_running():
    try:
        result = _run_hidden(["sc.exe", "query", SERVICE_NAME], timeout=20)
        output = ((result.stdout or b"") + (result.stderr or b"")).decode("mbcs", errors="ignore")
        return result.returncode == 0 and ("RUNNING" in output.upper() or "运行" in output)
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return False


def _safe_extract_payload(target_dir):
    payload = _payload_path()
    if not os.path.isfile(payload):
        raise FileNotFoundError("安装包内部缺少程序 payload")
    base = _norm(target_dir)
    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(payload, "r") as archive:
        for info in archive.infolist():
            destination = os.path.abspath(os.path.join(target_dir, info.filename))
            if _norm(destination) != base and not _norm(destination).startswith(base + os.sep):
                raise RuntimeError("安装包包含非法路径")
            if info.is_dir():
                os.makedirs(destination, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if os.path.isfile(destination):
                try:
                    os.chmod(destination, 0o666)
                except OSError:
                    pass
            with archive.open(info, "r") as source, open(destination, "wb") as target:
                shutil.copyfileobj(source, target)


def _install(target_dir, display_name, icon_preset="yangguofu"):
    target_dir = os.path.abspath(target_dir)
    icon_preset = icon_preset if icon_preset in APP_ICON_FILES else "yangguofu"
    old_dir = _existing_install_dir()
    old_display_name = _registry_display_name() or APP_DISPLAY_NAME
    was_running = _service_running()
    if old_dir and _norm(old_dir) != _norm(target_dir):
        _stop_service(old_dir, remove=True)
    else:
        _stop_service(target_dir, remove=False)
    _safe_extract_payload(target_dir)
    # Keep the uninstaller beside the launcher.  It is intentionally copied
    # from the setup executable rather than generated by the POS at runtime.
    shutil.copy2(sys.executable, os.path.join(target_dir, "卸载.exe"))
    legacy_launcher = os.path.join(target_dir, "驱动.exe")
    if os.path.isfile(legacy_launcher):
        try:
            os.chmod(legacy_launcher, 0o666)
            os.remove(legacy_launcher)
        except OSError:
            pass
    _remove_shortcuts(old_display_name)
    _write_uninstall_entry(target_dir, display_name, icon_preset)
    launcher = os.path.join(target_dir, "启动.exe")
    icon_path = os.path.join(target_dir, "data", "assets", APP_ICON_FILES[icon_preset])
    if not os.path.isfile(icon_path):
        # Older payloads may not have the selectable ICO assets; use the
        # launcher resource rather than creating a shortcut with a dead icon.
        icon_path = launcher
    desktop, start_menu, uninstall_link = _shortcut_paths(display_name)
    _create_shortcut(desktop, launcher, target_dir, display_name, icon_path)
    _create_shortcut(start_menu, launcher, target_dir, display_name, icon_path)
    _create_shortcut(uninstall_link, os.path.join(target_dir, "卸载.exe"), target_dir, "卸载 %s" % display_name)
    if was_running and (not old_dir or _norm(old_dir) == _norm(target_dir)):
        _run_hidden([os.path.join(target_dir, "ScaleBridgeService.exe"), "start"], timeout=60)


def _schedule_remove(install_dir, keep_data):
    path = os.path.abspath(install_dir)
    quoted = _powershell_quote(path)
    if keep_data:
        command = (
            "$p=%s; Start-Sleep -Seconds 2; "
            "Get-ChildItem -LiteralPath $p -Force | "
            "Where-Object { $_.Name -ne 'data' } | "
            "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"
        ) % quoted
    else:
        command = "$p=%s; Start-Sleep -Seconds 2; Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue" % quoted
    startupinfo = None
    kwargs = {"close_fds": True}
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        **kwargs
    )


def _uninstall(install_dir, root=None):
    if not install_dir or not os.path.isdir(install_dir):
        if HAS_TKINTER and root:
            messagebox.showinfo("卸载", "没有找到已安装的 YGF POS。", parent=root)
        else:
            _native_showinfo("卸载", "没有找到已安装的 YGF POS。")
        return
    if HAS_TKINTER and root:
        keep_data = messagebox.askyesno(
            "保留门店数据",
            "是否保留 data 文件夹中的数据库、配置和日志？\n\n选择“是”可便于以后重新安装恢复。",
            parent=root,
        )
        if not messagebox.askyesno("确认卸载", "将停止桥接服务并卸载 YGF POS，是否继续？", parent=root):
            return
    else:
        keep_data = _native_askyesno(
            "保留门店数据",
            "是否保留 data 文件夹中的数据库、配置和日志？\n\n选择“是”可便于以后重新安装恢复。",
        )
        if not _native_askyesno("确认卸载", "将停止桥接服务并卸载 YGF POS，是否继续？"):
            return
    display_name = _registry_display_name() or APP_DISPLAY_NAME
    _stop_service(install_dir, remove=True)
    _remove_shortcuts(display_name)
    _remove_uninstall_entry()
    _schedule_remove(install_dir, keep_data)
    msg = "程序文件将在退出后删除。" + ("门店数据已保留。" if keep_data else "门店数据也将删除。")
    if HAS_TKINTER and root:
        messagebox.showinfo("卸载已开始", msg, parent=root)
        root.destroy()
    else:
        _native_showinfo("卸载已开始", msg)


def _make_root():
    root = tk.Tk()
    root.title("YGF POS 安装程序")
    root.geometry("600x360")
    root.resizable(False, False)
    return root


def main():
    if not HAS_TKINTER:
        existing = _existing_install_dir()
        default_dir = existing or os.path.join(
            os.environ.get("ProgramFiles", r"C:\Program Files"), "YGF-POS"
        )
        target = _native_select_folder(default_dir)
        if not target:
            _native_showinfo("安装已取消", "未选择安装目录，安装没有执行。")
            return
        display_name = _native_prompt_string(
            "应用显示名称",
            "请输入安装后显示的应用名称：",
            _registry_display_name() or DISPLAY_NAME_OPTIONS[0],
        )
        if display_name is None:
            _native_showinfo("安装已取消", "未输入应用名称，安装没有执行。")
            return
        display_name = display_name.strip()
        if not display_name or any(char in display_name for char in "\\/:*?\"<>|\r\n"):
            _native_showerror("名称无效", "请输入有效的应用显示名称，不要包含 \\/:*?\"<>|。")
            return
        if len(display_name) > 48:
            _native_showerror("名称过长", "应用显示名称最多 48 个字符。")
            return
        try:
            _install(target, display_name)
            _native_install_complete(display_name, target)
        except Exception as exc:
            _native_showerror("安装失败", str(exc))
        return

    root = _make_root()
    existing = _existing_install_dir()
    default_dir = existing or os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "YGF-POS")
    path_var = tk.StringVar(value=default_dir)
    display_name_var = tk.StringVar(value=_registry_display_name() or DISPLAY_NAME_OPTIONS[0])
    saved_icon_preset = _registry_icon_preset() or "yangguofu"
    icon_labels = [label for _preset_id, label in APP_ICON_OPTIONS]
    icon_id_by_label = {label: preset_id for preset_id, label in APP_ICON_OPTIONS}
    icon_preset_var = tk.StringVar(value=icon_labels[0])
    for preset_id, label in APP_ICON_OPTIONS:
        if preset_id == saved_icon_preset:
            icon_preset_var.set(label)
            break

    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="POS 安装程序", font=("Microsoft YaHei", 18, "bold")).pack(anchor="w")
    ttk.Label(frame, text="安装、更新或卸载程序；更新时保留 data 中的门店数据。", wraplength=540).pack(anchor="w", pady=(8, 18))
    ttk.Label(frame, text="应用显示名称（可下拉选择，也可直接输入）：").pack(anchor="w")
    name_box = ttk.Combobox(
        frame,
        textvariable=display_name_var,
        values=DISPLAY_NAME_OPTIONS,
        state="normal",
        font=("Microsoft YaHei", 12),
    )
    name_box.pack(fill="x", pady=(6, 14), ipady=6)
    ttk.Label(frame, text="桌面快捷方式图标：").pack(anchor="w")
    icon_box = ttk.Combobox(
        frame,
        textvariable=icon_preset_var,
        values=icon_labels,
        state="readonly",
        font=("Microsoft YaHei", 12),
    )
    icon_box.pack(fill="x", pady=(6, 14), ipady=6)
    ttk.Label(frame, text="安装目录：").pack(anchor="w")
    path_row = ttk.Frame(frame)
    path_row.pack(fill="x", pady=(6, 18))
    ttk.Entry(path_row, textvariable=path_var, font=("Microsoft YaHei", 12)).pack(side="left", fill="x", expand=True, ipady=8)

    def browse():
        selected = filedialog.askdirectory(initialdir=path_var.get() or os.getcwd(), parent=root)
        if selected:
            path_var.set(selected)

    ttk.Button(path_row, text="浏览…", command=browse).pack(side="left", padx=(10, 0), ipadx=10, ipady=6)
    status = ttk.Label(frame, text=("检测到已有安装，可直接更新。" if existing else "尚未检测到安装，将执行首次安装。"))
    status.pack(anchor="w", pady=(0, 16))
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", side="bottom")

    def install_click():
        target = path_var.get().strip()
        display_name = display_name_var.get().strip()
        if display_name == "用户自定":
            display_name = simpledialog.askstring(
                "自定义应用名称",
                "请输入应用显示名称：",
                initialvalue="私有 POS 系统",
                parent=root,
            ) or ""
            display_name = display_name.strip()
        if not display_name or any(char in display_name for char in "\\/:*?\"<>|\r\n"):
            messagebox.showerror("名称无效", "请输入有效的应用显示名称，不要包含 \\/:*?\"<>|。", parent=root)
            return
        if len(display_name) > 48:
            messagebox.showerror("名称过长", "应用显示名称最多 48 个字符。", parent=root)
            return
        if not target or os.path.abspath(target) == os.path.dirname(os.path.abspath(target)):
            messagebox.showerror("目录无效", "请选择有效的安装目录。", parent=root)
            return
        try:
            icon_preset = icon_id_by_label.get(icon_preset_var.get(), "yangguofu")
            _install(target, display_name, icon_preset)
            status.configure(text="安装完成，正在显示完成提示。")
            root.update_idletasks()
            # Keep the root alive until the explicit foreground completion
            # dialog is closed; this avoids Win7 losing a Tk messagebox while
            # the installer window is being torn down.
            _show_install_complete(root, display_name, target)
            try:
                root_exists = bool(root.winfo_exists())
            except tk.TclError:
                root_exists = False
            if root_exists:
                root.destroy()
        except Exception as exc:
            messagebox.showerror("安装失败", str(exc), parent=root)

    ttk.Button(buttons, text="安装 / 更新", command=install_click).pack(side="left", ipadx=24, ipady=10)
    if existing:
        ttk.Button(buttons, text="卸载", command=lambda: _uninstall(existing, root)).pack(side="left", padx=12, ipadx=24, ipady=10)
    ttk.Button(buttons, text="取消", command=root.destroy).pack(side="right", ipadx=24, ipady=10)
    root.mainloop()


if __name__ == "__main__":
    if "/uninstall" in [item.lower() for item in sys.argv[1:]]:
        if HAS_TKINTER:
            root = _make_root()
            _uninstall(_existing_install_dir() or _application_dir(), root)
            try:
                if root.winfo_exists():
                    root.mainloop()
            except Exception:
                pass
        else:
            _uninstall(_existing_install_dir() or _application_dir())
    else:
        main()
