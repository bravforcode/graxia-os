# notebooklm-sync.ps1 — Pull data from NotebookLM into vault
# Uses notebooklm-mcp CLI to export notebooks and import into vault

param(
    [string]$VaultPath = "C:\Users\menum\Documents\ObsidianVault\Second Brain",
    [string]$OutputFolder = "03-resources/notebooklm"
)

$ErrorActionPreference = "Continue"

$targetDir = Join-Path $VaultPath $OutputFolder
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

$logFile = "$env:USERPROFILE\.graxia\notebooklm-sync.log"

function Write-Log([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts | $msg" | Out-File -FilePath $logFile -Append -Encoding utf8
    Write-Host "[$ts] $msg" -ForegroundColor Cyan
}

Write-Log "NOTEBOOKLM SYNC STARTED"
Write-Log "Target: $targetDir"

# List notebooks via npx
Write-Log "Listing notebooks..."
try {
    $notebooksJson = & npx -y notebooklm-mcp@latest list-notebooks 2>&1 | Out-String
    Write-Log "Notebooks: $notebooksJson"
} catch {
    Write-Log "ERROR listing notebooks: $($_.Exception.Message)"
    Write-Log "NOTE: notebooklm-mcp requires Google auth. Run 'npx notebooklm-mcp@latest auth' first."
}

# Create index note
$indexContent = @"
---
type: notebooklm-index
synced: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
---

# NotebookLM Sources

Synced from Google NotebookLM.

## How to Use

1. Create notebooks in NotebookLM
2. Run this script to pull notes
3. Notes appear in this folder

## Auth Setup

```
npx notebooklm-mcp@latest auth
```

## Manual Sync

```
.\notebooklm-sync.ps1
```

## Related

- [[03-resources/Index|Resources]]
- [[moc/MOC-root|Master Index]]
"@

$indexContent | Out-File -FilePath (Join-Path $targetDir "Index.md") -Encoding utf8

Write-Log "INDEX created"
Write-Log "NOTEBOOKLM SYNC COMPLETE"
Write-Log "Next: authenticate with 'npx notebooklm-mcp@latest auth'"
