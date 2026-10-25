@echo off
cd /d "%~dp0"
start "ICPPLUS Monitor" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0monitor_app.py"
