$ErrorActionPreference = "Stop"

$globalDir = Join-Path $env:USERPROFILE ".ai"
New-Item -ItemType Directory -Force -Path $globalDir | Out-Null
$globalRules = Join-Path $globalDir "GLOBAL_RULES.md"

$rules = @'
# Global AI Rules (All Projects / All Sessions)

Use these rules for every request unless the user explicitly overrides them.

## Mandatory Workflow
1. Select and use the best available skill first when relevant.
2. Read Obsidian-synced context before implementing:
   - C:\Users\menum\Documents\ObsidianVault\Second Brain\brain\latest.md
   - Project context under identity/, docs/, and templates/
3. Prefer official APIs and compliant automation.
4. Default to human-in-the-loop for outbound actions:
   - Email outreach
   - Platform submissions
   - External messages
5. If unclear, ask one concise clarification; otherwise execute end-to-end.

## Outbound Safety
- Never claim guaranteed anti-ban for platforms with anti-bot controls.
- Use approved partner APIs/programs where possible.
- Require explicit approval before irreversible/send actions.

## Obsidian Context Policy
- Read only relevant notes first (avoid broad vault crawling).
- Use Obsidian context to drive ICP, segmentation, and templates.
- Keep summaries concise and practical.

## Quality Bar
- Implement, verify, and report with concrete results.
- Prefer robust defaults with fallback paths (especially AI provider fallback).
- Keep configurations global-friendly and reusable across projects.
'@

Set-Content -Path $globalRules -Value $rules -Encoding UTF8

$globalSync = Join-Path $globalDir "sync_obsidian_brain.ps1"
Copy-Item -Force -Path (Join-Path $PSScriptRoot "sync_obsidian_brain.ps1") -Destination $globalSync

$claudeDir = Join-Path $env:USERPROFILE ".claude"
New-Item -ItemType Directory -Force -Path $claudeDir | Out-Null
$claudeFile = Join-Path $claudeDir "CLAUDE.md"
if (!(Test-Path $claudeFile)) {
  Set-Content -Path $claudeFile -Value "# Claude Global Rules`n" -Encoding UTF8
}
$claudeText = Get-Content -Raw $claudeFile
if ($claudeText -notmatch "GLOBAL_RULES\.md") {
  Add-Content -Path $claudeFile -Value "`n## Shared Global Rules`nRead and apply: $globalRules`n"
}

$codexDir = Join-Path $env:USERPROFILE ".codex"
New-Item -ItemType Directory -Force -Path $codexDir | Out-Null
$codexFile = Join-Path $codexDir "AGENTS.md"
if (!(Test-Path $codexFile)) {
  Set-Content -Path $codexFile -Value "# Codex Agent Context`n" -Encoding UTF8
}
$codexText = Get-Content -Raw $codexFile
if ($codexText -notmatch "GLOBAL_RULES\.md") {
  Add-Content -Path $codexFile -Value "`n## Shared Global Rules`nRead and apply: $globalRules`n"
}

$geminiDir = Join-Path $env:USERPROFILE ".gemini"
New-Item -ItemType Directory -Force -Path $geminiDir | Out-Null
$geminiFile = Join-Path $geminiDir "GEMINI.md"
if (!(Test-Path $geminiFile)) {
  Set-Content -Path $geminiFile -Value "# Gemini Global Rules`n" -Encoding UTF8
}
$geminiText = Get-Content -Raw $geminiFile
if ($geminiText -notmatch "GLOBAL_RULES\.md") {
  $prepend = "## Shared Global Rules`nRead and apply: $globalRules`n`n"
  Set-Content -Path $geminiFile -Value ($prepend + $geminiText) -Encoding UTF8
}

Write-Host "Applied global AI rules:"
Write-Host " - $globalRules"
Write-Host " - $claudeFile"
Write-Host " - $codexFile"
Write-Host " - $geminiFile"

Write-Host ""
Write-Host "Syncing Obsidian brain snapshot into Codex/Gemini/Claude global files..."
powershell -ExecutionPolicy Bypass -File $globalSync
