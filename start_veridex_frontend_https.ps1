param(
  [string]$WorkingDirectory = "C:\Office-App\office_app\frontend"
)

Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$WorkingDirectory`" && node server.cjs" -WorkingDirectory $WorkingDirectory
