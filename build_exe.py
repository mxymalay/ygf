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

    # 1. 检查并安装 PyInstaller
    try:
        import PyInstaller
        print("[✓] PyInstaller 已就绪")
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
    app_name = "杨国福称重打印系统"
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=%s" % app_name,
        "--noconsole",          # 纯图形界面，不弹出黑色终端窗口
        "--onedir",             # 生成绿色免安装软件包 (内置所有 Python 运行组件)
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
        dist_dir = os.path.join("dist", app_name)
        data_dir = os.path.join(dist_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        print("\n" + "=" * 60)
        print(" [v] 打包成功！可执行文件位于 dist/ 目录下。")
        print(" [📁] 绿色版软件位置:")
        print("      %s\\%s.exe" % (os.path.abspath(dist_dir), app_name))
        print("=" * 60)
        print("💡 重要提示：")
        print("   把 'dist\\%s' 整个文件夹打包压缩发送到任何新电脑或收银机上，" % app_name)
        print("   直接双击 '%s.exe' 即可直接启动运行！" % app_name)
        print("   💥 目标收银机电脑【完全不需要安装 Python】或任何环境！")
        print("=" * 60)
    else:
        print("\n[X] 打包失败，请检查编译日志！")

if __name__ == "__main__":
    main()
