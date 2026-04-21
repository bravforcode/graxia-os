param(
  [string]$TaskName = "OpenClaw Gateway (Startup)",
  [switch]$UseScheduledTask
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$startupDir = Join-Path $env:APPDATA "Microsoft\\Windows\\Start Menu\\Programs\\Startup"
$cmdSource = Join-Path $repoRoot "scripts\\openclaw_autostart.cmd"
$cmdTarget = Join-Path $startupDir "OpenClaw Gateway.cmd"

if (-not (Test-Path $startupDir)) { New-Item -ItemType Directory -Path $startupDir | Out-Null }
Copy-Item -Force $cmdSource $cmdTarget

if ($UseScheduledTask) {
  $action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$repoRoot\\scripts\\start_openclaw_gateway.ps1`""
  schtasks /Create /F /TN $TaskName /SC ONLOGON /TR "$action" /RL LIMITED | Out-Null
}

Write-Output $cmdTarget
