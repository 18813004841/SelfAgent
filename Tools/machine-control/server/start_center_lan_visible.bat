@echo off
title Machine Control Center - LAN Server (10.0.76.228:18765)
cd /d "%~dp0"
set "PYTHONPATH=%~dp0;%~dp0..\shared"
set "MC_ROOT=%~dp0.."
if defined MACHINE_CONTROL_PYTHON set "MC_PYTHON=%MACHINE_CONTROL_PYTHON%"
if not defined MC_PYTHON if exist "%MC_ROOT%\.venv\Scripts\python.exe" set "MC_PYTHON=%MC_ROOT%\.venv\Scripts\python.exe"
if not defined MC_PYTHON set "MC_PYTHON=python"
echo ================================================================
echo Machine Control Center - LAN mode
echo Listen URL for local machine : http://127.0.0.1:18765
echo Listen URL for LAN workers   : http://10.0.76.228:18765
echo Token                        : dev-token
echo ================================================================
"%MC_PYTHON%" -m control_center.server --host 0.0.0.0 --port 18765 --token dev-token
echo.
echo Central LAN server exited. Press any key to close.
pause >nul


