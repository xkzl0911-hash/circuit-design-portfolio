@echo off
cd /d "%~dp0"
python report_generator.py --latest --open
if errorlevel 1 pause
