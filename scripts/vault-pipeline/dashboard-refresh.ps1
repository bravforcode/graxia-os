# dashboard-refresh.ps1 — Auto-refresh vault dashboard
# Runs after sync to update dashboard.md with fresh stats

param(
    [string]$VaultPath = "C:/Users/menum/Documents/ObsidianVault/Second Brain"
)

$ErrorActionPreference = "Continue"

function Get-VaultStats {
    $vaultDir = [System.IO.DirectoryInfo]::new($VaultPath)
    if (-not $vaultDir.Exists) {
        return @{
            TotalNotes = 0; PARA = @{}; Skills = 0; MOCs = 0; Templates = 0; Agents = 0
            LastModified = "N/A"; TotalSizeMB = 0
        }
    }
    $mdFiles = @($vaultDir.GetFiles("*.md", [System.IO.SearchOption]::AllDirectories))
    $totalNotes = $mdFiles.Count

    # Count by PARA folder
    $inbox = 0; $projects = 0; $areas = 0; $resources = 0; $archive = 0; $people = 0; $meetings = 0; $daily = 0
    $skillsCount = 0; $mocsCount = 0; $templatesCount = 0; $agentsCount = 0
    foreach ($f in $mdFiles) {
        $fp = $f.FullName
        if ($fp -match "00-Inbox") { $inbox++ }
        elseif ($fp -match "01-projects") { $projects++ }
        elseif ($fp -match "02-areas") { $areas++ }
        elseif ($fp -match "03-resources") { $resources++ }
        elseif ($fp -match "04-archive") { $archive++ }
        elseif ($fp -match "05-People") { $people++ }
        elseif ($fp -match "06-Meetings") { $meetings++ }
        elseif ($fp -match "07-Daily") { $daily++ }
        if ($fp -match "\\skills\\" -or $fp -match "\\brain\\skills") { $skillsCount++ }
        if ($fp -match "\\moc\\") { $mocsCount++ }
        if ($fp -match "\\templates\\") { $templatesCount++ }
        if ($fp -match "\\.claude\\agents") { $agentsCount++ }
    }
    $para = @{
        Inbox = $inbox; Projects = $projects; Areas = $areas; Resources = $resources
        Archive = $archive; People = $people; Meetings = $meetings; Daily = $daily
    }
    $skills = $skillsCount
    $mocs = $mocsCount
    $templates = $templatesCount
    $agents = $agentsCount

    # Last modified
    $lastModFile = $mdFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $lastModStr = if ($lastModFile) { $lastModFile.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss") } else { "N/A" }

    # Total size
    $totalSize = 0
    foreach ($f in $mdFiles) { $totalSize += $f.Length }
    $totalSizeMB = [math]::Round($totalSize / 1MB, 2)

    $result = @{
        TotalNotes = $totalNotes
        PARA = $para
        Skills = $skills
        MOCs = $mocs
        Templates = $templates
        Agents = $agents
        LastModified = $lastModStr
        TotalSizeMB = $totalSizeMB
    }
    return $result
}

function Get-GraphStats {
    $graphFile = Join-Path $VaultPath "graphify-out\graph.json"
    if (!(Test-Path -LiteralPath $graphFile)) {
        return @{ Nodes = 0; Edges = 0; Communities = 0 }
    }

    try {
        $graph = Get-Content $graphFile -Raw | ConvertFrom-Json
        return @{
            Nodes = $graph.nodes.Count
            Edges = $graph.edges.Count
            Communities = ($graph.nodes | Where-Object { $_.community } | Group-Object community).Count
        }
    } catch {
        return @{ Nodes = 0; Edges = 0; Communities = 0 }
    }
}

function Get-SyncStatus {
    $stateFile = "$env:USERPROFILE\.graxia\sync-state.json"
    if (!(Test-Path $stateFile)) {
        return @{ LastSync = "never"; TotalSyncs = 0 }
    }

    $state = Get-Content $stateFile -Raw | ConvertFrom-Json
    return @{
        LastSync = $state.last_graphify
        TotalSyncs = $state.total_syncs
        TotalFilesProcessed = $state.total_files_processed
    }
}

function Get-MCPServers {
    $configFile = "$env:USERPROFILE\.config\opencode\opencode.json"
    if (!(Test-Path $configFile)) { return @() }

    $config = Get-Content $configFile -Raw | ConvertFrom-Json
    $servers = @()

    foreach ($prop in $config.mcp.PSObject.Properties) {
        $servers += @{
            Name = $prop.Name
            Enabled = $prop.Value.enabled
        }
    }
    return $servers
}

# === MAIN ===
Write-Host "`n  Vault Dashboard Refresh" -ForegroundColor Cyan
Write-Host "  ========================" -ForegroundColor Cyan

$stats = Get-VaultStats
$graph = Get-GraphStats
$sync = Get-SyncStatus
$mcpServers = Get-MCPServers

$dashboard = @"
---
type: dashboard
auto_generated: true
last_refresh: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
---

# Dashboard

## Vault Overview

| Metric | Value |
|--------|-------|
| Total Notes | $($stats.TotalNotes) |
| Total Size | $($stats.TotalSizeMB) MB |
| Last Modified | $($stats.LastModified) |
| MOCs | $($stats.MOCs) |
| Skills | $($stats.Skills) |
| Templates | $($stats.Templates) |
| Agents | $($stats.Agents) |

## PARA Structure

| Folder | Notes |
|--------|-------|
| 00-Inbox | $($stats.PARA.Inbox) |
| 01-Projects | $($stats.PARA.Projects) |
| 02-Areas | $($stats.PARA.Areas) |
| 03-Resources | $($stats.PARA.Resources) |
| 04-Archive | $($stats.PARA.Archive) |
| 05-People | $($stats.PARA.People) |
| 06-Meetings | $($stats.PARA.Meetings) |
| 07-Daily | $($stats.PARA.Daily) |

## Knowledge Graph

| Metric | Value |
|--------|-------|
| Nodes | $($graph.Nodes) |
| Edges | $($graph.Edges) |
| Communities | $($graph.Communities) |

## Sync Status

| Metric | Value |
|--------|-------|
| Last Sync | $($sync.LastSync) |
| Total Syncs | $($sync.TotalSyncs) |
| Files Processed | $($sync.TotalFilesProcessed) |

## MCP Servers

| Server | Status |
|--------|--------|
$(($mcpServers | ForEach-Object { "| $($_.Name) | $(if($_.Enabled){'✅ ON'}else{'❌ OFF'}) |" }) -join "`n")

## Quick Navigation

- [[moc/MOC-root|Master Index]]
- [[00-Inbox/Index|Inbox]]
- [[01-projects/Index|Projects]]
- [[brain/skills-universal/Master_Skills_Hub|Skills Hub]]

## System Health

- Last refresh: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss UTC")
- Pipeline: vault-watcher → continuous-sync → dashboard-refresh
- Graphify: auto-update every 5 min
- Brain snapshot: auto-sync every hour

---
*Auto-generated by vault-pipeline*
"@

$dashboardPath = Join-Path $VaultPath "dashboard.md"
$dashboard | Out-File -FilePath $dashboardPath -Encoding utf8 -Force

Write-Host "`n  Dashboard refreshed!" -ForegroundColor Green
Write-Host "  Notes: $($stats.TotalNotes) | Size: $($stats.TotalSizeMB) MB" -ForegroundColor Yellow
Write-Host "  Graph: $($graph.Nodes) nodes, $($graph.Edges) edges" -ForegroundColor Yellow
Write-Host "  Saved: $dashboardPath" -ForegroundColor Gray
