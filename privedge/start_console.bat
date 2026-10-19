@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [error] Run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" check_inputs.py
if errorlevel 1 (
  echo [error] Input verification failed. Restore the complete package before starting.
  pause
  exit /b 1
)
set "PYTHONPATH=%CD%"
echo Starting the PrivEdge console at http://127.0.0.1:8765/  (close this window to stop it)
start "" cmd /c "timeout /t 4 >nul & start "" http://127.0.0.1:8765/"
".venv\Scripts\python.exe" -m uvicorn privedge.server.app:app --host 127.0.0.1 --port 8765
pause
