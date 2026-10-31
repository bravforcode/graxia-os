#Requires -Version 7.0
<#
.SYNOPSIS
Prompts for API keys with hidden input and writes them into .env.production.

.DESCRIPTION
Blank input keeps the current value. An existing KEY= line is replaced, and a
missing key is appended. Values are never printed. Nothing is written unless
every entered value passes the checks. The previous file is backed up to $env:TEMP.

.EXAMPLE
pwsh -File .\scripts\set-env-keys.ps1
#>
[CmdletBinding()]
param(
    [string]$EnvFile = (Join-Path $PSScriptRoot '..\.env.production')
)

# Keys to prompt for. Add or remove entries as needed.
$Keys = @(
    'OPENAI_API_KEY'
    'GEMINI_API_KEY'
    # 'SERPAPI_KEY'
    # 'TELEGRAM_BOT_TOKEN'
    # 'LAYA_API_KEY'
    # 'OBSIDIAN_API_KEY'
)

$ErrorActionPreference = 'Stop'
$EnvFile = (Resolve-Path -LiteralPath $EnvFile).Path

$lines = [System.Collections.Generic.List[string]]::new()
$lines.AddRange([string[]](Get-Content -LiteralPath $EnvFile -Encoding UTF8))

$backup = Join-Path $env:TEMP ('env.production.{0:yyyyMMdd-HHmmss}.bak' -f (Get-Date))
Copy-Item -LiteralPath $EnvFile -Destination $backup
Write-Host "Backup written to $backup (contains secrets; delete it when done)."

$pending = [ordered]@{}
foreach ($key in $Keys) {
    $secure = Read-Host "$key (blank keeps current)" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim()
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    if ($value -eq '') {
        Write-Host "kept    $key"
        continue
    }
    if ($value -match '[\s"''`$#]') {
        throw "$key contains whitespace, a quote, `$, # or a backtick. Nothing was written."
    }
    $pending[$key] = $value
}

foreach ($key in $pending.Keys) {
    $line = "$key=$($pending[$key])"
    $index = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -like "$key=*") { $index = $i; break }
    }
    if ($index -ge 0) { $lines[$index] = $line } else { $lines.Add($line) }
    Write-Host "set     $key"
}

$text = ($lines -join "`n") + "`n"
[System.IO.File]::WriteAllText($EnvFile, $text, [System.Text.UTF8Encoding]::new($false))
Write-Host "Written: $EnvFile"
Write-Host 'Recreate backend, celery and beat so the containers read the new values.'
