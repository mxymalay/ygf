"""
Windows 独立 EXE 软件打包脚本
一键生成免安装绿色可执行程序 (支持 Win7 / Win10 / Win11)
"""
import os
import sys
import subprocess
import shutil

def main():
    print("=" * 60)
    print("      杨国福麻辣烫 · 独立称重与打印系统 — EXE 打包工具")
    print("=" * 60)

    # 1. 检查并安装 PyInstaller
    try:
        import PyInstaller
        print("[✓] PyInstaller 已安装")
    except ImportError:
        print("[!] 正在安装 PyInstaller 打包依赖...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])

    # 2. 清理旧的构建文件
    print("[*] 清理历史构建缓存...")
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)

    # 3. 构造 PyInstaller 参数
    app_name = "杨国福称重打印系统"
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=%s" % app_name,
        "--noconsole",          # 隐藏黑色命令行控制台
        "--onedir",             # 生成绿色独立文件夹 (启动更快)
        "--clean",              # 清理临时文件
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

    print("[*] 正在执行 PyInstaller 编译...")
    print("    命令:", " ".join(cmd))
    
    res = subprocess.call(cmd)

    if res == 0:
        dist_dir = os.path.join("dist", app_name)
        data_dir = os.path.join(dist_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        print("\n" + "=" * 60)
        print(" [🎉] 软件打包成功！")
        print(" [📁] 可执行程序存放位置:")
        print("      %s\\%s.exe" % (os.path.abspath(dist_dir), app_name))
        print("=" * 60)
        print("提示：可以将 dist\\%s 整个文件夹复制或压缩，直接发送到收银机双击运行！" % app_name)
    else:
        print("\n[X] 打包失败，请检查编译日志！")

if __name__ == "__main__":
    main()
