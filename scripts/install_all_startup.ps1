param(
  [string]$Name = "BravOS Autostart.cmd"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$startupDir = Join-Path $env:APPDATA "Microsoft\\Windows\\Start Menu\\Programs\\Startup"
$cmdSource = Join-Path $repoRoot "scripts\\bravos_autostart.cmd"
$cmdTarget = Join-Path $startupDir $Name

if (-not (Test-Path $startupDir)) { New-Item -ItemType Directory -Path $startupDir | Out-Null }
Copy-Item -Force $cmdSource $cmdTarget

$legacy = @(
  (Join-Path $startupDir "OpenClaw Gateway.cmd"),
  (Join-Path $startupDir "BravOS Backend.cmd"),
  (Join-Path $startupDir "BravOS Frontend.cmd")
)

foreach ($p in $legacy) {
  if (Test-Path $p) { Remove-Item -Force $p }
}

Write-Output $cmdTarget
