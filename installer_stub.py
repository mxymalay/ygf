"""Small self-contained Windows installer/uninstaller for the YGF POS bundle.

The build script embeds a zip payload into this file with PyInstaller.  This
module intentionally uses only the Python standard library so the setup EXE
does not depend on the POS application's virtual environment.
"""
import os
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

import ctypes
from ctypes import wintypes

# Do not import Tk at module import time.  The installed POS imports a few
# shortcut-update helpers from this module, and loading Tcl/Tk there can keep
# PyInstaller's one-file ``_MEI`` directory locked on Win7 until the POS exits.
# The standalone installer still loads Tk lazily when its own UI starts.
HAS_TKINTER = None
tk = filedialog = messagebox = simpledialog = ttk = None


def _ensure_tkinter():
    """Load Tk only for the standalone installer UI, never for the POS."""
    global HAS_TKINTER, tk, filedialog, messagebox, simpledialog, ttk
    if HAS_TKINTER is not None:
        return bool(HAS_TKINTER)
    try:
        import tkinter as _tk
        from tkinter import filedialog as _filedialog
        from tkinter import messagebox as _messagebox
        from tkinter import simpledialog as _simpledialog
        from tkinter import ttk as _ttk
        tk = _tk
        filedialog = _filedialog
        messagebox = _messagebox
        simpledialog = _simpledialog
        ttk = _ttk
        HAS_TKINTER = True
    except ImportError:
        HAS_TKINTER = False
    return bool(HAS_TKINTER)

try:
    import winreg
except ImportError:  # pragma: no cover - only used on Windows
    winreg = None


def _native_message_box(title, message, flags):
    """Call the stock Win32 MessageBox with an explicit stable signature."""
    if os.name != "nt":
        return 6
    message_box = ctypes.windll.user32.MessageBoxW
    message_box.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
    message_box.restype = ctypes.c_int
    return message_box(0, str(message), str(title), int(flags))


def _native_showinfo(title, message):
    _native_message_box(title, message, 0x40)


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
    """Start the installed launcher after this one-file installer exits.

    On Win7, launching another PyInstaller one-file executable immediately
    from this installer makes the child try to remove the installer's still
    locked ``_MEI`` directory.  Use a tiny detached cmd helper that waits for
    the parent process to finish before starting the installed POS.
    """
    launcher = os.path.join(os.path.abspath(target_dir), "启动.exe")
    if not os.path.isfile(launcher):
        return False
    script = None
    try:
        if os.name == "nt":
            script = os.path.join(
                tempfile.gettempdir(),
                "ygf_pos_start_%s.cmd" % os.getpid(),
            )
            # ping is available on every supported Win7 image and provides a
            # shell-level delay without keeping the installer process alive.
            with open(script, "w", encoding="mbcs", errors="replace") as handle:
                handle.write("@echo off\r\n")
                handle.write("ping 127.0.0.1 -n 3 >nul\r\n")
                handle.write('start "" "%s"\r\n' % launcher.replace('"', '""'))
                handle.write('del "%%~f0"\r\n')
            flags = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            subprocess.Popen(
                ["cmd.exe", "/d", "/c", script],
                cwd=os.path.dirname(launcher),
                close_fds=True,
                creationflags=flags,
            )
        else:
            subprocess.Popen([launcher], cwd=os.path.dirname(launcher), close_fds=True)
        return True
    except (OSError, subprocess.SubprocessError):
        try:
            if os.path.isfile(script):
                os.remove(script)
        except (OSError, UnboundLocalError):
            pass
        return False


def _native_install_complete(display_name, target_dir):
    """Win32 fallback with explicit Open/Finish choices for Win7."""
    message = _install_complete_message(display_name, target_dir)
    if os.name == "nt":
        result = _native_message_box(
            "安装/更新完成",
            message,
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
    _native_message_box(title, message, 0x10)


def _native_askyesno(title, message):
    return _native_message_box(title, message, 0x24) == 6


def _native_select_folder(initial_dir):
    """Use the stock Win7 folder picker when the packaged Tk runtime is unavailable."""
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
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_void_p]
    user32.SendMessageW.restype = ctypes.c_ssize_t

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, message, _lparam, data):
        if message == BFFM_INITIALIZED:
            initial_path = ctypes.cast(data, ctypes.c_void_p)
            user32.SendMessageW(hwnd, BFFM_SETSELECTIONW, 1, initial_path)
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
    shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFO)]
    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
    shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
    shell32.SHGetPathFromIDListW.restype = wintypes.BOOL
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
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
    """Confirm the existing name without using a custom Win32 callback window.

    If Tk cannot start, a hand-built edit control is significantly less
    reliable than a stock MessageBox on Win7.  The normal Tk installer still
    supports entering a custom name; this emergency path retains the existing
    name (or the supplied default) and lets the operator continue safely.
    """
    default_name = str(initial_value or "私有 POS 系统").strip()
    result = _native_message_box(
        title,
        "%s\n\n当前名称：%s\n\n"
        "是：使用此名称继续\n否：取消安装" % (prompt, default_name),
        0x00000004 | 0x00000020 | 0x00010000,  # MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND
    )
    return default_name if result == 6 else None


