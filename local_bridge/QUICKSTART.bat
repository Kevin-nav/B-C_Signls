@echo off
setlocal enabledelayedexpansion
color 0B

echo.
echo ========================================================================
echo              LOCAL BRIDGE - QUICK START SETUP
echo ========================================================================
echo.
echo This script will set up everything you need to run the Local Bridge.
echo.
echo Steps:
echo   1. Create Python virtual environment
echo   2. Install required packages
echo   3. Verify installation
echo   4. Test configuration
echo.
echo Press Ctrl+C to cancel, or
pause
echo.

:: Step 1: Check Python
echo ========================================================================
echo Step 1/4: Checking Python installation...
echo ========================================================================
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo.
    echo [ERROR] Python is not installed or not in PATH!
    echo.
    echo Please install Python 3.7 or higher from:
    echo   https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set pyver=%%i
echo [OK] Python !pyver! found
echo.
pause

:: Step 2: Create virtual environment
echo ========================================================================
echo Step 2/4: Creating virtual environment...
echo ========================================================================

if exist venv (
    echo [INFO] Virtual environment already exists
    choice /C YN /M "Do you want to recreate it (this will delete existing packages)"
    if errorlevel 2 (
        echo [INFO] Skipping virtual environment creation
        goto :install_packages
    )
    echo [INFO] Removing old virtual environment...
    rmdir /s /q venv
)

echo [INFO] Creating new virtual environment...
python -m venv venv

if errorlevel 1 (
    color 0C
    echo [ERROR] Failed to create virtual environment!
    pause
    exit /b 1
)

echo [OK] Virtual environment created
echo.
pause

:: Step 3: Install packages
:install_packages
echo ========================================================================
echo Step 3/4: Installing required Python packages...
echo ========================================================================
echo.
echo This may take a few minutes...
echo.

if exist requirements.txt (
    echo [INFO] Installing from requirements.txt...
    venv\Scripts\pip install --upgrade pip
    venv\Scripts\pip install -r requirements.txt
) else (
    echo [INFO] requirements.txt not found, installing packages individually...
    venv\Scripts\pip install --upgrade pip
    venv\Scripts\pip install pywin32
)

if errorlevel 1 (
    color 0C
    echo.
    echo [ERROR] Failed to install packages!
    echo.
    echo Try manual installation:
    echo   venv\Scripts\pip install pywin32
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] All packages installed successfully
echo.
pause

:: Step 4: Verify installation
echo ========================================================================
echo Step 4/4: Verifying installation...
echo ========================================================================
echo.

:: Check if config.ini exists
if not exist config.ini (
    color 0E
    echo [WARNING] config.ini not found!
    echo.
    echo You need to create config.ini before running the bridge.
    echo.
    choice /C YN /M "Would you like to create a template config.ini now"
    if errorlevel 2 goto :skip_config
    
    echo.
    echo Creating config.ini template...
    (
        echo [server]
        echo vps_host = 127.0.0.1
        echo vps_port = 5200
        echo.
        echo [bridge]
        echo local_host = 127.0.0.1
        echo local_port = 31415
        echo.
        echo [security]
        echo secret_key = CHANGE_THIS_SECRET_KEY
        echo.
        echo [timing]
        echo heartbeat_interval = 30
    ) > config.ini
    
    echo [OK] Template config.ini created
    echo.
    color 0E
    echo IMPORTANT: Edit config.ini and set your actual values before running!
    echo Especially the secret_key must match your VPS server.
    echo.
)
:skip_config

:: Run installation checker
if exist check_installation.bat (
    echo Running installation checker...
    echo.
    call check_installation.bat
) else (
    echo [INFO] Checking packages manually...
    venv\Scripts\python.exe -c "import win32com; print('[OK] pywin32 (win32com) imported successfully')"
)

echo.
echo ========================================================================
echo                    SETUP COMPLETE!
echo ========================================================================
echo.
color 0A
echo Installation successful! Next steps:
echo.
echo 1. EDIT config.ini:
echo    - Set vps_host to your VPS IP (or 127.0.0.1 for local testing)
echo    - Set secret_key to match your VPS server
echo    - Adjust other settings as needed
echo.
echo 2. START your VPS server first (if testing locally)
echo.
echo 3. TEST the bridge:
echo    Run: debug_run.bat
echo    Look for "VPS_CONNECTED" and "EA_SERVER_RUNNING" messages
echo.
echo 4. CHECK status:
echo    Run: check_bridge_status.bat
echo.
echo 5. DEPLOY to production:
echo    Once testing is successful, use: run_background.vbs
echo.
echo ========================================================================
echo.
echo Available commands:
echo   debug_run.bat             - Run bridge with visible console (for testing)
echo   run_background.vbs        - Run bridge silently in background (for production)
echo   check_bridge_status.bat   - Check if bridge is running and healthy
echo   stop_bridge.bat           - Stop the bridge
echo   check_installation.bat    - Verify all files and packages
echo.
echo Documentation:
echo   Read README.md for detailed instructions.
echo.
echo ========================================================================
echo.

if exist config.ini (
    findstr "LZ2QThkLXWjmUCIADhLDu8tz4UwwQ35RnP3Bks76tjI" config.ini >nul
    if not errorlevel 1 (
        color 0E
        echo.
        echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        echo !  REMINDER: You must edit config.ini before running the bridge  !
        echo !  The current secret_key is just a placeholder!                 !
        echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        echo.
    )
)

pause