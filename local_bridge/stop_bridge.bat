@echo off
echo.
echo ========================================================================
echo                   LOCAL BRIDGE - STOP SCRIPT
echo ========================================================================
echo.

:: Try to kill pythonw.exe processes running bridge.py
echo Looking for running bridge processes...
echo.

set found=0

for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq pythonw.exe" /FO LIST ^| findstr "PID:"') do (
    set found=1
    set pid=%%i
    echo Found pythonw.exe process: PID !pid!
    
    :: Try to kill gracefully first
    taskkill /PID !pid! >nul 2>&1
    
    if errorlevel 1 (
        echo   - Failed to terminate gracefully, forcing...
        taskkill /F /PID !pid! >nul 2>&1
        if errorlevel 1 (
            echo   - [ERROR] Could not terminate process !pid!
        ) else (
            echo   - [OK] Process !pid! terminated (forced)
        )
    ) else (
        echo   - [OK] Process !pid! terminated gracefully
    )
)

if !found!==0 (
    echo No pythonw.exe processes found.
    echo The bridge may not be running, or it's running in a visible window.
    echo.
    echo Checking for python.exe...
    
    for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| findstr "PID:"') do (
        set found=1
        set pid=%%i
        echo Found python.exe process: PID !pid!
        echo   - This might be the bridge running in debug mode
        echo   - Close the console window manually or use Ctrl+C
    )
    
    if !found!==0 (
        echo No python processes found running the bridge.
    )
)

echo.

:: Check if port is still in use
timeout /t 2 /nobreak >nul
netstat -ano | findstr ":31415" >nul
if "%ERRORLEVEL%"=="0" (
    echo [WARNING] Port 31415 is still in use
    echo The bridge may still be shutting down, or another process is using the port
    echo.
    netstat -ano | findstr ":31415"
) else (
    echo [OK] Port 31415 is now free
)

echo.
echo ========================================================================
echo                        STOP SCRIPT COMPLETE
echo ========================================================================
echo.

pause