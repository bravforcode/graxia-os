#!/bin/bash
set -e

echo "🔧 Setting up monitoring for Graxia OS..."
echo ""

# Check if Grafana is running
if ! docker ps | grep -q grafana; then
    echo "❌ Grafana is not running. Start it with: make up"
    exit 1
fi

# Wait for Grafana to be ready
echo "⏳ Waiting for Grafana to be ready..."
until curl -s http://localhost:3000/api/health > /dev/null 2>&1; do
    sleep 2
done
echo "✅ Grafana is ready"
echo ""

# Get Grafana admin password
GRAFANA_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-admin}

# Create datasource
echo "📊 Creating Prometheus datasource..."
curl -X POST \
    -H "Content-Type: application/json" \
    -u "admin:${GRAFANA_PASSWORD}" \
    http://localhost:3000/api/datasources \
    -d '{
        "name": "Prometheus",
        "type": "prometheus",
        "url": "http://prometheus:9090",
        "access": "proxy",
        "isDefault": true
    }' 2>/dev/null || echo "Datasource may already exist"
echo ""

# Import dashboards
echo "📈 Importing Grafana dashboards..."
for dashboard in deploy/monitoring/grafana/dashboards/*.json; do
    if [ -f "$dashboard" ]; then
        dashboard_name=$(basename "$dashboard" .json)
        echo "  - Importing $dashboard_name..."
        
        curl -X POST \
            -H "Content-Type: application/json" \
            -u "admin:${GRAFANA_PASSWORD}" \
            http://localhost:3000/api/dashboards/db \
            -d @"$dashboard" 2>/dev/null || echo "    Dashboard may already exist"
    fi
done
echo ""

# Configure Alertmanager
echo "🚨 Configuring Alertmanager..."
if [ -f "deploy/monitoring/alertmanager/rules.yml" ]; then
    docker cp deploy/monitoring/alertmanager/rules.yml personal_os_alertmanager:/etc/alertmanager/ 2>/dev/null || true
    docker restart personal_os_alertmanager 2>/dev/null || echo "Alertmanager not running"
fi
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Monitoring setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Access Grafana:"
echo "   URL: http://localhost:3000"
echo "   Username: admin"
echo "   Password: ${GRAFANA_PASSWORD}"
echo ""
echo "📈 Available Dashboards:"
echo "   - System Health"
echo "   - Application Metrics"
echo "   - Business Metrics"
echo "   - Celery Workers"
echo "   - LLM Costs"
echo ""
echo "🚨 Alertmanager:"
echo "   URL: http://localhost:9093"
echo ""
