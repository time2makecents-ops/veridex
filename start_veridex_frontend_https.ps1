param(
  [string]$WorkingDirectory = "C:\Office-App\office_app\frontend"
)

$nodePath = (Get-Command node -ErrorAction Stop).Source
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "`"$nodePath`" server.cjs" -WorkingDirectory $WorkingDirectory
