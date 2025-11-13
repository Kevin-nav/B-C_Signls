@echo off
:: This script checks if the local bridge process is running using PowerShell.

echo Checking bridge status...
echo.

:: Use PowerShell to get the process. It's more reliable than wmic or tasklist for this.
:: This command will have an exit code of 0 if it finds the process, and 1 if it doesn't.
powershell -Command "exit (Get-CimInstance Win32_Process -Filter \"Name = 'pythonw.exe' AND CommandLine LIKE '%%bridge.py%%'\" | Measure-Object).Count" > nul 2>&1

:: Check the errorlevel set by PowerShell's exit code.
if %errorlevel% equ 1 (
    color 0A
    echo.
    echo  +----------------------------------------------------+
    echo.  ^|   STATUS: The AutoSig Bridge is ACTIVE and running.  ^|
    echo.  +----------------------------------------------------+
) else (
    color 0C
    echo.
    echo  +------------------------------------------------------+
    echo.  ^|   STATUS: The AutoSig Bridge is NOT RUNNING.         ^|
    echo.  ^|   (You can start it by running run_background.vbs)   ^|
    echo.  +------------------------------------------------------+
)

:: Reset color and pause to see the result
echo.
color 07
pause