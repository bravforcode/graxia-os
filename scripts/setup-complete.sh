#!/bin/bash
# Graxia OS - Complete Setup Script
# Run this after all accounts are created and .env is configured

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🚀 Graxia OS - Complete Production Setup"
echo "========================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check prerequisites
echo "📋 Checking prerequisites..."

if ! command -v flyctl &> /dev/null; then
    echo "${RED}❌ flyctl not found. Please install first:${NC}"
    echo "   curl -L https://fly.io/install.sh | sh"
    exit 1
fi

if ! flyctl auth whoami &> /dev/null; then
    echo "${RED}❌ Not logged in to Fly.io. Please run:${NC}"
    echo "   flyctl auth login"
    exit 1
fi

if [ ! -f "$PROJECT_ROOT/backend/.env" ]; then
    echo "${RED}❌ .env file not found at backend/.env${NC}"
    echo "   Please copy from .env.flyio-template and fill in your values"
    exit 1
fi

echo "${GREEN}✅ All prerequisites met${NC}"
echo ""

# Step 1: Create apps if not exist
echo "📝 Step 1: Setting up Fly.io apps..."

if ! flyctl apps list | grep -q "graxia-api"; then
    echo "Creating graxia-api app..."
    flyctl apps create graxia-api
else
    echo "graxia-api app already exists"
fi

if ! flyctl apps list | grep -q "graxia-worker"; then
    echo "Creating graxia-worker app..."
    flyctl apps create graxia-worker
else
    echo "graxia-worker app already exists"
fi

echo "${GREEN}✅ Apps ready${NC}"
echo ""

# Step 2: Set secrets
echo "🔐 Step 2: Setting secrets..."
echo "   This will set all secrets from backend/.env to both apps"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

cd "$PROJECT_ROOT/backend"

# Set secrets for API app
echo "Setting secrets for graxia-api..."
while IFS= read -r line; do
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    
    key=$(echo "$line" | cut -d= -f1)
    value=$(echo "$line" | cut -d= -f2-)
    
    # Skip empty or placeholder values
    [[ -z "$value" ]] && continue
    [[ "$value" == "your-"* ]] && continue
    [[ "$value" == "sk-"* ]] && continue
    [[ "$value" == "replace-"* ]] && continue
    
    echo "  Setting $key..."
    flyctl secrets set --app graxia-api "$key=$value" &> /dev/null || echo "  ⚠️  Failed to set $key"
done < .env

# Set secrets for Worker app
echo "Setting secrets for graxia-worker..."
while IFS= read -r line; do
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    
    key=$(echo "$line" | cut -d= -f1)
    value=$(echo "$line" | cut -d= -f2-)
    
    [[ -z "$value" ]] && continue
    [[ "$value" == "your-"* ]] && continue
    [[ "$value" == "sk-"* ]] && continue
    [[ "$value" == "replace-"* ]] && continue
    
    flyctl secrets set --app graxia-worker "$key=$value" &> /dev/null || true
done < .env

echo "${GREEN}✅ Secrets set${NC}"
echo ""

# Step 3: Deploy
echo "🚀 Step 3: Deploying applications..."
echo ""

echo "Deploying API..."
flyctl deploy --config fly.toml --remote-only

echo ""
echo "Deploying Worker..."
flyctl deploy --config fly.worker.toml --remote-only

echo "${GREEN}✅ Deployment complete${NC}"
echo ""

# Step 4: Verify
echo "🔍 Step 4: Verifying deployment..."
echo ""

echo "API Status:"
flyctl status --app graxia-api

echo ""
echo "Worker Status:"
flyctl status --app graxia-worker

echo ""
echo "Health Check:"
curl -s "https://graxia-api.fly.dev/health" | jq . || curl -s "https://graxia-api.fly.dev/health"

echo ""
echo "${GREEN}====================================${NC}"
echo "${GREEN}🎉 Setup Complete!${NC}"
echo "${GREEN}====================================${NC}"
echo ""
echo "Next steps:"
echo "1. Set up GitHub Secrets for automated deployment:"
echo "   - GRAXIA_API_URL=https://graxia-api.fly.dev"
echo "   - INTERNAL_API_KEY=<your key>"
echo "   - FLY_API_TOKEN=$(flyctl tokens create 2>/dev/null || echo '<run: flyctl tokens create>')"
echo ""
echo "2. Update vercel.json with the API URL"
echo "3. Test the deployment"
echo ""
echo "Useful commands:"
echo "  View logs:     flyctl logs --app graxia-api"
echo "  View status:   flyctl status --app graxia-api"
echo "  Restart:       flyctl restart --app graxia-api"
echo "  SSH into app:  flyctl ssh console --app graxia-api"
echo ""
