$ErrorActionPreference = "Stop"

$name = "AI-Brain-Sync-Obsidian"
$syncScript = Join-Path (Join-Path $env:USERPROFILE ".ai") "sync_obsidian_brain.ps1"

if (!(Test-Path $syncScript)) {
  Write-Host "Missing sync script: $syncScript"
  Write-Host "Run scripts/apply_global_ai_rules.ps1 first."
  exit 1
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
New-Item -Path $runKey -Force | Out-Null

$cmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"& { while(`$true) { try { & `"$syncScript`" | Out-Null } catch {} Start-Sleep -Seconds 300 } }`""
Set-ItemProperty -Path $runKey -Name $name -Value $cmd

Write-Host "Registered brain sync daemon in HKCU Run:"
Write-Host " - $name"
Write-Host "Runs every 5 minutes while logged in."
