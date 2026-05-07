#!/usr/bin/env pwsh
# Cleanup unused scripts that consume RAM/CPU
# Moves unused scripts to 04-Archive/Scripts-Unused/

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$archiveDir = Join-Path $root "04-Archive\Scripts-Unused"

# Scripts to KEEP (used frequently)
$keepScripts = @(
    "start.ps1",                    # Main start script
    "start.sh",                     # Linux/mac start
    "dev.ps1",                      # Dev mode
    "install-autostart.ps1",        # Auto-start installer
    "verify.ps1",                   # Verification
    "verify-chaos.ps1"              # Chaos testing
)

# Scripts in scripts/ folder to KEEP
$keepInScripts = @(
    "graxia-daemon.ps1",            # New daemon
    "cleanup-unused.ps1",           # This script
    "setup.ps1"                     # Initial setup
)

# Scripts to REMOVE (unused/redundant)
$removeScripts = @(
    # Old autostart scripts (replaced by graxia-daemon)
    "install_all_startup.ps1",
    "install_backend_autostart.ps1", 
    "install_frontend_startup.ps1",
    "install_openclaw_autostart.ps1",
    "register_brain_sync_daemon.ps1",
    "register_brain_sync_task.ps1",
    
    # Old start scripts (replaced by start.ps1)
    "start_all.ps1",
    "start_backend.ps1",
    "start_frontend.ps1",
    "start_openclaw_gateway.ps1",
    "start-staging-api.ps1",
    
    # Old deploy scripts (use GitHub Actions instead)
    "deploy-staging.ps1",
    "deploy-staging-local.ps1",
    "quick-staging.ps1",
    
    # Unused utility scripts
    "apply_global_ai_rules.ps1",
    "configure_all_ides_obsidian.ps1",
    "setup_global_obsidian_env.ps1",
    "setup-skill-symlinks.ps1",
    "patch_gemini_settings.ps1",
    "rename_folder.ps1",
    "sync_obsidian_brain.ps1",
    "run-chaos-tests.ps1",
    
    # MCP (if not used)
    "mcp\run-testsprite-mcp.ps1"
)

Write-Host "Cleaning up unused scripts..." -ForegroundColor Cyan
Write-Host "Archive: $archiveDir" -ForegroundColor Gray

# Create archive directory
$null = New-Item -ItemType Directory -Force -Path $archiveDir

$moved = 0
foreach ($script in $removeScripts) {
    $source = Join-Path $root $script
    $dest = Join-Path $archiveDir (Split-Path $script -Leaf)
    
    if (Test-Path $source) {
        Move-Item $source $dest -Force
        Write-Host "  Archived: $script" -ForegroundColor Yellow
        $moved++
    }
}

# Also cleanup old .cmd files
$oldCmdFiles = @(
    "scripts\backend_autostart.cmd",
    "scripts\bravos_autostart.cmd", 
    "scripts\frontend_autostart.cmd",
    "scripts\openclaw_autostart.cmd"
)

foreach ($cmd in $oldCmdFiles) {
    $path = Join-Path $root $cmd
    if (Test-Path $path) {
        $dest = Join-Path $archiveDir (Split-Path $cmd -Leaf)
        Move-Item $path $dest -Force
        Write-Host "  Archived: $cmd" -ForegroundColor Yellow
        $moved++
    }
}

Write-Host ""
Write-Host "✅ Cleanup complete! Archived $moved files." -ForegroundColor Green
Write-Host "Scripts kept:" -ForegroundColor Gray
$keepScripts | ForEach-Object { Write-Host "  ✓ $_" -ForegroundColor DarkGray }
Write-Host ""
Write-Host "If something breaks, restore from: $archiveDir" -ForegroundColor DarkGray
