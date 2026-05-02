@echo off
setlocal
set PORT=8078
set HOST=127.0.0.1
set "PYTHON_CMD=C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\python.exe"
if not exist "%PYTHON_CMD%" set "PYTHON_CMD=python"

echo Starting Office App Server on %HOST%:%PORT%...
"%PYTHON_CMD%" -m uvicorn office_app.server.app:app --host %HOST% --port %PORT%