def _native_prompt_choice(title, prompt, options, initial_id=""):
    """Choose an icon with stock Win7 MessageBoxes, never a custom WndProc.

    The no-Tk path previously created a COMBOBOX by hand through ctypes.  On
    some Win7 installs that native callback could close the whole installer
    during a selection.  MessageBoxW is available on every supported Win7
    system and has no user-defined window procedure or pointer callbacks.
    """
    if os.name != "nt":
        return None
    choices = list(options or [])
    if not choices:
        return None
    preferred = next(
        (index for index, (preset_id, _label) in enumerate(choices) if preset_id == initial_id),
        0,
    )
    ordered = choices[preferred:] + choices[:preferred]
    for index, (preset_id, label) in enumerate(ordered, 1):
        result = _native_message_box(
            title,
            "%s\n\n图标 %d/%d：%s\n\n"
            "是：使用此图标\n否：查看下一个图标\n取消：取消安装"
            % (prompt, index, len(ordered), label),
            0x00000003 | 0x00000020 | 0x00010000,  # MB_YESNOCANCEL | MB_ICONQUESTION | MB_SETFOREGROUND
        )
        if result == 6:  # IDYES
            return preset_id
        if result != 7:  # IDNO
            return None
    return None


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
APP_ICON_FILES["custom"] = "custom_shortcut_icon.ico"
APP_ICON_CATEGORIES = {
    "yangguofu": "pos",
    "netease_music": "music",
    "windows": "driver",
    "qq_penguin": "social",
    "dollar": "finance",
    "settings_gears": "settings",
    "red_music_note": "music",
    "gold_blue_mark": "pos",
    "green_dollar": "finance",
    "instagram": "social",
    "google": "google",
    "alert": "security",
    "coca_cola": "food",
    "custom": "custom",
}
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\YGF-POS"
SERVICE_NAME = "ppposScaleBridge"
LEGACY_SCALE_SERVICE_NAMES = ("YgfScaleBridge",)
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
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY) as key:
            return str(winreg.QueryValueEx(key, "DisplayName")[0] or "")
    except (OSError, TypeError, ValueError):
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


def _write_runtime_branding(install_dir, icon_preset):
    """Seed the first-run config from the installer's icon choice."""
    settings_path = os.path.join(install_dir, "data", "settings", "base.json")
    try:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        if os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as handle:
                settings = json.load(handle)
        else:
            settings = {}
        if not isinstance(settings, dict):
            settings = {}
        settings["shortcut_icon_preset"] = icon_preset
        settings["app_category"] = APP_ICON_CATEGORIES.get(icon_preset, "pos")
        temporary = settings_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        try:
            os.replace(temporary, settings_path)
        except AttributeError:  # Python 3.8/Win7 fallback
            if os.path.isfile(settings_path):
                os.remove(settings_path)
            os.rename(temporary, settings_path)
    except (OSError, ValueError, TypeError):
        # Branding is optional; never make a valid installation fail because
        # an old/custom settings file is temporarily unreadable.
        try:
            if os.path.isfile(settings_path + ".tmp"):
                os.remove(settings_path + ".tmp")
        except OSError:
            pass


def current_shortcut_icon_preset():
    """Return the installed shortcut icon id for settings-page initialization."""
    return _registry_icon_preset() or "yangguofu"


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


def update_current_shortcut_icon(icon_preset):
    """Update the installed desktop/start-menu shortcuts to a selected icon."""
    if icon_preset not in APP_ICON_FILES:
        return False, "未知的桌面图标选项"
    install_dir = _existing_install_dir()
    if not install_dir:
        return False, "未找到当前安装目录"
    display_name = _registry_display_name() or APP_DISPLAY_NAME
    launcher = os.path.join(install_dir, "启动.exe")
    icon_path = os.path.join(install_dir, "data", "assets", APP_ICON_FILES[icon_preset])
    if not os.path.isfile(launcher):
        return False, "安装目录中缺少启动.exe"
    if not os.path.isfile(icon_path):
        return False, "安装目录中缺少所选图标资源"
    desktop, start_menu, _uninstall_link = _shortcut_paths(display_name)
    ok_desktop = _create_shortcut(desktop, launcher, install_dir, display_name, icon_path)
    ok_start_menu = _create_shortcut(start_menu, launcher, install_dir, display_name, icon_path)
    if not (ok_desktop and ok_start_menu):
        return False, "更新桌面或开始菜单快捷方式失败，请检查权限"
    if winreg:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "IconPreset", 0, winreg.REG_SZ, icon_preset)
        except (OSError, TypeError, ValueError):
            # The shortcut itself was updated; registry metadata is only used
            # as the next installer's initial selection and is non-critical.
            pass
    return True, "桌面快捷方式图标已更新"


