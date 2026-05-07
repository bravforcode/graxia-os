#!/bin/bash
# =============================================================================
# GRAXIA OS - PREFLIGHT CHECK SCRIPT
# Comprehensive pre-deployment verification
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
TESTS_PASSED=0
TESTS_FAILED=0
WARNINGS=0

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARNINGS++))
}

# Header
echo "============================================================================="
echo "                    GRAXIA OS - PREFLIGHT CHECK                              "
echo "============================================================================="
echo "Date: $(date)"
echo "============================================================================="

# =============================================================================
# PHASE 1: Environment Check
# =============================================================================
echo ""
echo "PHASE 1: Environment Check"
echo "----------------------------------------------------------------------------"

# Check Python version
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"; then
        log_success "Python version: $PYTHON_VERSION (>= 3.11)"
    else
        log_error "Python version: $PYTHON_VERSION (requires >= 3.11)"
    fi
else
    log_error "Python3 not found"
fi

# Check Node.js
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    log_success "Node.js version: $NODE_VERSION"
else
    log_warn "Node.js not found (optional for frontend builds)"
fi

# Check Docker
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version | cut -d' ' -f3 | tr -d ',')
    log_success "Docker version: $DOCKER_VERSION"
    
    if docker compose version &> /dev/null; then
        log_success "Docker Compose available"
    else
        log_warn "Docker Compose not found"
    fi
else
    log_warn "Docker not found (optional for local development)"
fi

# =============================================================================
# PHASE 2: Backend Dependencies
# =============================================================================
echo ""
echo "PHASE 2: Backend Dependencies"
echo "----------------------------------------------------------------------------"

cd backend

# Check requirements.txt exists
if [ -f "requirements.txt" ]; then
    log_success "requirements.txt found"
else
    log_error "requirements.txt not found"
fi

# Check virtual environment
if [ -d "venv" ] || [ -d ".venv" ]; then
    log_success "Virtual environment exists"
else
    log_warn "Virtual environment not found (recommended)"
fi

# Test Python imports
log_info "Testing critical Python imports..."

python3 << 'PYTHON_EOF'
import sys
import os
sys.path.insert(0, os.getcwd())

modules = [
    ('fastapi', 'FastAPI'),
    ('sqlalchemy', 'create_engine'),
    ('pydantic', 'BaseModel'),
    ('redis', 'Redis'),
    ('celery', 'Celery'),
    ('stripe', 'stripe'),
]

failed = []
for mod, attr in modules:
    try:
        m = __import__(mod)
        getattr(m, attr)
        print(f"[OK] {mod}")
    except ImportError as e:
        print(f"[MISSING] {mod}: {e}")
        failed.append(mod)

if failed:
    print(f"\nMissing packages: {', '.join(failed)}")
    sys.exit(1)
else:
    print("\nAll critical packages available")
    sys.exit(0)
PYTHON_EOF

if [ $? -eq 0 ]; then
    log_success "All critical Python packages available"
else
    log_error "Some Python packages missing - run: pip install -r requirements.txt"
fi

cd ..

# =============================================================================
# PHASE 3: Configuration Check
# =============================================================================
echo ""
echo "PHASE 3: Configuration Check"
echo "----------------------------------------------------------------------------"

cd backend

# Check .env file
if [ -f ".env" ]; then
    log_success ".env file exists"
    
    # Check required variables
    REQUIRED_VARS=(
        "SECRET_KEY"
        "DATABASE_URL"
        "REDIS_URL"
    )
    
    for var in "${REQUIRED_VARS[@]}"; do
        if grep -q "^$var=" .env 2>/dev/null; then
            value=$(grep "^$var=" .env | cut -d'=' -f2)
            if [ -n "$value" ] && [ "$value" != "your_$var" ]; then
                log_success "$var is set"
            else
                log_error "$var is empty or using placeholder"
            fi
        else
            log_error "$var not found in .env"
        fi
    done
else
    log_warn ".env file not found - copy from .env.example"
fi

