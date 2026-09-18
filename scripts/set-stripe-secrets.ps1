[CmdletBinding()]
param(
    [string]$OutputPath = ".env",
    [switch]$AllowLive,
    [switch]$ConfigureRevenueOs,
    [switch]$SetProcessEnvironment
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

function Resolve-EnvPath {
    param([string]$RequestedPath)

    $candidate = if ([System.IO.Path]::IsPathRooted($RequestedPath)) {
        [System.IO.Path]::GetFullPath($RequestedPath)
    }
    else {
        [System.IO.Path]::GetFullPath((Join-Path $repoRoot $RequestedPath))
    }

    $rootPrefix = $repoRoot.TrimEnd("\") + "\"
    if (
        ($candidate -ne $repoRoot) -and
        (-not $candidate.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase))
    ) {
        throw "OutputPath must stay inside the Graxia OS repository."
    }

    $fileName = [System.IO.Path]::GetFileName($candidate)
    if ($fileName -notmatch "^\.env(?:\..*)?$") {
        throw "OutputPath must be an env file such as .env or .env.production."
    }

    return $candidate
}

function Get-ExistingEnvValue {
    param(
        [string[]]$Lines,
        [string]$Name
    )

    $pattern = "^\s*" + [regex]::Escape($Name) + "\s*=(.*)$"
    foreach ($line in @($Lines)) {
        if ($line -match $pattern) {
            $value = $Matches[1].Trim()
            if ($value.Length -ge 2) {
                $isDoubleQuoted = $value.StartsWith('"') -and $value.EndsWith('"')
                $isSingleQuoted = $value.StartsWith("'") -and $value.EndsWith("'")
                if ($isDoubleQuoted -or $isSingleQuoted) {
                    $value = $value.Substring(1, $value.Length - 2)
                    $value = $value.Replace('\"', '"').Replace('\\', '\')
                }
            }
            return $value
        }
    }

    return ""
}

function ConvertFrom-SecureInput {
    param([System.Security.SecureString]$SecureValue)

    $pointer = [System.IntPtr]::Zero
    try {
        $pointer = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        if ($pointer -ne [System.IntPtr]::Zero) {
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
}

function Read-SecretValue {
    param(
        [string]$Name,
        [string]$ExistingValue,
        [switch]$Required
    )

    $secureValue = Read-Host -Prompt "$Name (hidden; Enter keeps current value)" -AsSecureString
    $value = (ConvertFrom-SecureInput -SecureValue $secureValue).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = $ExistingValue
    }
    if ($Required -and [string]::IsNullOrWhiteSpace($value)) {
        throw "$Name is required."
    }
    return $value
}

function Read-PlainValue {
    param(
        [string]$Name,
        [string]$ExistingValue
    )

    $value = (Read-Host -Prompt "$Name (Enter keeps current value)").Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $ExistingValue
    }
    return $value
}

function ConvertTo-DotEnvValue {
    param([string]$Value)

    if ($Value -match "^[A-Za-z0-9_./:@%+?,=&-]+$") {
        return $Value
    }

    $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
    return '"' + $escaped + '"'
}

function Set-EnvValue {
    param(
        [string[]]$Lines,
        [string]$Name,
        [string]$Value
    )

    $result = New-Object 'System.Collections.Generic.List[string]'
    $pattern = "^\s*" + [regex]::Escape($Name) + "\s*="
    $replaced = $false
    $formatted = "$Name=$(ConvertTo-DotEnvValue -Value $Value)"

    foreach ($line in @($Lines)) {
        if ($line -match $pattern) {
            if (-not $replaced) {
                [void]$result.Add($formatted)
                $replaced = $true
            }
            continue
        }
        [void]$result.Add($line)
    }

    if (-not $replaced) {
        [void]$result.Add($formatted)
    }

    return $result.ToArray()
}

function Assert-Prefix {
    param(
        [string]$Name,
        [string]$Value,
        [string[]]$Prefixes
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is required."
    }

    $matchesPrefix = $false
    foreach ($prefix in $Prefixes) {
        if ($Value.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
            $matchesPrefix = $true
            break
        }
    }
    if (-not $matchesPrefix) {
        throw "$Name has an unexpected format."
    }
}

$outputFile = Resolve-EnvPath -RequestedPath $OutputPath
$outputDirectory = Split-Path -Parent $outputFile
if (-not (Test-Path -LiteralPath $outputDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}

$lines = @()
if (Test-Path -LiteralPath $outputFile -PathType Leaf) {
    $lines = @([System.IO.File]::ReadAllLines($outputFile))
}

$stripeSecret = Read-SecretValue `
    -Name "STRIPE_SECRET_KEY" `
    -ExistingValue (Get-ExistingEnvValue -Lines $lines -Name "STRIPE_SECRET_KEY") `
    -Required
$stripeWebhook = Read-SecretValue `
    -Name "STRIPE_WEBHOOK_SECRET" `
    -ExistingValue (Get-ExistingEnvValue -Lines $lines -Name "STRIPE_WEBHOOK_SECRET") `
    -Required
$stripePublishable = Read-SecretValue `
    -Name "STRIPE_PUBLISHABLE_KEY" `
    -ExistingValue (Get-ExistingEnvValue -Lines $lines -Name "STRIPE_PUBLISHABLE_KEY")

Assert-Prefix -Name "STRIPE_SECRET_KEY" -Value $stripeSecret -Prefixes @("sk_test_", "sk_live_")
Assert-Prefix -Name "STRIPE_WEBHOOK_SECRET" -Value $stripeWebhook -Prefixes @("whsec_")
if ($stripePublishable) {
    Assert-Prefix -Name "STRIPE_PUBLISHABLE_KEY" -Value $stripePublishable -Prefixes @("pk_test_", "pk_live_")
}

$secretMode = if ($stripeSecret.StartsWith("sk_live_", [System.StringComparison]::Ordinal)) {
    "live"
}
else {
    "test"
}

if ($stripePublishable) {
    $publishableMode = if ($stripePublishable.StartsWith("pk_live_", [System.StringComparison]::Ordinal)) {
        "live"
    }
    else {
        "test"
    }
    if ($publishableMode -ne $secretMode) {
        throw "Stripe secret and publishable keys must use the same mode."
    }
}

if (($secretMode -eq "live") -and (-not $AllowLive)) {
    throw "A live Stripe key was entered. Rerun with -AllowLive to opt in explicitly."
}
if ($secretMode -eq "live") {
    $liveConfirmation = Read-Host "Live mode can process real payments. Type LIVE to continue"
    if ($liveConfirmation -cne "LIVE") {
        throw "Live mode was not confirmed; no file was changed."
    }
}

$allowLiveValue = if ($secretMode -eq "live") { "true" } else { "false" }
$updates = [ordered]@{
    STRIPE_SECRET_KEY     = $stripeSecret
    STRIPE_WEBHOOK_SECRET = $stripeWebhook
    STRIPE_MODE           = $secretMode
    ALLOW_LIVE_STRIPE     = $allowLiveValue
}

$priceNames = @(
    "STRIPE_PRICE_STARTER_MONTHLY",
    "STRIPE_PRICE_PRO_MONTHLY",
    "STRIPE_PRICE_ENTERPRISE_MONTHLY"
)
foreach ($priceName in $priceNames) {
    $price = Read-PlainValue `
        -Name $priceName `
        -ExistingValue (Get-ExistingEnvValue -Lines $lines -Name $priceName)
    if ($price) {
        Assert-Prefix -Name $priceName -Value $price -Prefixes @("price_")
        $updates[$priceName] = $price
    }
}

if ($stripePublishable) {
    $updates["STRIPE_PUBLISHABLE_KEY"] = $stripePublishable
}

if ($ConfigureRevenueOs) {
    $downloadSigningSecret = Read-SecretValue `
        -Name "REVENUE_OS_DOWNLOAD_SIGNING_SECRET" `
        -ExistingValue (Get-ExistingEnvValue -Lines $lines -Name "REVENUE_OS_DOWNLOAD_SIGNING_SECRET")
    if ($downloadSigningSecret) {
        if ($downloadSigningSecret.Length -lt 16) {
            throw "REVENUE_OS_DOWNLOAD_SIGNING_SECRET must be at least 16 characters."
        }
        $updates["REVENUE_OS_DOWNLOAD_SIGNING_SECRET"] = $downloadSigningSecret
    }

    foreach ($urlName in @(
        "REVENUE_OS_WEBHOOK_URL",
        "REVENUE_OS_CHECKOUT_SUCCESS_URL",
        "REVENUE_OS_CHECKOUT_CANCEL_URL"
    )) {
        $url = Read-PlainValue `
            -Name $urlName `
            -ExistingValue (Get-ExistingEnvValue -Lines $lines -Name $urlName)
        if ($url) {
            $parsedUrl = $null
            if (-not [System.Uri]::TryCreate($url, [System.UriKind]::Absolute, [ref]$parsedUrl)) {
                throw "$urlName must be an absolute URL."
            }
            $updates[$urlName] = $url
        }
    }
}

if ($lines.Count -eq 0) {
    $lines = @("# Local Graxia OS secrets. Never commit this file.")
}
foreach ($entry in $updates.GetEnumerator()) {
    $lines = @(Set-EnvValue -Lines $lines -Name $entry.Key -Value ([string]$entry.Value))
}

$temporaryFile = "$outputFile.$PID.$([guid]::NewGuid().ToString('N')).tmp"
try {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $content = [string]::Join([Environment]::NewLine, $lines) + [Environment]::NewLine
    [System.IO.File]::WriteAllText($temporaryFile, $content, $utf8NoBom)
    Move-Item -LiteralPath $temporaryFile -Destination $outputFile -Force
}
finally {
    if (Test-Path -LiteralPath $temporaryFile -PathType Leaf) {
        Remove-Item -LiteralPath $temporaryFile -Force -ErrorAction SilentlyContinue
    }
}

if ($SetProcessEnvironment) {
    foreach ($entry in $updates.GetEnumerator()) {
        Set-Item -Path "Env:$($entry.Key)" -Value ([string]$entry.Value)
    }
}

Write-Host "Saved Stripe/Revenue OS configuration to $outputFile" -ForegroundColor Green
Write-Host "Mode: $secretMode; updated: $($updates.Keys -join ', ')" -ForegroundColor Cyan
if ($SetProcessEnvironment) {
    Write-Host "Also set values in this PowerShell process only." -ForegroundColor Yellow
}
if (-not $ConfigureRevenueOs) {
    Write-Host "Use -ConfigureRevenueOs to add Revenue OS webhook/download settings." -ForegroundColor Gray
}
Write-Host "This script does not reauthorize Stripe OAuth, deploy, or create a charge." -ForegroundColor Yellow
