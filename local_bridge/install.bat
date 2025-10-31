@echo off
:: This script sets up the Python environment for the local bridge and creates a startup task.

echo [1/3] Checking for Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in your PATH.
    echo Please install Python 3.8+ and ensure it is added to your system PATH.
    pause
    exit /b 1
)

echo [2/3] Creating Python virtual environment in './venv'...
if not exist venv (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists.
)

echo [3/3] Installing dependencies from requirements.txt...
call .\venv\Scripts\activate.bat
pip install -r requirements.txt

echo.
echo --- SETUP COMPLETE ---

echo Creating startup shortcut...

:: Define paths
set SCRIPT_PATH=%~dp0run_background.vbs
set SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\run_bridge.lnk
set TEMP_VBS_FILE=%~dp0_create_shortcut.vbs

:: Create a temporary VBScript file to generate the shortcut
(   echo Set oWS = WScript.CreateObject("WScript.Shell")
    echo Set oLink = oWS.CreateShortcut("%SHORTCUT_PATH%")
    echo oLink.TargetPath = "%SCRIPT_PATH%"
    echo oLink.WindowStyle = 7
    echo oLink.Description = "Start the AutoSig Local Bridge"
    echo oLink.WorkingDirectory = "%~dp0"
    echo oLink.Save
) > "%TEMP_VBS_FILE%"

:: Execute the VBScript
cscript /nologo "%TEMP_VBS_FILE%"

:: Clean up the temporary file
del "%TEMP_VBS_FILE%"

echo.
echo A shortcut has been added to your Startup folder.
echo The bridge will now start automatically when you log in.
echo You can run the bridge manually by double-clicking 'run_background.vbs'.
echo.
pause
