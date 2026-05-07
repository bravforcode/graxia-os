#!/bin/bash
# GRAXIA OS - 24/7 Always-On Deployment Script
# ใช้สำหรับ deploy ระบบขึ้น cloud และให้ทำงานตลอดเวลา แม้ปิดเครื่อง

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration
PROJECT_NAME="personal-os"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.production"

# Function: Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if .env.production exists
    if [ ! -f "$ENV_FILE" ]; then
        log_error "$ENV_FILE not found! Please create it from .env.production.template"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Function: Deploy with restart policy
deploy_24_7() {
    log_info "Deploying GRAXIA OS for 24/7 operation..."
    
    # Pull latest images
    log_info "Pulling latest Docker images..."
    docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE pull
    
    # Deploy with production profile
    log_info "Starting all services with auto-restart policy..."
    docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d --remove-orphans
    
    # Verify all services are running
    log_info "Verifying service health..."
    sleep 10
    
    # Check critical services
    services=("backend" "worker-critical" "worker-default" "beat" "redis" "postgres")
    for service in "${services[@]}"; do
        if docker-compose -f $COMPOSE_FILE ps | grep -q "$service.*Up"; then
            log_success "$service is running"
        else
            log_error "$service is not running!"
            docker-compose -f $COMPOSE_FILE logs --tail=50 $service
            exit 1
        fi
    done
    
    log_success "All services deployed successfully!"
}

# Function: Setup auto-restart on system boot
setup_autostart() {
    log_info "Setting up auto-start on system boot..."
    
    # Create systemd service file for this project
    SERVICE_FILE="/etc/systemd/system/${PROJECT_NAME}-24-7.service"
    
    sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=GRAXIA OS - 24/7 Always-On Service
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$(pwd)
ExecStart=$(which docker-compose) -f ${COMPOSE_FILE} --env-file ${ENV_FILE} up -d
ExecStop=$(which docker-compose) -f ${COMPOSE_FILE} --env-file ${ENV_FILE} down
ExecReload=$(which docker-compose) -f ${COMPOSE_FILE} --env-file ${ENV_FILE} up -d
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable ${PROJECT_NAME}-24-7.service
    
    log_success "Auto-start configured. System will restart on boot."
}

# Function: Setup health monitoring
setup_health_monitoring() {
    log_info "Setting up health monitoring..."
    
    # Create health check script
    cat > health-check.sh <<'HEALTH_SCRIPT'
#!/bin/bash
# Health check script for GRAXIA OS

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.production"

# Check if backend is responding
if ! curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "[$(date)] Backend health check failed. Restarting..."
    docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE restart backend
fi

# Check if Redis is responding
if ! docker-compose -f $COMPOSE_FILE exec -T redis redis-cli ping | grep -q "PONG"; then
    echo "[$(date)] Redis health check failed. Restarting..."
    docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE restart redis
fi

# Check memory usage and restart if too high
MEMORY_USAGE=$(docker stats --no-stream --format "{{.MemPerc}}" $(docker-compose -f $COMPOSE_FILE ps -q) | awk '{sum+=$1} END {printf "%.0f", sum}')
if [ "$MEMORY_USAGE" -gt 90 ]; then
    echo "[$(date)] Memory usage critical (${MEMORY_USAGE}%). Restarting services..."
    docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE restart backend worker-critical worker-default
fi
HEALTH_SCRIPT
    
    chmod +x health-check.sh
    
    # Add to crontab for every 5 minutes
    (crontab -l 2>/dev/null; echo "*/5 * * * * cd $(pwd) && ./health-check.sh >> logs/health-check.log 2>&1") | crontab -
    
    log_success "Health monitoring configured (checks every 5 minutes)"
}

# Function: Setup log rotation
setup_log_rotation() {
    log_info "Setting up log rotation..."
    
    sudo tee /etc/logrotate.d/${PROJECT_NAME} > /dev/null <<EOF
$(pwd)/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
    postrotate
        docker-compose -f $(pwd)/${COMPOSE_FILE} kill -s USR1 2>/dev/null || true
    endscript
}
EOF
    
    log_success "Log rotation configured"
}

# Function: Display status
display_status() {
    echo ""
    echo "=========================================="
    echo "  GRAXIA OS - 24/7 Status"
    echo "=========================================="
    
    docker-compose -f $COMPOSE_FILE ps
    
    echo ""
    echo "Access Points:"
    echo "  - Web UI:     https://your-domain.com"
    echo "  - API:        https://your-domain.com/api/v1"
    echo "  - Health:     https://your-domain.com/health"
    echo "  - Grafana:    https://your-domain.com/grafana"
    echo "  - Flower:     https://your-domain.com/flower"
    
    echo ""
    echo "Useful Commands:"
    echo "  - View logs:     docker-compose -f ${COMPOSE_FILE} logs -f"
    echo "  - Restart:       docker-compose -f ${COMPOSE_FILE} restart"
    echo "  - Stop:          docker-compose -f ${COMPOSE_FILE} down"
    echo "  - Update:        ./deploy/24-7-always-on.sh update"
    
    echo ""
    log_success "System is running 24/7! You can now turn off your local machine."
}

# Function: Update deployment
update_deployment() {
    log_info "Updating GRAXIA OS to latest version..."
    
    # Backup current state
    log_info "Creating backup..."
    docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE exec -T backend python -m app.cli backup create --name "pre-update-$(date +%Y%m%d-%H%M%S)"
    
    # Pull and restart
    docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE pull
    docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d --remove-orphans
    
    log_success "Update completed!"
}

# Main execution
main() {
    case "${1:-deploy}" in
        deploy)
            check_prerequisites
            deploy_24_7
            setup_autostart
            setup_health_monitoring
            setup_log_rotation
            display_status
            ;;
        update)
            check_prerequisites
            update_deployment
            display_status
            ;;
        stop)
            log_info "Stopping all services..."
            docker-compose -f $COMPOSE_FILE down
            log_success "Services stopped"
            ;;
        restart)
            log_info "Restarting all services..."
            docker-compose -f $COMPOSE_FILE restart
            display_status
            ;;
        status)
            display_status
            ;;
        logs)
            docker-compose -f $COMPOSE_FILE logs -f
            ;;
        *)
            echo "Usage: $0 {deploy|update|stop|restart|status|logs}"
            exit 1
            ;;
    esac
}

main "$@"
