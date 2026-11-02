@echo off
REM Builds a standalone SysTuklas.exe (optional). Requires: pip install pyinstaller
cd /d "%~dp0"
pyinstaller --noconsole --onefile --name SysTuklas --collect-all customtkinter main.py
echo.
echo Done. The executable is in the "dist" folder.
pause
