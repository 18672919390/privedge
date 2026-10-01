@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [error] Run setup.bat first.
  pause
  exit /b 1
)
if not exist "data\meituan_trd\private_events.csv.gz" (
  echo [error] The data folder is missing. Unzip the data package so that data\meituan_trd, data\olist_brazil
  echo         and data\massive_steps sit inside this folder, then run this script again.
  pause
  exit /b 1
)
if not exist "web\dist\index.html" (
  echo [error] web\dist is missing. Build it once with: cd web ^& npm install ^& npm run build
  pause
  exit /b 1
)
set "PYTHONPATH=%CD%"
echo Starting the PrivEdge console at http://127.0.0.1:8765/  (close this window to stop it)
start "" cmd /c "timeout /t 4 >nul & start "" http://127.0.0.1:8765/"
".venv\Scripts\python.exe" -m uvicorn privedge.server.app:app --port 8765
pause
