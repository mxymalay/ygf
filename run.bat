@echo off
cd /d "%~dp0"
start "" pythonw main.py
if errorlevel 1 start "" python main.py
