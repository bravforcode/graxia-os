# Generate secrets for Graxia OS without openssl
# Run: .\scripts\generate-secrets.ps1

Write-Host "🔑 Generating Secrets for Graxia OS" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan

# Method 1: Using .NET RandomNumberGenerator
function Get-RandomHex {
    param([int]$Bytes = 32)
    $randomBytes = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($randomBytes)
    return [BitConverter]::ToString($randomBytes).Replace("-", "").ToLower()
}

# Generate INTERNAL_API_KEY (32 bytes = 64 hex chars)
$internalApiKey = Get-RandomHex -Bytes 32
Write-Host "`nINTERNAL_API_KEY: " -NoNewline
Write-Host $internalApiKey -ForegroundColor Green

# Generate SECRET_KEY (64 bytes = 128 hex chars)
$secretKey = Get-RandomHex -Bytes 64
Write-Host "`nSECRET_KEY: " -NoNewline
Write-Host $secretKey -ForegroundColor Green

# Generate ENCRYPTION_KEY (32 bytes for Fernet - base64)
$encryptionBytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Fill($encryptionBytes)
$encryptionKey = [Convert]::ToBase64String($encryptionBytes)
Write-Host "`nENCRYPTION_KEY: " -NoNewline
Write-Host $encryptionKey -ForegroundColor Green

# Generate another key for comparison
$internalApiKey2 = Get-RandomHex -Bytes 32
Write-Host "`nAlternative INTERNAL_API_KEY: " -NoNewline
Write-Host $internalApiKey2 -ForegroundColor Yellow

# Instructions
Write-Host "`n====================================" -ForegroundColor Cyan
Write-Host "📋 Instructions:" -ForegroundColor Cyan
Write-Host "1. Copy INTERNAL_API_KEY ด้านบน" -ForegroundColor White
Write-Host "2. ตั้งบน Fly.io:" -ForegroundColor White
Write-Host "   flyctl secrets set --app graxia-api INTERNAL_API_KEY=`"$internalApiKey`"" -ForegroundColor Gray
Write-Host "   flyctl secrets set --app graxia-worker INTERNAL_API_KEY=`"$internalApiKey`"" -ForegroundColor Gray
Write-Host "3. เก็บไว้ทดสอบ:" -ForegroundColor White
Write-Host "   `$env:INTERNAL_API_KEY = `"$internalApiKey`"" -ForegroundColor Gray
Write-Host "4. ตั้งบน GitHub Secrets ด้วย (สำหรับ Actions)" -ForegroundColor White

# Option to set automatically
Write-Host "`nต้องการตั้ง `$env:INTERNAL_API_KEY ตอนนี้เลยหรือไม่? (y/n): " -NoNewline
$confirm = Read-Host

if ($confirm -eq 'y') {
    $env:INTERNAL_API_KEY = $internalApiKey
    Write-Host "✅ ตั้ง `$env:INTERNAL_API_KEY เรียบร้อย" -ForegroundColor Green
    Write-Host "   ค่า: $internalApiKey" -ForegroundColor Gray
} else {
    Write-Host "⏭️  ข้ามการตั้ง environment variable" -ForegroundColor Yellow
}

# Copy to clipboard option
Write-Host "`nต้องการ copy INTERNAL_API_KEY ไป clipboard หรือไม่? (y/n): " -NoNewline
$confirm2 = Read-Host
if ($confirm2 -eq 'y') {
    $internalApiKey | Set-Clipboard
    Write-Host "✅ Copied to clipboard!" -ForegroundColor Green
}
