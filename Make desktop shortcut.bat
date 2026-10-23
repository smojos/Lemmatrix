@echo off
@REM SPDX-License-Identifier: AGPL-3.0-or-later
@REM Copyright (c) 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
rem Puts a Lemmatrix shortcut, with its icon, on the desktop and in the Start menu.
rem The shortcut starts Lemmatrix without a console window.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Run "Run Lemmatrix.bat" once first, so Lemmatrix is set up. Then run this again.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\make_shortcut.ps1"
if errorlevel 1 (
    echo The shortcut could not be made.
    pause
    exit /b 1
)
echo Done: Lemmatrix is on your desktop and in the Start menu.
pause
