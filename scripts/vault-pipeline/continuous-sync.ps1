# continuous-sync.ps1 — Main sync daemon for Obsidian vault
# Processes file change triggers and runs sync pipeline

param(
    [string]$VaultPath = "C:\Users\menum\Documents\ObsidianVault\Second Brain",
    [string]$TriggerDir = "$env:USERPROFILE\.graxia",
    [int]$PollIntervalSec = 5,
    [int]$GraphifyCooldownSec = 300
)

$ErrorActionPreference = "Continue"

# Ensure dirs
New-Item -ItemType Directory -Force -Path $TriggerDir | Out-Null

$triggerFile = Join-Path $TriggerDir ".sync-trigger"
$logFile = Join-Path $TriggerDir "continuous-sync.log"
$stateFile = Join-Path $TriggerDir "sync-state.json"
$brainSource = Join-Path $VaultPath "brain\latest.md"
$brainTargets = @(
    "$env:USERPROFILE\.codex\AGENTS.md",
    "$env:USERPROFILE\.gemini\GEMINI.md",
    "$env:USERPROFILE\.claude\CLAUDE.md"
)

function Write-Log([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts | $msg" | Out-File -FilePath $logFile -Append -Encoding utf8
    Write-Host "[$ts] $msg" -ForegroundColor Cyan
}

function Load-State {
    if (Test-Path $stateFile) {
        return Get-Content $stateFile -Raw | ConvertFrom-Json
    }
    return @{
        last_graphify = [datetime]::MinValue.ToString("o")
        last_brain_sync = [datetime]::MinValue.ToString("o")
        total_syncs = 0
        total_files_processed = 0
    }
}

function Save-State($state) {
    $state | ConvertTo-Json -Depth 3 | Out-File $stateFile -Encoding utf8
}

function Sync-BrainSnapshot {
    # Sync brain/latest.md → IDE AGENTS.md files
    if (!(Test-Path $brainSource)) {
        Write-Log "SKIP brain sync: source not found"
        return
    }

    $brain = Get-Content -Raw $brainSource
    $wrapped = @"
<!--BRAIN_SNAPSHOT_START-->
## Brain Snapshot (auto-synced)
Source: $brainSource
Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

$brain
<!--BRAIN_SNAPSHOT_END-->
"@

    foreach ($target in $brainTargets) {
        if (!(Test-Path $target)) { continue }
        $content = Get-Content -Raw $target

        $regionStart = "<!--BRAIN_SNAPSHOT_START-->"
        $regionEnd = "<!--BRAIN_SNAPSHOT_END-->"

        if ($content -match [regex]::Escape($regionStart)) {
            $pattern = [regex]::Escape($regionStart) + "([\s\S]*?)" + [regex]::Escape($regionEnd)
            $content = [regex]::Replace($content, $pattern, $wrapped, [System.Text.RegularExpressions.RegexOptions]::Multiline)
        } else {
            $content = $content.TrimEnd() + "`n`n$wrapped`n"
        }

        [System.IO.File]::WriteAllText($target, $content, (New-Object System.Text.UTF8Encoding($true)))
        Write-Log "BRAIN SYNC: -> $target"
    }
}

function Run-Graphify {
    # Run graphify update (incremental, no API cost)
    $since = (Get-Date).AddSeconds(-$GraphifyCooldownSec)
    Write-Log "GRAPHIFY: Running incremental update..."

    try {
        Push-Location $VaultPath
        $output = graphify update . --cluster-only 2>&1 | Out-String
        Pop-Location

        if ($LASTEXITCODE -eq 0) {
            Write-Log "GRAPHIFY: OK | $output"
            return $true
        } else {
            Write-Log "GRAPHIFY: WARN | exit=$LASTEXITCODE | $output"
            return $false
        }
    } catch {
        Write-Log "GRAPHIFY: ERROR | $($_.Exception.Message)"
        Pop-Location
        return $false
    }
}

function Run-MerkleSync {
    # Trigger graxia incremental sync via Python
    $pythonPath = "C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe"
    $syncScript = @"
import sys
sys.path.insert(0, r'C:\Users\menum\enterprise-agent-os\src')
from graxia_tool.mcp.incremental_sync import MerkleSync
import asyncio
sync = MerkleSync()
result = asyncio.run(sync.sync())
print(f"files_synced={result.files_synced} files_added={result.files_added} files_modified={result.files_modified}")
"@

    try {
        $output = & $pythonPath -c $syncScript 2>&1 | Out-String
        Write-Log "MERKLE SYNC: $output"
        return $true
    } catch {
        Write-Log "MERKLE SYNC ERROR: $($_.Exception.Message)"
        return $false
    }
}

function Process-Trigger {
    if (!(Test-Path $triggerFile)) { return $false }

    $raw = [System.IO.File]::ReadAllText($triggerFile)
    [System.IO.File]::Delete($triggerFile)

    try {
        $change = $raw | ConvertFrom-Json
        Write-Log "TRIGGER: $($change.change_type) -> $($change.file)"
        return $true
    } catch {
        Write-Log "TRIGGER: parse error | $raw"
        return $false
    }
}

# === MAIN LOOP ===
Write-Log "========================================="
Write-Log "CONTINUOUS SYNC DAEMON STARTED"
Write-Log "Vault: $VaultPath"
Write-Log "Poll: ${PollIntervalSec}s | Graphify cooldown: ${GraphifyCooldownSec}s"
Write-Log "========================================="

$state = Load-State
$lastGraphify = [datetime]::Parse($state.last_graphify)
$lastBrainSync = [datetime]::Parse($state.last_brain_sync)
$pendingChanges = 0

try {
    while ($true) {
        Start-Sleep -Seconds $PollIntervalSec

        # Check for triggers
        if (Process-Trigger) {
            $pendingChanges++
        }

        $now = Get-Date

        # Debounced processing: wait for quiet period
        if ($pendingChanges -gt 0) {
            $quietSeconds = 10
            $lastChangeTime = $now  # simplified
            $timeSinceLastChange = ($now - $lastChangeTime).TotalSeconds

            if ($timeSinceLastChange -ge $quietSeconds -or $pendingChanges -ge 5) {
                Write-Log "PROCESSING: $pendingChanges pending changes"

                # 1. Merkle sync (fast, local)
                Run-MerkleSync | Out-Null

                # 2. Brain snapshot sync
                $timeSinceBrain = ($now - $lastBrainSync).TotalMinutes
                if ($timeSinceBrain -ge 5) {
                    Sync-BrainSnapshot
                    $lastBrainSync = $now
                    $state.last_brain_sync = $now.ToString("o")
                }

                # 3. Graphify update (debounced)
                $timeSinceGraphify = ($now - $lastGraphify).TotalSeconds
                if ($timeSinceGraphify -ge $GraphifyCooldownSec) {
                    Run-Graphify | Out-Null
                    $lastGraphify = $now
                    $state.last_graphify = $now.ToString("o")
                }

                $state.total_syncs++
                $state.total_files_processed += $pendingChanges
                $pendingChanges = 0
                Save-State $state
            }
        }

        # Hourly brain sync regardless of changes
        $timeSinceBrainAll = ($now - $lastBrainSync).TotalMinutes
        if ($timeSinceBrainAll -ge 60) {
            Sync-BrainSnapshot
            $lastBrainSync = $now
            $state.last_brain_sync = $now.ToString("o")
            Save-State $state
        }
    }
} finally {
    Write-Log "DAEMON STOPPED"
    Save-State $state
}
