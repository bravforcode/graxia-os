#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-config/docker-compose.production.yml}"
APP_URL="${APP_URL:?APP_URL is required}"
COMMIT_SHA="${COMMIT_SHA:?COMMIT_SHA is required for source-build deployment}"
DEPLOY_OPERATOR="${DEPLOY_OPERATOR:-unknown}"
HISTORY_FILE="${DEPLOY_HISTORY_FILE:-deploy/deploy_history.jsonl}"
ENV_FILE="${ENV_FILE:-.env.production}"

# This compose file builds images locally; these fields retain deploy-history
# compatibility without claiming that a registry image digest was deployed.
BACKEND_DIGEST="source-build:${COMMIT_SHA}"
FRONTEND_DIGEST="source-build:${COMMIT_SHA}"
export BACKEND_DIGEST FRONTEND_DIGEST HISTORY_FILE COMMIT_SHA DEPLOY_OPERATOR ENV_FILE

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Production env file not found: $ENV_FILE" >&2
  exit 1
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

python3 backend/scripts/production_env_audit.py \
  --env-file "$ENV_FILE" \
  --compose-file "$COMPOSE_FILE" \
  --frontend-env-file frontend/.env.production

compose config --quiet
compose up -d --wait postgres redis

compose run --rm --no-deps backend python scripts/alembic_safe.py upgrade head
MIGRATION_VERSION="$(
  compose run --rm --no-deps backend python scripts/current_migration.py 2>/dev/null || true
)"
export MIGRATION_VERSION

compose build --pull backend frontend celery_worker celery_beat
compose up -d --remove-orphans --wait
compose exec -T backend curl -sf http://localhost:8000/health >/dev/null

python3 deploy/scripts/smoke_test.py --target "$APP_URL"

compose exec -T backend python scripts/record_deploy.py \
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

echo "Deploy complete: source-build=${COMMIT_SHA}"
