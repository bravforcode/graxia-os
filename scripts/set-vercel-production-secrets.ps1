[CmdletBinding()]
param(
    [switch]$OnlyRequired
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\Users\menum\graxia os"
$ProjectName = "graxia-os-funnel"
$CanonicalUrl = "https://graxia-os-funnel.vercel.app"

function Invoke-VercelEnvValue {
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [string]$Value
    )

    & vercel env add $Name production --value $Value --force --yes --non-interactive
    if ($LASTEXITCODE -ne 0) {
        throw "Vercel rejected production variable '$Name'."
    }
}

function Read-AndSetSecret {
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [string]$Description
    )

    $secure = Read-Host -Prompt "$Name ($Description; Enter เพื่อข้าม)" -AsSecureString
    if ($secure.Length -eq 0) {
        Write-Host "Skipped $Name"
        return $false
    }

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $plain = $null
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        $vercelPath = (Get-Command vercel.cmd -CommandType Application).Source
        $startInfo = [Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $vercelPath
        $startInfo.WorkingDirectory = $ProjectRoot
        $startInfo.UseShellExecute = $false
        $startInfo.RedirectStandardInput = $true
        # Arguments contain only hardcoded variable names; the secret remains
        # exclusively on stdin and is never included in the process command.
        $startInfo.Arguments = "env add $Name production --sensitive --force --yes --non-interactive"
        $process = [Diagnostics.Process]::Start($startInfo)
        # Write without a trailing newline; Vercel stores stdin byte-for-byte.
        $process.StandardInput.Write($plain)
        $process.StandardInput.Close()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "Vercel rejected production variable '$Name'."
        }
        $process.Dispose()
        Write-Host "Set $Name"
        return $true
    }
    finally {
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
        $plain = $null
        $secure.Dispose()
    }
}

Set-Location -LiteralPath $ProjectRoot
if (-not (Get-Command vercel -ErrorAction SilentlyContinue)) {
    throw "Vercel CLI is not installed or is not on PATH."
}

Write-Host "Checking Vercel authentication and project..."
& vercel whoami
if ($LASTEXITCODE -ne 0) {
    throw "Vercel authentication failed. Run 'vercel login' and retry."
}
& vercel env ls production --non-interactive
if ($LASTEXITCODE -ne 0) {
    throw "Cannot read production environment for '$ProjectName'."
}

Write-Host "Setting non-secret production configuration..."
$publicValues = [ordered]@{
    APP_ENV = "production"
    APP_BASE_URL = $CanonicalUrl
    FRONTEND_URL = $CanonicalUrl
    ALLOWED_CORS_ORIGINS = $CanonicalUrl
    DB_POOL_SIZE = "1"
    DB_MAX_OVERFLOW = "1"
    NO_LIVE_PAYMENT_MODE = "true"
    ALLOW_LIVE_STRIPE = "false"
}
foreach ($entry in $publicValues.GetEnumerator()) {
    Invoke-VercelEnvValue -Name $entry.Key -Value $entry.Value
}

$required = [ordered]@{
    DATABASE_URL = "production database URL"
    SECRET_KEY = "application signing key"
    ENCRYPTION_KEY = "data encryption key"
    API_KEY = "application API key"
    CSRF_SECRET = "CSRF signing secret"
    ADMIN_API_KEY = "admin API key"
    INTERNAL_API_KEY = "internal API key"
    INTERNAL_METRICS_TOKEN = "cron/internal metrics token"
    ADMIN_DEFAULT_EMAIL = "admin login email"
    ADMIN_DEFAULT_PASSWORD = "admin login password"
    RESEND_API_KEY = "email provider API key"
}

