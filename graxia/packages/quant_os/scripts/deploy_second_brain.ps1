# Cloudflare Second Brain Deployment Script for quant_os
# Requires: Cloudflare Account ID and API Token or wrangler login

param (
    [string]$AccountId = $env:CF_ACCOUNT_ID,
    [switch]$SaveToEnvFile
)

Write-Host "=== Cloudflare Second Brain Worker Deployment ===" -ForegroundColor Cyan

if (-not $AccountId) {
    $AccountId = Read-Host "Enter your Cloudflare Account ID (not secret, safe to show)"
}

if (-not (Get-Command wrangler -ErrorAction SilentlyContinue)) {
    Write-Host "Installing wrangler CLI globally..." -ForegroundColor Yellow
    npm install -g wrangler
}

$env:CLOUDFLARE_ACCOUNT_ID = $AccountId

# Secure token entry — masked input, never echoed, never written to shell history/transcript.
if (-not $env:CLOUDFLARE_API_TOKEN) {
    $secureToken = Read-Host "Enter your Cloudflare API Token (input hidden)" -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainToken = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    $env:CLOUDFLARE_API_TOKEN = $plainToken

    if ($SaveToEnvFile) {
        $envFile = "$PSScriptRoot\..\.env"
        Add-Content -Path $envFile -Value "`nCLOUDFLARE_API_TOKEN=$plainToken"
        Write-Host "Token saved to $envFile (already .gitignore'd — never commit it)." -ForegroundColor Yellow
    }
    $plainToken = $null  # clear from memory once no longer needed
}

Write-Host "`n1. Verifying Cloudflare Authentication..." -ForegroundColor Green
npx wrangler whoami

Write-Host "`n2. Provisioning D1 Database (second_brain_db)..." -ForegroundColor Green
npx wrangler d1 create second_brain_db

Write-Host "`n3. Provisioning Vectorize Index (second_brain_vectors)..." -ForegroundColor Green
npx wrangler vectorize create second_brain_vectors --dimensions=768 --metric=cosine

Write-Host "`n4. Provisioning KV Namespace (second_brain_kv)..." -ForegroundColor Green
npx wrangler kv:namespace create second_brain_kv

Write-Host "`n5. Deploying Worker (second-brain-worker)..." -ForegroundColor Green
npx wrangler deploy

Write-Host "`n=== Deployment Complete ===" -ForegroundColor Cyan
