"""
Windows 独立 EXE 软件打包脚本
一键生成免安装绿色独立可执行程序 (内置完整 Python 解释器与所有依赖库)
支持 Windows 7 / Windows 10 / Windows 11 纯净无 Python 环境运行
"""
import os
import sys
import subprocess
import shutil

def main():
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

    # 3. 构造 PyInstaller 独立打包参数
    app_name = "驱动"
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=%s" % app_name,
        "--noconsole",          # 纯图形界面，不弹出黑色终端窗口
        "--onefile",            # 生成纯单文件 EXE (无需携带任何子文件夹，单个文件即可运行)
        "--clean",
        "--hidden-import=win32print",
        "--hidden-import=win32api",
        "--hidden-import=win32gui",
        "--hidden-import=serial",
        "--hidden-import=sqlite3",
        "--hidden-import=PyQt5.QtCore",
        "--hidden-import=PyQt5.QtWidgets",
        "--hidden-import=PyQt5.QtGui",
        "main.py"
    ]

    print("[*] 正在打包独立软件程序（包含完整 Python 运行时与二进制动态库）...")
    res = subprocess.call(cmd)

    if res == 0:
        dist_file = os.path.join("dist", "%s.exe" % app_name)
        
        # 自动分发逻辑
        import platform
        try:
            is_win7 = (platform.release() == "7" or (sys.getwindowsversion().major == 6 and sys.getwindowsversion().minor == 1))
        except Exception:
            is_win7 = False
            
        if is_win7:
            target_dir = r"C:\驱动"
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, "%s.exe" % app_name)
            action_desc = f"系统检测为 Windows 7，已自动部署至: {target_path}"
        else:
            target_dir = os.path.join(os.path.expanduser("~"), "Desktop")
            target_path = os.path.join(target_dir, "%s.exe" % app_name)
            action_desc = f"系统检测非 Windows 7，已自动拷贝至桌面: {target_path}"
            
        shutil.copy2(dist_file, target_path)

        print("\n" + "=" * 60)
        print(" [v] 打包成功！")
        print(f" [*] {action_desc}")
        print("=" * 60)
        print("[!] 重要提示：")
        print("   原始文件仍保留在: %s" % os.path.abspath(dist_file))
        print("   目标收银机电脑【完全不需要安装 Python】或任何环境！")
        print("=" * 60)
    else:
        print("\n[X] 打包失败，请检查编译日志！")

if __name__ == "__main__":
    main()
