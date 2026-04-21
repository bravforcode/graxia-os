param(
  [int]$OpenClawPort = 9001,
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

function Test-PortOpen {
  param([string]$HostName, [int]$Port)
  try {
    return (Test-NetConnection $HostName -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded
  } catch {
    return $false
  }
}

function Wait-HttpOk {
  param([string]$Url, [int]$TimeoutSeconds)
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 3
      if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { return $true }
    } catch {
    }
    Start-Sleep -Seconds 1
  }
  return $false
}

function Start-Worker {
  param([string]$ScriptPath)
  $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
  if (-not $pwsh) { $pwsh = Get-Command powershell -ErrorAction SilentlyContinue }
  if (-not $pwsh) { throw "PowerShell not found" }
  Start-Process $pwsh.Source -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-WindowStyle", "Hidden",
    "-File", $ScriptPath
  ) -WindowStyle Hidden | Out-Null
}

$openclawScript = Join-Path $repoRoot "scripts\\start_openclaw_gateway.ps1"
$backendScript = Join-Path $repoRoot "scripts\\start_backend.ps1"
$frontendScript = Join-Path $repoRoot "scripts\\start_frontend.ps1"

if (-not (Test-PortOpen "127.0.0.1" $OpenClawPort)) {
  Start-Worker $openclawScript
  [void](Wait-HttpOk "http://127.0.0.1:$OpenClawPort/health" 120)
}

if (-not (Test-PortOpen "127.0.0.1" $BackendPort)) {
  Start-Worker $backendScript
  [void](Wait-HttpOk "http://127.0.0.1:$BackendPort/health" 180)
}

if (-not (Test-PortOpen "localhost" $FrontendPort)) {
  Start-Worker $frontendScript
  [void](Wait-HttpOk "http://localhost:$FrontendPort/" 180)
}
