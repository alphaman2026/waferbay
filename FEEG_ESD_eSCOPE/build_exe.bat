@echo off
rem ============================================================
rem  FEEG_ESD_eSCOPE - build a standalone FEEG_ESD_eSCOPE.exe
rem  Requires Python. Output: dist\FEEG_ESD_eSCOPE.exe
rem  The exe runs on PCs WITHOUT Python installed.
rem ============================================================
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

echo Installing build tools and dependencies...
python -m pip install -q -r requirements.txt pyinstaller
if errorlevel 1 (
    echo [ERROR] Package installation failed.
    pause
    exit /b 1
)

echo Building FEEG_ESD_eSCOPE.exe (this can take a few minutes)...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name FEEG_ESD_eSCOPE FEEG_ESD_eSCOPE.py
if errorlevel 1 (
    echo [ERROR] Build failed. See messages above.
    pause
    exit /b 1
)

echo.
echo Build complete: %~dp0dist\FEEG_ESD_eSCOPE.exe
echo Copy that single file to any PC and double-click to run.
echo (Analog Discovery 2 still needs Digilent WaveForms installed.)
pause
