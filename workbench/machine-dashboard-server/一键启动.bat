@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%~dp0src"
set "MACHINE_DASHBOARD_HOST=0.0.0.0"
set "PORT=18888"
if defined MACHINE_DASHBOARD_PORT set "PORT=%MACHINE_DASHBOARD_PORT%"
set "MACHINE_DASHBOARD_PORT=%PORT%"

rem 不结束未知端口进程；端口冲突由服务启动检查报告。
echo 启动工作台服务（端口 %PORT%）；不会清理未知占用进程...

echo 正在启动工作台服务（端口 %PORT%）...
"%PYTHON%" src\server.py
if errorlevel 1 (
    echo.
    echo 服务启动失败，错误代码：%errorlevel%
    pause
)
