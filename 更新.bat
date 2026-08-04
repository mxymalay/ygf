@echo off
cd /d "%~dp0"
title YGF POS Update

echo ========================================================
echo   YGF POS System Update (Git Pull)
echo ========================================================
echo.
echo [*] Pulling latest code updates from Git repository...
echo.

git pull

echo.
echo Update finished. Press any key to close.
pause
