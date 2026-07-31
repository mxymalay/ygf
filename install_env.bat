@echo off
title Yangguofu POS - Win7 Environment Installer
cls
echo ===================================================
echo   Yangguofu POS System - Environment Installer
echo ===================================================
echo.

python --version
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.8.10 and check "Add Python to PATH".
    echo.
    pause
    exit /b
)

echo.
echo [1/3] Setting Tsinghua PyPI Mirror...
python -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

echo.
echo [2/3] Upgrading pip...
python -m pip install --upgrade pip

echo.
echo [3/3] Installing Dependencies (PyQt5, pyserial, pywin32)...
python -m pip install PyQt5 pyserial pywin32

echo.
echo ===================================================
echo   Installation Finished! Press any key to run diagnosis...
echo ===================================================
pause

python diagnose.py

pause
