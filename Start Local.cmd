@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please run Setup Local.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\start_local.py
if errorlevel 1 pause
