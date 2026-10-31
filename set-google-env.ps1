param(
    [string]$EnvFile = (Join-Path $PSScriptRoot '.env.production')
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Env file not found: $EnvFile"
}

$clientId = (Read-Host 'GOOGLE_CLIENT_ID').Trim()
$clientSecret = [System.Net.NetworkCredential]::new('', (Read-Host 'GOOGLE_CLIENT_SECRET' -AsSecureString)).Password.Trim()
$refreshToken = [System.Net.NetworkCredential]::new('', (Read-Host 'GOOGLE_REFRESH_TOKEN' -AsSecureString)).Password.Trim()
$workspaceEmail = (Read-Host 'GOOGLE_WORKSPACE_EMAIL').Trim()

if ($clientId -notmatch '\.apps\.googleusercontent\.com$') {
    throw 'GOOGLE_CLIENT_ID must end with .apps.googleusercontent.com'
}
if ([string]::IsNullOrWhiteSpace($clientSecret)) {
    throw 'GOOGLE_CLIENT_SECRET is empty'
}
if ($refreshToken -notmatch '^1//') {
    throw 'GOOGLE_REFRESH_TOKEN must start with 1//'
}
if ($workspaceEmail -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
    throw 'GOOGLE_WORKSPACE_EMAIL is not an email address'
}

$backup = "$EnvFile.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
Copy-Item -LiteralPath $EnvFile -Destination $backup

$updates = [ordered]@{
    GOOGLE_CLIENT_ID       = $clientId
    GOOGLE_CLIENT_SECRET   = $clientSecret
    GOOGLE_REFRESH_TOKEN   = $refreshToken
    GOOGLE_WORKSPACE_EMAIL = $workspaceEmail
}

$lines = [System.Collections.Generic.List[string]]::new()
$lines.AddRange([string[]]@(Get-Content -LiteralPath $EnvFile -Encoding UTF8))

$seen = @{}
for ($i = 0; $i -lt $lines.Count; $i++) {
    foreach ($key in $updates.Keys) {
        if ($lines[$i] -match "^\s*$key=") {
            $lines[$i] = "$key=$($updates[$key])"
            $seen[$key] = $true
        }
    }
}
foreach ($key in $updates.Keys) {
    if (-not $seen.ContainsKey($key)) {
        $lines.Add("$key=$($updates[$key])")
    }
}

[System.IO.File]::WriteAllLines($EnvFile, $lines, [System.Text.UTF8Encoding]::new($false))

$clientSecret = $null
$refreshToken = $null

Write-Host "Updated the 4 Google keys in $EnvFile (values not shown)."
Write-Host "Backup of the previous file: $backup"
Write-Host 'Next: tell Claude "keys set" so the backend can be restarted.'
