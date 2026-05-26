@echo off
setlocal
set PORT=8078
set HOST=127.0.0.1
set "PYTHON_CMD=C:\Users\redca\AppData\Local\Programs\Python\Python313\python.exe"

cd /d "%~dp0"

if not exist "%PYTHON_CMD%" set "PYTHON_CMD=py -3.13"

echo Using Python:
%PYTHON_CMD% --version
if errorlevel 1 (
  echo Failed to run Python launcher: %PYTHON_CMD%
  echo Falling back to python on PATH...
  set "PYTHON_CMD=python"
  python --version
  if errorlevel 1 (
    echo Failed to run Python. Install Python 3.13 or reopen PowerShell after installation.
    exit /b 1
  )
)

%PYTHON_CMD% -c "import uvicorn" >nul 2>nul
if errorlevel 1 (
  echo.
  echo ERROR: uvicorn is not installed for this Python.
  echo Run:
  echo   py -3.13 -m pip install -r requirements.txt
  exit /b 1
)

echo Starting Office App Server on %HOST%:%PORT%...
%PYTHON_CMD% -m uvicorn office_app.server.app:app --host %HOST% --port %PORT%
