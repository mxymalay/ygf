"""
Windows 独立 EXE 软件打包脚本
一键生成免安装绿色独立可执行程序 (内置完整 Python 解释器与所有依赖库)
支持 Windows 7 / Windows 10 / Windows 11 纯净无 Python 环境运行
"""
import os
import sys
import subprocess
import shutil
import time
import hashlib
import stat
import zipfile

# 仅在 Git Bash 等 Bash 终端中使用 UTF-8 重定向，防止破坏 Windows 7 原生 CMD 控制台 WriteConsoleW
if "MSYSTEM" in os.environ or "TERM" in os.environ:
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def _unique_build_dir(base_dir):
    """Return a new sibling directory for a locked build output."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = "%s-%s" % (base_dir, stamp)
    index = 1
    while os.path.exists(candidate):
        candidate = "%s-%s-%d" % (base_dir, stamp, index)
        index += 1
    return candidate


def _remove_readonly(func, path, _exc_info):
    """Allow build-cache cleanup to remove files copied as read-only."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        # The caller will detect that the directory still exists and choose a
        # fresh build directory instead of silently reusing stale artifacts.
        pass


def _clean_build_tree(path):
    """Best-effort removal of a build tree; report whether it remains."""
    if not os.path.exists(path):
        return True
    try:
        shutil.rmtree(path, onerror=_remove_readonly)
    except OSError:
        pass
    return not os.path.exists(path)


def _create_payload_archive(package_dir, archive_path):
    """Create the payload embedded into the standalone setup executable."""
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _directories, filenames in os.walk(package_dir):
            for filename in filenames:
                if filename in (os.path.basename(archive_path), "YGF-POS-Setup.exe", "卸载.exe"):
                    continue
                source = os.path.join(root, filename)
                relative = os.path.relpath(source, package_dir).replace(os.sep, "/")
                archive.write(source, relative)


