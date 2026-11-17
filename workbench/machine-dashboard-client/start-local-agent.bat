@echo off
setlocal
cd /d "%~dp0"
if not defined WORKBENCH_LOCAL_AGENT_PORT set "WORKBENCH_LOCAL_AGENT_PORT=18991"
if not defined WORKBENCH_DASHBOARD_URL set "WORKBENCH_DASHBOARD_URL=http://10.0.76.228:18888"
if defined WORKBENCH_CLIENT_PYTHON goto launch
set "WORKBENCH_CLIENT_PYTHON=%~dp0.venv\Scripts\python.exe"
:launch
if not exist "%WORKBENCH_CLIENT_PYTHON%" goto initialize
"%WORKBENCH_CLIENT_PYTHON%" -m src.local_agent --host 127.0.0.1 --port %WORKBENCH_LOCAL_AGENT_PORT% --dashboard-url "%WORKBENCH_DASHBOARD_URL%"
if errorlevel 1 goto failed
exit /b 0
:initialize
echo First run: creating the local Python environment.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-client.ps1" -DashboardUrl "%WORKBENCH_DASHBOARD_URL%" -Start
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo LOCAL_AGENT_START_FAILED
 echo Read the error above. Python 3.11+ is required.
echo Do not close unknown processes if port 18991 is occupied.
pause
exit /b 1
