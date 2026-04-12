#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
APP_URL="${APP_URL:?APP_URL is required}"
BACKEND_DIGEST="${BACKEND_DIGEST:?BACKEND_DIGEST is required}"
FRONTEND_DIGEST="${FRONTEND_DIGEST:?FRONTEND_DIGEST is required}"
COMMIT_SHA="${COMMIT_SHA:-unknown}"
DEPLOY_OPERATOR="${DEPLOY_OPERATOR:-unknown}"
HISTORY_FILE="${DEPLOY_HISTORY_FILE:-deploy/deploy_history.jsonl}"
ENV_FILE="${ENV_FILE:-.env.production}"

export BACKEND_DIGEST FRONTEND_DIGEST HISTORY_FILE COMMIT_SHA DEPLOY_OPERATOR ENV_FILE

docker compose -f "$COMPOSE_FILE" pull backend frontend worker-critical worker-default worker-background beat

docker compose -f "$COMPOSE_FILE" run --rm backend python scripts/production_preflight.py
docker compose -f "$COMPOSE_FILE" run --rm backend python scripts/alembic_safe.py upgrade head
MIGRATION_VERSION="$(
  docker compose -f "$COMPOSE_FILE" run --rm backend python scripts/current_migration.py 2>/dev/null || true
)"
export MIGRATION_VERSION

docker compose -f "$COMPOSE_FILE" up -d --no-deps backend
sleep 10
docker compose -f "$COMPOSE_FILE" exec -T backend curl -sf http://localhost:8000/health >/dev/null

docker compose -f "$COMPOSE_FILE" up -d --no-deps worker-critical
sleep 5
docker compose -f "$COMPOSE_FILE" up -d --no-deps worker-default worker-background beat
docker compose -f "$COMPOSE_FILE" up -d --no-deps frontend

python3 deploy/scripts/smoke_test.py --target "$APP_URL"

docker compose -f "$COMPOSE_FILE" exec -T backend python scripts/record_deploy.py \
  --commit-sha "$COMMIT_SHA" \
  --backend-digest "$BACKEND_DIGEST" \
  --frontend-digest "$FRONTEND_DIGEST" \
  --operator "$DEPLOY_OPERATOR" \
  --migration-version "$MIGRATION_VERSION" \
  --smoke-test-result pass

mkdir -p "$(dirname "$HISTORY_FILE")"
python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

history = Path(os.environ["HISTORY_FILE"])
record = {
    "commit_sha": os.environ["COMMIT_SHA"],
    "backend_digest": os.environ["BACKEND_DIGEST"],
    "frontend_digest": os.environ["FRONTEND_DIGEST"],
    "operator": os.environ["DEPLOY_OPERATOR"],
    "migration_version": os.environ.get("MIGRATION_VERSION", ""),
    "smoke_test_result": "pass",
    "deployed_at": datetime.now(timezone.utc).isoformat(),
}
with history.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
PY

echo "Deploy complete: backend=${BACKEND_DIGEST} frontend=${FRONTEND_DIGEST}"
