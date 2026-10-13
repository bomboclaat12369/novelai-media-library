@echo off
setlocal
cd /d "%~dp0"
title Local Duplicate Review
set "PY_CMD="
if exist ".venv\Scripts\python.exe" goto dependencies
call :try_python 3.13
call :try_python 3.12
call :try_python 3.11
call :try_python 3.14
if defined PY_CMD goto create_env
python -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,15)" >nul 2>&1
if not errorlevel 1 set "PY_CMD=python"
if defined PY_CMD goto create_env
echo Python 3.11 through 3.14 is needed to run this tool.
echo Install Python 3.13 for Windows from https://www.python.org/downloads/windows/
echo Include tkinter and the Python launcher during installation.
echo Then double-click this launcher again.
pause
exit /b 1
:create_env
echo Setting up Local Duplicate Review. This is only needed once.
%PY_CMD% -m venv .venv
if errorlevel 1 goto failure
:dependencies
".venv\Scripts\python.exe" -c "import PIL,numpy,cv2; assert PIL.__version__ == '12.3.0' and numpy.__version__ == '2.3.5' and cv2.__version__ == '4.13.0'" >nul 2>&1
if not errorlevel 1 goto launch
echo Installing image libraries. Internet is needed for this first-time setup.
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failure
:launch
set "OPENBLAS_NUM_THREADS=1"
set "OMP_NUM_THREADS=1"
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto failure
exit /b 0
:try_python
if defined PY_CMD exit /b 0
py -%1 -c "import tkinter" >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -%1"
exit /b 0
:failure
echo.
echo The app could not start. The error is shown above.
echo If setup failed, check your internet connection and run this launcher again.
pause
exit /b 1