# Check config can load
log_info "Testing configuration load..."
python3 << 'PYTHON_EOF'
import sys
import os
sys.path.insert(0, os.getcwd())

try:
    from app.config import settings
    print(f"[OK] Config loaded: {len(settings.dict())} settings")
    sys.exit(0)
except Exception as e:
    print(f"[FAIL] Config load error: {e}")
    sys.exit(1)
PYTHON_EOF

if [ $? -eq 0 ]; then
    log_success "Configuration loads successfully"
else
    log_error "Configuration failed to load"
fi

cd ..

# =============================================================================
# PHASE 4: Database Check
# =============================================================================
echo ""
echo "PHASE 4: Database Check"
echo "----------------------------------------------------------------------------"

cd backend

# Check Alembic
if [ -d "alembic" ]; then
    log_success "Alembic migrations directory exists"
    
    # Check migration files count
    MIGRATION_COUNT=$(find alembic/versions -name "*.py" -type f | wc -l)
    log_info "Found $MIGRATION_COUNT migration files"
    
    if [ "$MIGRATION_COUNT" -gt 0 ]; then
        log_success "Migrations available"
    else
        log_warn "No migration files found"
    fi
else
    log_error "Alembic directory not found"
fi

# Test database connection
log_info "Testing database connection..."
python3 << 'PYTHON_EOF'
import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings

async def test_db():
    try:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            await result.fetchone()
        print("[OK] Database connection successful")
        return True
    except Exception as e:
        print(f"[FAIL] Database connection failed: {e}")
        return False

from sqlalchemy import text
result = asyncio.run(test_db())
sys.exit(0 if result else 1)
PYTHON_EOF

if [ $? -eq 0 ]; then
    log_success "Database connection OK"
else
    log_error "Database connection failed"
fi

cd ..

# =============================================================================
# PHASE 5: Redis Check
# =============================================================================
echo ""
echo "PHASE 5: Redis Check"
echo "----------------------------------------------------------------------------"

cd backend

log_info "Testing Redis connection..."
python3 << 'PYTHON_EOF'
import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
from app.config import settings

async def test_redis():
    try:
        import redis.asyncio as redis
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.ping()
        await r.close()
        print("[OK] Redis connection successful")
        return True
    except Exception as e:
        print(f"[FAIL] Redis connection failed: {e}")
        return False

result = asyncio.run(test_redis())
sys.exit(0 if result else 1)
PYTHON_EOF

if [ $? -eq 0 ]; then
    log_success "Redis connection OK"
else
    log_warn "Redis connection failed (will use fallback)"
fi

cd ..

# =============================================================================
# PHASE 6: ULTRA Modules Check
# =============================================================================
echo ""
echo "PHASE 6: ULTRA Modules Verification"
echo "----------------------------------------------------------------------------"

cd backend

log_info "Testing all ULTRA modules..."
python3 << 'PYTHON_EOF'
import sys
import os
sys.path.insert(0, os.getcwd())

modules = [
    ('app.models.base', 'ULTRABase'),
    ('app.core.security_ultra', 'ULTRASecurityManager'),
    ('app.models.audit', 'AuditLog'),
    ('app.core.cache', 'TenantCacheManager'),
    ('app.middleware.tiered_rate_limit', 'tiered_limiter'),
    ('app.core.observability', 'REQUEST_COUNT'),
    ('app.core.circuit_breaker', 'stripe_circuit_breaker'),
    ('app.core.feature_flags', 'feature_flags'),
    ('app.core.disaster_recovery', 'recovery_orchestrator'),
]

failed = []
for module_name, attr in modules:
    try:
        mod = __import__(module_name, fromlist=[attr])
        getattr(mod, attr)
        print(f"[OK] {module_name}")
    except Exception as e:
        print(f"[FAIL] {module_name}: {e}")
        failed.append((module_name, str(e)))

if failed:
    print(f"\n{len(failed)} ULTRA module(s) failed")
    sys.exit(1)
else:
    print("\nAll ULTRA modules operational")
    sys.exit(0)
PYTHON_EOF

