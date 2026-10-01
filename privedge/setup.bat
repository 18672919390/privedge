@echo off
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && py -3.12 -c "import sys" >nul 2>nul && set "PY=py -3.12"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [error] Python 3.12 or newer was not found.
  echo         Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

echo Using %PY%
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv || goto :fail
)
".venv\Scripts\python.exe" -m pip install -r requirements.lock || goto :fail

echo.
echo Setup finished. Next: run_tests.bat, then start_console.bat
pause
exit /b 0

:fail
echo [error] Setup failed. See the messages above.
pause
exit /b 1
