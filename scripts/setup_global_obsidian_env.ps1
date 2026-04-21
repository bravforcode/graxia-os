$targetDir = Join-Path $env:USERPROFILE ".config"
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
$envFile = Join-Path $targetDir "obsidian.env"

Write-Host "Paste your Obsidian Local REST API base URL (example: https://127.0.0.1:27124) then press Enter:"
$url = Read-Host
Write-Host "Paste your Obsidian API key then press Enter:"
$key = Read-Host
Write-Host "Does your Obsidian API use a self-signed HTTPS cert? (y/n). If unsure and you use https://127.0.0.1, choose y:"
$ans = Read-Host
$verify = "true"
if ($ans -match "^(y|Y)") { $verify = "false" }

$content = @"
OBSIDIAN_API_URL=$url
OBSIDIAN_API_KEY=$key
OBSIDIAN_API_VERIFY_SSL=$verify
"@

Set-Content -Path $envFile -Value $content -Encoding utf8

Write-Host ""
Write-Host "Saved: $envFile"
Write-Host ""
Write-Host "For ANY project, run:"
Write-Host "  docker compose --env-file `"$envFile`" --env-file .env up -d"
Write-Host ""
Write-Host "For this repo, set in .env (recommended):"
Write-Host "  OBSIDIAN_API_URL=https://host.docker.internal:27124"
Write-Host "  OBSIDIAN_API_KEY=***"
Write-Host "  OBSIDIAN_API_VERIFY_SSL=false (only if self-signed)"
