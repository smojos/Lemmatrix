@echo off
@REM SPDX-License-Identifier: AGPL-3.0-or-later
@REM Copyright (c) 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
rem Runs Lemmatrix's automated tests. Run "Run Lemmatrix.bat" once first.
setlocal
cd /d "%~dp0"
rem The test tools (requirements-dev.txt) are installed the first time, and whenever it changes.
fc /b requirements-dev.txt ".venv\requirements-dev.installed" >nul 2>&1
if errorlevel 1 (
    echo Installing the test tools...
    ".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
    if errorlevel 1 (
        echo.
        echo The test tools couldn't be installed. Check the internet connection and try again.
        pause
        exit /b 1
    )
    copy /y requirements-dev.txt ".venv\requirements-dev.installed" >nul
)

".venv\Scripts\python.exe" -m pytest -q
pause
