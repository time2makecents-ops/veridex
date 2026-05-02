@echo off
setlocal
set PORT=8078
set HOST=127.0.0.1
set "PYTHON_CMD=C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\python.exe"
if not exist "%PYTHON_CMD%" set "PYTHON_CMD=python"

cd /d "%~dp0"

echo Using Python:
"%PYTHON_CMD%" --version
if errorlevel 1 (
  echo Failed to run Python command: "%PYTHON_CMD%"
  exit /b 1
)

"%PYTHON_CMD%" -c "import uvicorn" >nul 2>nul
if errorlevel 1 (
  echo.
  echo ERROR: uvicorn is not installed for this Python:
  echo "%PYTHON_CMD%"
  echo.
  echo Install it for this Python, or update run_server.cmd to point at the Python that has uvicorn.
  exit /b 1
)

echo Starting Office App Server on %HOST%:%PORT%...
"%PYTHON_CMD%" -m uvicorn office_app.server.app:app --host %HOST% --port %PORT%
