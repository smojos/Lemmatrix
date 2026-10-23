@echo off
@REM SPDX-License-Identifier: AGPL-3.0-or-later
@REM Copyright (c) 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
rem Runs Lemmatrix's automated tests. Run "Run Lemmatrix.bat" once first.
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pytest -q
pause
