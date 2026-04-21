param(
  [string]$HostName = "localhost",
  [int]$Port = 5173
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot "frontend"
$nodeModules = Join-Path $frontendDir "node_modules"

if (-not (Test-Path $frontendDir)) { throw "frontend directory not found" }

$bun = Get-Command bun -ErrorAction SilentlyContinue
if (-not $bun) { throw "bun not found" }

if (-not (Test-Path $nodeModules)) {
  Push-Location $frontendDir
  try {
    & $bun.Source install
  } finally {
    Pop-Location
  }
}

while ($true) {
  $existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($existing) {
    Start-Sleep -Seconds 10
    continue
  }

  Push-Location $frontendDir
  try {
    & $bun.Source run dev --host $HostName --port $Port
  } finally {
    Pop-Location
  }

  Start-Sleep -Seconds 2
}
