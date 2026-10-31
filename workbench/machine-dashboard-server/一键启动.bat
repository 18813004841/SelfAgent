@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%~dp0src"
start "Local Workbench Server" cmd /k "cd /d "%~dp0" && set PYTHONPATH=%PYTHONPATH% && "%PYTHON%" src\server.py"
endlocal
