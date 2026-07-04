# install-pipeline.ps1 — One-time setup: register vault pipeline as auto-start
# Uses registry Run key (no admin needed)

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$pipelineDir = "C:\Users\menum\graxia os\scripts\vault-pipeline"
$startScript = Join-Path $pipelineDir "start-pipeline.ps1"
$regKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$regName = "GraxiaVaultPipeline"

if ($Uninstall) {
    Remove-ItemProperty -Path $regKey -Name $regName -ErrorAction SilentlyContinue
    Write-Host "Uninstalled: removed from auto-start" -ForegroundColor Green
    return
}

# Register in Run key — starts on login (no admin needed)
$cmd = "pwsh.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startScript`" -Daemon"
Set-ItemProperty -Path $regKey -Name $regName -Value $cmd -Force

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Green
Write-Host "  Vault Pipeline registered for auto-start" -ForegroundColor Green
Write-Host "  ============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Registry: $regKey\$regName" -ForegroundColor Cyan
Write-Host "  Trigger:  On login" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Commands:" -ForegroundColor Gray
Write-Host "    Stop:        .\start-pipeline.ps1 -Stop" -ForegroundColor Gray
Write-Host "    Uninstall:   .\install-pipeline.ps1 -Uninstall" -ForegroundColor Gray
Write-Host "    Status:      .\start-pipeline.ps1 -Status" -ForegroundColor Gray
Write-Host ""

# Start now
Write-Host "  Starting pipeline now..." -ForegroundColor Yellow
Start-Process -FilePath "pwsh" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`"" -WindowStyle Minimized
Start-Sleep -Seconds 2
Write-Host "  Pipeline started!" -ForegroundColor Green
