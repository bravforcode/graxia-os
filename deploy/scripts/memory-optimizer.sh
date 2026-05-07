#!/bin/bash
# Memory optimizer for CPX11 (2GB RAM)
# Run this when memory is critical

set -e

COMPOSE_FILE="docker-compose.cpx11.yml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}GRAXIA OS - Memory Optimizer for CPX11${NC}"
echo "======================================"

# Check current memory
MEMORY_INFO=$(free -m | grep Mem)
TOTAL=$(echo $MEMORY_INFO | awk '{print $2}')
USED=$(echo $MEMORY_INFO | awk '{print $3}')
FREE=$(echo $MEMORY_INFO | awk '{print $7}')
USAGE_PERCENT=$((USED * 100 / TOTAL))

echo "Current Memory: ${USED}MB / ${TOTAL}MB (${USAGE_PERCENT}%)"
echo "Free Memory: ${FREE}MB"
echo ""

if [ "$USAGE_PERCENT" -lt 70 ]; then
    echo -e "${GREEN}Memory usage is healthy. No action needed.${NC}"
    exit 0
fi

echo -e "${YELLOW}Memory usage is high. Applying optimizations...${NC}"

# 1. Clear cache
echo "[1/5] Clearing system cache..."
sync && echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null

# 2. Restart non-critical services
echo "[2/5] Restarting worker to free memory..."
docker-compose -f $COMPOSE_FILE restart worker 2>/dev/null || true
sleep 2

# 3. Clear Redis if memory usage is critical
echo "[3/5] Checking Redis memory..."
REDIS_MEM=$(docker-compose -f $COMPOSE_FILE exec -T redis redis-cli INFO memory | grep used_memory_human | cut -d: -f2)
echo "Redis using: $REDIS_MEM"

if [ "$USAGE_PERCENT" -gt 85 ]; then
    echo "Critical memory! Clearing Redis cache..."
    docker-compose -f $COMPOSE_FILE exec -T redis redis-cli FLUSHDB 2>/dev/null || true
fi

# 4. Prune Docker
echo "[4/5] Pruning Docker system..."
docker system prune -f --volumes 2>/dev/null || true

# 5. Check and restart heavy containers
echo "[5/5] Checking container memory usage..."
docker stats --no-stream --format "{{.Name}}\t{{.MemPerc}}" | while read line; do
    NAME=$(echo $line | awk '{print $1}')
    PERC=$(echo $line | awk '{print $2}' | sed 's/%//')
    
    if [ -n "$PERC" ] && [ "$PERC" -gt 50 ] 2>/dev/null; then
        echo "Container $NAME using ${PERC}% memory - considering restart"
    fi
done

# Final status
echo ""
echo "======================================"
free -h | grep Mem
echo ""
echo -e "${GREEN}Optimization complete!${NC}"
echo "Run 'docker-compose -f $COMPOSE_FILE ps' to check service status."
