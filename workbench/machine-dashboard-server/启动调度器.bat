@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%~dp0src"
start "Local Workbench Scheduler" cmd /k "cd /d "%~dp0" && set PYTHONPATH=%PYTHONPATH% && "%PYTHON%" src\scheduler.py"
endlocal
