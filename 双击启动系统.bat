@echo off
chcp 936 >nul
title 杨国福麻辣烫 - 称重与小票打印系统
cd /d "%~dp0"
echo ===================================================
echo     杨国福麻辣烫 · 称重与小票打印 POS 系统
echo ===================================================
echo 正在启动系统程序，请稍候...
echo.

python main.py

if errorlevel 1 (
    echo.
    echo [提示] 正在使用默认 python 命令...
    py main.py
)

if errorlevel 1 (
    echo.
    echo [错误] 系统启动异常，请按任意键退出或检查 Python 环境。
    pause
)
