@echo off
echo.
echo --- DEBUG MODE --- 
echo This script will run the bridge in a visible window to show any errors.
echo.

if not exist venv\Scripts\python.exe (
    echo ERROR: Virtual environment not found. Please run 'install.bat' first.
    pause
    exit /b 1
)

:: Activate the virtual environment and run the python script
call .\venv\Scripts\activate.bat
python bridge.py

echo.
echo --- Script finished or crashed. ---
_pause
