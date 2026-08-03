@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ScaleBridge installation and Windows-service maintenance require admin.
rem Elevate only this launcher; never disable or weaken Windows UAC.
powershell -NoProfile -Command "$p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent()); if ($p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator permission...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

if exist "G:\AI\anaconda3\envs\py38_win7\python.exe" (
    "G:\AI\anaconda3\envs\py38_win7\python.exe" main.py
    goto :finished
)

where python >nul 2>&1
if not errorlevel 1 (
    python main.py
    goto :finished
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3 main.py
    goto :finished
)

echo Python was not found. Run install_env.bat first.
pause
exit /b 1

:finished
if errorlevel 1 pause
