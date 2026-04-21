$ErrorActionPreference = "Stop"

$taskName = "AI-Brain-Sync-Obsidian"
$syncScript = Join-Path (Join-Path $env:USERPROFILE ".ai") "sync_obsidian_brain.ps1"

if (!(Test-Path $syncScript)) {
  Write-Host "Missing sync script: $syncScript"
  Write-Host "Run scripts/apply_global_ai_rules.ps1 first."
  exit 1
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$syncScript`""
$trigger1 = New-ScheduledTaskTrigger -AtLogOn
$trigger2 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

try {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
} catch {}

try {
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($trigger1, $trigger2) -Principal $principal -Settings $settings | Out-Null
  Write-Host "Registered scheduled task: $taskName"
  Write-Host "Runs: $syncScript"
  exit 0
} catch {
  Write-Host "Scheduled task creation failed; falling back to HKCU Run key."
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$syncScript`""
New-Item -Path $runKey -Force | Out-Null
Set-ItemProperty -Path $runKey -Name $taskName -Value $cmd

Write-Host "Registered Run key: $taskName"
Write-Host "Runs: $cmd"
