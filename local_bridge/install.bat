@echo off
setlocal
cls
title AutoSig Local Bridge Installer

:: Set default color to light green on black
color 0A

echo.
echo  +------------------------------------------------------------------------+
echo  ^|                                                                        ^|
echo  ^|                  AutoSig Local Bridge Installer v1.0                   ^|
echo  ^|                                                                        ^|
echo  ^|                  Developed by HCX Technologies                       ^|
echo  ^|                                                                        ^|
echo  +------------------------------------------------------------------------+
echo.
echo  This tool will set up the local bridge to connect your MT5 terminal
echo  to the main signal server.
echo.
echo  Press any key to begin the installation...
pause > nul


:: === PHASE 1: ENVIRONMENT SETUP ===
echo.
echo  ==========================================================================
echo  :: [PHASE 1 of 2] Preparing Python Environment
echo  ==========================================================================
echo.

if not exist venv (
    echo   - Python virtual environment not found. Creating one now...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo   - ERROR: Failed to create virtual environment. Is Python installed?
        goto :error
    )
    echo   - Virtual environment created successfully.
) else (
    echo   - Virtual environment already exists.
)
echo.

echo   - Installing required libraries (pywin32). This may take a moment...
call .\venv\Scripts\activate.bat >nul 2>&1
.\venv\Scripts\pip.exe install -r requirements.txt
if %errorlevel% neq 0 (
    echo   - ERROR: Failed to install libraries. Check your internet connection.
    goto :error
)
echo   - Libraries installed successfully.
echo.
echo  --------------------------------------------------------------------------
echo  [PHASE 1 COMPLETE]

echo.


:: === PHASE 2: SHORTCUT CREATION ===
echo  ==========================================================================
echo  :: [PHASE 2 of 2] Creating Windows Startup Shortcut
echo  ==========================================================================
echo.

if not exist .\venv\Scripts\python.exe (
    echo   - ERROR: Cannot find Python in the virtual environment.
    goto :error
)

:: Run the Python script to create the shortcut
.\venv\Scripts\python.exe installer.py
if %errorlevel% neq 0 (
    echo.
    echo   - The shortcut creation script reported an error.
    goto :error
)
echo.
echo  --------------------------------------------------------------------------
echo  [PHASE 2 COMPLETE]

echo.
echo.
echo  +------------------------------------------------------------------------+
echo.  ^|                                                                        ^|
echo.  ^|                      INSTALLATION COMPLETE!                            ^|
echo.  ^|                                                                        ^|
echo.  +------------------------------------------------------------------------+
echo.
echo  The bridge will now start automatically every time you log into Windows.
echo.
echo  To start it for the current session, double-click 'run_background.vbs'.
echo  To check its status at any time, run 'check_status.bat'.
echo.
goto :end


:end
color 07
echo.
echo  Press any key to exit.
pause > nul
goto :eof

:error
color 0C
echo.
echo  +------------------------------------------------------------------------+
echo.  ^|                                                                        ^|
echo.  ^|                       INSTALLATION FAILED                              ^|
echo.  ^|                                                                        ^|
echo.  +------------------------------------------------------------------------+
echo.
echo  Please review the error messages above.
echo.
color 07
echo.
echo  Press any key to exit.
pause > nul

:eof
endlocal