@echo off
title Machine Control Center - LAN Server (10.0.76.228:18765)
cd /d "%~dp0"
set "PYTHONPATH=%~dp0;%~dp0..\shared"
echo ================================================================
echo Machine Control Center - LAN mode
echo Listen URL for local machine : http://127.0.0.1:18765
echo Listen URL for LAN workers   : http://10.0.76.228:18765
echo Token                        : dev-token
echo ================================================================
python -m control_center.server --host 0.0.0.0 --port 18765 --token dev-token
echo.
echo Central LAN server exited. Press any key to close.
pause >nul


