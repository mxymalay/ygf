@echo off
cd /d "%~dp0"
chcp 65001 >nul
title 正在打包【杨国福麻辣烫称重打印系统】...

echo ========================================================
echo   杨国福麻辣烫 · 独立称重打印系统 一键打包独立软件 (EXE)
echo ========================================================
echo.

if exist "G:\AI\anaconda3\envs\py38_win7\python.exe" (
    "G:\AI\anaconda3\envs\py38_win7\python.exe" build_exe.py
) else (
    python build_exe.py
)

echo.
pause
