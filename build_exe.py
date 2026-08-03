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

# 强制控制台输出使用 UTF-8 编码，防止在 Git Bash (MINGW64) 等终端中出现中文乱码
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

def main():
    start_time = time.time()
    
    print("=" * 60)
    print("      杨国福麻辣烫 · 独立称重与打印系统 — 免安装 EXE 打包工具")
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
            try:
                shutil.rmtree(folder)
            except Exception:
                pass

    # 3. 构造主程序与独立 Windows 服务的 PyInstaller 参数
    app_name = "驱动"
    package_dir = os.path.join("dist", "YGF-POS")
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
        "--console",
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
        dist_file = os.path.join(package_dir, "%s.exe" % app_name)
        service_file = os.path.join(package_dir, "ScaleBridgeService.exe")
        maintenance_file = os.path.join(package_dir, "ScaleBridgeMaintenance.exe")
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
        bundled_data = os.path.join(package_dir, "data")
        os.makedirs(bundled_data, exist_ok=True)
        shutil.copy2(os.path.join("data", "scale_bridge.example.json"), os.path.join(bundled_data, "scale_bridge.example.json"))
        bundled_docs = os.path.join(package_dir, "docs")
        os.makedirs(bundled_docs, exist_ok=True)
        shutil.copy2(os.path.join("docs", "scale_bridge_win7.md"), os.path.join(bundled_docs, "scale_bridge_win7.md"))
        shutil.copy2(
            os.path.join("docs", "scale_bridge_troubleshooting.md"),
            os.path.join(bundled_docs, "scale_bridge_troubleshooting.md"),
        )
        
        # 自动分发逻辑
        import platform
        try:
            is_win7 = (platform.release() == "7" or (sys.getwindowsversion().major == 6 and sys.getwindowsversion().minor == 1))
        except Exception:
            is_win7 = False
            
        if is_win7:
            target_dir = r"C:\驱动\YGF-POS"
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
            action_desc = f"系统检测为 Windows 7，已自动部署至: {target_dir}"
        else:
            target_dir = os.path.join(os.path.expanduser("~"), "Desktop", "YGF-POS")
            os.makedirs(target_dir, exist_ok=True)
            action_desc = f"系统检测非 Windows 7，已自动拷贝部署目录至: {target_dir}"

        # Merge instead of deleting the target, preserving data/scale_bridge.json
        # and the installation ownership manifest created on the POS computer.
        shutil.copytree(package_dir, target_dir, dirs_exist_ok=True)

        print("\n" + "=" * 60)
        print(" [v] 打包成功！")
        print(f" [*] {action_desc}")
        print("=" * 60)
        print("[!] 重要提示：")
        print("   主程序: %s" % os.path.abspath(dist_file))
        print("   桥接服务: %s" % os.path.abspath(service_file))
        print("   维修工具: %s" % os.path.abspath(maintenance_file))
        print("   完整部署目录: %s" % os.path.abspath(package_dir))
        print("   目标收银机电脑【完全不需要安装 Python】或任何环境！")
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
