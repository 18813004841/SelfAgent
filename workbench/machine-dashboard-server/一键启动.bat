@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%~dp0src"
set "MACHINE_DASHBOARD_HOST=0.0.0.0"
set "PORT=%MACHINE_DASHBOARD_PORT%"
if "%PORT%"=="" set "PORT=18888"
set "MACHINE_DASHBOARD_PORT=%PORT%"

rem 清理占用工作台端口的监听进程，避免启动失败
echo 检查端口 %PORT% 是否被占用...
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    if not "%%P"=="0" (
        echo 端口 %PORT% 被进程 %%P 占用，正在结束...
        taskkill /PID %%P /T /F
        if errorlevel 1 (
            echo 无法结束占用进程，请尝试以管理员身份运行此脚本。
            pause
            exit /b 1
        )
    )
)

echo 正在启动工作台服务（端口 %PORT%）...
"%PYTHON%" src\server.py
if errorlevel 1 (
    echo.
    echo 服务启动失败，错误代码：%errorlevel%
    pause
)