def update_current_shortcut_icon_file(icon_path):
    """Apply a custom ICO already stored inside the installed data folder."""
    install_dir = _existing_install_dir()
    if not install_dir:
        return False, "未找到当前安装目录"
    icon_path = os.path.abspath(str(icon_path or ""))
    if not os.path.isfile(icon_path):
        return False, "自定义图标文件不存在"
    display_name = _registry_display_name() or APP_DISPLAY_NAME
    launcher = os.path.join(install_dir, "启动.exe")
    if not os.path.isfile(launcher):
        return False, "安装目录中缺少启动.exe"
    desktop, start_menu, _uninstall_link = _shortcut_paths(display_name)
    ok_desktop = _create_shortcut(desktop, launcher, install_dir, display_name, icon_path)
    ok_start_menu = _create_shortcut(start_menu, launcher, install_dir, display_name, icon_path)
    if not (ok_desktop and ok_start_menu):
        return False, "更新桌面或开始菜单快捷方式失败，请检查权限"
    if winreg:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "IconPreset", 0, winreg.REG_SZ, "custom")
        except (OSError, TypeError, ValueError):
            pass
    return True, "桌面快捷方式图标已更新"


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


PRINTER_RELAY_SERVICE_NAME = "ppposPrinterRelay"
_OBSOLETE_RELAY_SERVICE_NAME = "ppposTakeoutRelay"
_OBSOLETE_RELAY_EXECUTABLE = "TakeoutRelayService.exe"
_OBSOLETE_RELAY_FILES = (
    _OBSOLETE_RELAY_EXECUTABLE,
    "takeout_relay_service.py",
    "takeout_proxy_host.py",
    os.path.join("core", "takeout_capture.py"),
    os.path.join("core", "takeout_interceptor.py"),
    os.path.join("core", "takeout_jobs.py"),
    os.path.join("core", "takeout_proxy_host.py"),
    os.path.join("core", "takeout_relay.py"),
    os.path.join("ui", "takeout_sorting_widget.py"),
    os.path.join("docs", "takeout_proxy_win7.md"),
)


