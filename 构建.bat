@echo off
cd /d "%~dp0"
title YGF POS Build

echo ========================================================
echo   YGF POS standalone EXE build
echo ========================================================
echo.

if exist "G:\AI\anaconda3\envs\py38_win7\python.exe" (
    "G:\AI\anaconda3\envs\py38_win7\python.exe" build_exe.py
) else (
    python build_exe.py
)

echo.
echo Build command finished. Press any key to close.
pause
