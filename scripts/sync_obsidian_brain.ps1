$ErrorActionPreference = "Stop"

$vaultBrain = "C:\Users\menum\Documents\ObsidianVault\Second Brain\brain\latest.md"
$globalDir = Join-Path $env:USERPROFILE ".ai"
New-Item -ItemType Directory -Force -Path $globalDir | Out-Null
$snapshotPath = Join-Path $globalDir "BRAIN_SNAPSHOT.md"

if (!(Test-Path $vaultBrain)) {
  Write-Host "Brain file not found: $vaultBrain"
  exit 0
}

$brain = Get-Content -Raw $vaultBrain
[System.IO.File]::WriteAllText($snapshotPath, $brain, (New-Object System.Text.UTF8Encoding($true)))

function Upsert-Region([string]$path, [string]$startMarker, [string]$endMarker, [string]$content) {
  if (!(Test-Path $path)) {
    New-Item -ItemType File -Force -Path $path | Out-Null
  }
  $text = Get-Content -Raw $path
  if ($text -notmatch [regex]::Escape($startMarker)) {
    $text = $text.TrimEnd() + "`n`n$startMarker`n$endMarker`n"
  }
  $pattern = [regex]::Escape($startMarker) + "([\s\S]*?)" + [regex]::Escape($endMarker)
  $replacement = $startMarker + "`n" + $content.TrimEnd() + "`n" + $endMarker
  $updated = [regex]::Replace($text, $pattern, $replacement, [System.Text.RegularExpressions.RegexOptions]::Multiline)
  [System.IO.File]::WriteAllText($path, $updated, (New-Object System.Text.UTF8Encoding($true)))
}

$regionStart = "<!--BRAIN_SNAPSHOT_START-->"
$regionEnd = "<!--BRAIN_SNAPSHOT_END-->"
$wrapped = @"
## Brain Snapshot (auto-synced)
Source: $vaultBrain
Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

$brain
"@

$codexAgents = Join-Path (Join-Path $env:USERPROFILE ".codex") "AGENTS.md"
$geminiRules = Join-Path (Join-Path $env:USERPROFILE ".gemini") "GEMINI.md"
$claudeRules = Join-Path (Join-Path $env:USERPROFILE ".claude") "CLAUDE.md"

Upsert-Region -path $codexAgents -startMarker $regionStart -endMarker $regionEnd -content $wrapped
Upsert-Region -path $geminiRules -startMarker $regionStart -endMarker $regionEnd -content $wrapped
Upsert-Region -path $claudeRules -startMarker $regionStart -endMarker $regionEnd -content $wrapped

Write-Host "Synced brain snapshot:"
Write-Host " - $snapshotPath"
Write-Host "Updated regions:"
Write-Host " - $codexAgents"
Write-Host " - $geminiRules"
Write-Host " - $claudeRules"
