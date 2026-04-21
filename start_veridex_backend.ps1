param(
  [string]$WorkingDirectory = "C:\Office-App"
)

$cmd = Join-Path $WorkingDirectory "run_server.cmd"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "`"$cmd`"" -WorkingDirectory $WorkingDirectory
