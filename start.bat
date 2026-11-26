@echo off
cd /d "%~dp0"

if exist "runtime\pythonw.exe" (
    start "" "runtime\pythonw.exe" launch.py
) else if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" launch.py
) else (
    rem (no Python at all: say so instead of Windows' own "cannot find pythonw")
    where pythonw >nul 2>&1 && (start "" pythonw launch.py) || (start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "scripts\startup_error.ps1")
)