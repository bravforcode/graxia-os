# ═══════════════════════════════════════════════════════════════════════════════
# Graxia OS - Docker Network Cleanup
# ล้าง Docker Network ที่ conflict เพื่อให้สามารถสร้างใหม่ได้
# ═══════════════════════════════════════════════════════════════════════════════

[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = "Continue"

function Write-Status($icon, $message, $color = "White") {
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] $icon $message" -ForegroundColor $color
}

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         GRAXIA OS - Docker Network Cleanup Tool                            ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check for conflicting networks
Write-Status ">>>" "Checking for conflicting networks..." "Yellow"

$conflictingNetworks = docker network ls --format "{{.Name}}" | Where-Object {
    $_ -match "graxia" -or $_ -match "172\.20"
}

if ($conflictingNetworks) {
    Write-Status "!!!" "Found conflicting networks:" "Yellow"
    $conflictingNetworks | ForEach-Object { Write-Host "   - $_" -ForegroundColor Gray }

    if (-not $Force) {
        $response = Read-Host "`nRemove these networks? (y/N)"
        if ($response -ne "y" -and $response -ne "Y") {
            Write-Status "❌" "Cleanup cancelled" "Red"
            exit 0
        }
    }

    # Stop all graxia containers first
    Write-Status "|||" "Stopping Graxia containers..." "Yellow"
    $containers = docker ps -q --filter "name=graxia" 2>$null
    if ($containers) {
        docker stop $containers 2>$null | Out-Null
        Write-Status "✔" "Containers stopped" "Green"
    }

    # Remove containers
    Write-Status "xxx" "Removing containers..." "Yellow"
    docker ps -aq --filter "name=graxia" | ForEach-Object { docker rm $_ 2>$null }

    # Remove networks
    Write-Status "xxx" "Removing conflicting networks..." "Yellow"
    foreach ($net in $conflictingNetworks) {
        docker network rm $net 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Status "OK" "Removed: $net" "Green"
        } else {
            Write-Status "ERR" "Failed to remove: $net (may be in use)" "Red"
        }
    }
} else {
    Write-Status "OK" "No conflicting networks found" "Green"
}

# Prune dangling resources
Write-Status "..." "Pruning dangling resources..." "Yellow"
docker system prune -f 2>$null | Out-Null

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║         Cleanup Complete!                                                  ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

Write-Status ">>>" "You can now run: .\graxia.ps1 up" "Cyan"
