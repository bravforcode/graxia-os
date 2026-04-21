$ErrorActionPreference = "Stop"

$settingsPath = Join-Path (Join-Path $env:USERPROFILE ".gemini") "settings.json"
$syncScript = Join-Path (Join-Path $env:USERPROFILE ".ai") "sync_obsidian_brain.ps1"

if (!(Test-Path $settingsPath)) {
  Write-Host "Gemini settings.json not found: $settingsPath"
  exit 0
}

$json = Get-Content -Raw $settingsPath | ConvertFrom-Json
if ($null -eq $json.hooks) { $json | Add-Member -NotePropertyName hooks -NotePropertyValue (@{}) }
if ($null -eq $json.hooks.SessionStart) { $json.hooks.SessionStart = @() }

$cmd = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$syncScript`""
$hookObj = @{
  hooks = @(@{
    type = "command"
    command = $cmd
  })
}

$already = $false
foreach ($block in $json.hooks.SessionStart) {
  foreach ($h in ($block.hooks | ForEach-Object { $_ })) {
    if ($h.type -eq "command" -and ($h.command -like "*sync_obsidian_brain.ps1*")) { $already = $true }
  }
}

if (-not $already) {
  $json.hooks.SessionStart = @($hookObj) + $json.hooks.SessionStart
}

($json | ConvertTo-Json -Depth 10) | Set-Content -Path $settingsPath -Encoding UTF8
Write-Host "Patched Gemini SessionStart hook to run brain sync:"
Write-Host " - $settingsPath"
