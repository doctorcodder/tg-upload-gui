@echo on
REM tg-upload GUI Launcher with Console Output
REM Author: doctorcodder

echo ========================================================================
echo tg-upload GUI - Starting with Console Output
echo ========================================================================

REM Check if Python is installed
python --version
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

REM Change to script directory
cd /d "%~dp0"

echo [INFO] Launching tg-upload GUI...
echo [INFO] Working directory: %CD%
echo [INFO] Console will remain open to show all operations
echo ========================================================================

REM Run the application with console visible
python tg-upload-gui.py

REM Keep window open after exit
echo ========================================================================
echo Application closed. Press any key to exit...
pause >nul
