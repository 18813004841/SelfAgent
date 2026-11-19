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

rem 启动前只清理当前配置端口上的监听进程，避免旧工作台实例阻塞启动。
echo 检查工作台端口 %PORT% 的占用进程...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\clear_port.ps1" -Port %PORT%
if errorlevel 1 (
    echo 端口占用进程清理失败，已停止启动以避免误用端口。
    pause
    exit /b 1
)

echo 正在启动工作台服务（端口 %PORT%）...
"%PYTHON%" src\server.py
if errorlevel 1 (
    echo.
    echo 服务启动失败，错误代码：%errorlevel%
    pause
)
