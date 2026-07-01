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

rem The PowerShell controller owns both process trees and readiness checks.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%veridex.ps1" -Action start
