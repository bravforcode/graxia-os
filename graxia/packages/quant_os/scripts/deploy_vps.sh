#!/bin/bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════
# deploy_vps.sh — One-time setup script for VPS Docker deployment
# Run this script from the quant_os directory on the VPS
# ═══════════════════════════════════════════════════════════════════════════

echo "=========================================="
echo " Graxia Trading System — VPS Deploy"
echo "=========================================="

# Check running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (sudo su -)"
    exit 1
fi

# Check Docker
if ! command -v docker &>/dev/null; then
    echo "❌ Docker not found. Install first."
    exit 1
fi

# 1. Create directory structure
echo ""
echo "📁 Step 1: Creating directories..."
mkdir -p /opt/graxia-trading/{data/{postgres,models,features,logs,sqlite},docker/{db,trainer,api},scripts,backups}
echo "✅ /opt/graxia-trading/ ready"

# 2. Copy files from current directory (quant_os) to deployment target
echo ""
echo "📦 Step 2: Copying deployment files..."
DEPLOY_SRC="$(pwd)"
if [ ! -f "$DEPLOY_SRC/docker-compose.yml" ]; then
    echo "❌ Run this script from the quant_os directory with docker-compose.yml"
    exit 1
fi

cp -r "$DEPLOY_SRC"/docker/* /opt/graxia-trading/docker/
cp "$DEPLOY_SRC"/docker-compose.yml /opt/graxia-trading/
cp "$DEPLOY_SRC"/docker/.env.example /opt/graxia-trading/.env.example
cp "$DEPLOY_SRC"/docker/requirements.*.txt /opt/graxia-trading/docker/ 2>/dev/null || true

# 3. Copy quant_os source code (will be used as Docker build context)
echo ""
echo "📦 Step 3: Copying quant_os source code..."
rsync -a --exclude='.git' --exclude='__pycache__' --exclude='.venv' \
    --exclude='*.pyc' --exclude='node_modules' --exclude='.mypy_cache' \
    --exclude='.pytest_cache' --exclude='.ruff_cache' \
    "$DEPLOY_SRC/" /opt/graxia-trading/quant_os/
echo "✅ quant_os source copied"

# 4. Create .env from template if not exists
echo ""
echo "🔐 Step 4: Environment file..."
if [ ! -f /opt/graxia-trading/.env ]; then
    # Generate random secrets
    DB_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
    JWT_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    WEB_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    ADMIN_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")

    cp /opt/graxia-trading/.env.example /opt/graxia-trading/.env
    sed -i "s/DB_PASSWORD=.*/DB_PASSWORD=$DB_PASS/" /opt/graxia-trading/.env
    sed -i "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$JWT_KEY/" /opt/graxia-trading/.env
    sed -i "s/WEBHOOK_HMAC_SECRET=.*/WEBHOOK_HMAC_SECRET=$WEB_KEY/" /opt/graxia-trading/.env
    sed -i "s/ADMIN_API_KEY=.*/ADMIN_API_KEY=$ADMIN_KEY/" /opt/graxia-trading/.env
    chmod 600 /opt/graxia-trading/.env
    echo "✅ .env created with auto-generated secrets"
    echo ""
    echo "   ⚠️  IMPORTANT: Save these secrets somewhere safe!"
    echo "   DB_PASSWORD: $DB_PASS"
    echo "   JWT_KEY:     $JWT_KEY"
    echo "   ADMIN_KEY:   $ADMIN_KEY"
else
    echo "⏩ .env already exists, skipping"
fi

# 5. Verify port 8751 is free
echo ""
echo "🔌 Step 5: Checking port availability..."
if ss -tlnp "sport = :8751" | grep -q LISTEN; then
    echo "❌ Port 8751 is already in use! Change docker-compose.yml port mapping."
    exit 1
fi
echo "✅ Port 8751 is free"

# 6. Verify subnet 172.22.0.0/24 not in use
echo ""
echo "🌐 Step 6: Checking network..."
if docker network ls | grep -q "graxia-trading-net"; then
    echo "⏩ Network graxia-trading-net already exists"
else
    echo "✅ Network 172.22.0.0/24 available"
fi

# 7. Build and deploy
echo ""
echo "🐳 Step 7: Building Docker images..."
cd /opt/graxia-trading
docker compose build
echo "✅ Build complete"

echo ""
echo "🐳 Step 8: Starting containers..."
# Export env vars from .env
set -a; source .env; set +a
docker compose up -d
echo "✅ Containers started"

# 8. Verify deployment
echo ""
echo "🔍 Step 9: Verification..."
echo ""
echo "--- Docker containers ---"
docker compose ps
echo ""
echo "--- Health check (wait 10s) ---"
sleep 5
echo "API health:"
curl -sf http://localhost:8751/health && echo " — OK ✅" || echo " — FAIL ❌"
echo "DB health:"
docker exec graxia-db pg_isready -U graxia && echo " — OK ✅" || echo " — FAIL ❌"

echo ""
echo "=========================================="
echo " ✅ Deployment complete!"
echo "=========================================="
echo ""
echo "API endpoint:  http://$(curl -s ifconfig.me):8751"
echo "Dashboard:     http://$(curl -s ifconfig.me):8751/docs"
echo ""
echo "Logs: docker compose logs -f"
echo "Stop:  docker compose down"
echo "=========================================="
