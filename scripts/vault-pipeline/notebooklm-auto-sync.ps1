# notebooklm-auto-sync.ps1 — Sync NotebookLM library.json to vault
# Reads local MCP library, creates vault notes

param(
    [string]$VaultPath = "C:\Users\menum\Documents\ObsidianVault\Second Brain"
)

$ErrorActionPreference = "Stop"
$outputFolder = Join-Path $VaultPath "03-resources\notebooklm"
$libraryFile = "$env:USERPROFILE\AppData\Local\notebooklm-mcp\Data\library.json"
$logFile = "$env:USERPROFILE\.graxia\notebooklm-auto-sync.log"

New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null

function Write-Log([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts | $msg" | Out-File -FilePath $logFile -Append -Encoding utf8
}

try {
    Write-Log "NOTEBOOKLM SYNC STARTED"

    if (-not (Test-Path $libraryFile)) {
        Write-Log "ERROR: library.json not found at $libraryFile"
        exit 1
    }

    $library = Get-Content $libraryFile -Raw | ConvertFrom-Json
    $notebooks = $library.notebooks
    if (-not $notebooks) { $notebooks = @() }

    $count = 0
    foreach ($nb in $notebooks) {
        $nbId = $nb.id
        $nbName = $nb.name -replace '[\\/:*?"<>|]', '-'
        $nbDir = Join-Path $outputFolder $nbName
        New-Item -ItemType Directory -Force -Path $nbDir | Out-Null

        $sourceList = ""
        if ($nb.sources) {
            $sourceList = ($nb.sources | ForEach-Object { "- $($_.name)" }) -join "`n"
        }

        $indexContent = @"
---
type: notebooklm-notebook
notebook_id: $nbId
name: $($nb.name)
description: $($nb.description)
url: $($nb.url)
synced: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
---

# $($nb.name)

$($nb.description)

## Sources
$sourceList

## Related
- [[03-resources/notebooklm/Index|NotebookLM Index]]
"@
        $indexContent | Out-File -FilePath (Join-Path $nbDir "Index.md") -Encoding utf8 -Force
        $count++
    }

    # Create/update index
    $indexMd = "---
type: notebooklm-index
synced: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
---

# NotebookLM Notebooks

Total: $($notebooks.Count) notebooks

## All Notebooks
$(($notebooks | ForEach-Object { "- [[03-resources/notebooklm/$($_.name -replace '[\\/:*?"<>|]','-')/Index|$($_.name)]]" }) -join "`n")
"
    $indexMd | Out-File -FilePath (Join-Path $outputFolder "Index.md") -Encoding utf8 -Force

    Write-Log "SYNCED: $count notebooks to vault"
} catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    exit 1
}
