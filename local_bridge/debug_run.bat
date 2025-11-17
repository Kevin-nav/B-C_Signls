@echo off
setlocal enabledelayedexpansion
color 0A

echo.
echo ========================================================================
echo                        LOCAL BRIDGE - DEBUG MODE
echo ========================================================================
echo.
echo This script runs the bridge in a visible window to diagnose issues.
echo The window will stay open even if the script crashes.
echo.

:: Check for virtual environment
if not exist venv\Scripts\python.exe (
    color 0C
    echo [ERROR] Virtual environment not found!
    echo.
    echo Expected location: %CD%\venv\Scripts\python.exe
    echo Please run 'QUICKSTART.bat' to create the virtual environment.
    echo.
    pause
    exit /b 1
)

:: Check for bridge.py
if not exist bridge.py (
    color 0C
    echo [ERROR] bridge.py not found!
    echo.
    echo Expected location: %CD%\bridge.py
    echo Please ensure all files are in the correct directory.
    echo.
    pause
    exit /b 1
)

:: Check for config.ini
if not exist config.ini (
    color 0C
    echo [ERROR] config.ini not found!
    echo.
    echo Expected location: %CD%\config.ini
    echo Please create the configuration file before running.
    echo You can run QUICKSTART.bat to generate a template.
    echo.
    pause
    exit /b 1
)

:: Show configuration
echo [OK] All required files found.
echo.
echo Configuration:
echo   - Python: %CD%\venv\Scripts\python.exe
echo   - Script: %CD%\bridge.py
echo   - Config: %CD%\config.ini
echo.

:: Check if config.ini has content
for %%A in (config.ini) do set size=%%~zA
if !size! LSS 100 (
    color 0E
    echo [WARNING] config.ini appears to be empty or very small ^(!size! bytes^)
    echo Please check that it contains all required sections.
    echo.
)

echo ========================================================================
echo                        STARTING BRIDGE...
echo ========================================================================
echo.
echo Press Ctrl+C to stop the bridge
echo.

:: Activate virtual environment and run
call .\venv\Scripts\activate.bat

if errorlevel 1 (
    color 0C
    echo.
    echo [ERROR] Failed to activate virtual environment!
    echo.
    pause
    exit /b 1
)

:: Run the bridge
python bridge.py

:: Capture exit code
set EXIT_CODE=%errorlevel%

echo.
echo ========================================================================
echo                        BRIDGE STOPPED
echo ========================================================================
echo.

if %EXIT_CODE% EQU 0 (
    color 0A
    echo [INFO] Bridge exited normally ^(exit code: %EXIT_CODE%^)
) else (
    color 0C
    echo [ERROR] Bridge crashed or exited with error ^(exit code: %EXIT_CODE%^)
    echo.
    echo Common exit codes:
    echo   1 = Configuration error or initialization failure
    echo.
    echo Check the log files in the 'logs' directory for details.
)

echo.
echo Check bridge_status.txt for last known status.
if exist bridge_status.txt (
    echo.
    echo Last status:
    type bridge_status.txt
)

echo.
pause