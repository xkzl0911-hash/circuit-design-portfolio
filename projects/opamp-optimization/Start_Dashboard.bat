@echo off
cd /d "%~dp0"
python live_dashboard.py
if errorlevel 1 pause
