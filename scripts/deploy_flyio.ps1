# Graxia OS Fly.io Deployment Script
# Sets up secrets and deploys to Fly.io

Write-Host "🚀 Graxia OS Fly.io Deployment" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Yellow

# Check if Fly CLI is installed
try {
    fly version | Out-Null
    Write-Host "✅ Fly CLI found" -ForegroundColor Green
} catch {
    Write-Host "❌ Fly CLI not found. Please install: https://fly.io/docs/hands-on/install-flyctl/" -ForegroundColor Red
    exit 1
}

# Set required secrets
Write-Host "🔧 Setting up Fly.io secrets..." -ForegroundColor Yellow

$secrets = @{
    "DATABASE_URL" = "postgresql://graxia:password@db.graxia.flycast.com:5432/graxia_prod"
    "REDIS_URL" = "redis://default:password@redis.graxia.flycast.com:6379"
    "SECRET_KEY" = "graxia-production-secret-key-change-me"
    "STRIPE_SECRET_KEY" = "sk_live_change_me"
    "STRIPE_WEBHOOK_SECRET" = "whsec_change_me"
    "RESEND_API_KEY" = "re_change_me"
    "OPENCLAW_API_KEY" = "sk-change-me"
    "OBSIDIAN_REST_TOKEN" = "change_me_token"
    "TELEGRAM_BOT_TOKEN" = "change_me_bot_token"
    "INTERNAL_METRICS_TOKEN" = "metrics-token-change-me"
}

foreach ($secret in $secrets.GetEnumerator()) {
    Write-Host "  Setting $($secret.Key)..." -ForegroundColor Cyan
    try {
        fly secrets set $($secret.Key)=$($secret.Value) --app graxia-api
        Write-Host "  ✅ $($secret.Key) set" -ForegroundColor Green
    } catch {
        Write-Host "  ❌ Failed to set $($secret.Key): $($_.Exception.Message)" -ForegroundColor Red
    }
}

# Deploy to Fly.io
Write-Host "`n🚀 Deploying to Fly.io..." -ForegroundColor Yellow

try {
    # Set up database
    Write-Host "  Setting up PostgreSQL database..." -ForegroundColor Cyan
    fly postgres create --name graxia-db --region sin --vm-size shared-cpu-1x --initial-cluster-size 1 --app graxia-api

    # Deploy application
    Write-Host "  Deploying application..." -ForegroundColor Cyan
    fly deploy --app graxia-api --region sin

    Write-Host "✅ Deployment completed!" -ForegroundColor Green
    Write-Host "`n🌐 Application URL: https://graxia-api.fly.dev" -ForegroundColor Green
    Write-Host "📊 Health check: https://graxia-api.fly.dev/health" -ForegroundColor Green

} catch {
    Write-Host "❌ Deployment failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "`n📋 Post-deployment checklist:" -ForegroundColor Yellow
Write-Host "  1. Update DNS to point to Fly.io" -ForegroundColor White
Write-Host "  2. Configure custom domain in Fly.io dashboard" -ForegroundColor White
Write-Host "  3. Set up monitoring and alerts" -ForegroundColor White
Write-Host "  4. Test all API endpoints" -ForegroundColor White
Write-Host "  5. Verify Stripe webhook endpoints" -ForegroundColor White

Write-Host "`n✨ Graxia OS deployment complete!" -ForegroundColor Green
