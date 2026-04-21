param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 9001
)

$ErrorActionPreference = "Stop"

$cmd = Get-Command openclaw -ErrorAction SilentlyContinue
if (-not $cmd) { $cmd = Get-Command openclaw.cmd -ErrorAction SilentlyContinue }
if (-not $cmd) {
  $candidate = Join-Path $env:USERPROFILE ".openclaw\\openclaw.cmd"
  if (Test-Path $candidate) {
    $cmd = Get-Command $candidate
  }
}

if (-not $cmd) {
  throw "OpenClaw CLI not found"
}

while ($true) {
  $existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($existing) {
    Start-Sleep -Seconds 10
    continue
  }

  & $cmd.Source gateway run --allow-unconfigured --bind loopback --port $Port --auth none --force --verbose
  Start-Sleep -Seconds 2
}
