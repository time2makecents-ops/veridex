param(
  [string]$WorkingDirectory = "C:\Office-App\office_app\frontend",
  [string]$LogRoot = "C:\Office-App"
)

Start-Process `
  -FilePath "cmd.exe" `
  -ArgumentList "/c", 'start "Veridex Frontend" cmd /k node server.cjs' `
  -WorkingDirectory $WorkingDirectory | Out-Null
