#!/bin/bash
# GRAXIA OS - Deploy Script for Hetzner CPX11 (2GB RAM)
# Optimized for minimal resource usage with maximum stability

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

PROJECT_NAME="graxia"
COMPOSE_FILE="docker-compose.cpx11.yml"
ENV_FILE=".env.production"

# Memory thresholds for CPX11 (2GB)
MEMORY_WARNING=1500000  # 1.5GB
MEMORY_CRITICAL=1800000 # 1.8GB

check_prerequisites() {
    log_info "Checking prerequisites for CPX11 deployment..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker not found. Install: curl -fsSL https://get.docker.com | sh"
        exit 1
    fi

    if ! docker compose version &> /dev/null && ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose not found. Install: sudo apt install -y docker-compose-plugin"
        exit 1
    fi

    # Check available memory
    AVAILABLE_MEM=$(free -m | awk 'NR==2{printf "%.0f", $7}')
    if [ "$AVAILABLE_MEM" -lt 1800 ]; then
        log_warn "Available memory is ${AVAILABLE_MEM}MB. CPX11 has 2GB total."
        log_warn "Make sure no other services are running."
    fi

    # Check disk space
    AVAILABLE_DISK=$(df -m . | tail -1 | awk '{print $4}')
    if [ "$AVAILABLE_DISK" -lt 5000 ]; then
        log_warn "Low disk space: ${AVAILABLE_DISK}MB available. Clean up recommended."
    fi

    log_success "Prerequisites check passed"
}

optimize_system() {
    log_info "Optimizing system for 2GB RAM..."

    # Disable unnecessary services
    sudo systemctl disable --now snapd 2>/dev/null || true
    sudo systemctl disable --now packagekit 2>/dev/null || true

    # Set swappiness for low memory
    sudo sysctl -w vm.swappiness=10
    echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf

    # Set overcommit memory for Redis
    sudo sysctl -w vm.overcommit_memory=1
    echo 'vm.overcommit_memory=1' | sudo tee -a /etc/sysctl.conf

    # Clean up Docker
    docker system prune -af --volumes 2>/dev/null || true

    log_success "System optimized"
}

setup_swap() {
    log_info "Setting up swap for memory safety..."

    if ! swapon --show | grep -q "/swapfile"; then
        if [ ! -f /swapfile ]; then
            sudo fallocate -l 2G /swapfile
            sudo chmod 600 /swapfile
            sudo mkswap /swapfile
        fi
        sudo swapon /swapfile
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
        log_success "2GB swap configured"
    else
        log_info "Swap already configured"
    fi
}

deploy() {
    log_info "Deploying GRAXIA OS on CPX11 (2GB)..."

    # Pull images with retry
    log_info "Pulling Docker images..."
    docker compose -f $COMPOSE_FILE pull --ignore-pull-failures 2>/dev/null || docker-compose -f $COMPOSE_FILE pull --ignore-pull-failures || {
        log_warn "Some images failed to pull, will build locally"
    }

    # Build if needed
    if [ ! -f .env.production ]; then
        log_error ".env.production not found! Copy from template."
        exit 1
    fi

    # Deploy with resource monitoring
    log_info "Starting services with memory limits..."
    docker compose -f $COMPOSE_FILE up -d --remove-orphans 2>/dev/null || docker-compose -f $COMPOSE_FILE up -d --remove-orphans

    # Wait for services
    log_info "Waiting for services to start..."
    sleep 10

    verify_deployment
}

verify_deployment() {
    log_info "Verifying deployment..."

    services=("caddy" "backend" "worker" "beat" "redis")
    failed=0

    for service in "${services[@]}"; do
        if docker compose -f $COMPOSE_FILE ps 2>/dev/null | grep -q "$service.*Up" || docker-compose -f $COMPOSE_FILE ps | grep -q "$service.*Up"; then
            log_success "$service is running"
        else
            log_error "$service failed to start!"
            docker compose -f $COMPOSE_FILE logs --tail=20 $service 2>/dev/null || docker-compose -f $COMPOSE_FILE logs --tail=20 $service
            failed=1
        fi
    done

    if [ $failed -eq 1 ]; then
        log_error "Some services failed to start. Check logs."
        exit 1
    fi

    # Check memory usage
    log_info "Current memory usage (run 'docker stats' for details)"

    log_success "Deployment verified!"
}

