@echo off
rem Starts PPT2 Stats Overlay (recognition server + HUD) without a console window.
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" launch.py
) else (
    start "" pythonw launch.py
)
