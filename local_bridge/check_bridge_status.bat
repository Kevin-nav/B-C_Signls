@echo off
setlocal enabledelayedexpansion

echo.
echo ========================================================================
echo                   LOCAL BRIDGE - HEALTH CHECK
echo ========================================================================
echo.

:: Check if bridge is running (looking for pythonw.exe running bridge.py)
tasklist /FI "IMAGENAME eq pythonw.exe" 2>NUL | find /I /N "pythonw.exe">NUL
if "%ERRORLEVEL%"=="0" (
    color 0A
    echo [STATUS] Python process is running
) else (
    color 0E
    echo [STATUS] No Python process detected - bridge may not be running
)

echo.

:: Check status file
if exist bridge_status.txt (
    echo [STATUS FILE] Last reported status:
    echo ----------------------------------------
    type bridge_status.txt
    echo ----------------------------------------
    echo.
    
    :: Parse the status file
    for /f "tokens=1,2,3 delims=|" %%a in (bridge_status.txt) do (
        set "timestamp=%%a"
        set "status=%%b"
        set "details=%%c"
    )
    
    :: Check the status
    if "!status!"=="VPS_CONNECTED" (
        color 0A
        echo [ANALYSIS] Bridge is connected to VPS - HEALTHY
    ) else if "!status!"=="EA_SERVER_RUNNING" (
        color 0A
        echo [ANALYSIS] EA server is running - HEALTHY
    ) else if "!status!"=="VPS_CONNECTION_REFUSED" (
        color 0C
        echo [ANALYSIS] Cannot connect to VPS - CHECK VPS SERVER
    ) else if "!status!"=="STOPPED" (
        color 0E
        echo [ANALYSIS] Bridge is stopped
    ) else (
        color 0E
        echo [ANALYSIS] Bridge status: !status!
    )
) else (
    color 0C
    echo [ERROR] Status file not found - bridge has not been started
)

echo.

:: Check for recent log file
if exist logs (
    for /f %%i in ('dir /b /od logs\bridge_*.log 2^>nul') do set latest_log=%%i
    
    if defined latest_log (
        echo [LOG FILE] Latest log: logs\!latest_log!
        echo.
        echo [LOG FILE] Last 10 lines:
        echo ----------------------------------------
        powershell -Command "Get-Content 'logs\!latest_log!' -Tail 10"
        echo ----------------------------------------
    ) else (
        echo [WARNING] No log files found in logs directory
    )
) else (
    echo [WARNING] Logs directory does not exist
)

echo.

:: Check port binding
echo [NETWORK] Checking if bridge port is listening...
netstat -ano | findstr ":31415" >nul
if "%ERRORLEVEL%"=="0" (
    color 0A
    echo [OK] Port 31415 is in use ^(bridge is listening for EA connections^)
    netstat -ano | findstr ":31415"
) else (
    color 0E
    echo [WARNING] Port 31415 is not in use ^(bridge may not be listening^)
)

echo.
echo ========================================================================
echo                        HEALTH CHECK COMPLETE
echo ========================================================================
echo.

pause