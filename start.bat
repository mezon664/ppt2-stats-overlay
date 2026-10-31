@echo off
rem Starts PPTetrics (recognition server + HUD) without a console window.
rem Uses the bundled Python of the full package (runtime\) when it's there,
rem else a .venv made by hand, else Python on the PATH.
cd /d "%~dp0"
if exist "runtime\pythonw.exe" (
    start "" "runtime\pythonw.exe" launch.py
) else if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" launch.py
) else (
    start "" pythonw launch.py
)
