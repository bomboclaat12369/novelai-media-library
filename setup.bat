@echo off
setlocal
cd /d "%~dp0"

echo Setting up NovelAI Media Library...
where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python was not found. Install Python 3.11 or newer from python.org,
  echo then run this file again. Make sure the Python Launcher is installed.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto :fail
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo Setup complete.
echo Run run.bat whenever you want to use the NovelAI media viewer.
echo Future launcher and companion runtime updates install automatically from GitHub.
echo.
pause
exit /b 0

:fail
echo.
echo Setup failed. See the error above.
pause
exit /b 1
