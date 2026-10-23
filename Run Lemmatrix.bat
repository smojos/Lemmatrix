@echo off
@REM SPDX-License-Identifier: AGPL-3.0-or-later
@REM Copyright (c) 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
rem Starts Lemmatrix on Windows. The first run sets up its own Python 3.13
rem environment in the .venv folder, which takes a few minutes.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up Lemmatrix for the first time. This takes a few minutes...
    py -3.13 -m venv .venv
    if errorlevel 1 (
        echo.
        echo Couldn't find Python 3.13. Install it from python.org, then run this again.
        pause
        exit /b 1
    )
)

rem Install or update the packages whenever requirements.txt has changed.
fc /b requirements.txt ".venv\requirements.installed" >nul 2>&1
if errorlevel 1 (
    echo Installing the packages Lemmatrix needs...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo The packages couldn't be installed. Check the internet connection and try again.
        pause
        exit /b 1
    )
    copy /y requirements.txt ".venv\requirements.installed" >nul
)

".venv\Scripts\python.exe" -m lemmatrix %*
if errorlevel 1 pause
