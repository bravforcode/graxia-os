param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\\python.exe"
$requirements = Join-Path $backendDir "requirements.txt"

if (-not (Test-Path $backendDir)) { throw "backend directory not found" }
if (-not (Test-Path $requirements)) { throw "backend requirements.txt not found" }

if (-not (Test-Path $venvPython)) {
  Push-Location $backendDir
  try {
    python -m venv $venvDir
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r $requirements
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

  Push-Location $backendDir
  try {
    & $venvPython -m uvicorn app.main:app --host $HostName --port $Port
  } finally {
    Pop-Location
  }

  Start-Sleep -Seconds 2
}
