@echo off
setlocal
set PORT=8078
set HOST=127.0.0.1
set "PYTHON_CMD=python"
where python >nul 2>nul || set "PYTHON_CMD=py -3"

echo Starting Office App Server on %HOST%:%PORT%...
%PYTHON_CMD% -m uvicorn office_app.server.app:app --host %HOST% --port %PORT%