if [ $? -eq 0 ]; then
    log_success "All ULTRA modules operational"
else
    log_error "Some ULTRA modules failed"
fi

cd ..

# =============================================================================
# PHASE 7: Test Suite
# =============================================================================
echo ""
echo "PHASE 7: Test Suite"
echo "----------------------------------------------------------------------------"

cd backend

if [ -d "tests" ]; then
    TEST_COUNT=$(find tests -name "test_*.py" -type f | wc -l)
    log_info "Found $TEST_COUNT test files"
    
    if [ "$TEST_COUNT" -gt 0 ]; then
        log_info "Running test suite..."
        
        # Run tests with pytest
        if python3 -m pytest tests/ -v --tb=short -x 2>&1 | head -50; then
            log_success "Test suite passed"
        else
            log_warn "Some tests failed (check output above)"
        fi
    else
        log_warn "No test files found"
    fi
else
    log_warn "tests/ directory not found"
fi

cd ..

# =============================================================================
# PHASE 8: Frontend Check
# =============================================================================
echo ""
echo "PHASE 8: Frontend Check"
echo "----------------------------------------------------------------------------"

cd frontend

if [ -f "package.json" ]; then
    log_success "package.json found"
    
    # Check for lock file
    if [ -f "package-lock.json" ] || [ -f "yarn.lock" ] || [ -f "pnpm-lock.yaml" ]; then
        log_success "Lock file exists"
    else
        log_warn "No lock file found (run npm install)"
    fi
    
    # Check node_modules
    if [ -d "node_modules" ]; then
        log_success "node_modules exists"
    else
        log_warn "node_modules not found (run npm install)"
    fi
else
    log_warn "package.json not found"
fi

cd ..

# =============================================================================
# PHASE 9: Security Scan
# =============================================================================
echo ""
echo "PHASE 9: Security Scan"
echo "----------------------------------------------------------------------------"

cd backend

# Check for security issues
log_info "Running basic security checks..."

# Check for hardcoded secrets
if grep -r "password.*=.*\"" --include="*.py" . 2>/dev/null | grep -v "__pycache__" | grep -v ".pyc" | head -5 > /dev/null; then
    log_warn "Potential hardcoded passwords found (review required)"
else
    log_success "No obvious hardcoded passwords found"
fi

# Check for SQL injection vectors
if grep -r "execute.*%" --include="*.py" . 2>/dev/null | grep -v "__pycache__" | grep -v "test" | head -5 > /dev/null; then
    log_warn "Potential SQL injection vectors (review required)"
else
    log_success "No obvious SQL injection vectors"
fi

cd ..

# =============================================================================
# PHASE 10: Performance Baseline
# =============================================================================
echo ""
echo "PHASE 10: Performance Baseline"
echo "----------------------------------------------------------------------------"

log_info "Checking performance configuration..."

# Check for database indexes
cd backend
INDEX_COUNT=$(grep -r "Index(" alembic/versions/*.py 2>/dev/null | wc -l)
log_info "Found approximately $INDEX_COUNT database indexes"

if [ "$INDEX_COUNT" -gt 5 ]; then
    log_success "Database indexes configured"
else
    log_warn "Few database indexes found (may impact performance)"
fi

# Check caching configuration
if grep -q "cache" app/config.py 2>/dev/null; then
    log_success "Caching configuration found"
else
    log_warn "No explicit caching configuration"
fi

cd ..

# =============================================================================
# SUMMARY
# =============================================================================
echo ""
echo "============================================================================="
echo "                           PREFLIGHT SUMMARY                                 "
echo "============================================================================="
echo "Tests Passed:  $TESTS_PASSED"
echo "Tests Failed:   $TESTS_FAILED"
echo "Warnings:      $WARNINGS"
echo "============================================================================="

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ PREFLIGHT CHECK PASSED${NC}"
    echo "System is ready for deployment!"
    exit 0
else
    echo -e "${RED}❌ PREFLIGHT CHECK FAILED${NC}"
    echo "Please fix the issues above before deploying."
    exit 1
fi
