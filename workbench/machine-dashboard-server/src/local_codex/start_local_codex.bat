@echo off
setlocal
cd /d "%~dp0..\.."
if not defined HOME set "HOME=%USERPROFILE%"
if not defined CODEX_HOME set "CODEX_HOME=%~dp0..\..\.codex-runtime"
if not exist "%CODEX_HOME%" mkdir "%CODEX_HOME%"
set "CODEX_PORT=4500"
if defined CODEX_APP_SERVER_PORT set "CODEX_PORT=%CODEX_APP_SERVER_PORT%"
echo Starting local Codex App Server on port %CODEX_PORT%...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& codex app-server --listen ws://127.0.0.1:%CODEX_PORT%"
if errorlevel 1 (
  echo Codex App Server 启动失败，错误代码：%errorlevel%
  pause
)
