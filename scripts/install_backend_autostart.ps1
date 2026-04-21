param(
  [string]$TaskName = "BravOS Backend (Startup)",
  [switch]$OnStart
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $repoRoot "scripts\\start_backend.ps1"
$cmdPath = Join-Path $repoRoot "scripts\\backend_autostart.cmd"

if (-not (Test-Path $scriptPath)) { throw "start_backend.ps1 not found" }
if (-not (Test-Path $cmdPath)) { throw "backend_autostart.cmd not found" }

$schedule = if ($OnStart) { "ONSTART" } else { "ONLOGON" }
$tr = "`"$cmdPath`""
$tn = "`"$TaskName`""
$args = @("/Create", "/F", "/TN", $tn, "/SC", $schedule, "/TR", $tr, "/RL", "LIMITED")
Start-Process -FilePath schtasks -ArgumentList $args -Wait -NoNewWindow | Out-Null
Start-Process -FilePath schtasks -ArgumentList @("/Run", "/TN", $tn) -Wait -NoNewWindow | Out-Null

Write-Output $TaskName
