# vault-watcher.ps1 — FileSystemWatcher for Obsidian vault
# Monitors vault for changes and triggers sync events

param(
    [string]$VaultPath = "C:\Users\menum\Documents\ObsidianVault\Second Brain",
    [string]$TriggerDir = "$env:USERPROFILE\.graxia",
    [int]$DebounceMs = 2000
)

$ErrorActionPreference = "Continue"

# Ensure trigger dir exists
New-Item -ItemType Directory -Force -Path $TriggerDir | Out-Null

$triggerFile = Join-Path $TriggerDir ".sync-trigger"
$logFile = Join-Path $TriggerDir "vault-watcher.log"

function Write-Log([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts | $msg" | Out-File -FilePath $logFile -Append -Encoding utf8
    Write-Host "[$ts] $msg"
}

# Debounce timer
$script:lastEvent = [datetime]::MinValue
$script:pendingChanges = [System.Collections.Generic.List[string]]::new()

function On-Changed($source, $e) {
    $now = Get-Date
    $elapsed = ($now - $script:lastEvent).TotalMilliseconds

    if ($elapsed -lt $DebounceMs) {
        # Still debouncing — accumulate changes
        $script:pendingChanges.Add($e.FullPath)
        return
    }

    # Process accumulated changes
    $changes = $script:pendingChanges.ToArray()
    $script:pendingChanges.Clear()
    $script:pendingChanges.Add($e.FullPath)
    $script:lastEvent = $now

    # Skip hidden/system files, .obsidian internal
    $relPath = $e.FullPath.Replace($VaultPath, "").TrimStart("\", "/")
    if ($relPath -match "^\.(obsidian|git|openhuman|smart-env|claude|cursor|windsurf|github)") {
        return
    }
    if ($relPath -match "\.(pyc|pyo|db|sqlite)$") {
        return
    }

    Write-Log "CHANGE: $($e.ChangeType) -> $relPath"

    # Write trigger file for sync daemon
    $payload = @{
        timestamp = $now.ToString("o")
        change_type = $e.ChangeType.ToString()
        file = $relPath
        vault_path = $VaultPath
    } | ConvertTo-Json -Compress

    [System.IO.File]::WriteAllText($triggerFile, $payload, [System.Text.Encoding]::UTF8)
}

# Set up watchers
$watchers = @()

# Watch markdown files
$mdWatcher = New-Object System.IO.FileSystemWatcher
$mdWatcher.Path = $VaultPath
$mdWatcher.Filter = "*.md"
$mdWatcher.IncludeSubdirectories = $true
$mdWatcher.NotifyFilter = [System.IO.NotifyFilters]::LastWrite -bor [System.IO.NotifyFilters]::FileName -bor [System.IO.NotifyFilters]::Size
$mdWatcher.EnableRaisingEvents = $false

Register-ObjectEvent $mdWatcher "Changed" -Action { On-Changed $source $e }
Register-ObjectEvent $mdWatcher "Created" -Action { On-Changed $source $e }
Register-ObjectEvent $mdWatcher "Deleted" -Action { On-Changed $source $e }
Register-ObjectEvent $mdWatcher "Renamed" -Action { On-Changed $source $e }

$watchers += $mdWatcher

# Watch JSON files (graph data, configs)
$jsonWatcher = New-Object System.IO.FileSystemWatcher
$jsonWatcher.Path = $VaultPath
$jsonWatcher.Filter = "*.json"
$jsonWatcher.IncludeSubdirectories = $true
$jsonWatcher.NotifyFilter = [System.IO.NotifyFilters]::LastWrite
$jsonWatcher.EnableRaisingEvents = $false

Register-ObjectEvent $jsonWatcher "Changed" -Action { On-Changed $source $e }

$watchers += $jsonWatcher

# Enable all watchers
foreach ($w in $watchers) {
    $w.EnableRaisingEvents = $true
}

Write-Log "STARTED | Watching: $VaultPath | Debounce: ${DebounceMs}ms"
Write-Log "Filters: *.md, *.json | Subdirs: true"

# Keep alive
try {
    while ($true) {
        Start-Sleep -Seconds 5

        # Heartbeat every 60s
        $min = (Get-Date).Minute
        if ($min -eq 0 -and (Get-Date).Second -lt 5) {
            $fileCount = (Get-ChildItem -Path $VaultPath -Filter "*.md" -Recurse -File).Count
            Write-Log "HEARTBEAT | Vault: $fileCount md files"
        }
    }
} finally {
    foreach ($w in $watchers) {
        $w.EnableRaisingEvents = $false
        $w.Dispose()
    }
    Write-Log "STOPPED"
}
