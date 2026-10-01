@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [error] Run setup.bat first.
  pause
  exit /b 1
)
set "PYTHONPATH=%CD%"
".venv\Scripts\python.exe" -m pytest -q
pause