def main():
    start_time = time.time()

    # A .bat launched by double-click is not guaranteed to inherit the
    # repository directory as its current working directory.  All resources
    # (ThirdParty, data and docs) must be resolved beside this script, or a
    # packaged build can appear to succeed while silently omitting assets.
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)
    
    print("=" * 60)
    print("      YGF POS standalone EXE build tool")
    print("=" * 60)

    # 0. 强制锁定 Windows 7 兼容的 Python 3.8 环境
    target_python = r"G:\AI\anaconda3\envs\py38_win7\python.exe"
    if os.path.exists(target_python) and sys.executable.lower() != target_python.lower():
        print(f"[*] 发现您当前正在使用 Python {sys.version.split()[0]}")
        print("[*] 为确保打包后的软件完美兼容店内 Windows 7 老系统，正在强行无缝切换至底层核心 3.8...")
        print("=" * 60)
        sys.exit(subprocess.call([target_python] + sys.argv))

    # 1. 检查并安装 PyInstaller
    try:
        import PyInstaller
        print("[v] PyInstaller 已就绪")
    except ImportError:
        print("[!] 正在安装 PyInstaller 独立编译组件...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])

    # 2. 清理旧的构建文件
    print("[*] 正在清理历史构建缓存...")
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            if not _clean_build_tree(folder):
                print("[i] 无法完全清理旧构建目录，后续将避开被占用文件")
    # A locked old installer (or an old dist/YGF-POS folder) would make the
    # output ambiguous: dist must contain exactly one deliverable.  Stop
    # before compiling rather than silently mixing old and new files.
    if os.path.isdir("dist") and os.listdir("dist"):
        print("[X] dist 目录仍有文件被占用，无法保证只生成一个安装包")
        print("    请先关闭旧的安装包/程序后再运行构建脚本")
        return 7

    # 3. 构造主程序与独立 Windows 服务的 PyInstaller 参数
    app_name = "启动"
    dist_dir = "dist"
    # The application EXEs are build-only staging files.  They are embedded
    # into the setup payload and must not be presented as separate deliverables
    # in dist/.
    package_dir = os.path.join("build", "package", "YGF-POS")
    if os.path.exists(package_dir):
        # A previous deployment may still have the bundled installer open.
        # Never overwrite that locked tree; stage this build beside it.
        package_dir = _unique_build_dir(package_dir + "-build")
    os.makedirs(package_dir, exist_ok=True)
    os.makedirs(os.path.join("build", "spec"), exist_ok=True)
    common_hidden = [
        "--hidden-import=win32api",
        "--hidden-import=win32gui",
        "--hidden-import=serial",
        "--hidden-import=serial.tools.list_ports",
        "--hidden-import=pythoncom",
        "--hidden-import=win32com.client",
        "--hidden-import=pywintypes",
    ]
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=%s" % app_name,
        "--noconsole",          # 纯图形界面，不弹出黑色终端窗口
        "--onefile",            # 主程序本身为单 EXE；完整功能仍需整个 YGF-POS 部署目录
        "--clean",
        "--distpath=%s" % package_dir,
        "--workpath=%s" % os.path.join("build", "pos"),
        "--specpath=%s" % os.path.join("build", "spec"),
        "--uac-admin",          # 强制请求管理员权限 (解决UIPI隔离导致无法控制收钱吧的问题)
        "--icon=%s" % os.path.join("data", "assets", "app_icon_yangguofu.ico"),
        "--hidden-import=win32print",
        "--hidden-import=sqlite3",
        "--hidden-import=PyQt5.QtCore",
        "--hidden-import=PyQt5.QtWidgets",
        "--hidden-import=PyQt5.QtGui",
        "--hidden-import=scale_bridge.lifecycle",
        "--hidden-import=scale_bridge.service",
    ] + common_hidden + [
        "main.py"
    ]

    service_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=ScaleBridgeService",
        # A console-subsystem onefile executable started from the windowed POS
        # with CREATE_NO_WINDOW can fail on Win7 before our code runs with
        # ``init_sys_streams: can't initialize sys standard streams``.  A
        # Windows service has no interactive console, so build the host with
        # the correct windowed subsystem and provide explicit null streams in
        # its entry point for pywin32's command-line helper.
        "--noconsole",
        "--onefile",
        "--clean",
        "--distpath=%s" % package_dir,
        "--workpath=%s" % os.path.join("build", "scale_bridge_service"),
        "--specpath=%s" % os.path.join("build", "spec"),
        "--hidden-import=servicemanager",
        "--hidden-import=win32service",
        "--hidden-import=win32serviceutil",
        "--hidden-import=win32event",
        "--hidden-import=win32pipe",
        "--hidden-import=win32file",
        "--hidden-import=win32timezone",
    ] + common_hidden + [
        "scale_bridge_service.py"
    ]

    maintenance_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=ScaleBridgeMaintenance",
        "--console",
        "--onefile",
        "--clean",
        "--uac-admin",
        "--distpath=%s" % package_dir,
        "--workpath=%s" % os.path.join("build", "scale_bridge_maintenance"),
        "--specpath=%s" % os.path.join("build", "spec"),
        "--hidden-import=win32service",
        "--hidden-import=win32serviceutil",
        "--hidden-import=win32pipe",
        "--hidden-import=win32file",
    ] + common_hidden + [
        "scale_bridge_maintenance.py"
    ]

    print("[*] 正在打包独立软件程序（包含完整 Python 运行时与二进制动态库）...")
    res = subprocess.call(cmd)
    if res == 0:
        print("[*] 正在打包独立 ScaleBridge Windows 服务...")
        res = subprocess.call(service_cmd)
    if res == 0:
        print("[*] 正在打包 ScaleBridge 命令行维修工具...")
        res = subprocess.call(maintenance_cmd)

    if res == 0:
        installer_candidates = [
            os.path.join("ThirdParty", "com0com", name)
            for name in os.listdir(os.path.join("ThirdParty", "com0com"))
            if name.lower().endswith(".exe") and name.lower().startswith("setup_com0com")
        ] if os.path.isdir(os.path.join("ThirdParty", "com0com")) else []
        if not installer_candidates:
            print("[X] 部署包缺少经过验证的 com0com Win7 x64 签名安装程序")
            return 2
        with open(installer_candidates[0], "rb") as installer_handle:
            installer_hash = hashlib.sha256(installer_handle.read()).hexdigest().upper()
        expected_installer_hash = "26486B28604B49A9008C54FEB11B9ECE0008A8287EE5CAF0BCF2A62F4317128F"
        if installer_hash != expected_installer_hash:
            print("[X] com0com 安装包 SHA-256 不匹配，拒绝加入部署包: %s" % installer_hash)
            return 3
        bundled_com0com = os.path.join(package_dir, "ThirdParty", "com0com")
        os.makedirs(bundled_com0com, exist_ok=True)
        shutil.copy2(installer_candidates[0], os.path.join(bundled_com0com, os.path.basename(installer_candidates[0])))

        # hub4com is deliberately optional: ScaleBridge does not depend on
        # it at runtime, but including the local utility and its documented
        # batch wrappers makes post-install diagnostics reproducible when the
        # deployment source contains ThirdParty\hub4com.
        hub4com_source = os.path.join("ThirdParty", "hub4com")
        hub4com_exe = os.path.join(hub4com_source, "hub4com.exe")
        if os.path.isfile(hub4com_exe):
            bundled_hub4com = os.path.join(package_dir, "ThirdParty", "hub4com")
            os.makedirs(bundled_hub4com, exist_ok=True)
            for name in os.listdir(hub4com_source):
                source = os.path.join(hub4com_source, name)
                if os.path.isfile(source) and (
                    name.lower().endswith((".exe", ".bat", ".txt"))
                ):
                    shutil.copy2(source, os.path.join(bundled_hub4com, name))
            print("[*] 已包含可选 hub4com 手工诊断工具（ScaleBridge 运行时不依赖）")
        else:
            print("[i] 未发现可选 hub4com，部署包仍可正常运行 ScaleBridge")

        # Bundle the exact Shouqianba PC assistant installer used by the store
        # so the settings page can copy it to the operator's desktop.  It is
        # never executed silently by the POS.
        sqb_installer = os.path.join("ThirdParty", "shouqianba", "PC收款安装包v4.0.4.exe")
        expected_sqb_hash = "666EFBA745C7D20D33C22B65E765B027D431E32B7C8CAA4BF8B65A86AD6F15AC"
        if not os.path.isfile(sqb_installer):
            print("[X] 部署包缺少收钱吧 PC 助手安装包: %s" % sqb_installer)
            return 4
        with open(sqb_installer, "rb") as sqb_handle:
            sqb_hash = hashlib.sha256(sqb_handle.read()).hexdigest().upper()
        if sqb_hash != expected_sqb_hash:
            print("[X] 收钱吧安装包 SHA-256 不匹配，拒绝加入部署包: %s" % sqb_hash)
            return 5
        bundled_sqb = os.path.join(package_dir, "ThirdParty", "shouqianba")
        os.makedirs(bundled_sqb, exist_ok=True)
        shutil.copy2(sqb_installer, os.path.join(bundled_sqb, os.path.basename(sqb_installer)))
        bundled_data = os.path.join(package_dir, "data")
        os.makedirs(bundled_data, exist_ok=True)
        # The runtime resolves bundled Logos and printer artwork from
        # ``data/assets`` beside the installed executable.  Include the whole
        # asset folder so newly selectable Logo presets also work in a clean
        # deployment, not only from a source checkout.
        assets_source = os.path.join("data", "assets")
        assets_target = os.path.join(bundled_data, "assets")
        if os.path.isdir(assets_source):
            shutil.copytree(assets_source, assets_target, dirs_exist_ok=True)
        scale_example = os.path.join("data", "scale_bridge.example.json")
        if os.path.isfile(scale_example):
            shutil.copy2(scale_example, os.path.join(bundled_data, "scale_bridge.example.json"))
        else:
            # This is documentation only; the real bridge configuration is
            # created by the settings workflow.  Older source checkouts may
            # have removed the example after moving settings into data/db and
            # data/settings, so it must not make an otherwise valid build fail.
            print("[i] 未找到可选 data\\scale_bridge.example.json，跳过示例配置复制")
        bundled_docs = os.path.join(package_dir, "docs")
        os.makedirs(bundled_docs, exist_ok=True)
        shutil.copy2(os.path.join("docs", "scale_bridge_win7.md"), os.path.join(bundled_docs, "scale_bridge_win7.md"))
        shutil.copy2(
            os.path.join("docs", "scale_bridge_troubleshooting.md"),
            os.path.join(bundled_docs, "scale_bridge_troubleshooting.md"),
        )

        # Build a self-contained setup EXE.  The setup embeds the complete
        # package, installs/updates in a user-selected directory, creates
        # shortcuts and an uninstaller, and preserves data/ on updates.
        payload_zip = os.path.join(package_dir, "YGF-POS-Payload.zip")
        _create_payload_archive(package_dir, payload_zip)
        # PyInstaller resolves --add-data sources relative to the generated
        # spec file (build/spec).  Pass an absolute path so the setup build
        # cannot accidentally look under build/spec/dist/... and fail with
        # "Unable to find ... YGF-POS-Payload.zip".
        payload_zip_source = os.path.abspath(payload_zip)
        installer_cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name=YGF-POS-Setup",
            "--noconsole",
            "--onefile",
            "--clean",
            "--uac-admin",
            "--distpath=%s" % dist_dir,
            "--workpath=%s" % os.path.join("build", "installer"),
            "--specpath=%s" % os.path.join("build", "spec"),
            "--hidden-import=_tkinter",
            "--hidden-import=tkinter",
            "--hidden-import=tkinter.filedialog",
            "--hidden-import=tkinter.messagebox",
            "--hidden-import=tkinter.simpledialog",
            "--hidden-import=tkinter.ttk",
            # PyInstaller normally detects tkinter, but Win7 one-file builds
            # can omit Tcl/Tk data and silently enter installer_stub's native
            # fallback. Collect both the Python package and Tcl bridge so the
            # touch-friendly directory/name chooser is present on the target.
            "--collect-all=tkinter",
            "--collect-binaries=_tkinter",
            "--add-data=%s;payload" % payload_zip_source,
            "installer_stub.py",
        ]
        print("[*] 正在生成安装/更新/卸载一体化安装包...")
        res = subprocess.call(installer_cmd)
        if res != 0:
            print("[X] 安装包 EXE 生成失败，保留 payload 供诊断: %s" % payload_zip)
            return int(res or 6)
        try:
            os.remove(payload_zip)
        except OSError:
            pass
        setup_file = os.path.join(dist_dir, "YGF-POS-Setup.exe")
        try:
            shutil.rmtree(package_dir, onerror=_remove_readonly)
        except OSError:
            # A failed cleanup only leaves an internal build cache under
            # build/; the dist directory still contains the single installer.
            print("[i] 暂时无法清理内部 staging 目录，不影响安装包输出")
        
        print("\n" + "=" * 60)
        print(" [v] 打包成功！")
        print(" [*] dist 目录只保留一个安装包；应用文件将在安装时释放")
        print("=" * 60)
        print("[!] 输出文件：")
        print("   安装包: %s" % os.path.abspath(setup_file))
        print("   （主程序、桥接服务和维修工具已嵌入安装包，安装时释放）")
        print("=" * 60)
        elapsed_time = time.time() - start_time
        print(f" [i] 打包总耗时: {elapsed_time:.1f} 秒")
        print("=" * 60)
        return 0
    else:
        print("\n[X] 打包失败，请检查编译日志！")
        elapsed_time = time.time() - start_time
        print(f" [i] 失败，共耗时: {elapsed_time:.1f} 秒")
        return int(res or 1)

if __name__ == "__main__":
    raise SystemExit(main())