def _stop_printer_relay_service(install_dir, remove=False):
    """Stop/remove the current printer relay registration."""
    service_exe = os.path.join(install_dir, "PrinterRelayService.exe")
    try:
        if os.path.isfile(service_exe):
            _run_hidden([service_exe, "stop"], timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass
    # The service command returns as soon as the stop request is accepted;
    # on Win7 the service process can still hold its own EXE for another few
    # seconds.  Stop through SCM as well and wait for the process state before
    # the payload extractor attempts to replace PrinterRelayService.exe.
    try:
        _run_hidden(["sc.exe", "stop", PRINTER_RELAY_SERVICE_NAME], timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass
    _wait_for_service_stopped(PRINTER_RELAY_SERVICE_NAME, timeout=20)
    if remove:
        try:
            if os.path.isfile(service_exe):
                _run_hidden([service_exe, "remove"], timeout=60)
        except (OSError, subprocess.SubprocessError):
            pass
    if remove:
        try:
            _run_hidden(["sc.exe", "delete", PRINTER_RELAY_SERVICE_NAME], timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass


def _service_state_code(service_name):
    """Return the SCM numeric state, or 0 when the service is absent."""
    try:
        result = _run_hidden(["sc.exe", "query", service_name], timeout=20)
        output = ((result.stdout or b"") + (result.stderr or b"")).decode("mbcs", errors="ignore")
        match = re.search(r"(?:STATE|状态)\s*:\s*([1-7])", output, re.IGNORECASE)
        return int(match.group(1)) if result.returncode == 0 and match else 0
    except (OSError, UnicodeError, subprocess.SubprocessError, ValueError):
        return 0


def _wait_for_service_stopped(service_name, timeout=20):
    """Wait until SCM reports a service stopped/not installed."""
    deadline = time.monotonic() + max(0, float(timeout or 0))
    while time.monotonic() < deadline:
        if _service_state_code(service_name) in (0, 1):
            return True
        time.sleep(0.25)
    return _service_state_code(service_name) in (0, 1)


def _remove_obsolete_printer_relay_artifacts(install_dir):
    """Remove the pre-PrinterRelayService executable/service once.

    This is a cleanup migration, not a runtime compatibility path. New
    packages never contain the obsolete executable and never query its name.
    """
    if not install_dir:
        return
    old_exe = os.path.join(install_dir, _OBSOLETE_RELAY_EXECUTABLE)
    try:
        if os.path.isfile(old_exe):
            _run_hidden([old_exe, "stop"], timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        _run_hidden(["sc.exe", "stop", _OBSOLETE_RELAY_SERVICE_NAME], timeout=30)
        _run_hidden(["sc.exe", "delete", _OBSOLETE_RELAY_SERVICE_NAME], timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass
    for relative_path in _OBSOLETE_RELAY_FILES:
        path = os.path.join(install_dir, relative_path)
        try:
            if os.path.isfile(path):
                os.chmod(path, 0o666)
                os.remove(path)
        except OSError:
            continue


def _remove_legacy_scale_services():
    """Migrate the pre-pppos service name without touching user config/data."""
    for legacy_name in LEGACY_SCALE_SERVICE_NAMES:
        try:
            _run_hidden(["sc.exe", "stop", legacy_name], timeout=30)
            _run_hidden(["sc.exe", "delete", legacy_name], timeout=30)
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
            temporary = "%s.installing.%s" % (destination, os.getpid())
            replaced = False
            last_error = None
            # A stopped Win7 service can take a short interval to release its
            # executable.  Extract to a side file first, then retry the final
            # replace instead of truncating the old file or failing on the
            # first sharing violation.
            for attempt in range(20):
                try:
                    with archive.open(info, "r") as source, open(temporary, "wb") as target:
                        shutil.copyfileobj(source, target)
                    os.replace(temporary, destination)
                    replaced = True
                    break
                except PermissionError as exc:
                    last_error = exc
                    try:
                        if os.path.isfile(temporary):
                            os.remove(temporary)
                    except OSError:
                        pass
                    if attempt >= 19:
                        raise PermissionError(
                            "无法覆盖文件：%s；请先退出 POS 并停止 ppposPrinterRelay 服务后重试。" % destination
                        ) from exc
                    time.sleep(0.5)
            if not replaced and last_error is not None:
                raise last_error


def _install(target_dir, display_name, icon_preset="yangguofu"):
    target_dir = os.path.abspath(target_dir)
    icon_preset = icon_preset if icon_preset in APP_ICON_FILES else "yangguofu"
    old_dir = _existing_install_dir()
    old_display_name = _registry_display_name() or APP_DISPLAY_NAME
    _remove_legacy_scale_services()
    was_running = _service_running()
    try:
        relay_query = _run_hidden(["sc.exe", "query", PRINTER_RELAY_SERVICE_NAME], timeout=20)
        relay_output = ((relay_query.stdout or b"") + (relay_query.stderr or b"")).decode("mbcs", errors="ignore")
        printer_relay_was_running = relay_query.returncode == 0 and (
            "RUNNING" in relay_output.upper() or "运行" in relay_output
        )
    except (OSError, UnicodeError, subprocess.SubprocessError):
        printer_relay_was_running = False
    _remove_obsolete_printer_relay_artifacts(old_dir or target_dir)
    if old_dir and _norm(old_dir) != _norm(target_dir):
        _remove_obsolete_printer_relay_artifacts(target_dir)
    if old_dir and _norm(old_dir) != _norm(target_dir):
        _stop_service(old_dir, remove=True)
        _stop_printer_relay_service(old_dir, remove=True)
    else:
        _stop_service(target_dir, remove=False)
        _stop_printer_relay_service(target_dir, remove=False)
    _safe_extract_payload(target_dir)
    _write_runtime_branding(target_dir, icon_preset)
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
    if printer_relay_was_running and (not old_dir or _norm(old_dir) == _norm(target_dir)):
        service_exe = os.path.join(target_dir, "PrinterRelayService.exe")
        if os.path.isfile(service_exe):
            _run_hidden([service_exe, "start"], timeout=60)


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
    _stop_printer_relay_service(install_dir, remove=True)
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
    # The icon selector adds one full input row.  The old 360px window left
    # the install/update buttons below the visible area on Win7 DPI scaling.
    root.geometry("620x460")
    root.minsize(620, 460)
    root.resizable(False, False)
    return root


def main():
    _ensure_tkinter()
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
        saved_icon_preset = _registry_icon_preset() or "yangguofu"
        try:
            icon_preset = _native_prompt_choice(
                "桌面快捷方式图标",
                "请选择安装后桌面快捷方式使用的图标：",
                APP_ICON_OPTIONS,
                saved_icon_preset,
            )
        except Exception as exc:
            # A broken native control must report a normal installer error;
            # never let a Win7 fallback exception look like a silent crash.
            _native_showerror("图标选择失败", "无法打开快捷方式图标选择窗口：%s" % exc)
            return
        if icon_preset is None:
            _native_showinfo("安装已取消", "未选择桌面快捷方式图标，安装没有执行。")
            return
        try:
            _install(target, display_name, icon_preset)
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
