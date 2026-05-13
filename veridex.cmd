@echo off
setlocal
set "ROOT=%~dp0"

if /I "%~1"=="groqtest" (
  shift
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%veridex.ps1" -Action start -GroqFallbackTest
  goto :eof
)

if not "%~1"=="" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%veridex.ps1" %*
  goto :eof
)

title Veridex Backend
echo Stopping existing Veridex ports...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%veridex.ps1" stop

echo.
echo Starting Veridex frontend...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%start_veridex_frontend_https.ps1"

echo.
echo Starting Veridex backend on 127.0.0.1:8078...
call "%ROOT%run_server.cmd"

echo.
echo Veridex backend stopped or failed.
pause
