@echo off
echo.
echo [MT5 Trade Server Runner]
echo.
echo This script will install dependencies and run the trading server.
echo Make sure you have filled in your account details in config.ini first.
echo.

set VENV_DIR=.\venv

if not exist %VENV_DIR%\Scripts\activate (
    echo [INFO] Virtual environment not found. Creating one now...
    python -m venv %VENV_DIR%
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment. Please ensure Python is installed and in your PATH.
        pause
        exit /b
    )
    echo [INFO] Virtual environment created successfully.
)

echo.
echo --- Activating virtual environment ---
call %VENV_DIR%\Scripts\activate

echo.
echo --- Installing dependencies from requirements.txt ---
pip install -r requirements.txt

echo.
echo --- Starting Trade Server ---
echo Press Ctrl+C to stop the server.
echo.

python trade_server.py

echo.
echo --- Server stopped ---
pause

