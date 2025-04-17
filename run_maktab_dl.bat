@echo off
echo Maktabkhooneh Downloader Setup
echo =============================

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH
    echo Please install Python and try again
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment and install requirements
echo Activating virtual environment and installing requirements...
call venv\Scripts\activate.bat
pip install -r requirements.txt

REM Run the application
echo Starting Maktabkhooneh Downloader...
python main.py

REM Keep the window open if there's an error
if %errorlevel% neq 0 (
    echo.
    echo An error occurred. Press any key to exit...
    pause
) 