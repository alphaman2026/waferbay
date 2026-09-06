@echo off
rem ============================================================
rem  FEEG_ESD_eSCOPE - one-click launcher for Windows
rem  1) Checks that Python is installed
rem  2) Installs required packages (first run only)
rem  3) Starts the program
rem ============================================================
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Install Python 3.9+ from https://www.python.org/downloads/
    echo         and check "Add Python to PATH" during setup.
    pause
    exit /b 1
)

echo Checking required packages (pyserial, matplotlib)...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed. Check your network connection.
    pause
    exit /b 1
)

echo Starting FEEG_ESD_eSCOPE...
start "" pythonw FEEG_ESD_eSCOPE.py
exit /b 0
