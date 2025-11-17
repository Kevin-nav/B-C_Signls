@echo off
setlocal enabledelayedexpansion
color 0B

echo.
echo ========================================================================
echo                 LOCAL BRIDGE - INSTALLATION CHECKER
echo ========================================================================
echo.
echo This script verifies that all required files and dependencies are
echo properly installed and configured.
echo.

set "errors=0"
set "warnings=0"

:: Check Python installation
echo [1/6] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo   [ERROR] Python not found in PATH
    echo   Please install Python 3.7 or higher from python.org
    set /a errors+=1
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set pyver=%%i
    echo   [OK] Python !pyver! found
)
echo.

:: Check virtual environment
echo [2/6] Checking virtual environment...
if not exist venv\Scripts\python.exe (
    color 0E
    echo   [ERROR] Virtual environment not found
    echo   Expected: %CD%\venv\Scripts\python.exe
    echo   Run: python -m venv venv
    set /a errors+=1
) else (
    echo   [OK] Virtual environment exists
    
    :: Check if venv is activated (for info only)
    if defined VIRTUAL_ENV (
        echo   [INFO] Virtual environment is currently activated
    )
)
echo.

:: Check required Python files
echo [3/6] Checking required Python files...

set "required_files=bridge.py"
for %%f in (!required_files!) do (
    if not exist %%f (
        color 0C
        echo   [ERROR] Missing file: %%f
        set /a errors+=1
    ) else (
        echo   [OK] Found %%f
    )
)
echo.

:: Check batch/vbs files
echo [4/6] Checking helper scripts...
set "helper_files=run_background.vbs debug_run.bat check_bridge_status.bat stop_bridge.bat"
for %%f in (!helper_files!) do (
    if not exist %%f (
        color 0E
        echo   [WARNING] Missing helper script: %%f
        set /a warnings+=1
    ) else (
        echo   [OK] Found %%f
    )
)
echo.

:: Check config.ini
echo [5/6] Checking configuration file...
if not exist config.ini (
    color 0C
    echo   [ERROR] config.ini not found!
    echo   Create config.ini before running the bridge.
    set /a errors+=1
) else (
    for %%A in (config.ini) do set cfgsize=%%~zA
    if !cfgsize! LSS 100 (
        color 0E
        echo   [WARNING] config.ini appears empty or very small ^(!cfgsize! bytes^)
        set /a warnings+=1
    ) else (
        echo   [OK] config.ini exists ^(!cfgsize! bytes^)
        
        :: Check for required sections
        findstr /C:"[server]" config.ini >nul
        if errorlevel 1 (
            color 0C
            echo   [ERROR] config.ini missing [server] section
            set /a errors+=1
        ) else (
            echo   [OK] Found [server] section
        )
        
        findstr /C:"[bridge]" config.ini >nul
        if errorlevel 1 (
            color 0C
            echo   [ERROR] config.ini missing [bridge] section
            set /a errors+=1
        ) else (
            echo   [OK] Found [bridge] section
        )
        
        findstr /C:"[security]" config.ini >nul
        if errorlevel 1 (
            color 0C
            echo   [ERROR] config.ini missing [security] section
            set /a errors+=1
        ) else (
            echo   [OK] Found [security] section
        )
    )
)
echo.

:: Check Python packages
echo [6/6] Checking Python packages in virtual environment...
if exist venv\Scripts\python.exe (
    echo   Checking installed packages...
    
    venv\Scripts\python.exe -c "import win32com; print('[OK] pywin32 (win32com) installed')" 2>nul
    if errorlevel 1 (
        color 0C
        echo   [ERROR] pywin32 package not installed
        echo   Run: venv\Scripts\pip install pywin32
        set /a errors+=1
    )
) else (
    echo   [SKIP] Virtual environment not found
)
echo.

:: Check ports availability
echo [7/7] Checking port availability...
netstat -ano | findstr ":31415" >nul
if not errorlevel 1 (
    color 0E
    echo   [WARNING] Port 31415 is already in use
    echo   Another instance may be running, or another program is using this port
    set /a warnings+=1
) else (
    echo   [OK] Port 31415 is available
)
echo.

:: Summary
echo ========================================================================
echo                         INSTALLATION SUMMARY
echo ========================================================================
echo.

if !errors! EQU 0 (
    if !warnings! EQU 0 (
        color 0A
        echo   STATUS: PERFECT - No issues found!
        echo.
        echo   Your bridge is ready to run.
        echo   Next steps:
        echo     1. Review config.ini settings
        echo     2. Run debug_run.bat to test
        echo     3. Use run_background.vbs for production
    ) else (
        color 0E
        echo   STATUS: READY WITH WARNINGS - !warnings! warning^(s^) found
        echo.
        echo   The bridge should work, but review the warnings above.
        echo   Some optional features may not be available.
    )
) else (
    color 0C
    echo   STATUS: NOT READY - !errors! error^(s^) found
    echo.
    echo   Please fix the errors above before running the bridge.
    echo   Common fixes:
    echo     - Install Python packages: venv\Scripts\pip install pywin32
    echo     - Create config.ini from the template
    echo     - Run QUICKSTART.bat if available
)

echo.
echo   Errors:   !errors!
echo   Warnings: !warnings!
echo.

if !errors! GTR 0 (
    echo ========================================================================
    echo                         QUICK FIX GUIDE
    echo ========================================================================
    echo.
    echo To install missing Python packages:
    echo   venv\Scripts\pip install pywin32
    echo.
    echo To create virtual environment:
    echo   python -m venv venv
    echo.
    echo To create config.ini:
    echo   Copy and customize the provided config.ini template
    echo.
)

echo ========================================================================
echo.
pause