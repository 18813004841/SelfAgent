@echo off
setlocal EnableExtensions`r`nset "PYTHONPATH=%~dp0;%~dp0..\shared"

rem ================================================================
rem Machine Control Windows Worker - universal launcher
rem Place this file in the machine-control root directory and double-click.
rem Works for controller-local Windows worker and remote Windows workers.
rem No absolute install path is used.
rem
rem Machine ID rule:
rem   1) If MACHINE_ID_OVERRIDE is set, use it.
rem   2) Else detect from local LAN IP:
rem        10.0.76.228 -> win-pack-228
rem        10.0.27.224 -> win-pack-224
rem        10.0.27.169 -> win-pack-169
rem   3) Else fallback to win-pack-%COMPUTERNAME%.
rem ================================================================

set "LOG_FILE=%~dp0worker_start_debug.log"
echo ================================================================ > "%LOG_FILE%"
echo Machine Control Windows Worker startup debug log >> "%LOG_FILE%"
echo Time: %DATE% %TIME% >> "%LOG_FILE%"
echo Script: %~f0 >> "%LOG_FILE%"
echo PATH: %PATH% >> "%LOG_FILE%"
echo ================================================================ >> "%LOG_FILE%"

call :LOG "Entering script directory: %~dp0"
cd /d "%~dp0" 1>>"%LOG_FILE%" 2>>&1
if errorlevel 1 goto FAIL_CWD

call :LOG "Working dir: %CD%"
if not exist "control_worker\client.py" goto FAIL_ROOT
if not exist "control_worker\detect_machine_id.py" goto FAIL_DETECTOR

set "CENTRAL_URL=http://10.0.27.95:18765"
set "TOKEN=dev-token"

call :LOG "Checking Python candidates without using where.exe..."
set "PYTHON_CMD="
set "PYTHON_ARGS="

call :TRY_PYTHON python3 ""
if not "%PYTHON_CMD%"=="" goto PYTHON_FOUND

call :TRY_PYTHON python ""
if not "%PYTHON_CMD%"=="" goto PYTHON_FOUND

call :TRY_PYTHON py "-3"
if not "%PYTHON_CMD%"=="" goto PYTHON_FOUND

if exist "%LocalAppData%\Python\bin\python3.exe" call :TRY_PYTHON "%LocalAppData%\Python\bin\python3.exe" ""
if not "%PYTHON_CMD%"=="" goto PYTHON_FOUND

if exist "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" call :TRY_PYTHON "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" ""
if not "%PYTHON_CMD%"=="" goto PYTHON_FOUND

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" call :TRY_PYTHON "%LocalAppData%\Programs\Python\Python312\python.exe" ""
if not "%PYTHON_CMD%"=="" goto PYTHON_FOUND

goto FAIL_PYTHON

:PYTHON_FOUND
call :LOG "Selected Python: %PYTHON_CMD% %PYTHON_ARGS%"

if not "%MACHINE_ID_OVERRIDE%"=="" (
  set "MACHINE_ID=%MACHINE_ID_OVERRIDE%"
  call :LOG "Using MACHINE_ID_OVERRIDE=%MACHINE_ID%"
) else (
  call :LOG "Detecting machine id from local IP..."
  set "MACHINE_ID="
  for /f "usebackq delims=" %%i in (`%PYTHON_CMD% %PYTHON_ARGS% -m control_worker.detect_machine_id 2^>^>"%LOG_FILE%"`) do set "MACHINE_ID=%%i"
  call :LOG "Detected MACHINE_ID=%MACHINE_ID%"
)
if "%MACHINE_ID%"=="" set "MACHINE_ID=win-pack-%COMPUTERNAME%"

title Machine Control Worker - %MACHINE_ID% -> 10.0.27.95:18765

echo ================================================================
echo Machine Control Windows Worker
echo Working dir    : %CD%
echo Python         : %PYTHON_CMD% %PYTHON_ARGS%
echo Connect server : %CENTRAL_URL%
echo Machine ID     : %MACHINE_ID%
echo Token          : %TOKEN%
echo Capabilities   : shell, unity, adb
echo Log file       : %LOG_FILE%
echo ================================================================

call :LOG "Detect debug:"
%PYTHON_CMD% %PYTHON_ARGS% -m control_worker.detect_machine_id --debug 1>>"%LOG_FILE%" 2>>&1

call :LOG "Starting worker client..."
%PYTHON_CMD% %PYTHON_ARGS% -m control_worker.client ^
  --server %CENTRAL_URL% ^
  --machine-id %MACHINE_ID% ^
  --token %TOKEN% ^
  --capability shell ^
  --capability unity ^
  --capability adb ^
  --allow-command tail ^
  --allow-command ls ^
  --allow-command cat ^
  --allow-command grep ^
  --allow-command find ^
  --allow-command df ^
  --allow-command du ^
  --allow-command git ^
  --allow-command hostname ^
  --allow-command whoami ^
  --allow-command pwd ^
  --allow-command python ^
  --allow-command python3

set "EXIT_CODE=%ERRORLEVEL%"
call :LOG "Worker exited. ExitCode=%EXIT_CODE%"
echo.
echo Worker exited. ExitCode: %EXIT_CODE%
echo See log: %LOG_FILE%
echo Press any key to close.
pause >nul
exit /b %EXIT_CODE%

:TRY_PYTHON
set "CANDIDATE_CMD=%~1"
set "CANDIDATE_ARGS=%~2"
call :LOG "Trying Python candidate: %CANDIDATE_CMD% %CANDIDATE_ARGS%"
%CANDIDATE_CMD% %CANDIDATE_ARGS% --version 1>>"%LOG_FILE%" 2>>&1
if not errorlevel 1 (
  set "PYTHON_CMD=%CANDIDATE_CMD%"
  set "PYTHON_ARGS=%CANDIDATE_ARGS%"
  exit /b 0
)
call :LOG "Candidate failed: %CANDIDATE_CMD% %CANDIDATE_ARGS%"
exit /b 1

:FAIL_CWD
call :LOG "ERROR: Failed to enter script directory: %~dp0"
echo Failed to enter script directory: %~dp0
echo See log: %LOG_FILE%
pause
exit /b 1

:FAIL_ROOT
call :LOG "ERROR: Missing control_worker\client.py in %CD%"
echo Missing control_worker\client.py in: %CD%
echo This bat must be placed in the machine-control root directory.
echo See log: %LOG_FILE%
pause
exit /b 1

:FAIL_DETECTOR
call :LOG "ERROR: Missing control_worker\detect_machine_id.py in %CD%"
echo Missing control_worker\detect_machine_id.py in: %CD%
echo Please copy the latest machine-control files to this machine.
echo See log: %LOG_FILE%
pause
exit /b 1

:FAIL_PYTHON
call :LOG "ERROR: No runnable Python found. Tried python3, python, py -3 and known local paths."
echo No runnable Python found. Tried python3, python, py -3 and known local paths.
echo See log: %LOG_FILE%
pause
exit /b 1

:LOG
echo %~1
echo [%DATE% %TIME%] %~1 >> "%LOG_FILE%"
exit /b 0

