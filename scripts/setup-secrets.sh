#!/bin/bash
# Graxia OS - Setup Fly.io Secrets
# Usage: ./setup-secrets.sh

set -e

SCRIPT_DIR="$($(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/backend/.env"

echo "🔐 Graxia OS - Setup Fly.io Secrets"
echo "===================================="
echo ""

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env file not found at $ENV_FILE"
    echo "Please create .env from .env.flyio-template first"
    exit 1
fi

echo "📋 Available secrets to set:"
echo ""

# Extract and display secrets (without values)
grep -E '^(DATABASE_URL|REDIS_URL|SECRET_KEY|ENCRYPTION_KEY|INTERNAL_API_KEY|OPENAI_API_KEY|SUPABASE_URL|TELEGRAM_BOT_TOKEN|RESEND_API_KEY)=' "$ENV_FILE" | \
    cut -d= -f1 | \
    while read -r key; do
        echo "  - $key"
    done

echo ""
echo "⚠️  Warning: This will set secrets from your .env file to Fly.io"
echo "   Make sure your .env file contains production values!"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Setting secrets for graxia-api..."

# Set secrets one by one to handle errors gracefully
while IFS= read -r line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    
    # Extract key and value
    key=$(echo "$line" | cut -d= -f1)
    value=$(echo "$line" | cut -d= -f2-)
    
    # Skip if value is placeholder
    if [[ "$value" == "your-"* ]] || [[ "$value" == "sk-"* ]] || [[ "$value" == "" ]]; then
        echo "  ⚠️  Skipping $key (placeholder or empty)"
        continue
    fi
    
    echo "  Setting $key..."
    flyctl secrets set --app graxia-api "$key=$value" &> /dev/null || echo "  ❌ Failed to set $key"
    
done < "$ENV_FILE"

echo ""
echo "Setting secrets for graxia-worker..."

# Same for worker
while IFS= read -r line; do
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    
    key=$(echo "$line" | cut -d= -f1)
    value=$(echo "$line" | cut -d= -f2-)
    
    if [[ "$value" == "your-"* ]] || [[ "$value" == "sk-"* ]] || [[ "$value" == "" ]]; then
        continue
    fi
    
    flyctl secrets set --app graxia-worker "$key=$value" &> /dev/null || true
    
done < "$ENV_FILE"

echo ""
echo "✅ Secrets set successfully!"
echo ""
echo "Verify with:"
echo "  flyctl secrets list --app graxia-api"
