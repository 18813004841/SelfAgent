@echo off
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":18888" ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>nul
for /f "tokens=5" %%p in ('wmic process where "commandline like '%%src\\scheduler.py%%'" get ProcessId ^| findstr /r "[0-9]"') do taskkill /PID %%p /F >nul 2>nul