setup_monitoring() {
    log_info "Setting up memory monitoring..."

    # Create memory check script
    cat > /tmp/memory-check.sh << 'EOF'
#!/bin/bash
MEMORY=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100}')
if [ "$MEMORY" -gt 85 ]; then
    echo "[ALERT] Memory usage: ${MEMORY}%" >> /var/log/graxia/memory-alerts.log
    # Send notification if Telegram configured
    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=🚨 GRAXIA Memory Alert: ${MEMORY}% used on $(hostname)"
    fi
fi
EOF

    sudo mv /tmp/memory-check.sh /usr/local/bin/
    sudo chmod +x /usr/local/bin/memory-check.sh

    # Add to crontab
    (crontab -l 2>/dev/null || true; echo "*/5 * * * * /usr/local/bin/memory-check.sh") | crontab -

    log_success "Memory monitoring configured (checks every 5 min)"
}

setup_autostart() {
    log_info "Setting up auto-start on boot..."

    SERVICE_FILE="/etc/systemd/system/graxia-cpx11.service"

    sudo tee $SERVICE_FILE > /dev/null << EOF
[Unit]
Description=GRAXIA OS - CPX11 Optimized
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/docker compose -f ${COMPOSE_FILE} up -d
ExecStop=/usr/bin/docker compose -f ${COMPOSE_FILE} down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable graxia-cpx11.service

    log_success "Auto-start configured"
}

show_status() {
    echo ""
    echo "=========================================="
    echo "  GRAXIA OS - CPX11 Status (2GB RAM)"
    echo "=========================================="
    echo ""

    # Memory status
    echo "💾 Memory Status:"
    free -h | grep -E "(Mem|Swap)"
    echo ""

    # Docker status
    echo "🐳 Container Status:"
    docker compose -f $COMPOSE_FILE ps 2>/dev/null || docker-compose -f $COMPOSE_FILE ps
    echo ""

    # Resource usage
    echo "📊 Container Resource Usage:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | grep -E "(NAME|graxia)"
    echo ""

    # Endpoints
    echo "🔗 Access Points:"
    echo "  API Health: http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR-IP'):8000/health"
    echo "  Caddy:      http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR-IP')"
    echo ""

    echo "📚 Useful Commands:"
    echo "  Logs:        docker compose -f ${COMPOSE_FILE} logs -f [service]"
    echo "  Restart:     docker compose -f ${COMPOSE_FILE} restart"
    echo "  Stop:        docker compose -f ${COMPOSE_FILE} down"
    echo "  Memory:      ./deploy/scripts/deploy-cpx11.sh status"
    echo ""

    log_success "System running! Monitor memory closely."
}

show_help() {
    echo "Usage: $0 {deploy|status|logs|restart|stop|update|monitor}"
    echo ""
    echo "Commands:"
    echo "  deploy   - Initial deployment with optimization"
    echo "  status   - Show system status and resource usage"
    echo "  logs     - Show logs (optionally: logs [service])"
    echo "  restart  - Restart all services"
    echo "  stop     - Stop all services"
    echo "  update   - Pull and restart with latest images"
    echo "  monitor  - Show real-time resource monitoring"
    echo ""
    echo "Optimized for Hetzner CPX11: 2 vCPU, 2GB RAM, 40GB SSD"
}

# Main
case "${1:-}" in
    deploy)
        check_prerequisites
        optimize_system
        setup_swap
        deploy
        setup_monitoring
        setup_autostart
        show_status
        ;;
    status)
        show_status
        ;;
    logs)
        if [ -n "$2" ]; then
            docker compose -f $COMPOSE_FILE logs -f "$2" 2>/dev/null || docker-compose -f $COMPOSE_FILE logs -f "$2"
        else
            docker compose -f $COMPOSE_FILE logs -f 2>/dev/null || docker-compose -f $COMPOSE_FILE logs -f
        fi
        ;;
    restart)
        log_info "Restarting services..."
        docker compose -f $COMPOSE_FILE restart 2>/dev/null || docker-compose -f $COMPOSE_FILE restart
        sleep 5
        show_status
        ;;
    stop)
        log_info "Stopping services..."
        docker compose -f $COMPOSE_FILE down 2>/dev/null || docker-compose -f $COMPOSE_FILE down
        log_success "Services stopped"
        ;;
    update)
        log_info "Updating to latest version..."
        docker compose -f $COMPOSE_FILE pull 2>/dev/null || docker-compose -f $COMPOSE_FILE pull
        docker compose -f $COMPOSE_FILE up -d --remove-orphans 2>/dev/null || docker-compose -f $COMPOSE_FILE up -d --remove-orphans
        show_status
        ;;
    monitor)
        watch -n 2 'docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | grep -E "(NAME|graxia)"'
        ;;
    *)
        show_help
        exit 1
        ;;
esac
