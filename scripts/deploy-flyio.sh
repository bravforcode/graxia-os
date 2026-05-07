#!/bin/bash
# Graxia OS - Fly.io Deployment Script
# Usage: ./deploy-flyio.sh [api|worker|both]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "🚀 Graxia OS - Fly.io Deployment"
echo "================================"

# Check for flyctl
if ! command -v flyctl &> /dev/null; then
    echo "❌ flyctl not found. Installing..."
    curl -L https://fly.io/install.sh | sh
    export FLYCTL_INSTALL="$HOME/.fly"
    export PATH="$FLYCTL_INSTALL/bin:$PATH"
fi

# Check authentication
if ! flyctl auth whoami &> /dev/null; then
    echo "🔐 Please login to Fly.io:"
    flyctl auth login
fi

cd "$BACKEND_DIR"

# Parse arguments
TARGET="${1:-both}"

deploy_api() {
    echo ""
    echo "📦 Deploying API..."
    echo "==================="
    
    # Check if app exists
    if ! flyctl status --app graxia-api &> /dev/null; then
        echo "🆕 Creating new app: graxia-api"
        flyctl apps create graxia-api
    fi
    
    # Check secrets are set
    echo "🔍 Checking secrets..."
    if ! flyctl secrets list --app graxia-api | grep -q "DATABASE_URL"; then
        echo "⚠️  Warning: DATABASE_URL not set. Please set secrets first:"
        echo "   flyctl secrets set --app graxia-api DATABASE_URL=your-url"
        echo ""
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    # Deploy
    echo "🚀 Deploying..."
    flyctl deploy --config fly.toml --remote-only
    
    echo "✅ API deployed successfully!"
    echo "   URL: https://graxia-api.fly.dev"
}

deploy_worker() {
    echo ""
    echo "📦 Deploying Worker..."
    echo "====================="
    
    # Check if app exists
    if ! flyctl status --app graxia-worker &> /dev/null; then
        echo "🆕 Creating new app: graxia-worker"
        flyctl apps create graxia-worker
    fi
    
    # Deploy
    echo "🚀 Deploying..."
    flyctl deploy --config fly.worker.toml --remote-only
    
    echo "✅ Worker deployed successfully!"
}

# Main deployment logic
case "$TARGET" in
    api)
        deploy_api
        ;;
    worker)
        deploy_worker
        ;;
    both)
        deploy_api
        deploy_worker
        ;;
    *)
        echo "Usage: $0 [api|worker|both]"
        exit 1
        ;;
esac

echo ""
echo "🎉 Deployment complete!"
echo "======================="
echo "API:    https://graxia-api.fly.dev"
echo "Health: https://graxia-api.fly.dev/health"
echo ""
echo "Next steps:"
echo "1. Set up GitHub Secrets for automated deployment"
echo "2. Configure Vercel rewrites to point to Fly.io"
echo "3. Test the endpoints"
