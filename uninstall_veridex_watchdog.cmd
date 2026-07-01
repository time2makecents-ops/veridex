@echo off
setlocal

set TASK_NAME=Veridex Backend Watchdog

echo Removing scheduled task "%TASK_NAME%"...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Unregister-ScheduledTask -TaskName '%TASK_NAME%' -Confirm:$false"
if errorlevel 1 (
  echo Failed to remove scheduled task.
  exit /b 1
)

echo Scheduled task removed.
