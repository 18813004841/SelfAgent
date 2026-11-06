@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%~dp0src"
set "MACHINE_DASHBOARD_HOST=0.0.0.0"
"%PYTHON%" src\server.py
