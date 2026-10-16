@echo off
rem Runs Lemmatrix's automated tests. Run "Run Lemmatrix.bat" once first.
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pytest -q
pause