$optional = [ordered]@{
    JWT_SIGNING_KEYS = "JWT signing key set"
    DATABASE_MIGRATION_URL = "migration database URL, if separate"
    POSTGRES_PASSWORD = "database password, only if your deployment needs it"
    SUPABASE_URL = "Supabase project URL"
    SUPABASE_ANON_KEY = "Supabase anonymous key"
    SUPABASE_SERVICE_ROLE_KEY = "Supabase service role key"
    SUPABASE_JWT_SECRET = "Supabase JWT secret"
    REDIS_PASSWORD = "Redis password"
    REDIS_URL = "Redis URL"
    CELERY_BROKER_URL = "broker URL, only if a worker deployment uses it"
    CELERY_RESULT_BACKEND = "result backend URL, only if a worker deployment uses it"
    OPENCLAW_API_KEY = "OpenClaw provider key"
    HERMES_API_KEY = "Hermes provider key"
    STRIPE_SECRET_KEY = "Stripe test key; do not enter a live key while live mode is disabled"
    STRIPE_PUBLISHABLE_KEY = "Stripe test publishable key"
    STRIPE_WEBHOOK_SECRET = "Stripe webhook signing secret"
    STRIPE_PRICE_STARTER_MONTHLY = "Stripe price ID for the starter plan"
    STRIPE_PRICE_PRO_MONTHLY = "Stripe price ID for the pro plan"
    STRIPE_PRICE_ENTERPRISE_MONTHLY = "Stripe price ID for the enterprise plan"
    REVENUE_OS_WEBHOOK_URL = "Revenue OS webhook URL"
    OPENAI_API_KEY = "OpenAI provider key"
    GEMINI_API_KEY = "Gemini provider key"
    SERPAPI_KEY = "search provider key"
    GOOGLE_CLIENT_ID = "Google OAuth client ID"
    GOOGLE_CLIENT_SECRET = "Google OAuth client secret"
    GOOGLE_REFRESH_TOKEN = "Google OAuth refresh token"
    GOOGLE_WORKSPACE_EMAIL = "Google Workspace sender email"
    TELEGRAM_BOT_TOKEN = "Telegram bot token"
    TELEGRAM_CHAT_ID = "Telegram destination ID"
    ALERTMANAGER_WEBHOOK_TOKEN = "Alertmanager webhook token"
    ALERTMANAGER_WEBHOOK_SECRET = "Alertmanager webhook secret"
    SITE_REBUILD_WEBHOOKS = "site rebuild webhook map"
    META_ACCESS_TOKEN = "Meta provider token"
    META_AD_ACCOUNT_ID = "Meta account ID"
    TIKTOK_ACCESS_TOKEN = "TikTok provider token"
    LINE_CHANNEL_ACCESS_TOKEN = "LINE channel token"
    LINE_CHANNEL_SECRET = "LINE channel secret"
    OBSIDIAN_API_KEY = "Obsidian API key"
    TRACKING_SIGNING_SECRET = "email tracking signing secret"
    SALESFORCE_ACCESS_TOKEN = "Salesforce access token"
    SENTRY_DSN = "Sentry DSN"
    SHOPIFY_STORE_DOMAIN = "Shopify store domain"
    SHOPIFY_ACCESS_TOKEN = "Shopify access token"
    SHOPIFY_WEBHOOK_SECRET = "Shopify webhook secret"
    HUBSPOT_PRIVATE_APP_TOKEN = "HubSpot private app token"
}

$setCount = 0
$skipCount = 0
foreach ($entry in $required.GetEnumerator()) {
    if (Read-AndSetSecret -Name $entry.Key -Description $entry.Value) { $setCount++ } else { $skipCount++ }
}
if (-not $OnlyRequired) {
    foreach ($entry in $optional.GetEnumerator()) {
        if (Read-AndSetSecret -Name $entry.Key -Description $entry.Value) { $setCount++ } else { $skipCount++ }
    }
}

Write-Host ""
Write-Host "Production env update finished for $ProjectName"
Write-Host "Canonical URL: $CanonicalUrl"
Write-Host "Secrets set: $setCount; skipped: $skipCount"
Write-Host "Values were not printed or written to a local .env file."
Write-Host "Live payment remains disabled by NO_LIVE_PAYMENT_MODE=true and ALLOW_LIVE_STRIPE=false."
