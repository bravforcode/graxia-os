#!/usr/bin/env bash
#
# Personal Sovereign OS — Local Development Setup
#
# Usage:
#   ./setup.sh
#   ./setup.sh --skip-models
#   ./setup.sh --skip-tests
#   ./setup.sh --force-env
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SKIP_MODELS=false
SKIP_TESTS=false
FORCE_ENV=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-models) SKIP_MODELS=true; shift ;;
    --skip-tests) SKIP_TESTS=true; shift ;;
    --force-env) FORCE_ENV=true; shift ;;
    *)
      echo "Unknown flag: $1" >&2
      exit 1
      ;;
  esac
done

echo -e "${GREEN}=== Personal OS Setup ===${NC}\n"

if ! command -v docker >/dev/null 2>&1; then
  echo -e "${RED}Docker is required. Install Docker Desktop first.${NC}" >&2
  exit 1
fi
echo "✓ Docker found"

if ! docker compose version >/dev/null 2>&1; then
  echo -e "${RED}Docker Compose plugin is required.${NC}" >&2
  exit 1
fi
echo "✓ Docker Compose found"

if ! docker info >/dev/null 2>&1; then
  echo -e "${RED}Docker engine is not running. Start Docker Desktop and rerun setup.${NC}" >&2
  exit 1
fi
echo "✓ Docker engine is running"

if [[ ! -f .env.example ]]; then
  echo -e "${RED}.env.example is missing from the repo root.${NC}" >&2
  exit 1
fi

if [[ ! -f .env || "$FORCE_ENV" == true ]]; then
  echo -e "\n${YELLOW}Preparing .env from .env.example...${NC}"
  cp .env.example .env
  echo "✓ .env created from .env.example"
else
  echo "✓ .env exists"
fi

echo -e "\n${YELLOW}Building Docker images...${NC}"
docker compose build backend celery
echo "✓ Images built"

if [[ "$SKIP_MODELS" == false ]]; then
  echo -e "\n${YELLOW}Starting Ollama service...${NC}"
  docker compose up -d ollama

  echo "Waiting for Ollama to be ready..."
  for _ in {1..30}; do
    if curl -sS http://localhost:11434/api/tags >/dev/null 2>&1; then
      echo "✓ Ollama is ready"
      break
    fi
    sleep 2
  done

  if ! curl -sS http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo -e "${RED}Ollama failed to become ready in time.${NC}" >&2
    exit 1
  fi

  echo -e "\n${YELLOW}Pulling Ollama model gemma3:4b...${NC}"
  docker exec personal_os_ollama ollama pull gemma3:4b
  echo "✓ Model downloaded"
fi

if [[ "$SKIP_TESTS" == false ]]; then
  echo -e "\n${YELLOW}Running backend tests inside Docker...${NC}"
  docker compose run --rm backend python -m pytest tests -q
  echo "✓ Backend tests passed"
fi

echo -e "\n${GREEN}=== Setup Complete ===${NC}\n"
echo "Next steps:"
echo "1. Review .env and replace placeholder secrets before using live integrations"
echo "2. Start the local stack: docker compose --profile default up -d"
echo "3. Apply migrations: make migrate"
echo "4. Open API docs: http://localhost:8000/docs"
echo "5. Open frontend: http://localhost:5173"
echo "6. Run smoke tests: bash backend/scripts/smoke_tests.sh"
