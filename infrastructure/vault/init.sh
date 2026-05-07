#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════════
# Vault Initialization Script for Graxia OS
# Creates secrets structure and enables required engines
# ═══════════════════════════════════════════════════════════════════════════════

set -e

export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=graxia-vault-root-2024

echo "🔐 Initializing Vault for Graxia OS..."

# Wait for Vault to be ready
sleep 3

# Enable KV v2 secrets engine at graxia/
vault secrets enable -path=graxia -version=2 kv 2>/dev/null || echo "KV engine already enabled"

# Enable database secrets engine
vault secrets enable database 2>/dev/null || echo "Database engine already enabled"

# Enable Transit (encryption) engine
vault secrets enable transit 2>/dev/null || echo "Transit engine already enabled"

# Create encryption keys
vault write -f transit/keys/graxia-data 2>/dev/null || echo "Key already exists"

# Store database credentials
echo "💾 Storing database credentials..."
vault kv put graxia/database \
    host=db.eezrhwiwwsmarkvejeoi.supabase.co \
    port=5432 \
    database=postgres \
    username=postgres \
    password=Q5HkxsiINJSPy7vN \
    ssl_mode=require

# Store Redis credentials
echo "💾 Storing Redis credentials..."
vault kv put graxia/redis \
    url="redis://redis-node-1:6379,redis-node-2:6379,redis-node-3:6379/0" \
    cluster=true

# Store API Keys
echo "💾 Storing API keys..."
vault kv put graxia/api-keys \
    jwt_secret="${JWT_SECRET_KEY:-default-jwt-secret-change-in-production}" \
    admin_key="${ADMIN_API_KEY:-default-admin-key-change-in-production}" \
    webhook_hmac="${WEBHOOK_HMAC_SECRET:-default-hmac-change-in-production}"

# Store Payment Gateway keys
echo "💾 Storing payment gateway keys..."
vault kv put graxia/payments/stripe \
    secret_key="${STRIPE_SECRET_KEY:-sk_test_placeholder}" \
    webhook_secret="${STRIPE_WEBHOOK_SECRET:-whsec_placeholder}"

vault kv put graxia/payments/paypal \
    client_id="${PAYPAL_CLIENT_ID:-placeholder}"

# Store Telegram credentials
echo "💾 Storing Telegram credentials..."
vault kv put graxia/telegram \
    bot_token="${TELEGRAM_BOT_TOKEN:-placeholder}" \
    chat_id="${TELEGRAM_CHAT_ID:-placeholder}"

# Store MinIO credentials
echo "💾 Storing MinIO credentials..."
vault kv put graxia/minio \
    endpoint="http://minio:9002" \
    access_key="graxiaadmin" \
    secret_key="graxiaadmin2024"

# Store Kafka credentials
echo "💾 Storing Kafka credentials..."
vault kv put graxia/kafka \
    bootstrap_servers="kafka:29092" \
    client_id="graxia-producer"

# Create policy for Graxia services
echo "📜 Creating access policy..."
cat > /tmp/graxia-policy.hcl << 'EOF'
path "graxia/*" {
  capabilities = ["read", "list"]
}

path "transit/encrypt/graxia-data" {
  capabilities = ["update"]
}

path "transit/decrypt/graxia-data" {
  capabilities = ["update"]
}
EOF

vault policy write graxia-app /tmp/graxia-policy.hcl 2>/dev/null || echo "Policy already exists"

# Create AppRole for services
echo "🔑 Creating AppRole..."
vault auth enable approle 2>/dev/null || echo "AppRole already enabled"

vault write auth/approle/role/graxia-api \
    token_policies="graxia-app" \
    secret_id_ttl=0 \
    token_ttl=1h \
    token_max_ttl=4h 2>/dev/null || echo "AppRole already configured"

# Get RoleID (for service configuration)
ROLE_ID=$(vault read -field=role_id auth/approle/role/graxia-api/role-id 2>/dev/null || echo "")
echo "RoleID: $ROLE_ID"

echo ""
echo "✅ Vault initialization complete!"
echo ""
echo "🔑 Vault UI: http://localhost:8200"
echo "   Token: graxia-vault-root-2024"
echo ""
echo "📦 Secrets stored:"
echo "   - graxia/database        (Supabase PostgreSQL)"
echo "   - graxia/redis            (Redis Cluster)"
echo "   - graxia/api-keys         (JWT, Admin, Webhook)"
echo "   - graxia/payments/stripe  (Stripe keys)"
echo "   - graxia/payments/paypal  (PayPal keys)"
echo "   - graxia/telegram         (Bot credentials)"
echo "   - graxia/minio            (S3-compatible storage)"
echo "   - graxia/kafka            (Kafka bootstrap)"
echo ""
