param(
  [string]$WorkingDirectory = "C:\Office-App\office_app\frontend"
)

$nodePath = (Get-Command node -ErrorAction Stop).Source
$command = "cd /d `"$WorkingDirectory`" && `"$nodePath`" server.cjs"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", $command -WorkingDirectory $WorkingDirectory
