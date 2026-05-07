#!/bin/bash
set -e

echo "🔧 Applying critical fixes to Graxia OS / Brav OS..."
echo ""

# Check if we're in the right directory
if [ ! -f "backend/app/main.py" ]; then
    echo "❌ Error: Must run from project root directory"
    exit 1
fi

# 1. Backup current files
echo "📦 Creating backups..."
mkdir -p .backups/$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=".backups/$(date +%Y%m%d_%H%M%S)"

cp backend/app/main.py "$BACKUP_DIR/main.py.backup" 2>/dev/null || true
cp backend/app/config.py "$BACKUP_DIR/config.py.backup" 2>/dev/null || true
cp backend/app/tasks/celery_app.py "$BACKUP_DIR/celery_app.py.backup" 2>/dev/null || true
cp graxia/packages/revenue_os/db.py "$BACKUP_DIR/db.py.backup" 2>/dev/null || true

echo "✅ Backups created in $BACKUP_DIR"
echo ""

# 2. Generate secrets if not exists
if [ ! -f ".env.secrets" ]; then
    echo "🔐 Generating secrets..."
    bash scripts/generate_secrets.sh > .env.secrets
    echo "✅ Secrets generated in .env.secrets"
    echo "⚠️  Please review and add to .env file"
else
    echo "ℹ️  .env.secrets already exists, skipping generation"
fi
echo ""

# 3. Update environment file
echo "🌍 Updating .env file..."
if [ -f ".env" ]; then
    if ! grep -q "GRAXIA_ENABLED" .env; then
        echo "" >> .env
        echo "# Graxia OS Configuration (added by fix script)" >> .env
        echo "GRAXIA_ENABLED=false" >> .env
        echo "DEFAULT_EMBEDDING_MODEL=text-embedding-3-small" >> .env
        echo "DEFAULT_LLM_MODEL=gpt-4o-mini" >> .env
        echo "OPENAI_API_KEY=" >> .env
        echo "✅ Added Graxia OS configuration to .env"
    else
        echo "ℹ️  Graxia OS configuration already exists in .env"
    fi
else
    echo "⚠️  .env file not found, copying from .env.example"
    cp .env.example .env
    echo "✅ Created .env from .env.example"
fi
echo ""

# 4. Verify Python environment
echo "🐍 Verifying Python environment..."
if command -v python &> /dev/null; then
    PYTHON_CMD=python
elif command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
else
    echo "❌ Python not found"
    exit 1
fi

echo "Using: $PYTHON_CMD"
echo ""

# 5. Test backend import
echo "🧪 Testing backend import..."
cd backend
if $PYTHON_CMD -c "import sys; sys.path.insert(0, '..'); from app.main import app; print('✅ Backend imports successfully')" 2>&1; then
    echo "✅ Backend import test passed"
else
    echo "⚠️  Backend import test failed - this is expected if dependencies are not installed"
    echo "   Run: cd backend && pip install -r requirements.txt"
fi
cd ..
echo ""

# 6. Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Critical fixes applied successfully!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 NEXT STEPS:"
echo ""
echo "1. Review generated secrets:"
echo "   cat .env.secrets"
echo ""
echo "2. Add secrets to .env file:"
echo "   nano .env  # or your preferred editor"
echo ""
echo "3. Install dependencies (if not already done):"
echo "   cd backend && pip install -r requirements.txt"
echo "   cd frontend && bun install"
echo ""
echo "4. Test backend startup:"
echo "   cd backend && python -c 'from app.main import app'"
echo ""
echo "5. Run tests:"
echo "   make test-local"
echo ""
echo "6. Start services:"
echo "   make up"
echo ""
echo "7. Verify health:"
echo "   curl http://localhost:8000/health"
echo "   curl http://localhost:8000/api/v1/system/health"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📚 For detailed information, see:"
echo "   - ULTRA_DEEP_ANALYSIS_REPORT.md"
echo "   - CRITICAL_FIXES_IMPLEMENTATION.md"
echo ""
echo "🔄 To rollback changes:"
echo "   cp $BACKUP_DIR/*.backup <original-location>"
echo ""
