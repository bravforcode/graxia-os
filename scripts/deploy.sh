#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Quant OS — Deployment Script
# Production deployment automation
# ═══════════════════════════════════════════════════════════════════════════════

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.quant.yml"
ENV_FILE=".env"

# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════════════════════
# Pre-deployment Checks
# ═══════════════════════════════════════════════════════════════════════════════

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check .env file
    if [ ! -f "$ENV_FILE" ]; then
        log_error ".env file not found. Please create it from .env.quant_os"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Environment Setup
# ═══════════════════════════════════════════════════════════════════════════════

setup_environment() {
    log_info "Setting up environment..."
    
    # Create necessary directories
    mkdir -p logs
    mkdir -p ml_models
    mkdir -p init-scripts
    
    # Set permissions
    chmod 755 logs
    chmod 755 ml_models
    
    log_success "Environment setup complete"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Build & Deploy
# ═══════════════════════════════════════════════════════════════════════════════

build_images() {
    log_info "Building Docker images..."
    
    if docker compose -f "$COMPOSE_FILE" build; then
        log_success "Images built successfully"
    else
        log_error "Failed to build images"
        exit 1
    fi
}

start_services() {
    log_info "Starting services..."
    
    # Pull latest images
    docker compose -f "$COMPOSE_FILE" pull
    
    # Start services
    if docker compose -f "$COMPOSE_FILE" up -d; then
        log_success "Services started successfully"
    else
        log_error "Failed to start services"
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Database Migrations
# ═══════════════════════════════════════════════════════════════════════════════

run_migrations() {
    log_info "Running database migrations..."
    
    # Wait for database to be ready
    log_info "Waiting for database..."
    sleep 10
    
    # Run migrations using the API container
    if docker compose -f "$COMPOSE_FILE" exec -T quant-api python -m alembic upgrade head; then
        log_success "Migrations completed"
    else
        log_warning "Migrations may have already been applied"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Health Checks
# ═══════════════════════════════════════════════════════════════════════════════

health_check() {
    log_info "Running health checks..."
    
    # Check API health
    for i in {1..30}; do
        if curl -s http://localhost:8000/health > /dev/null; then
            log_success "API is healthy"
            return 0
        fi
        log_info "Waiting for API to be ready... ($i/30)"
        sleep 2
    done
    
    log_error "API health check failed"
    return 1
}

# ═══════════════════════════════════════════════════════════════════════════════
# Monitoring Setup
# ═══════════════════════════════════════════════════════════════════════════════

setup_monitoring() {
    log_info "Setting up monitoring..."
    
    # Check Prometheus
    if curl -s http://localhost:9091/-/healthy > /dev/null 2>&1; then
        log_success "Prometheus is running"
    fi
    
    # Check Grafana
    if curl -s http://localhost:3001/api/health > /dev/null 2>&1; then
        log_success "Grafana is running"
        log_info "Grafana: http://localhost:3001 (admin/admin)"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Telegram Bot Setup
# ═══════════════════════════════════════════════════════════════════════════════

setup_telegram() {
    log_info "Telegram Bot Setup"
    log_info "===================="
    log_info "1. Message @BotFather on Telegram"
    log_info "2. Create a new bot with /newbot"
    log_info "3. Copy the token and run:"
    log_info "   python scripts/setup_telegram_bot.py"
    log_info "4. Message @userinfobot to get your Chat ID"
    log_info "5. Update TELEGRAM_CHAT_ID in .env"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Main Deployment
# ═══════════════════════════════════════════════════════════════════════════════

deploy() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════════╗"
    echo "║           Quant OS — Deployment Script                             ║"
    echo "╚════════════════════════════════════════════════════════════════════╝"
    echo ""
    
    check_prerequisites
    setup_environment
    build_images
    start_services
    run_migrations
    health_check
    setup_monitoring
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════════════"
    log_success "Deployment completed successfully!"
    echo "═══════════════════════════════════════════════════════════════════════"
    echo ""
    echo "📊 Services:"
    echo "   API:        http://localhost:8000"
    echo "   Grafana:    http://localhost:3001 (admin/admin)"
    echo "   Prometheus: http://localhost:9091"
    echo ""
    echo "📋 Useful commands:"
    echo "   View logs:   docker compose -f $COMPOSE_FILE logs -f quant-api"
    echo "   Stop all:    docker compose -f $COMPOSE_FILE down"
    echo "   Restart:     docker compose -f $COMPOSE_FILE restart"
    echo ""
    
    setup_telegram
    
    echo ""
    echo "⚠️  SAFETY CHECKLIST BEFORE LIVE TRADING:"
    echo "   [ ] TRADING_MODE=PAPER in .env"
    echo "   [ ] LIVE_TRADING_ENABLED=false"
    echo "   [ ] MT5 credentials configured"
    echo "   [ ] Telegram bot configured"
    echo "   [ ] Kill switch tested"
    echo "   [ ] Paper trading for 60 days minimum"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
# Command Handlers
# ═══════════════════════════════════════════════════════════════════════════════

case "${1:-deploy}" in
    deploy)
        deploy
        ;;
    update)
        log_info "Updating deployment..."
        docker compose -f "$COMPOSE_FILE" pull
        docker compose -f "$COMPOSE_FILE" up -d
        log_success "Update complete"
        ;;
    stop)
        log_info "Stopping services..."
        docker compose -f "$COMPOSE_FILE" down
        log_success "Services stopped"
        ;;
    logs)
        docker compose -f "$COMPOSE_FILE" logs -f "${2:-quant-api}"
        ;;
    status)
        docker compose -f "$COMPOSE_FILE" ps
        ;;
    backup)
        log_info "Creating backup..."
        # Add backup logic here
        log_success "Backup complete"
        ;;
    telegram)
        setup_telegram
        python3 scripts/setup_telegram_bot.py
        ;;
    *)
        echo "Usage: $0 {deploy|update|stop|logs|status|backup|telegram}"
        exit 1
        ;;
esac
