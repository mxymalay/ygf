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

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    import winreg
except ImportError:  # pragma: no cover - only used on Windows
    winreg = None


APP_DISPLAY_NAME = "YGF POS 称重打印系统"
DISPLAY_NAME_OPTIONS = ("私有 POS 系统", "门店称重助手", "称重桥接管理器", "用户自定")
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


def _write_uninstall_entry(install_dir, display_name):
    if not winreg:
        return
    with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, display_name)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "1.0")
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "YGF POS")
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
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


def _create_shortcut(shortcut_path, target_path, working_dir, display_name):
    os.makedirs(os.path.dirname(shortcut_path), exist_ok=True)
    script = (
        "$s=New-Object -ComObject WScript.Shell;"
        "$l=$s.CreateShortcut(%s);"
        "$l.TargetPath=%s;"
        "$l.WorkingDirectory=%s;"
        "$l.Description=%s;"
        "$l.Save()"
        % (
            _powershell_quote(shortcut_path),
            _powershell_quote(target_path),
            _powershell_quote(working_dir),
            _powershell_quote(display_name),
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


def _install(target_dir, display_name):
    target_dir = os.path.abspath(target_dir)
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
    _write_uninstall_entry(target_dir, display_name)
    launcher = os.path.join(target_dir, "启动.exe")
    desktop, start_menu, uninstall_link = _shortcut_paths(display_name)
    _create_shortcut(desktop, launcher, target_dir, display_name)
    _create_shortcut(start_menu, launcher, target_dir, display_name)
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


def _uninstall(install_dir, root):
    if not install_dir or not os.path.isdir(install_dir):
        messagebox.showinfo("卸载", "没有找到已安装的 YGF POS。", parent=root)
        return
    keep_data = messagebox.askyesno(
        "保留门店数据",
        "是否保留 data 文件夹中的数据库、配置和日志？\n\n选择“是”可便于以后重新安装恢复。",
        parent=root,
    )
    if not messagebox.askyesno("确认卸载", "将停止桥接服务并卸载 YGF POS，是否继续？", parent=root):
        return
    display_name = _registry_display_name() or APP_DISPLAY_NAME
    _stop_service(install_dir, remove=True)
    _remove_shortcuts(display_name)
    _remove_uninstall_entry()
    _schedule_remove(install_dir, keep_data)
    messagebox.showinfo("卸载已开始", "程序文件将在退出后删除。" + ("门店数据已保留。" if keep_data else "门店数据也将删除。"), parent=root)
    root.destroy()


def _make_root():
    root = tk.Tk()
    root.title("YGF POS 安装程序")
    root.geometry("600x360")
    root.resizable(False, False)
    return root


def main():
    root = _make_root()
    existing = _existing_install_dir()
    default_dir = existing or os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "YGF-POS")
    path_var = tk.StringVar(value=default_dir)
    display_name_var = tk.StringVar(value=_registry_display_name() or DISPLAY_NAME_OPTIONS[0])

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
            _install(target, display_name)
            messagebox.showinfo("安装完成", "%s 已安装/更新完成。\n\n启动程序：%s\n实际程序文件：启动.exe" % (display_name, display_name), parent=root)
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
        root = _make_root()
        _uninstall(_existing_install_dir() or _application_dir(), root)
        try:
            if root.winfo_exists():
                root.mainloop()
        except tk.TclError:
            pass
    else:
        main()
