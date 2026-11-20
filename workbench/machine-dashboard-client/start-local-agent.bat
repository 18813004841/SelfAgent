@echo off
setlocal
cd /d "%~dp0"
if not defined WORKBENCH_LOCAL_AGENT_PORT set "WORKBENCH_LOCAL_AGENT_PORT=18991"
rem Prefer an explicit origin; otherwise use this machine's active IPv4.
if not defined WORKBENCH_DASHBOARD_URL for /f "tokens=2 delims=:" %%I in ('ipconfig ^| findstr /R /C:"IPv4 Address"') do if not defined WORKBENCH_DASHBOARD_URL set "WORKBENCH_DASHBOARD_URL=http://%%I:18888"
if not defined WORKBENCH_DASHBOARD_URL set "WORKBENCH_DASHBOARD_URL=http://127.0.0.1:18888"

rem Restart an existing Local Agent, but never kill an unrelated listener.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=[int]$env:WORKBENCH_LOCAL_AGENT_PORT; $connections=@(Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort $port -ErrorAction SilentlyContinue); foreach($c in $connections){ $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$c.OwningProcess) -ErrorAction SilentlyContinue; if(-not $p -or [string]$p.CommandLine -notmatch 'src[\\/]local_agent' -or [string]$p.CommandLine -notmatch ('--port\\s+'+$port)){ Write-Error ('端口 127.0.0.1:'+ $port +' 已被其他进程占用，未执行清理。'); exit 1 }; Stop-Process -Id $c.OwningProcess -Force }; exit 0"
if errorlevel 1 exit /b 1
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
