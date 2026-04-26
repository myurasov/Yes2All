@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: -- version --------------------------------------------------------------
for /f "tokens=2 delims==" %%v in ('findstr /b "version" pyproject.toml') do (
    set "RAW=%%v"
)
set "VERSION=%RAW: =%"
set "VERSION=%VERSION:~1,-1%"

:menu
cls
echo [96m[1mYes2All[0m [2mv%VERSION% — Auto-approve agent tool prompts[0m
echo.
echo     [33m1[0m)  Run y2a-service [2m(Ctrl+C to stop)[0m
echo     [33m2[0m)  Run y2a-service with custom settings
echo.
echo     [33m3[0m)  Show CDP targets
echo     [33m4[0m)  Probe for approval buttons
echo.
echo     [33mq[0m)  Quit
echo.
choice /c 1234q /n /m "  Choose [1-4/q]: "

if errorlevel 5 goto :quit
if errorlevel 4 goto :probe
if errorlevel 3 goto :targets
if errorlevel 2 goto :custom
if errorlevel 1 goto :run_default

:run_default
echo.
echo   [36mRunning y2a-service on ports 9222,9333 (Ctrl+C to stop)...[0m
echo.
uv run yes2all watch --port 9222 --port 9333 --interval 1 --countdown 3
echo.
pause
goto :menu

:custom
echo.
set /p "PORTS=  Ports (comma-separated) [9222,9333]: "
if "%PORTS%"=="" set "PORTS=9222,9333"
set /p "INTERVAL=  Poll interval (seconds) [1]: "
if "%INTERVAL%"=="" set "INTERVAL=1"
set /p "COUNTDOWN=  Countdown before click (seconds, 0=instant) [3]: "
if "%COUNTDOWN%"=="" set "COUNTDOWN=3"
set /p "SWEEP=  Cycle Cursor tabs? [y/N]: "
if "%SWEEP%"=="" set "SWEEP=N"

set "PORT_ARGS="
for %%p in (%PORTS%) do set "PORT_ARGS=!PORT_ARGS! --port %%p"

set "SWEEP_FLAG=--no-sweep-tabs"
if /i "%SWEEP%"=="y" set "SWEEP_FLAG=--sweep-tabs"

echo.
echo   [36mRunning y2a-service (Ctrl+C to stop)...[0m
echo.
uv run yes2all watch %PORT_ARGS% --interval %INTERVAL% %SWEEP_FLAG% --countdown %COUNTDOWN%
echo.
pause
goto :menu

:targets
echo.
set /p "TPORT=  Port [9222]: "
if "%TPORT%"=="" set "TPORT=9222"
echo.
uv run yes2all targets --port %TPORT%
echo.
pause
goto :menu

:probe
echo.
set /p "PPORT=  Port [9222]: "
if "%PPORT%"=="" set "PPORT=9222"
echo.
uv run yes2all probe --port %PPORT%
echo.
pause
goto :menu

:quit
echo.
echo   [2mBye.[0m
echo.
exit /b 0
