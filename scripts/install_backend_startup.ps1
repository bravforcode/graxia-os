param(
  [string]$Name = "BravOS Backend.cmd"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$startupDir = Join-Path $env:APPDATA "Microsoft\\Windows\\Start Menu\\Programs\\Startup"
$cmdSource = Join-Path $repoRoot "scripts\\backend_autostart.cmd"
$cmdTarget = Join-Path $startupDir $Name

if (-not (Test-Path $startupDir)) { New-Item -ItemType Directory -Path $startupDir | Out-Null }
Copy-Item -Force $cmdSource $cmdTarget

Write-Output $cmdTarget
