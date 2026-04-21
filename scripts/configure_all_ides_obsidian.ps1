$ErrorActionPreference = "Stop"

$targets = @(
  "$env:APPDATA\\Code\\User\\settings.json",
  "$env:APPDATA\\Trae\\User\\settings.json",
  "$env:APPDATA\\Cursor\\User\\settings.json",
  "$env:APPDATA\\Windsurf\\User\\settings.json",
  "$env:APPDATA\\Antigravity\\User\\settings.json",
  "$env:APPDATA\\Kiro\\User\\settings.json"
)

function Update-Settings([string]$path) {
  if (!(Test-Path $path)) { return }
  $raw = Get-Content -Raw $path
  $isJsonc = $raw -match "^\s*//" -or $raw -match "\s//"
  if ($isJsonc) {
    if ($raw -notmatch "claudeCode\.preferredLocation") {
      $raw = $raw -replace "\}\s*$", "  `"claudeCode.preferredLocation`": `"panel`",`n}"
    }
    if ($raw -notmatch "claudeCode\.selectedModel") {
      $raw = $raw -replace "\}\s*$", "  `"claudeCode.selectedModel`": `"haiku`",`n}"
    }
    if ($raw -notmatch "AI\.rules\.importClaudeMd") {
      $raw = $raw -replace "\}\s*$", "  `"AI.rules.importClaudeMd`": true,`n}"
    }
    Set-Content -Path $path -Value $raw -Encoding UTF8
    Write-Host "Updated (jsonc): $path"
    return
  }

  try { $obj = $raw | ConvertFrom-Json } catch { return }

  if ($null -eq $obj) { $obj = @{} }
  if ($obj.PSObject.Properties.Match("claudeCode.preferredLocation").Count -eq 0) {
    $obj | Add-Member -NotePropertyName "claudeCode.preferredLocation" -NotePropertyValue "panel"
  } else {
    $obj."claudeCode.preferredLocation" = "panel"
  }
  if ($obj.PSObject.Properties.Match("claudeCode.selectedModel").Count -eq 0) {
    $obj | Add-Member -NotePropertyName "claudeCode.selectedModel" -NotePropertyValue "haiku"
  }
  if ($obj.PSObject.Properties.Match("AI.rules.importClaudeMd").Count -eq 0) {
    $obj | Add-Member -NotePropertyName "AI.rules.importClaudeMd" -NotePropertyValue $true
  } else {
    $obj."AI.rules.importClaudeMd" = $true
  }

  ($obj | ConvertTo-Json -Depth 20) | Set-Content -Path $path -Encoding UTF8
  Write-Host "Updated: $path"
}

foreach ($t in $targets) { Update-Settings $t }

Write-Host "Done. If an IDE uses Claude Code extension, it will now load ~/.claude/CLAUDE.md (with Obsidian brain snapshot)."
