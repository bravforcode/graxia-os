# Register GoldBot health check as scheduled task (every 1 hour)
$action = New-ScheduledTaskAction -Execute 'python' `
    -Argument 'graxia\packages\quant_os\gold_bot\health_check.py --auto-restart' `
    -WorkingDirectory 'C:\Users\menum\graxia os'

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) `
    -RepetitionInterval (New-TimeSpan -Hours 1) `
    -RepetitionDuration (New-TimeSpan -Days 7)

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName 'GoldBot-HealthCheck' `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description 'Gold Bot health check - auto restart if dead' -Force

Write-Host 'Scheduled task registered: GoldBot-HealthCheck (every 1 hour)'
