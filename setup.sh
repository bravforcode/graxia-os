#!/bin/bash
#
# Personal Sovereign OS — Local Development Setup
#
# Usage:
#   ./setup.sh                    # Full setup: env, Ollama models, tests
#   ./setup.sh --skip-models      # Skip Ollama model download
#   ./setup.sh --skip-tests       # Skip running tests
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Parse flags
SKIP_MODELS=false
SKIP_TESTS=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-models) SKIP_MODELS=true; shift ;;
    --skip-tests) SKIP_TESTS=true; shift ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

# ─────────────────────────────────────────────────────────────────────────────
# 1. Check prerequisites
# ─────────────────────────────────────────────────────────────────────────────

echo -e "${GREEN}=== Personal OS Setup ===${NC}\n"

echo "Checking prerequisites..."
if ! command -v docker &> /dev/null; then
  echo -e "${RED}✗ Docker not found. Install from https://www.docker.com${NC}"
  exit 1
fi
echo "✓ Docker found"

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
  echo -e "${RED}✗ Docker Compose not found${NC}"
  exit 1
fi
echo "✓ Docker Compose found"

# ─────────────────────────────────────────────────────────────────────────────
# 2. Create .env if missing
# ─────────────────────────────────────────────────────────────────────────────

if [ ! -f .env ]; then
  echo -e "\n${YELLOW}Creating .env file...${NC}"
  cat > .env << 'EOF'
# Database (Local Postgres)
DATABASE_URL=postgresql+asyncpg://personal_os:changeme@postgres:5432/personal_os
POSTGRES_DB=personal_os
POSTGRES_USER=personal_os
POSTGRES_PASSWORD=changeme

# Redis
REDIS_URL=redis://redis:6379

# LLM Configuration
LLM_PRIMARY=ollama
OLLAMA_BASE_URL=http://ollama:11434
TOGETHER_API_KEY=
HUGGINGFACE_API_KEY=

# API Keys
OPENAI_API_KEY=
GOOGLE_GEMINI_API_KEY=
ANTHROPIC_API_KEY=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_CHAT_ID=

# n8n
N8N_USER=admin
N8N_PASSWORD=changeme

# App Configuration
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
SECRET_KEY=dev-secret-key-change-in-production
UVICORN_WORKERS=2

# Costs (Development)
DAILY_COST_LIMIT=10.0
MONTHLY_COST_LIMIT=200.0
EOF
  echo "✓ .env created (adjust settings as needed)"
else
  echo "✓ .env exists"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 3. Build images (ensure latest code)
# ─────────────────────────────────────────────────────────────────────────────

echo -e "\n${YELLOW}Building Docker images...${NC}"
docker-compose build backend celery
echo "✓ Images built"

# ─────────────────────────────────────────────────────────────────────────────
# 4. Start Ollama and download models
# ─────────────────────────────────────────────────────────────────────────────

if [ "$SKIP_MODELS" = false ]; then
  echo -e "\n${YELLOW}Starting Ollama service...${NC}"
  docker-compose up -d ollama

  # Wait for Ollama to be ready
  echo "Waiting for Ollama to be ready..."
  for i in {1..30}; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
      echo "✓ Ollama is ready"
      break
    fi
    if [ $i -eq 30 ]; then
      echo -e "${RED}✗ Ollama failed to start${NC}"
      exit 1
    fi
    sleep 2
  done

  # Download gemma3:4b model
  echo -e "\n${YELLOW}Downloading gemma3:4b model (may take 5-10 minutes)...${NC}"
  docker exec personal_os_ollama ollama pull gemma3:4b
  echo "✓ Model downloaded"

  # List available models
  echo -e "\n${YELLOW}Available Ollama models:${NC}"
  docker exec personal_os_ollama ollama list
fi

# ─────────────────────────────────────────────────────────────────────────────
# 5. Run tests
# ─────────────────────────────────────────────────────────────────────────────

if [ "$SKIP_TESTS" = false ]; then
  echo -e "\n${YELLOW}Running backend tests...${NC}"
  docker-compose run --rm backend pytest tests/ -q
  echo "✓ All tests passed"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 6. Setup complete
# ─────────────────────────────────────────────────────────────────────────────

echo -e "\n${GREEN}=== Setup Complete ===${NC}\n"
echo "Next steps:"
echo "1. Review and adjust .env file as needed"
echo "2. Start the full stack: docker-compose up"
echo "3. Access dashboard: http://localhost:3000"
echo "4. View API docs: http://localhost:8000/docs"
echo "5. Monitor n8n: http://localhost:5678"
echo ""
echo "Profiles available:"
echo "  make up              # Full stack (postgres + redis + backend + celery + frontend + n8n)"
echo "  make supabase-up     # Supabase mode (skip local postgres)"
echo "  make test-local      # Run tests locally (no Docker)"
echo ""
